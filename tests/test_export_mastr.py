"""Tests for export_mastr.py: select statements, naming and file conversion.

No database is involved: the select statements are built directly and the
CSV-to-Parquet/Excel conversion runs on a tiny generated CSV.
"""

import csv

import polars as pl
import pytest
from openpyxl import load_workbook

from db.entities import Einheiten, Marktakteur
from db.polars_schema import build_polars_schema
from export_mastr import (
    ConvertExportJob,
    MastrExporter,
    MastrType,
    write_excel_parallel,
    write_parquet_parallel,
)

latinify = MastrExporter.latinify


def build_exporter() -> MastrExporter:
    """Build a MastrExporter without touching the database."""
    exporter = object.__new__(MastrExporter)
    exporter.states = {}
    exporter.csv_files_states = {k: [] for k in MastrType}
    exporter.csv_files_germany = {k: None for k in MastrType}
    exporter.select_stmts = {k: "" for k in MastrType}
    exporter._MastrExporter__create_select_stmts()
    return exporter


def output_names(statement):
    """Output column names: explicit alias if present, else the column name."""
    names = []
    for line in statement.splitlines():
        if not line.startswith("\t"):
            continue
        line = line.rstrip(",")
        if line.endswith(")") and " " in line:
            names.append(line.rsplit(" ", 1)[1])  # udf(...) Alias
        elif " " in line:
            names.append(line.rsplit(" ", 1)[1])  # table.column Alias
        else:
            names.append(line.split(".")[-1])  # bare table.column
    return names


class TestSelectStatements:
    @pytest.mark.parametrize("mastr_type", list(MastrType))
    def test_output_names_are_unique(self, mastr_type):
        names = output_names(build_exporter().select_stmts[mastr_type])
        assert len(names) == len(set(names)), "duplicate export column names"

    @pytest.mark.parametrize("mastr_type", list(MastrType))
    def test_output_names_match_polars_schema(self, mastr_type):
        """CSV/Excel headers and Parquet column names must be identical."""
        entity = mastr_type.value.entity
        names = output_names(build_exporter().select_stmts[mastr_type])
        assert names == list(build_polars_schema(entity).keys())

    def test_operator_columns_are_prefixed(self):
        statement = build_exporter().select_stmts[MastrType.WIND]
        for column in Marktakteur:
            assert f"Marktakteur_{column.name}" in statement
        assert "\tMarktakteure.Land Land,\n" not in statement
        assert "\tMarktakteure.Land,\n" not in statement

    def test_udfs_are_applied(self):
        statement = build_exporter().select_stmts[MastrType.WIND]
        assert "katalog(EinheitenWind.Land) Land," in statement
        assert "boolean_hr(EinheitenWind.FernsteuerbarkeitNb) FernsteuerbarkeitNb," in statement
        assert "katalog_list(EinheitenSolar.ZusaetzlicheMerkmaleDerFlaecheUndDerAktuellenFlaechennutzung)" in (
            build_exporter().select_stmts[MastrType.SOLAR]
        )

    def test_join_condition(self):
        for mastr_type in MastrType:
            statement = build_exporter().select_stmts[mastr_type]
            table = mastr_type.value.entity.name
            assert f"ON {table}.AnlagenbetreiberMastrNummer = Marktakteure.MastrNummer" in statement


class TestLatinify:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("Baden-Württemberg", "Baden-Wuerttemberg"),
            ("Thüringen", "Thueringen"),
            ("Hessen", "Hessen"),
            ("Äpfel", "Aepfel"),
        ],
    )
    def test_umlauts(self, value, expected):
        assert latinify(value) == expected


def write_csv_with_schema(path, schema, rows):
    """Write a CSV matching the given polars schema (header + data rows)."""
    sample_values = {
        pl.String: "x",
        pl.Int64: "1",
        pl.Float64: "1.5",
        pl.Boolean: "true",
        pl.Datetime: "2024-01-01T00:00:00",
        pl.Date: "2024-01-01",
    }
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(schema.keys())
        for _ in range(rows):
            writer.writerow([sample_values[dtype] for dtype in schema.values()])


class TestFileConversion:
    def test_parquet_columns_match_schema(self, tmp_path):
        schema = build_polars_schema(Einheiten.EinheitenWind)
        csv_path = tmp_path / "wind.csv"
        parquet_path = tmp_path / "wind.parq"
        write_csv_with_schema(csv_path, schema, rows=2)

        job = ConvertExportJob(
            name="wind", file_output_path=parquet_path, csv_source_file=csv_path, schema=schema
        )
        write_parquet_parallel(job)

        frame = pl.read_parquet(parquet_path)
        assert frame.columns == list(schema.keys())
        assert frame.height == 2

    def test_excel_contains_all_rows(self, tmp_path):
        schema = build_polars_schema(Einheiten.EinheitenSolar)
        csv_path = tmp_path / "solar.csv"
        excel_path = tmp_path / "solar.xlsx"
        write_csv_with_schema(csv_path, schema, rows=3)

        job = ConvertExportJob(name="solar", file_output_path=excel_path, csv_source_file=csv_path)
        write_excel_parallel(job)

        workbook = load_workbook(excel_path)
        sheet = workbook.active
        assert sheet.max_row == 4  # header + 3 data rows
