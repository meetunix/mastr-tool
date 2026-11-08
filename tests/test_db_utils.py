"""Tests for the value conversion, the XML-to-row logic and the COPY writer
in db/db_utils.py."""

import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import pytest

from db.db_utils import DBConverter, DBElementWriter, to_copy_text
from db.entities import Einheiten, Type


class TestDBConverter:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("hello", "hello"),
            ("", ""),
            (None, None),
            ("None", None),
            ("none", None),
        ],
    )
    def test_text(self, value, expected):
        assert DBConverter.convert(value, Type.TEXT) == expected

    def test_int(self):
        assert DBConverter.convert("42", Type.INT) == 42
        assert DBConverter.convert(" 7 ", Type.INT) == 7

    def test_int_garbage_raises(self):
        with pytest.raises(ValueError):
            DBConverter.convert("not-a-number", Type.INT)

    def test_numeric(self):
        assert DBConverter.convert("12.5", Type.NUMERIC) == Decimal("12.5")

    def test_numeric_garbage_raises(self):
        with pytest.raises(InvalidOperation):
            DBConverter.convert("x", Type.NUMERIC)

    def test_timestamp(self):
        assert DBConverter.convert("2024-01-02T03:04:05", Type.TIMESTAMP) == datetime(2024, 1, 2, 3, 4, 5)

    def test_date(self):
        assert DBConverter.convert("2024-01-02", Type.DATE) == date(2024, 1, 2)

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("true", True),
            ("True", True),
            ("1", True),
            ("yes", True),
            ("ja", True),
            ("false", False),
            ("False", False),
            ("0", False),
            ("nein", False),
        ],
    )
    def test_boolean_encodings(self, value, expected):
        assert DBConverter.convert(value, Type.BOOLEAN) is expected

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError):
            DBConverter.convert("x", "not-a-type")


def values_of(entity, xml):
    element = ET.fromstring(xml)
    writer = DBElementWriter(entity, connection=None)
    names = [c.name for c in entity.value]
    return dict(zip(names, writer._DBElementWriter__get_values(element)))


WIND_RECORD = """
<EinheitWind>
  <EinheitMastrNummer>SEE1</EinheitMastrNummer>
  <DatumLetzteAktualisierung>2024-01-01T00:00:00</DatumLetzteAktualisierung>
  <Hausnummer>12a</Hausnummer>
  <Hausnummer_nv>false</Hausnummer_nv>
  <Weic>WEIC001</Weic>
  <Weic_nv>true</Weic_nv>
  <Kraftwerksnummer>KS1</Kraftwerksnummer>
  <Kraftwerksnummer_nv>1</Kraftwerksnummer_nv>
  <Ort></Ort>
  <EinheitBetriebsstatus>1</EinheitBetriebsstatus>
</EinheitWind>
"""


class TestGetValues:
    """The MaStR rule: a field whose _nv flag is true has no valid value."""

    def test_value_kept_when_nv_false(self):
        assert values_of(Einheiten.EinheitenWind, WIND_RECORD)["Hausnummer"] == "12a"

    def test_nv_flag_imported_as_boolean(self):
        values = values_of(Einheiten.EinheitenWind, WIND_RECORD)
        assert values["Hausnummer_nv"] is False
        assert values["Weic_nv"] is True

    def test_value_ignored_when_nv_true(self):
        assert values_of(Einheiten.EinheitenWind, WIND_RECORD)["Weic"] is None

    def test_value_ignored_when_nv_encoded_as_1(self):
        assert values_of(Einheiten.EinheitenWind, WIND_RECORD)["Kraftwerksnummer"] is None

    def test_empty_element_becomes_none(self):
        assert values_of(Einheiten.EinheitenWind, WIND_RECORD)["Ort"] is None

    def test_field_without_nv_untouched(self):
        assert values_of(Einheiten.EinheitenWind, WIND_RECORD)["EinheitBetriebsstatus"] == 1

    def test_missing_fields_become_none(self):
        values = values_of(
            Einheiten.EinheitenWind,
            "<EinheitWind><EinheitMastrNummer>SEE2</EinheitMastrNummer>"
            "<DatumLetzteAktualisierung>2024-01-01T00:00:00</DatumLetzteAktualisierung></EinheitWind>",
        )
        assert values["Hausnummer"] is None
        assert values["Hausnummer_nv"] is None

    def test_first_occurrence_wins_on_duplicate_tags(self):
        values = values_of(
            Einheiten.EinheitenWind,
            "<EinheitWind><EinheitMastrNummer>SEE3</EinheitMastrNummer>"
            "<EinheitMastrNummer>SEE4</EinheitMastrNummer>"
            "<DatumLetzteAktualisierung>2024-01-01T00:00:00</DatumLetzteAktualisierung></EinheitWind>",
        )
        assert values["EinheitMastrNummer"] == "SEE3"

    def test_garbage_value_with_nv_true_does_not_crash(self):
        values = values_of(
            Einheiten.EinheitenWind,
            "<EinheitWind><EinheitMastrNummer>SEE5</EinheitMastrNummer>"
            "<DatumLetzteAktualisierung>2024-01-01T00:00:00</DatumLetzteAktualisierung>"
            "<Weic>WEIC</Weic><Weic_nv>true</Weic_nv></EinheitWind>",
        )
        assert values["Weic"] is None


