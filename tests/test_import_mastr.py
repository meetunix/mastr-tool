"""Tests for import_mastr.py: file grouping, DDL generation and XML parsing.

No MaStR dump data is needed: XML documents are generated in memory and the
database is replaced by the fake connection from conftest.py.
"""

from pathlib import Path

from db.entities import Einheiten
import import_mastr
from tests.conftest import FakeConnection, FakeCursor


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


def constraints_sql(tmp_path) -> str:
    path = tmp_path / "constraints.sql"
    import_mastr.create_constraints(path)
    return path.read_text()


class TestCreateSchema:
    def test_schema_contains_all_tables(self, tmp_path):
        path = tmp_path / "schema.sql"
        import_mastr.create_schema(path)
        schema = path.read_text()
        for entity in Einheiten:
            assert f"create unlogged table if not exists {entity.name} (" in schema

    def test_schema_renders_constraints(self, tmp_path):
        path = tmp_path / "schema.sql"
        import_mastr.create_schema(path)
        schema = path.read_text()
        assert "EinheitMastrNummer" in schema
        assert "NOT NULL" in schema
        # primary keys and indices are built after the load
        assert "PRIMARY KEY" not in schema
        assert "CREATE INDEX" not in schema

    def test_autovacuum_is_disabled_during_the_import(self, tmp_path):
        """Building the primary keys and indices after the load cancels a
        running autovacuum, which Postgres logs as "ERROR: canceling
        autovacuum task" - the tables are created without autovacuum."""
        import re

        path = tmp_path / "schema.sql"
        import_mastr.create_schema(path)
        tables = re.findall(r"create unlogged table if not exists \w+ \(.*?\n\)([^;]*);", path.read_text(), re.S)
        assert len(tables) == len(Einheiten)
        for options in tables:
            assert options == " WITH (autovacuum_enabled = false, toast.autovacuum_enabled = false)"

    def test_enable_autovacuum_resets_all_tables(self, monkeypatch):
        connection = FakeConnection()
        monkeypatch.setattr(import_mastr, "get_db_connection", lambda: connection)
        import_mastr.enable_autovacuum()
        executed = [statement for cursor in connection.cursors for statement in cursor.executed]
        assert executed == [
            f"ALTER TABLE {entity.name} RESET (autovacuum_enabled, toast.autovacuum_enabled)" for entity in Einheiten
        ]
        assert connection.commits == 1
        assert connection.closed is True

    def test_constraints_contain_all_primary_keys(self, tmp_path):
        constraints = constraints_sql(tmp_path)
        for entity in Einheiten:
            primary_key = [c.name for c in entity.value if c.value.primary_key]
            if primary_key:
                assert f"ALTER TABLE {entity.name} ADD PRIMARY KEY ({', '.join(primary_key)});" in constraints
                assert f"conrelid = '{entity.name}'::regclass AND contype = 'p'" in constraints
            else:
                assert f"ALTER TABLE {entity.name} " not in constraints

    def test_schema_contains_indices(self, tmp_path):
        schema = constraints_sql(tmp_path)
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

        schema = constraints_sql(tmp_path)
        for mastr_type in MastrType:
            table = mastr_type.value.entity.name
            assert f"ON {table}(Bundesland)" in schema, table

    def test_map_indices_cover_the_units_with_coordinates(self, tmp_path):
        """The maps page of mastr-app reads the units of a state that have
        coordinates from a partial covering index (index-only scan), not
        from the table: e.g. EinheitenSolar has 2 GB."""
        from db.entities import MapIndices

        schema = constraints_sql(tmp_path)
        for index in MapIndices:
            extra = ", ".join(column.name for column in index.value)
            assert (
                f"CREATE INDEX IF NOT EXISTS {index.name}_map_idx ON {index.name}(Bundesland) "
                f"INCLUDE (EinheitMastrNummer, Breitengrad, Laengengrad, EinheitBetriebsstatus, {extra}) "
                "WHERE Breitengrad BETWEEN -90 AND 90 AND Laengengrad BETWEEN -180 AND 180;"
            ) in schema
        assert "ON EinheitenSolar(Bundesland) INCLUDE (" in schema
        assert "NameDesSolarparks, Nettonennleistung)" in schema

    def test_every_index_has_a_unique_name(self, tmp_path):
        """Regression: the index name used to be just '<column>_idx', so all
        Bundesland indices shared one name and 'IF NOT EXISTS' silently skipped
        every table after the first - only EinheitenWind got an index."""
        import re

        schema = constraints_sql(tmp_path)
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
        assert len(connection.cursors[0].copied_rows) == 3
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


