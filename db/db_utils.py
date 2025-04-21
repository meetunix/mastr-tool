#!/usr/bin/env python3
from datetime import datetime, date

import psycopg2

from .entities import Einheiten, Type
from xml.etree.ElementTree import Element
from typing import Union
from decimal import Decimal

from psycopg2.extras import execute_batch

def get_db_connection():
    return psycopg2.connect(dbname="mastr", user="mastr", password="password", host="127.0.0.1", port="15432")

class DBConverter:

    @staticmethod
    def convert(value: str, field_type: Type) -> Union[Decimal, int, float, str, datetime, date, None]:

        if value is None:
            return None

        if value is None or value.lower() == "none":
            return None

        if Type.TEXT:
            return value
        elif Type.INT:
            return int(value)
        elif Type.BOOLEAN:
            return value.lower().startswith(("true", "yes", "ja"))
        elif Type.TIMESTAMP:
            return datetime.fromisoformat(value)
        elif Type.DATE:
            return datetime.fromisoformat(value).date()
        elif Type.NUMERIC:
            return Decimal(value)
        else:
            raise ValueError(f"Unable ro convert type \"{field_type}\" for value \"{value}\"")


class DBElementWriter:
    BATCH_LIMIT = 1000

    def __init__(self, entity: Einheiten, connection):
        self.entity = entity
        self.connection = connection
        self.converter = DBConverter()
        self.sql_statement = self.__get_sql_insert_statement()
        self.batch_list = []
        self.batch_count = 0

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
        sql_params = []
        for subentity in self.entity.value:
            value = element.findtext(subentity.name)
            # print(f"{subentity.name:64} -> {value}")

            sql_params.append(self.converter.convert(value, subentity.value[1]))
        # print(sql_params)

        return sql_params
