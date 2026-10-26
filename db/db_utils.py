#!/usr/bin/env python3
import os
from datetime import datetime, date
from decimal import Decimal
from typing import Union
from xml.etree.ElementTree import Element

import psycopg2
from psycopg2.extras import execute_batch

from .entities import Einheiten, Type


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


class DBElementWriter:
    BATCH_LIMIT = 1000

    def __init__(self, entity: Einheiten, connection):
        self.entity = entity
        self.connection = connection
        self.converter = DBConverter()
        self.sql_statement = self.__get_sql_insert_statement()
        self.batch_list = []
        self.batch_count = 0
        # precomputed lookup keys for the hot import path (called once per record)
        self.__fields = [(column.name, f"{column.name}_nv", column.value.type) for column in entity.value]

    def write(self, element: Element) -> None:
        self.batch_list.append(self.__get_values(element))
        self.batch_count += 1
        if self.batch_count >= self.BATCH_LIMIT:
            self.__write_batch()

    def cleanup(self):
        self.__write_batch()
        self.connection.close()

    def __write_batch(self) -> None:
        with self.connection.cursor() as cursor:
            execute_batch(cursor, self.sql_statement, self.batch_list)
            self.connection.commit()
        self.batch_list = []
        self.batch_count = 0

    def __get_sql_insert_statement(self) -> str:
        stmnt = f"INSERT INTO {self.entity.name} ({','.join([e.name for e in self.entity.value])}) "
        stmnt += f"VALUES ({','.join(['%s' for _ in self.entity.value])})"
        return stmnt

    def __get_values(self, element: Element) -> list:
        """build the parameter values for one row used by the INSERT INTO statement."""
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
