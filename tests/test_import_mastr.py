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
        assert "CREATE INDEX IF NOT EXISTS EinheitenWind_Bundesland_idx ON EinheitenWind(Bundesland);" in schema
        assert "CREATE INDEX IF NOT EXISTS Marktakteure_Personenart_idx ON Marktakteure(Personenart);" in schema
        assert (
            "CREATE INDEX IF NOT EXISTS Katalogwerte_KatalogKategorieId_idx ON Katalogwerte(KatalogKategorieId);"
            in schema
        )

    def test_bundesland_indices_support_the_export_state_filter(self, tmp_path):
        """The state export filters on the raw column
        (<table>.bundesland = <catalog id>) - every exported table needs a
        plain Bundesland index, or the planner runs every state export as a
        sequential scan. An expression index on katalog(bundesland) is not an
        alternative: functions that access tables cannot run during
        CREATE INDEX."""
        from export_mastr import MastrType

        path = tmp_path / "schema.sql"
        import_mastr.create_schema(path)
        schema = path.read_text()
        for mastr_type in MastrType:
            table = mastr_type.value.entity.name
            assert f"ON {table}(Bundesland)" in schema, table

    def test_every_index_has_a_unique_name(self, tmp_path):
        """Regression: the index name used to be just '<column>_idx', so all
        Bundesland indices shared one name and 'IF NOT EXISTS' silently skipped
        every table after the first - only EinheitenWind got an index."""
        import re

        path = tmp_path / "schema.sql"
        import_mastr.create_schema(path)
        schema = path.read_text()
        names = re.findall(r"CREATE INDEX IF NOT EXISTS (\S+?) ON", schema)
        assert len(names) == len(set(names)), "duplicate index names in schema"

    def test_column_names_are_separated_from_their_type(self, tmp_path):
        """Regression: names longer than the 56-char padding used to be glued
        to the SQL type (e.g. '...Flaechennutzungtext'), producing invalid DDL."""
        import re

        from db.entities import Einheiten as AllEntities

        path = tmp_path / "schema.sql"
        import_mastr.create_schema(path)
        schema = path.read_text()
        for entity in AllEntities:
            for column in entity.value:
                assert re.search(rf"^\s*{re.escape(column.name)}\s", schema, re.M), (
                    f"{entity.name}.{column.name} is not separated from its type in the DDL"
                )


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
