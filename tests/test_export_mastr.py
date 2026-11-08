"""Tests for export_mastr.py: select statements, naming and file conversion.

No database is involved: the select statements are built directly and the
CSV-to-Parquet/Excel conversion runs on a tiny generated CSV.
"""

import csv

import polars as pl
import pytest
from openpyxl import load_workbook

from db.entities import Einheiten, Marktakteur, SelectUDFs, Type
from db.polars_schema import build_polars_schema
from export_mastr import (
    ConvertExportJob,
    DataFormats,
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
        assert "boolean_hr(EinheitenWind.FernsteuerbarkeitNb) FernsteuerbarkeitNb," in statement
        assert "marktfunktion(Marktakteure.Marktfunktion) Marktakteur_Marktfunktion," in statement
        assert "katalog_list(EinheitenSolar.ZusaetzlicheMerkmaleDerFlaecheUndDerAktuellenFlaechennutzung)" in (
            build_exporter().select_stmts[MastrType.SOLAR]
        )

    @pytest.mark.parametrize("mastr_type", list(MastrType))
    def test_catalog_values_are_resolved_by_joins(self, mastr_type):
        """Every catalog column gets its own LEFT JOIN on katalogwerte
        instead of a katalog() call per row."""
        import re

        statement = build_exporter().select_stmts[mastr_type]
        table = mastr_type.value.entity.name
        assert "katalog(" not in statement

        selected = dict(re.findall(r"^\t(katalog_\d+)\.Wert (\w+),?$", statement, re.M))
        joined = dict(re.findall(r"^LEFT JOIN Katalogwerte (katalog_\d+) ON katalog_\d+\.Id = (\S+) ?$", statement, re.M))
        expected = {f"{table}.{c.name}": c.name for c in mastr_type.value.entity.value if c.value.udf is SelectUDFs.Katalog}
        expected |= {f"Marktakteure.{c.name}": f"Marktakteur_{c.name}" for c in Marktakteur if c.value.udf is SelectUDFs.Katalog}
        assert {joined[alias]: name for alias, name in selected.items()} == expected
        assert len(joined) == len(expected)

    def test_join_condition(self):
        for mastr_type in MastrType:
            statement = build_exporter().select_stmts[mastr_type]
            table = mastr_type.value.entity.name
            assert f"ON {table}.AnlagenbetreiberMastrNummer = Marktakteure.MastrNummer" in statement

    def test_exported_boolean_columns_are_udf_wrapped(self):
        """Regression: COPY renders raw booleans as t/f, which polars cannot
        parse as Boolean - every boolean column of an exported entity must
        carry a UDF (boolean_hr -> ja/nein)."""
        exported = [mastr_type.value.entity.value for mastr_type in MastrType] + [Marktakteur]
        for entity_class in exported:
            for column in entity_class:
                if column.value.type is Type.BOOLEAN:
                    assert column.value.udf is not None, (
                        f"{entity_class.__name__}.{column.name} is exported as raw boolean"
                    )


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

    def test_excel_sheet_titles_fit_the_excel_limit(self):
        """Excel (all versions, including 365) rejects worksheet titles longer
        than 31 characters - openpyxl only warns, but Excel shows a repair
        dialog when opening such files. The file name carries the full
        identity, the sheet title stays short on purpose."""
        for mastr_type in MastrType:
            title = mastr_type.value.sheet_title
            assert len(title) <= 31, f"{mastr_type.name}: sheet title {title!r} exceeds Excel's 31-character limit"

    def test_large_datasets_have_no_excel_format(self):
        """Solar and Stromspeicher are too large for usable Excel files
        (openpyxl writes ~240k cells/s on a single core; Stromspeicher has
        ~1.5M units) - they are exported as CSV and Parquet only."""
        for mastr_type in (MastrType.SOLAR, MastrType.STROMSPEICHER):
            assert DataFormats.EXCEL not in mastr_type.value.data_formats, mastr_type.name

    def test_excel_contains_all_rows(self, tmp_path):
        schema = build_polars_schema(Einheiten.EinheitenSolar)
        csv_path = tmp_path / "solar.csv"
        excel_path = tmp_path / "solar.xlsx"
        write_csv_with_schema(csv_path, schema, rows=3)

        job = ConvertExportJob(name="solar", file_output_path=excel_path, csv_source_file=csv_path, schema=schema)
        write_excel_parallel(job)

        workbook = load_workbook(excel_path)
        sheet = workbook.active
        assert sheet.max_row == 4  # header + 3 data rows

    def test_excel_header_is_the_csv_header(self, tmp_path):
        """Regression: the header comes from the CSV (lower case names from
        COPY), not from the polars schema - as before the typed export."""
        schema = build_polars_schema(Einheiten.EinheitenWind)
        csv_path = tmp_path / "wind.csv"
        excel_path = tmp_path / "wind.xlsx"
        write_csv_with_schema(csv_path, schema, rows=1)
        header = [name.lower() for name in schema]
        lines = csv_path.read_text(encoding="utf-8").splitlines()
        csv_path.write_text("\n".join([",".join(header)] + lines[1:]) + "\n", encoding="utf-8")

        job = ConvertExportJob(name="wind", file_output_path=excel_path, csv_source_file=csv_path, schema=schema)
        write_excel_parallel(job)

        assert [cell.value for cell in load_workbook(excel_path).active[1]] == header

    def test_excel_cells_are_typed(self, tmp_path):
        """Numbers, dates and timestamps are written as numeric/date cells,
        not as text (Excel: "number stored as text", no sums or sorting)."""
        from datetime import datetime

        schema = {"Name": pl.String, "Anzahl": pl.Int64, "Leistung": pl.Float64, "Datum": pl.Date, "Zeit": pl.Datetime}
        csv_path = tmp_path / "typed.csv"
        excel_path = tmp_path / "typed.xlsx"
        # as written by Postgres' COPY ... (FORMAT CSV)
        csv_path.write_text(
            "Name,Anzahl,Leistung,Datum,Zeit\n"
            '"a, b",3,12.50,2024-01-31,2019-07-18 09:31:05.551\n'
            ",,,,\n"
            "c,7,Infinity,2020-02-29,2024-01-01 00:00:00\n",
            encoding="utf-8",
        )
        job = ConvertExportJob(name="typed", file_output_path=excel_path, csv_source_file=csv_path, schema=schema)
        write_excel_parallel(job)

        rows = list(load_workbook(excel_path).active.iter_rows(values_only=True))
        assert rows[0] == ("Name", "Anzahl", "Leistung", "Datum", "Zeit")
        assert rows[1] == ("a, b", 3, 12.5, datetime(2024, 1, 31), datetime(2019, 7, 18, 9, 31, 5, 551000))
        assert rows[2] == (None, None, None, None, None)
        # Excel has no infinity: the cell stays empty
        assert rows[3] == ("c", 7, None, datetime(2020, 2, 29), datetime(2024, 1, 1))

    def test_excel_uses_the_sheet_title_not_the_job_name(self, tmp_path):
        """Regression: the sheet title used to be the job name (the file
        descriptor), which exceeds Excel's 31-character limit for many
        exports (e.g. geothermie_grubengas_druckentspannung_mecklenburg-vorpommern)."""
        import warnings

        schema = build_polars_schema(Einheiten.EinheitenWind)
        csv_path = tmp_path / "geothermie_grubengas_druckentspannung_mecklenburg-vorpommern.csv"
        excel_path = tmp_path / "geothermie_grubengas_druckentspannung_mecklenburg-vorpommern.xlsx"
        write_csv_with_schema(csv_path, schema, rows=2)

        job = ConvertExportJob(
            name="geothermie_grubengas_druckentspannung_mecklenburg-vorpommern",
            file_output_path=excel_path,
            csv_source_file=csv_path,
            schema=schema,
            sheet_title="Geothermie",
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # fail on the openpyxl UserWarning
            write_excel_parallel(job)

        workbook = load_workbook(excel_path)
        assert workbook.active.title == "Geothermie"


class TestAtomicExportWrites:
    """All exports are written atomically (temp file + rename): readers only
    ever see complete files, and a failed export leaves the previous file
    and no temporary files behind."""

    def assert_no_temp_files(self, directory):
        leftovers = [p.name for p in directory.iterdir() if p.name.startswith(".")]
        assert leftovers == []

    def test_excel_write_leaves_no_temp_file(self, tmp_path):
        schema = build_polars_schema(Einheiten.EinheitenSolar)
        csv_path = tmp_path / "solar.csv"
        excel_path = tmp_path / "solar.xlsx"
        write_csv_with_schema(csv_path, schema, rows=2)

        write_excel_parallel(
            ConvertExportJob(name="solar", file_output_path=excel_path, csv_source_file=csv_path, schema=schema)
        )

        assert excel_path.exists()
        self.assert_no_temp_files(tmp_path)

    def test_parquet_failed_write_keeps_old_file(self, tmp_path):
        schema = build_polars_schema(Einheiten.EinheitenWind)
        csv_path = tmp_path / "wind.csv"
        parquet_path = tmp_path / "wind.parq"
        write_csv_with_schema(csv_path, schema, rows=2)
        job = ConvertExportJob(name="wind", file_output_path=parquet_path, csv_source_file=csv_path, schema=schema)
        write_parquet_parallel(job)
        previous_content = parquet_path.read_bytes()

        # a malformed row fails while the lazy frame is sunk, i.e. in the
        # middle of the atomic write
        csv_path.write_text(
            csv_path.read_text(encoding="utf-8") + "only,one,column\n", encoding="utf-8"
        )
        with pytest.raises(Exception):
            write_parquet_parallel(job)

        assert parquet_path.read_bytes() == previous_content
        self.assert_no_temp_files(tmp_path)
