"""Tests for db/tiles.sql: the function sources served by Martin.

The SQL is checked against the entity definitions in db/entities.py, so a
renamed table or column cannot silently break a layer: the tile function would
only fail at request time, when a client asks for a tile.
"""

import json
import re
from pathlib import Path

import pytest

from db.entities import Einheiten, GeomIndices, MAP_INDEX_CONDITION

TILES_SQL = Path(__file__).resolve().parent.parent / "db" / "tiles.sql"
UDF_SQL = Path(__file__).resolve().parent.parent / "db" / "udf.sql"

# Martin only publishes functions with z, x, y as the first three parameters
# that return bytea (query_available_function.sql in the Martin sources)
FUNCTION_PATTERN = re.compile(
    r"CREATE OR REPLACE FUNCTION tiles\.(\w+)\(z integer, x integer, y integer\)\s*"
    r"RETURNS bytea\s*AS \$\$(?P<body>.*?)\$\$\s*"
    r"LANGUAGE plpgsql\s*STABLE\s*PARALLEL SAFE\s*SECURITY DEFINER\s*"
    r"SET search_path = public, pg_temp;",
    re.S,
)

# every layer bundles its points per grid cell below a zoom: solar and
# stromspeicher have millions of units, the other layers tens of thousands
BUNDLED_BELOW_10 = {"solar", "stromspeicher"}
BUNDLED_BELOW_6 = {
    "wind",
    "biomasse",
    "wasser",
    "geothermie",
    "kernkraft",
    "verbrennung",
    "gaserzeuger",
    "gasspeicher",
    "gasverbraucher",
    "stromverbraucher",
}
BUNDLED_LAYERS = BUNDLED_BELOW_10 | BUNDLED_BELOW_6


def tile_functions() -> dict[str, str]:
    """layer name -> function body"""
    return {match.group(1): match.group("body") for match in FUNCTION_PATTERN.finditer(TILES_SQL.read_text())}


def source_table(body: str) -> str:
    match = re.search(r"FROM (\w+) e\b", body)
    assert match, "tile function does not select from a unit table"
    return match.group(1)


# the SQL uses the unquoted (lower case) table names
ENTITIES = {entity.name.lower(): entity for entity in Einheiten}


def entity_of(table: str):
    return ENTITIES[table.lower()].value


class TestFunctionLayers:
    def test_all_functions_match_the_expected_layout(self):
        """Guard for the pattern above: a reformatted function would silently
        drop out of the parsed set and hide the other checks."""
        sql = TILES_SQL.read_text()
        assert sql.count("CREATE OR REPLACE FUNCTION tiles.") == len(tile_functions())

    def test_every_function_is_a_martin_source(self):
        """Signature, return type and the function attributes Martin and the
        read-only role rely on are part of the pattern above."""
        functions = tile_functions()
        assert len(functions) == len(GeomIndices)
        assert set(functions) == {
            "wind",
            "solar",
            "biomasse",
            "wasser",
            "geothermie",
            "stromspeicher",
            "kernkraft",
            "verbrennung",
            "gaserzeuger",
            "gasspeicher",
            "gasverbraucher",
            "stromverbraucher",
        }

    def test_every_unit_table_with_coordinates_has_exactly_one_layer(self):
        tables = [source_table(body).lower() for body in tile_functions().values()]
        assert sorted(tables) == sorted(index.name.lower() for index in GeomIndices)
        assert len(tables) == len(set(tables))

    def test_layer_name_matches_the_mvt_layer(self):
        """The MVT layer name is the function name, so clients can use the
        source id from /catalog as source-layer."""
        for name, body in tile_functions().items():
            assert f"ST_AsMVT(f, '{name}')" in body, name

    def test_referenced_columns_exist_in_the_entity(self):
        marktakteur = {column.name.lower() for column in Einheiten.Marktakteure.value}
        for name, body in tile_functions().items():
            table = source_table(body)
            columns = {column.name.lower() for column in entity_of(table)}
            for column in set(re.findall(r"\be\.(\w+)", body)):
                assert column in columns, f"{name}: {table} has no column {column}"
            for column in set(re.findall(r"\bm\.(\w+)", body)):
                assert column in marktakteur, f"{name}: Marktakteure has no column {column}"

    def test_every_layer_has_a_tilejson_comment(self):
        """Martin reads the function comment as TileJSON: a plain text comment
        is ignored with a warning and the layer has no description."""
        sql = TILES_SQL.read_text()
        for name in tile_functions():
            match = re.search(
                rf"COMMENT ON FUNCTION tiles\.{name}\(integer, integer, integer\) IS\s*'(.*?)';",
                sql,
                re.S,
            )
            assert match, f"{name} has no comment"
            comment = json.loads(match.group(1))
            assert comment["description"], name

    def test_tile_query_uses_the_gist_index(self):
        """The bbox filter must use the same expression as the GiST index,
        otherwise the planner cannot use the index and every tile request
        scans the whole table."""
        for name, body in tile_functions().items():
            assert (
                "ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326) && b.env4326" in body
            ), name

    def test_tile_envelope_is_transformed_to_the_table_srid(self):
        for name, body in tile_functions().items():
            assert "ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326" in body, name
            assert "ST_AsMVTGeom(" in body, name

    def test_empty_tiles_are_empty_bytes(self):
        """ST_AsMVT returns an empty bytea for a tile without features; the
        coalesce keeps a NULL out of the response."""
        for name, body in tile_functions().items():
            assert "RETURN coalesce(result, ''::bytea);" in body, name

    def test_out_of_range_coordinates_return_an_empty_tile(self):
        """ST_TileEnvelope raises for x/y outside 0..2^z-1 and Martin turns
        that into a 500. A client error must not look like a server error, so
        the guard runs before the envelope is built."""
        for name, body in tile_functions().items():
            assert "IF z < 0 OR z > 30 THEN" in body, name
            assert "IF x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN" in body, name
            assert body.index("IF x < 0") < body.index("ST_TileEnvelope"), name


