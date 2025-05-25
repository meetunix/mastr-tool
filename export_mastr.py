#!/usr/bin/env python3
import argparse
import time
from dataclasses import dataclass
from multiprocessing import Pool
from typing import Optional

from db.db_utils import get_db_connection
from db.entities import *
from enum import Enum
from pathlib import Path

import pandas as pd
import polars as pl


def timer(func):
    def helper_function(*args, **kwargs):
        print(f"start {func.__name__}")
        start = time.perf_counter()
        func(*args, **kwargs)
        print(f"{func.__name__} took {time.perf_counter() - start:.3f} s")

    return helper_function


class DataFormats(Enum):
    CSV = ".csv"
    CSV_COMPRESSED = ".csv.xz"
    EXCEL = ".xlsx"
    PARQUET = ".parq"


@dataclass
class ExportJob:
    name: str  # e.g. germany or state
    file_output_path: Path


@dataclass
class CsvExportJob(ExportJob):
    sql_stmt: str
    force_file_write: bool


@dataclass
class ConvertExportJob(ExportJob):
    csv_source_file: Path


@dataclass
class MastrOption:
    entity: Einheiten
    germany: bool
    states: bool
    data_formats: set[DataFormats]


class MastrType(Enum):
    WIND = MastrOption(Einheiten.EinheitenWind, True, True, {DataFormats.CSV, DataFormats.EXCEL, DataFormats.PARQUET})
    SOLAR = MastrOption(Einheiten.EinheitenSolar, False, True, {DataFormats.CSV, DataFormats.PARQUET})


class MastrExporter:

    def __init__(self, connection, concurrency: int):
        self.conn = connection
        self.concurrency = concurrency
        self.states: dict[int, str] = self.__create_state_mapping()
        self.csv_files_states: dict[MastrType, list[Path]] = {k: [] for k in MastrType}
        self.csv_files_germany: dict[MastrType, Optional[Path]] = {k: None for k in MastrType}
        self.select_stmts: dict[MastrType, str] = {k: "" for k in MastrType}
        self.state_filter = "WHERE katalog(<<table>>.bundesland) = '<<STATE>>'"
        self.__create_select_stmts()

    def __market_fields(self) -> str:
        columns = ""
        table_name = Einheiten.Marktakteure.name
        for column in Marktakteur:
            column_name = f"{table_name}.{column.name}"
            col_opts = column.value
            if col_opts[4]:
                udf: str = col_opts[4].value
                udf = udf.replace("{{field}}", column_name)
                columns += f"\t{udf} {column.name},\n"
            else:
                columns += f"\t{column_name},\n"

        return columns

    def __create_select_stmts(self) -> None:

        for mastr_type in MastrType:
            main_entity = mastr_type.value.entity
            main_table = main_entity.value
            table_name = main_entity.name
            columns = ""
            for column in main_table:
                column_name = f"{table_name}.{column.name}"
                col_opts = column.value
                if col_opts[4]:
                    udf: str = col_opts[4].value
                    udf = udf.replace("{{field}}", column_name)
                    columns += f"\t{udf} {column.name},\n"
                else:
                    columns += f"\t{column_name},\n"

            columns += self.__market_fields()
            # erase last hyphen and linebreak
            columns = columns[:-2]
            stmt = (
                f"SELECT\n{columns}\nFROM {main_entity.name}\n"
                f"LEFT JOIN {Einheiten.Marktakteure.name} "
                f"ON {main_entity.name}.{main_table.AnlagenbetreiberMastrNummer.name} "
                f"= {Einheiten.Marktakteure.name}.{Marktakteur.MastrNummer.name} "
            )

            # print(stmt)
            self.select_stmts[mastr_type] = stmt

    @staticmethod
    def latinify(input: str) -> str:
        umlauts = [("ä", "ae"), ("ü", "ue"), ("ö", "oe")]
        out = input
        for umlaut in umlauts:
            out = out.replace(umlaut[0], umlaut[1])
            out = out.replace(umlaut[0].capitalize(), umlaut[1].capitalize())
        return out

    def __create_state_mapping(self) -> dict[int, str]:
        stmt = """
            SELECT kw.id,kw.wert
            FROM katalogwerte kw
            JOIN katalogkategorien kg ON kw.katalogkategorieid = kg.id
            WHERE kg.name = 'Bundesland'
            """
        results = self.__query_db(stmt)
        return {result[0]: result[1] for result in results}

    @timer
    def write_csv(self, type: MastrType, out_path: Path, force: bool = True) -> None:
        mastr_option = type.value
        csv_jobs = []

        if mastr_option.germany:
            # create csv job for whole germany
            stmt = self.select_stmts[type]
            stmt = f"COPY ({stmt}) TO STDOUT WITH (FORMAT CSV, HEADER)"
            csv_path = out_path / Path(f"{type.name.lower()}_deutschland.csv")
            self.csv_files_germany[type] = csv_path
            job = CsvExportJob(name="germany", file_output_path=csv_path, sql_stmt=stmt, force_file_write=force)
            csv_jobs.append(job)

        if mastr_option.states:
            # create csv job for every state
            for _, state in self.states.items():
                stmt = self.select_stmts[type]
                state_filter = self.state_filter.replace("<<STATE>>", state).replace(
                    "<<table>>", type.value.entity.name
                )
                stmt = stmt + " " + state_filter
                stmt = f"COPY ({stmt}) TO STDOUT WITH (FORMAT CSV, HEADER)"
                csv_path = out_path / Path(f"{type.name.lower()}_{self.latinify(state.lower())}.csv")
                self.csv_files_states[type].append(csv_path)
                job = CsvExportJob(name=state, file_output_path=csv_path, sql_stmt=stmt, force_file_write=force)
                csv_jobs.append(job)

        execute_jobs_in_parallel(self.concurrency, write_csv_parallel, csv_jobs)

    @timer
    def write_excel(self, type: MastrType) -> None:
        """Import previously created CSV files and exports them to various Excel files."""
        mastr_option = type.value
        excel_jobs = []
        if DataFormats.EXCEL in mastr_option.data_formats:
            csv_files = []
            if mastr_option.germany:
                csv_files.append(self.csv_files_germany[type])
            if mastr_option.states:
                csv_files += self.csv_files_states[type]

            for csv_path in csv_files:
                file_descr = ".".join(csv_path.name.split(".")[:-1])
                excel_path = csv_path.parent / Path(file_descr + ".xlsx")
                job = ConvertExportJob(name=file_descr, file_output_path=excel_path, csv_source_file=csv_path)
                excel_jobs.append(job)

            execute_jobs_in_parallel(self.concurrency, write_excel_parallel, excel_jobs)

    @timer
    def write_parquet(self, type: MastrType) -> None:
        """Import previously created CSV files and exports them to various Parquet files."""
        mastr_option = type.value
        parquet_jobs = []
        if DataFormats.PARQUET in mastr_option.data_formats:
            csv_files = []
            if mastr_option.germany:
                csv_files.append(self.csv_files_germany[type])
            if mastr_option.states:
                csv_files += self.csv_files_states[type]

            for csv_path in csv_files:
                file_descr = ".".join(csv_path.name.split(".")[:-1])
                parq_path = csv_path.parent / Path(file_descr + ".parq")
                job = ConvertExportJob(name=file_descr, file_output_path=parq_path, csv_source_file=csv_path)
                parquet_jobs.append(job)

            # until python 3.14 it is absolutely not recommended to use polars with multiprocessing
            # execute_jobs_in_parallel(self.concurrency, write_parquet_parallel, parquet_jobs)
            for job in parquet_jobs:
                print(f"{job.name}")
                write_parquet_parallel(job)

    def __copy_to(self, stmt: str, file_path: Path):
        with open(file_path, "w", encoding="utf-8") as f:
            with self.conn.cursor() as cursor:
                cursor.copy_expert(sql=stmt, file=f)

    def __query_db(self, stmt: str, params: tuple = (), returnable=True) -> tuple:
        with self.conn.cursor() as cursor:
            cursor.execute(stmt, (tuple,))
            return cursor.fetchall() if returnable else ()


