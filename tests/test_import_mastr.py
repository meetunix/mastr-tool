"""Tests for import_mastr.py: file grouping, DDL generation and XML parsing.

No MaStR dump data is needed: XML documents are generated in memory and the
database is replaced by the fake connection from conftest.py.
"""

from pathlib import Path

from db.entities import Einheiten
import import_mastr
from tests.conftest import FakeConnection


class TestGetFiles:
    def test_split_files_are_grouped_and_ordered(self):
        files = {
            Path("EinheitenWind_1.xml"),
            Path("EinheitenWind_2.xml"),
            Path("EinheitenWind_10.xml"),
        }
        result = import_mastr.get_files(files)
        assert list(result.keys()) == ["EinheitenWind"]
        assert [f.name for f in result["EinheitenWind"]] == [
            "EinheitenWind_1.xml",
            "EinheitenWind_2.xml",
            "EinheitenWind_10.xml",
        ]

    def test_non_split_files_are_keyed_by_stem(self):
        result = import_mastr.get_files({Path("Marktakteure.xml")})
        assert list(result.keys()) == ["Marktakteure"]

    def test_mixed_files(self):
        files = {Path("EinheitenSolar_1.xml"), Path("EinheitenSolar_2.xml"), Path("Katalogwerte.xml")}
        result = import_mastr.get_files(files)
        assert set(result.keys()) == {"EinheitenSolar", "Katalogwerte"}
        assert len(result["EinheitenSolar"]) == 2


class TestCreateSchema:
    def test_schema_contains_all_tables(self, tmp_path):
        path = tmp_path / "schema.sql"
        import_mastr.create_schema(path)
        schema = path.read_text()
        for entity in Einheiten:
            assert f"create table if not exists {entity.name} (" in schema

    def test_schema_renders_constraints(self, tmp_path):
        path = tmp_path / "schema.sql"
        import_mastr.create_schema(path)
        schema = path.read_text()
        assert "EinheitMastrNummer" in schema
        assert "PRIMARY KEY" in schema
        assert "NOT NULL" in schema

    def test_schema_contains_indices(self, tmp_path):
        path = tmp_path / "schema.sql"
        import_mastr.create_schema(path)
        schema = path.read_text()
        assert "CREATE INDEX IF NOT EXISTS Bundesland_idx ON EinheitenWind(Bundesland);" in schema
        assert "CREATE INDEX IF NOT EXISTS Personenart_idx ON Marktakteure(Personenart);" in schema


def wind_xml(record_count):
    records = "".join(
        f"<EinheitWind><EinheitMastrNummer>SEE{i}</EinheitMastrNummer>"
        f"<DatumLetzteAktualisierung>2024-01-01T00:00:00</DatumLetzteAktualisierung>"
        f"<Hausnummer>{i}</Hausnummer><Hausnummer_nv>false</Hausnummer_nv></EinheitWind>"
        for i in range(record_count)
    )
    return f"<EinheitenWind>{records}</EinheitenWind>"


class TestParseAndWriteXml:
    def test_records_are_written_and_connection_closed(self, tmp_path, monkeypatch):
        connections = []

        def fake_get_db_connection():
            connection = FakeConnection()
            connections.append(connection)
            return connection

        monkeypatch.setattr(import_mastr, "get_db_connection", fake_get_db_connection)

        xml_file = tmp_path / "EinheitenWind.xml"
        xml_file.write_text(wind_xml(3))

        import_mastr.parse_and_write_xml(xml_file, Einheiten.EinheitenWind, silent=True)

        assert len(connections) == 1
        connection = connections[0]
        assert connection.closed is True
        # all 3 records reached the database layer
        assert connection.cursors[0].mogrify_calls == 3
        assert connection.commits >= 1

    def test_nv_rule_applies_during_import(self, tmp_path, monkeypatch):
        """A record whose Weic_nv is true must import Weic as NULL."""
        captured = []

        from db.db_utils import DBElementWriter

        class CapturingWriter(DBElementWriter):
            def write(self, element):
                captured.append(self._DBElementWriter__get_values(element))
                super().write(element)

        monkeypatch.setattr(import_mastr, "get_db_connection", FakeConnection)
        # parse_and_write_xml resolves DBElementWriter from the import_mastr
        # namespace, so the subclass must be patched there
        monkeypatch.setattr(import_mastr, "DBElementWriter", CapturingWriter)

        xml = (
            "<EinheitenWind><EinheitWind><EinheitMastrNummer>SEE1</EinheitMastrNummer>"
            "<DatumLetzteAktualisierung>2024-01-01T00:00:00</DatumLetzteAktualisierung>"
            "<Weic>WEIC</Weic><Weic_nv>true</Weic_nv></EinheitWind></EinheitenWind>"
        )
        xml_file = tmp_path / "EinheitenWind.xml"
        xml_file.write_text(xml)

        import_mastr.parse_and_write_xml(xml_file, Einheiten.EinheitenWind, silent=True)

        assert captured
        names = [c.name for c in Einheiten.EinheitenWind.value]
        values = dict(zip(names, captured[0]))
        assert values["Weic"] is None
        assert values["Weic_nv"] is True