# (alias, MaStR column, expression) - added to every layer that has the column
COMMON_FIELDS = [
    ("inbetriebnahme", "Inbetriebnahmedatum", "to_char(e.inbetriebnahmedatum, 'YYYY-MM-DD') AS inbetriebnahme"),
    ("brutto_kw", "Bruttoleistung", "e.bruttoleistung::float8 AS brutto_kw"),
    (
        "betreiber",
        "AnlagenbetreiberMastrNummer",
        "coalesce(m.firmenname, nullif(concat_ws(' ', m.marktakteurvorname, m.marktakteurnachname), '')) AS betreiber",
    ),
    ("fernsteuerbar_nb", "FernsteuerbarkeitNb", "e.fernsteuerbarkeitnb AS fernsteuerbar_nb"),
    ("fernsteuerbar_dv", "FernsteuerbarkeitDv", "e.fernsteuerbarkeitdv AS fernsteuerbar_dv"),
    ("hochspannung", "AnschlussAnHoechstOderHochSpannung", "e.anschlussanhoechstoderhochspannung AS hochspannung"),
    (
        "stillgelegt_am",
        "DatumEndgueltigeStilllegung",
        "to_char(e.datumendgueltigestilllegung, 'YYYY-MM-DD') AS stillgelegt_am",
    ),
]

# fields of the energy carrier, per layer
LAYER_FIELDS = {
    "wind": ["nabenhoehe", "rotordurchmesser", "hersteller", "typ", "offshore", "buergerenergie"],
    "solar": ["art", "module", "ausrichtung", "neigung", "flaeche_ha", "speicher_am_ort", "buergerenergie"],
    "biomasse": ["brennstoff", "biomasseart", "technologie"],
    "wasser": ["art"],
    "geothermie": ["technologie"],
    "stromspeicher": ["batterietechnologie", "acdc", "einsatzort", "pumpspeicher", "notstrom", "wechselrichter"],
    "kernkraft": ["block", "technologie"],
    "verbrennung": ["brennstoff", "kombibetrieb", "einsatzort", "notstrom", "block"],
    "gaserzeuger": ["technologie"],
    "gasspeicher": ["speicherart", "arbeitsgasvolumen", "ausspeicherleistung"],
    "gasverbraucher": ["dient_der_stromerzeugung"],
    "stromverbraucher": ["anzahl_groesser_50mw"],
}


class TestAttributes:
    def test_every_layer_joins_the_market_actor(self):
        """The operator name comes from Marktakteure; a LEFT JOIN keeps units
        without an operator in the tile."""
        for name, body in tile_functions().items():
            assert "LEFT JOIN marktakteure m ON m.mastrnummer = e.anlagenbetreibermastrnummer" in body, name

    def test_common_fields_are_present_where_available(self):
        """Bruttoleistung, Fernsteuerbarkeit and the voltage flag do not exist
        in the gas and consumption tables - they are added where they exist."""
        for name, body in tile_functions().items():
            columns = {column.name for column in entity_of(source_table(body))}
            for alias, column, expression in COMMON_FIELDS:
                if column in columns:
                    assert expression in body, f"{name}: {alias}"

    @pytest.mark.parametrize("layer,fields", sorted(LAYER_FIELDS.items()))
    def test_layer_specific_fields(self, layer, fields):
        body = tile_functions()[layer]
        for field in fields:
            assert f" AS {field}" in body, f"{layer}: {field}"