class TestCopyStatement:
    def test_statement_shape_for_all_entities(self):
        for entity in Einheiten:
            writer = DBElementWriter(entity, connection=None)
            statement = writer.copy_statement
            assert statement.startswith(f"COPY {entity.name} (")
            assert statement.endswith(") FROM STDIN")
            columns = statement[statement.index("(") + 1 : statement.index(")")].split(",")
            assert columns == [c.name for c in entity.value], entity.name

    def test_statement_contains_nv_columns(self):
        writer = DBElementWriter(Einheiten.EinheitenWind, connection=None)
        for column in ("Hausnummer_nv", "Weic_nv", "Kraftwerksnummer_nv"):
            assert column in writer.copy_statement


class TestCopyText:
    """Values are rendered in COPY's text format: tab separated, NULL as \\N,
    backslash, newline, carriage return and tab escaped."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, "\\N"),
            ("", ""),
            ("plain", "plain"),
            ("tab\there", "tab\\there"),
            ("line1\nline2", "line1\\nline2"),
            ("cr\rlf", "cr\\rlf"),
            ("back\\slash", "back\\\\slash"),
            ("\\N", "\\\\N"),  # the text "\N" must not become NULL
            ('quote"d,comma', 'quote"d,comma'),
            (True, "t"),
            (False, "f"),
            (42, "42"),
            (Decimal("12.50"), "12.50"),
            (391234.5678901234, "391234.5678901234"),
            (float("inf"), "inf"),
            (date(2024, 1, 31), "2024-01-31"),
            (datetime(2019, 7, 18, 9, 31, 5, 551321), "2019-07-18T09:31:05.551321"),
        ],
    )
    def test_values(self, value, expected):
        assert to_copy_text(value) == expected

    def test_timestamp_with_offset_is_converted_to_utc(self):
        value = datetime(2024, 1, 1, 12, 0, tzinfo=timezone(timedelta(hours=1)))
        assert to_copy_text(value) == "2024-01-01T11:00:00"


def copied_values(connection, entity):
    """The copied rows of the fake connection as dicts (raw COPY text)."""
    names = [c.name for c in entity.value]
    rows = [row for cursor in connection.cursors for row in cursor.copied_rows]
    return [dict(zip(names, row.split("\t"))) for row in rows]


class TestBatching:
    def test_batches_are_flushed_at_batch_limit(self, monkeypatch):
        from tests.conftest import FakeConnection

        monkeypatch.setattr(DBElementWriter, "BATCH_LIMIT", 3)
        connection = FakeConnection()
        writer = DBElementWriter(Einheiten.Katalogwerte, connection)

        record = "<Katalogwert><Id>1</Id><Wert>x</Wert><KatalogKategorieId>2</KatalogKategorieId></Katalogwert>"

        for _ in range(5):
            writer.write(ET.fromstring(record))

        # 5 records with batch limit 3: one flush of 3 happened so far
        assert len(copied_values(connection, Einheiten.Katalogwerte)) == 3
        assert connection.commits == 1

        writer.cleanup()
        # cleanup flushes the remaining 2 and closes the connection
        assert copied_values(connection, Einheiten.Katalogwerte) == [{"Id": "1", "Wert": "x", "KatalogKategorieId": "2"}] * 5
        assert connection.commits == 2
        assert connection.closed is True

    def test_empty_batch_is_not_copied(self):
        from tests.conftest import FakeConnection

        connection = FakeConnection()
        DBElementWriter(Einheiten.Katalogwerte, connection).cleanup()
        assert connection.cursors == []
        assert connection.closed is True


class TestUtmEnrichment:
    """Units with geo coordinates get their UTM coordinates during the import
    (identical to CoordinateConverter.geo_to_utm)."""

    def write_wind(self, records):
        from tests.conftest import FakeConnection

        connection = FakeConnection()
        writer = DBElementWriter(Einheiten.EinheitenWind, connection)
        for i, coordinates in enumerate(records):
            writer.write(
                ET.fromstring(
                    f"<EinheitWind><EinheitMastrNummer>SEE{i}</EinheitMastrNummer>"
                    f"<DatumLetzteAktualisierung>2024-01-01T00:00:00</DatumLetzteAktualisierung>"
                    f"{coordinates}</EinheitWind>"
                )
            )
        writer.cleanup()
        return copied_values(connection, Einheiten.EinheitenWind)

    def test_utm_columns_are_filled(self):
        from enricher.enricher import CoordinateConverter

        rows = self.write_wind(
            [
                "<Breitengrad>52.516275</Breitengrad><Laengengrad>13.377704</Laengengrad>",
                "<Breitengrad>50.0</Breitengrad><Laengengrad>6.0</Laengengrad>",
            ]
        )
        for row, (lat, lon) in zip(rows, [("52.516275", "13.377704"), ("50.0", "6.0")]):
            utm = CoordinateConverter().geo_to_utm(Decimal(lat), Decimal(lon))
            assert row["UTM_zone"] == str(utm.zone)
            assert row["UTM_ost"] == repr(utm.easting)
            assert row["UTM_nord"] == repr(utm.northing)
        assert [row["UTM_zone"] for row in rows] == ["33", "32"]

    def test_rows_without_coordinates_stay_null(self):
        rows = self.write_wind(["<Breitengrad>52.5</Breitengrad>", "<Laengengrad>13.4</Laengengrad>", ""])
        for row in rows:
            assert (row["UTM_zone"], row["UTM_ost"], row["UTM_nord"]) == ("\\N", "\\N", "\\N")

    def test_entities_without_coordinates_are_not_enriched(self):
        writer = DBElementWriter(Einheiten.Marktakteure, connection=None)
        assert writer._DBElementWriter__utm_enricher is None