### specific export functions for parallel processing ###
def write_csv_parallel(job: CsvExportJob) -> None:
    conn = get_db_connection()
    if job.force_file_write or not job.file_output_path.exists():
        with open(job.file_output_path, "w", encoding="utf-8") as f:
            with conn.cursor() as cursor:
                cursor.copy_expert(sql=job.sql_stmt, file=f)
    conn.close()


def write_excel_parallel(job: ConvertExportJob) -> None:
    df = pd.read_csv(job.csv_source_file, low_memory=False)
    df.to_excel(job.file_output_path, index=False, sheet_name=job.name)


def write_parquet_parallel(job: ConvertExportJob) -> None:
    df = pl.scan_csv(job.csv_source_file, infer_schema_length=None) # scan whole data first to infer schema
    df.sink_parquet(job.file_output_path, compression="zstd")


def execute_jobs_in_parallel(concurrency: int, func, jobs: list[ExportJob]) -> None:
    with Pool(processes=concurrency) as pool:
        processes = []
        for job in jobs:
            processes.append(pool.apply_async(func, (job,)))

        for proc in processes:
            proc.get()


@timer
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Force overriding existent files")
    parser.add_argument("--concurrency", type=int, default=4, help="Number of parallel export processes (default: 4)")
    parser.add_argument("OUTPUT", type=Path, help="The export directory for converted files")
    args = parser.parse_args()

    connection = get_db_connection()
    exporter = MastrExporter(connection, args.concurrency)
    for mastr_type in MastrType:
        print(f"--- {mastr_type.name} ---")
        exporter.write_csv(mastr_type, args.OUTPUT, force=args.force)
        exporter.write_excel(mastr_type)
        exporter.write_parquet(mastr_type)


if __name__ == "__main__":
    main()
