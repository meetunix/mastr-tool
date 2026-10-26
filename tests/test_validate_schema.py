"""Tests for validate_schema.py against synthetic XSD documents.

The XSDs are generated from the entity definitions themselves (plus targeted
mutations), so no downloaded documentation archive is required.
"""

import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

import validate_schema
from db.entities import Einheiten, Type
from validate_schema import parse_xsd, resolve_field_type, validate_entity, extract_xsd_files

XS = "{http://www.w3.org/2001/XMLSchema}"
TYPE_TO_XSD = {
    Type.TEXT: "xs:string",
    Type.INT: "xs:int",
    Type.TIMESTAMP: "xs:dateTime",
    Type.DATE: "xs:date",
    Type.BOOLEAN: "xs:boolean",
    Type.NUMERIC: "xs:decimal",
}


def build_xsd(entity, mutations=None):
    """Build an XSD document that matches the entity definition.

    mutations: dict of column name -> new attribute string, applied to the
    generated field element (e.g. {"Wert": 'type="xs:int" name="Wert"'}).
    """
    mutations = mutations or {}
    fields = []
    for column in entity.value:
        attributes = mutations.get(column.name)
        if attributes is None:
            attributes = f'type="{TYPE_TO_XSD[column.value.type]}" name="{column.name}"'
            if not column.value.not_null:
                attributes += ' minOccurs="0"'
        fields.append(f"<xs:element {attributes}/>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        f'<xs:element name="{entity.name}"><xs:complexType><xs:sequence>'
        f'<xs:element name="{entity.value.__name__}" maxOccurs="unbounded" minOccurs="0">'
        "<xs:complexType><xs:sequence>"
        + "".join(fields)
        + "</xs:sequence></xs:complexType></xs:element>"
        "</xs:sequence></xs:complexType></xs:element></xs:schema>"
    )


def write_xsd(tmp_path, entity, content=None):
    path = tmp_path / f"{entity.name}.xsd"
    path.write_text(content or build_xsd(entity))
    return path


class TestResolveFieldType:
    def element(self, snippet):
        return ET.fromstring(
            f'<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" {snippet}></xs:element>'
        )

    def test_type_attribute_is_mapped(self):
        assert resolve_field_type(self.element('type="xs:string" name="X"')) == Type.TEXT
        assert resolve_field_type(self.element('type="xs:short" name="X"')) == Type.INT
        assert resolve_field_type(self.element('type="xs:float" name="X"')) == Type.NUMERIC

    def test_unknown_type_attribute_is_returned_verbatim(self):
        assert resolve_field_type(self.element('type="xs:foo" name="X"')) == "xs:foo"

    def test_byte_restriction_0_1_is_boolean(self):
        snippet = (
            'name="X"><xs:simpleType><xs:restriction base="xs:byte">'
            '<xs:enumeration value="0"/><xs:enumeration value="1"/>'
            "</xs:restriction></xs:simpleType>"
        )
        assert resolve_field_type(self.element(snippet)) == Type.BOOLEAN

    def test_byte_restriction_other_values_is_int(self):
        snippet = (
            'name="X"><xs:simpleType><xs:restriction base="xs:byte">'
            '<xs:enumeration value="7"/><xs:enumeration value="9"/>'
            "</xs:restriction></xs:simpleType>"
        )
        assert resolve_field_type(self.element(snippet)) == Type.INT

    def test_list_is_text(self):
        snippet = 'name="X"><xs:simpleType><xs:list><xs:simpleType><xs:restriction base="xs:short"/></xs:simpleType></xs:list></xs:simpleType>'
        assert resolve_field_type(self.element(snippet)) == Type.TEXT

    def test_composite_is_detected(self):
        snippet = 'name="X"><xs:complexType><xs:sequence/></xs:complexType>'
        assert resolve_field_type(self.element(snippet)) == "COMPOSITE"

    def test_no_type_at_all(self):
        assert resolve_field_type(self.element('name="X"')) is None


