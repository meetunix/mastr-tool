#!/usr/bin/env python3
import io
import os
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Union
from xml.etree.ElementTree import Element

import psycopg2

from enricher.enricher import CoordinateConverter
from .entities import Einheiten, EinheitenGeoEnrichment, Type

# characters with a special meaning in COPY's text format
_COPY_ESCAPES = str.maketrans({"\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t"})


def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "mastr"),
        user=os.environ.get("DB_USER", "mastr"),
        password=os.environ.get("DB_PASSWORD", "password"),
    )


class DBConverter:

    @staticmethod
    def convert(value: str, field_type: Type) -> Union[Decimal, int, float, str, datetime, date, None]:

        if value is None or value.lower() == "none":
            return None

        if field_type == Type.TEXT:
            return value
        elif field_type == Type.INT:
            return int(value)
        elif field_type == Type.BOOLEAN:
            return value.strip().lower() in ("true", "1", "yes", "ja")
        elif field_type == Type.TIMESTAMP:
            return datetime.fromisoformat(value)
        elif field_type == Type.DATE:
            return datetime.fromisoformat(value).date()
        elif field_type == Type.NUMERIC:
            return Decimal(value)
        else:
            raise ValueError(f'Unable ro convert type "{field_type}" for value "{value}"')


def to_copy_text(value) -> str:
    """Render a converted value as a field of COPY's text format."""
    if value is None:
        return "\\N"
    if isinstance(value, bool):
        return "t" if value else "f"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            # COPY drops the offset of a value for a "timestamp" column - an
            # INSERT (psycopg2) converted it to the session time zone, which
            # is UTC in the Postgres images used by compose and the chart
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).translate(_COPY_ESCAPES)


class UtmRowEnricher:
    """Fills UTM_zone/UTM_ost/UTM_nord of import rows that carry geo
    coordinates (Breitengrad/Laengengrad)."""

    def __init__(self, column_names: list[str]):
        self.__lat = column_names.index("Breitengrad")
        self.__lon = column_names.index("Laengengrad")
        self.__zone = column_names.index("UTM_zone")
        self.__east = column_names.index("UTM_ost")
        self.__north = column_names.index("UTM_nord")
        self.__converter = CoordinateConverter()

    def enrich(self, rows: list[list]) -> None:
        rows = [row for row in rows if row[self.__lat] is not None and row[self.__lon] is not None]
        if not rows:
            return
        utms = self.__converter.geo_to_utm_batch([row[self.__lat] for row in rows], [row[self.__lon] for row in rows])
        for row, utm in zip(rows, utms):
            row[self.__zone] = str(utm.zone)
            row[self.__east] = utm.easting
            row[self.__north] = utm.northing


class DBElementWriter:
    BATCH_LIMIT = 1000

    def __init__(self, entity: Einheiten, connection):
        self.entity = entity
        self.connection = connection
        self.converter = DBConverter()
        self.copy_statement = self.__get_copy_statement()
        self.batch_list = []
        self.batch_count = 0
        # precomputed lookup keys for the hot import path (called once per record)
        self.__fields = [(column.name, f"{column.name}_nv", column.value.type) for column in entity.value]
        # units with geo coordinates get their UTM coordinates during the import
        self.__utm_enricher = (
            UtmRowEnricher([column.name for column in entity.value])
            if entity.name in EinheitenGeoEnrichment.__members__
            else None
        )

    def write(self, element: Element) -> None:
        self.batch_list.append(self.__get_values(element))
        self.batch_count += 1
        if self.batch_count >= self.BATCH_LIMIT:
            self.__write_batch()

    def cleanup(self):
        self.__write_batch()
        self.connection.close()

    def __write_batch(self) -> None:
        if self.batch_list:
            if self.__utm_enricher is not None:
                self.__utm_enricher.enrich(self.batch_list)
            data = io.StringIO()
            for row in self.batch_list:
                data.write("\t".join(to_copy_text(value) for value in row))
                data.write("\n")
            data.seek(0)
            with self.connection.cursor() as cursor:
                cursor.copy_expert(self.copy_statement, data)
                self.connection.commit()
        self.batch_list = []
        self.batch_count = 0

    def __get_copy_statement(self) -> str:
        return f"COPY {self.entity.name} ({','.join([e.name for e in self.entity.value])}) FROM STDIN"

    def __get_values(self, element: Element) -> list:
        """build the values for one row written by the COPY statement."""
        # single pass over the record's child elements (first occurrence wins)
        content: dict[str, str | None] = {}
        for child in element:
            if child.tag not in content:
                content[child.tag] = child.text

        convert = self.converter.convert
        sql_params = []
        for name, nv_name, field_type in self.__fields:
            value = content.get(name)
            # MaStR export rule: a field whose "nicht vorhanden" flag
            # (<field>_nv) is true has no valid value - any content of the
            # field itself must be ignored.
            nv_flag = content.get(nv_name)
            if nv_flag is not None and nv_flag.strip().lower() in ("true", "1"):
                value = None

            sql_params.append(convert(value, field_type))

        return sql_params