class TestBundling:
    def test_every_layer_is_bundled(self):
        """A z0 tile of wind carries 43k units and grows to 4.7 MB; the
        aggregated cell is what a map draws at that zoom anyway."""
        assert set(tile_functions()) == BUNDLED_LAYERS

    def test_bundling_threshold(self):
        """Solar and Stromspeicher have millions of units and bundle up to
        zoom 10; the other layers have tens of thousands and bundle below
        zoom 6."""
        for name in BUNDLED_BELOW_10:
            assert "IF z < 10 THEN" in tile_functions()[name], name
        for name in BUNDLED_BELOW_6:
            assert "IF z < 6 THEN" in tile_functions()[name], name

    def test_bundled_branch_aggregates_per_cell(self):
        """A z5 tile with all solar units would contain hundreds of thousands
        of points and grow to several megabytes."""
        for name in BUNDLED_LAYERS:
            bundled = tile_functions()[name].split("ELSE")[0]
            # cell size = tile width / 64, computed in degrees
            assert "(ST_XMax(env4326) - ST_XMin(env4326)) / 64.0 AS dlon" in bundled, name
            assert "(ST_YMax(env4326) - ST_YMin(env4326)) / 64.0 AS dlat" in bundled, name
            assert "count(*) AS anzahl" in bundled, name
            assert "GROUP BY 1, 2" in bundled, name

    def test_bundled_layers_project_the_cells_not_the_units(self):
        """A projection per unit is what made a z1 tile take 30 s: the bundled
        branch transforms the grid cells (at most 4096), not every point."""
        for name in BUNDLED_LAYERS:
            bundled = tile_functions()[name].split("ELSE")[0]
            assert "ST_Transform(ST_SetSRID(ST_MakePoint(e." not in bundled, name
            assert "ST_SnapToGrid" not in bundled, name

    def test_bundled_layers_also_have_the_detail_level(self):
        for name in BUNDLED_LAYERS:
            body = tile_functions()[name]
            assert "ELSE" in body, name
            assert "e.einheitmastrnummer AS mastr_nr" in body, name

    def test_bundled_features_carry_the_power_where_the_layer_has_one(self):
        """Stromverbraucher has no power column in the MaStR, so its cells
        carry the count only."""
        for name in BUNDLED_LAYERS:
            bundled = tile_functions()[name].split("ELSE")[0]
            if name == "stromverbraucher":
                assert "sum(" not in bundled, name
                assert "c.anzahl, c.kw" not in bundled, name
            else:
                assert "sum(e." in bundled, name
                assert "c.anzahl, c.kw" in bundled, name


class TestSchemaAndGrants:
    def test_tiles_schema_is_created(self):
        assert "CREATE SCHEMA IF NOT EXISTS tiles;" in TILES_SQL.read_text()

    def test_postgis_extension_is_created(self):
        assert "CREATE EXTENSION IF NOT EXISTS postgis;" in UDF_SQL.read_text()

    def test_grants_are_limited_to_the_tiles_schema(self):
        """Martin connects with tiles_reader: the role may execute the tile
        functions but must not read the unit tables, otherwise it would
        publish them as table sources."""
        sql = TILES_SQL.read_text()
        assert "GRANT USAGE ON SCHEMA tiles TO tiles_reader;" in sql
        assert "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA tiles TO tiles_reader;" in sql
        assert "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA tiles FROM PUBLIC;" in sql
        assert "REVOKE ALL ON SCHEMA public FROM tiles_reader;" in sql
        # the grants must not fail when the role does not exist yet
        assert "IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'tiles_reader')" in sql

    def test_no_table_privileges_are_granted(self):
        sql = TILES_SQL.read_text()
        assert not re.search(r"GRANT\s+SELECT", sql, re.I)
        assert not re.search(r"GRANT\s+ALL\s+ON\s+ALL\s+TABLES", sql, re.I)


class TestIndexCondition:
    def test_index_condition_matches_the_tile_query(self):
        """The partial index condition and the tile query must stay in sync:
        the planner only uses a partial index if the query implies it. The
        expected query text is derived from the condition, so the two cannot
        drift apart."""
        conditions = re.findall(r"(\w+) BETWEEN (-?\d+) AND (-?\d+)", MAP_INDEX_CONDITION)
        assert len(conditions) == 2
        for name, body in tile_functions().items():
            for column, low, high in conditions:
                assert f"e.{column.lower()} BETWEEN {low} AND {high}" in body, f"{name}: {column}"


@pytest.mark.parametrize("name", sorted(BUNDLED_LAYERS))
def test_bundled_layer_keeps_the_bbox_filter_in_both_branches(name):
    body = tile_functions()[name]
    assert body.count("&& b.env4326") == 2


class TestCachePurge:
    def test_purge_list_matches_the_tile_layers(self):
        """download-mastr.sh purges Martin's cache per source after the import:
        a new layer must be added to MARTIN_SOURCES, otherwise its cached
        tiles survive the import until the TTL expires."""
        script = (Path(__file__).resolve().parent.parent / "download-mastr.sh").read_text()
        match = re.search(r'^MARTIN_SOURCES="([^"]+)"', script, re.M)
        assert match, "MARTIN_SOURCES not found in download-mastr.sh"
        assert sorted(match.group(1).split()) == sorted(tile_functions())