class TestValidateEntity:
    def test_matching_xsd_produces_no_errors(self, tmp_path):
        errors, warnings = validate_entity(Einheiten.Katalogwerte, write_xsd(tmp_path, Einheiten.Katalogwerte))
        assert errors == []
        assert warnings == []

    def test_renamed_xsd_field_is_an_error(self, tmp_path):
        content = build_xsd(Einheiten.Katalogwerte, {"Wert": 'type="xs:string" name="WertX"'})
        errors, _ = validate_entity(Einheiten.Katalogwerte, write_xsd(tmp_path, Einheiten.Katalogwerte, content))
        assert any("Wert" in e and "always be NULL" in e for e in errors)

    def test_not_null_but_optional_is_an_error(self, tmp_path):
        content = build_xsd(Einheiten.Katalogwerte, {"Id": 'type="xs:int" name="Id" minOccurs="0"'})
        errors, _ = validate_entity(Einheiten.Katalogwerte, write_xsd(tmp_path, Einheiten.Katalogwerte, content))
        assert any("Id" in e and "NOT NULL" in e for e in errors)

    def test_type_mismatch_is_an_error(self, tmp_path):
        content = build_xsd(Einheiten.Katalogwerte, {"Wert": 'type="xs:int" name="Wert"'})
        errors, _ = validate_entity(Einheiten.Katalogwerte, write_xsd(tmp_path, Einheiten.Katalogwerte, content))
        assert any("Wert" in e and "XSD type" in e for e in errors)

    def test_date_vs_timestamp_is_a_benign_warning(self, tmp_path):
        content = build_xsd(
            Einheiten.Marktakteure,
            {"RegistrierungsdatumMarktakteur": 'type="xs:date" name="RegistrierungsdatumMarktakteur" minOccurs="0"'},
        )
        errors, warnings = validate_entity(
            Einheiten.Marktakteure, write_xsd(tmp_path, Einheiten.Marktakteure, content)
        )
        assert errors == []
        assert any("RegistrierungsdatumMarktakteur" in w and "losslessly" in w for w in warnings)

    def test_missing_nv_companion_is_a_warning(self, tmp_path):
        content = build_xsd(Einheiten.Katalogwerte).replace(
            "</xs:sequence></xs:complexType></xs:element>",
            '<xs:element type="xs:boolean" name="Wert_nv"/></xs:sequence></xs:complexType></xs:element>',
        )
        _, warnings = validate_entity(Einheiten.Katalogwerte, write_xsd(tmp_path, Einheiten.Katalogwerte, content))
        assert any("Wert_nv" in w and "_nv" in w for w in warnings)

    def test_record_tag_mismatch_is_an_error(self, tmp_path):
        content = build_xsd(Einheiten.Katalogwerte).replace('name="Katalogwert"', 'name="KatalogwertX"')
        errors, _ = validate_entity(Einheiten.Katalogwerte, write_xsd(tmp_path, Einheiten.Katalogwerte, content))
        assert any("record element" in e for e in errors)

    def test_table_tag_mismatch_is_an_error(self, tmp_path):
        content = build_xsd(Einheiten.Katalogwerte).replace('name="Katalogwerte"', 'name="KatalogwerteX"', 1)
        errors, _ = validate_entity(Einheiten.Katalogwerte, write_xsd(tmp_path, Einheiten.Katalogwerte, content))
        assert any("root element" in e for e in errors)


class TestExtractAndMain:
    def test_extract_xsd_files(self, tmp_path):
        zip_path = tmp_path / "doc.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("doc/xsd/Katalogwerte.xsd", build_xsd(Einheiten.Katalogwerte))
            archive.writestr("doc/ignored.txt", "not an xsd")
        target = tmp_path / "out"
        target.mkdir()
        extracted = extract_xsd_files(zip_path, target)
        assert extracted == {"Katalogwerte.xsd"}
        assert (target / "Katalogwerte.xsd").exists()

    def test_main_passes_for_self_consistent_zip(self, tmp_path, monkeypatch, capsys):
        zip_path = tmp_path / "doc.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            for entity in Einheiten:
                archive.writestr(f"doc/xsd/{entity.name}.xsd", build_xsd(entity))
        monkeypatch.setattr(sys, "argv", ["validate_schema.py", "--zip", str(zip_path)])
        exit_code = validate_schema.main()
        assert exit_code == 0
        assert "schema matches the XSD files" in capsys.readouterr().out

    def test_main_fails_on_mismatch(self, tmp_path, monkeypatch):
        zip_path = tmp_path / "doc.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            for entity in Einheiten:
                content = build_xsd(entity)
                if entity.name == "Katalogwerte":
                    content = content.replace('name="Wert"', 'name="WertX"')
                archive.writestr(f"doc/xsd/{entity.name}.xsd", content)
        monkeypatch.setattr(sys, "argv", ["validate_schema.py", "--zip", str(zip_path)])
        assert validate_schema.main() == 1

    def test_download_failure_exits_cleanly(self, tmp_path, monkeypatch):
        import urllib.error

        def failing_urlopen(url, timeout):
            raise urllib.error.URLError("no network")

        monkeypatch.setattr(validate_schema.urllib.request, "urlopen", failing_urlopen)
        monkeypatch.setattr(sys, "argv", ["validate_schema.py"])
        with pytest.raises(SystemExit) as excinfo:
            validate_schema.main()
        assert excinfo.value.code == 2

    def test_malformed_xsd_is_reported_not_fatal(self, tmp_path, monkeypatch):
        zip_path = tmp_path / "doc.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            for entity in Einheiten:
                content = build_xsd(entity)
                if entity.name == "Katalogwerte":
                    content = "this is not xml"
                archive.writestr(f"doc/xsd/{entity.name}.xsd", content)
        monkeypatch.setattr(sys, "argv", ["validate_schema.py", "--zip", str(zip_path)])
        assert validate_schema.main() == 1