class TestGeomIndices:
    def test_geom_indices_use_the_point_expression(self, tmp_path):
        """No geometry column is stored: the GiST index is built on the point
        expression, so the import stays unchanged."""
        from db.entities import GEOM_INDEX_EXPRESSION, GeomIndices, MAP_INDEX_CONDITION

        schema = constraints_sql(tmp_path)
        for index in GeomIndices:
            assert (
                f"CREATE INDEX IF NOT EXISTS {index.name}_geom_idx ON {index.name} "
                f"USING GIST ({GEOM_INDEX_EXPRESSION}) WHERE {MAP_INDEX_CONDITION};"
            ) in schema

    def test_geom_indices_cover_all_tables_with_coordinates(self):
        """A unit table with coordinates without an index would make every
        tile request a sequential scan."""
        from db.entities import GeomIndices

        for index in GeomIndices:
            # the index expression is built from these two columns
            columns = {column.name for column in index.value}
            assert {"Laengengrad", "Breitengrad"} <= columns, index.name
        for entity in Einheiten:
            columns = {column.name for column in entity.value}
            has_coordinates = {"Laengengrad", "Breitengrad"} <= columns
            assert (entity.name in GeomIndices.__members__) == has_coordinates, entity.name

    def test_geom_index_expression_matches_the_tile_query(self):
        """The tile functions filter with "&&" on exactly the indexed
        expression - any difference and the index is not used."""
        from db.entities import GEOM_INDEX_EXPRESSION

        tiles_sql = (Path(__file__).resolve().parent.parent / "db" / "tiles.sql").read_text()
        query_expression = GEOM_INDEX_EXPRESSION.replace("Laengengrad", "e.laengengrad").replace(
            "Breitengrad", "e.breitengrad"
        )
        assert query_expression in tiles_sql


class TestWriteSchema:
    def test_schema_udf_and_tiles_are_executed_in_order(self, tmp_path, monkeypatch):
        """The tile functions need the tables (schema) and PostGIS (udf.sql),
        so the three files are executed as one script in this order."""
        connection = FakeConnection()
        calls = []
        monkeypatch.setattr(import_mastr, "get_db_connection", lambda: connection)
        monkeypatch.setattr(import_mastr, "create_tiles_role", lambda: calls.append("role"))

        path_schema = tmp_path / "schema.sql"
        path_udf = tmp_path / "udf.sql"
        path_tiles = tmp_path / "tiles.sql"
        path_schema.write_text("CREATE TABLE t (id int);")
        path_udf.write_text("CREATE EXTENSION IF NOT EXISTS postgis;")
        path_tiles.write_text("CREATE SCHEMA IF NOT EXISTS tiles;")

        import_mastr.write_schema(path_schema, path_udf, path_tiles)

        executed = connection.cursors[0].executed[0]
        assert executed.index("CREATE TABLE t") < executed.index("CREATE EXTENSION") < executed.index("CREATE SCHEMA")
        assert connection.commits == 1
        # the role must exist before db/tiles.sql grants it access
        assert calls == ["role"]


class TestCreateTilesRole:
    def test_missing_role_is_created_with_the_env_password(self, monkeypatch):
        connection = FakeConnection()
        monkeypatch.setattr(import_mastr, "get_db_connection", lambda: connection)
        monkeypatch.setenv("TILES_DB_PASSWORD", "secret")

        import_mastr.create_tiles_role()

        cursor = connection.cursors[0]
        assert cursor.executed[0] == "SELECT 1 FROM pg_roles WHERE rolname = %s"
        assert cursor.executed[1] == 'CREATE ROLE tiles_reader WITH LOGIN PASSWORD %s'
        assert cursor.executed_params[1] == ("secret",)
        assert connection.commits == 1
        assert connection.closed is True

    def test_existing_role_gets_the_password_of_the_env(self, monkeypatch):
        connection = FakeConnection(rows=[(1,)])
        monkeypatch.setattr(import_mastr, "get_db_connection", lambda: connection)
        monkeypatch.setenv("TILES_DB_PASSWORD", "secret")

        import_mastr.create_tiles_role()

        cursor = connection.cursors[0]
        assert cursor.executed[1] == 'ALTER ROLE tiles_reader WITH LOGIN PASSWORD %s'
        assert cursor.executed_params[1] == ("secret",)

    def test_default_password_is_used_without_env(self, monkeypatch):
        connection = FakeConnection()
        monkeypatch.setattr(import_mastr, "get_db_connection", lambda: connection)
        monkeypatch.delenv("TILES_DB_PASSWORD", raising=False)

        import_mastr.create_tiles_role()

        assert connection.cursors[0].executed_params[1] == (import_mastr.TILES_DB_PASSWORD_DEFAULT,)

    def test_missing_createrole_does_not_abort_the_import(self, monkeypatch):
        """A CloudNativePG managed role has no CREATEROLE: the role has to be
        created by an administrator, the import must still run."""
        import psycopg2

        class PrivilegeErrorCursor(FakeCursor):
            def execute(self, statement, params=None):
                raise psycopg2.errors.InsufficientPrivilege("permission denied to create role")

        class PrivilegeErrorConnection(FakeConnection):
            def cursor(self):
                cursor = PrivilegeErrorCursor(self)
                self.cursors.append(cursor)
                return cursor

        connection = PrivilegeErrorConnection()
        monkeypatch.setattr(import_mastr, "get_db_connection", lambda: connection)

        import_mastr.create_tiles_role()

        assert connection.rollbacks == 1
        assert connection.closed is True
