#!/usr/bin/env python3
"""Validate the import schema (db/entities.py) against the official XSD files.

The XSD files shipped in the Bundesnetzagentur documentation archive describe
the structure of the XML files of the MaStR Gesamtdatenexport. This script
downloads the archive, extracts the XSD files and checks every entity of
db/entities.py against its corresponding XSD file:

- table name (Einheiten member) vs. XSD root element
- record tag (entity class name) vs. XSD record element
- enum fields without a counterpart in the XSD (silently always NULL on import)
- type mismatches between XSD type and column type
- NOT NULL columns for optional XSD fields (import crashes on missing values)
- missing "_nv" companion columns for imported fields
- XSD fields that are not imported at all (informational)

Exit code is 1 if at least one error was found, 0 otherwise.
"""
import argparse
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from db.entities import Einheiten, Type

XSD_ZIP_URL = (
    "https://www.marktstammdatenregister.de/MaStRHilfe/files/gesamtdatenexport/"
    "Dokumentation%20MaStR%20Gesamtdatenexport.zip"
)
XSD_ZIP_TIMEOUT_S = 60

XS = "{http://www.w3.org/2001/XMLSchema}"

# columns that only exist in the database (added by the enrichment step)
# and therefore have no counterpart in the XSD files
DB_ONLY_COLUMNS = {"UTM_zone", "UTM_ost", "UTM_nord"}

XSD_TYPE_MAP = {
    "xs:string": Type.TEXT,
    "xs:dateTime": Type.TIMESTAMP,
    "xs:date": Type.DATE,
    "xs:boolean": Type.BOOLEAN,
    "xs:decimal": Type.NUMERIC,
    "xs:float": Type.NUMERIC,
    "xs:double": Type.NUMERIC,
    "xs:byte": Type.INT,
    "xs:short": Type.INT,
    "xs:int": Type.INT,
    "xs:long": Type.INT,
    "xs:unsignedByte": Type.INT,
}

# column type pairs that do not match exactly but are converted losslessly
# on import (date/dateTime via fromisoformat; the dump encodes booleans as
# xs:byte with 0/1 enumeration values)
BENIGN_TYPE_MISMATCHES = {
    frozenset((Type.DATE, Type.TIMESTAMP)),
    frozenset((Type.INT, Type.BOOLEAN)),
}


def resolve_field_type(element: ET.Element) -> Type | str | None:
    """Resolve the effective type of an XSD element to a db.entities.Type.

    Elements either carry a "type" attribute or define an inline simpleType
    with a restriction. Restrictions based on xs:byte with the enumeration
    values 0/1 are the X representation of a boolean flag in the dump.
    Returns "COMPOSITE" for elements with nested complex types and None for
    unknown types.
    """
    if element.find(f"{XS}complexType") is not None:
        return "COMPOSITE"

    type_attribute = element.get("type")
    if type_attribute is not None:
        return XSD_TYPE_MAP.get(type_attribute, type_attribute)

    if element.find(f"{XS}simpleType/{XS}list") is not None:
        # a whitespace separated list of values - stored as raw text
        return Type.TEXT

    restriction = element.find(f"{XS}simpleType/{XS}restriction")
    if restriction is None:
        return None
    base = restriction.get("base")
    if base == "xs:byte":
        values = {e.get("value") for e in restriction.findall(f"{XS}enumeration")}
        if values and values <= {"0", "1"}:
            return Type.BOOLEAN
    return XSD_TYPE_MAP.get(base, base)


def download_xsd_zip(target: Path) -> None:
    """Download the documentation archive from the Bundesnetzagentur."""
    print(f"downloading {XSD_ZIP_URL}")
    try:
        with urllib.request.urlopen(XSD_ZIP_URL, timeout=XSD_ZIP_TIMEOUT_S) as response:
            target.write_bytes(response.read())
    except (urllib.error.URLError, OSError) as error:
        print(f"ERROR: could not download the documentation archive: {error}", file=sys.stderr)
        sys.exit(2)


def extract_xsd_files(zip_path: Path, target_dir: Path) -> set[str]:
    """Extract all XSD files from the archive into target_dir (flat)."""
    extracted = set()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            if not member.endswith(".xsd"):
                continue
            name = Path(member).name
            with archive.open(member) as source, open(target_dir / name, "wb") as sink:
                sink.write(source.read())
            extracted.add(name)
    return extracted


def parse_xsd(path: Path) -> tuple[str, str, dict[str, dict[str, object]]]:
    """Parse an XSD file.

    Returns (root element name, record element name, fields) where fields maps
    the field name to {"type": db.entities.Type or "COMPOSITE", "required": bool}.
    """
    root = ET.parse(path).getroot()
    top_element = root.find(f"{XS}element")
    record_element = top_element.find(f"{XS}complexType/{XS}sequence/{XS}element")
    if record_element is None:
        raise ValueError(f"unexpected XSD structure in {path}")
    complex_type = record_element.find(f"{XS}complexType")
    container = complex_type.find(f"{XS}sequence")
    if container is None:
        container = complex_type.find(f"{XS}choice")

    fields = {}
    for element in container:
        if element.tag != f"{XS}element":
            continue
        fields[element.get("name")] = {
            "type": resolve_field_type(element),
            "required": element.get("minOccurs") != "0",
        }
    return top_element.get("name"), record_element.get("name"), fields


def validate_entity(entity: Einheiten, xsd_path: Path) -> tuple[list[str], list[str]]:
    """Validate one entity against its XSD file. Returns (errors, warnings)."""
    errors, warnings = [], []
    table_tag, record_tag, xsd_fields = parse_xsd(xsd_path)
    enum_names = [column.name for column in entity.value]

    if table_tag != entity.name:
        errors.append(f"XSD root element '{table_tag}' != table name '{entity.name}'")
    if record_tag != entity.value.__name__:
        errors.append(f"XSD record element '{record_tag}' != entity class '{entity.value.__name__}'")

    for column in entity.value:
        if column.name in DB_ONLY_COLUMNS:
            continue
        field = xsd_fields.get(column.name)
        if field is None:
            errors.append(f"'{column.name}' has no counterpart in the XSD - column will always be NULL")
            continue

        if field["type"] == "COMPOSITE":
            errors.append(f"'{column.name}' is a composite XSD element but mapped to a scalar column")
        elif not isinstance(field["type"], Type):
            warnings.append(f"'{column.name}': unknown XSD type '{field['type']}' - check manually")
        else:
            xsd_type = field["type"]
            column_type = column.value.type
            if xsd_type != column_type:
                message = f"'{column.name}': XSD type {xsd_type.name} != column type {column_type.name}"
                if frozenset((xsd_type, column_type)) in BENIGN_TYPE_MISMATCHES:
                    warnings.append(message + " (converted losslessly)")
                else:
                    errors.append(message)

        if column.value.not_null and not field["required"]:
            errors.append(f"'{column.name}' is NOT NULL but optional in the XSD (minOccurs=0)")

    for field_name in xsd_fields:
        if field_name in enum_names:
            continue
        if field_name.endswith("_nv") and field_name[:-3] in enum_names:
            warnings.append(f"'{field_name}' not imported - '_nv' companion of an imported field")
        else:
            warnings.append(f"'{field_name}' not imported")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, help="use a local documentation zip instead of downloading")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        zip_path = args.zip if args.zip else temp_path / "mastr-documentation.zip"
        if args.zip is None:
            download_xsd_zip(zip_path)
        xsd_dir = temp_path / "xsd"
        xsd_dir.mkdir()
        extracted = extract_xsd_files(zip_path, xsd_dir)

        total_errors, total_warnings = 0, 0
        for entity in Einheiten:
            print(f"=== {entity.name} ===")
            xsd_path = xsd_dir / f"{entity.name}.xsd"
            if xsd_path.name not in extracted:
                print("  ERROR: no XSD file found for this entity\n")
                total_errors += 1
                continue
            errors, warnings = [], []
            try:
                errors, warnings = validate_entity(entity, xsd_path)
            except (ET.ParseError, ValueError) as error:
                errors = [f"could not parse XSD file: {error}"]
            for error in errors:
                print(f"  ERROR: {error}")
            for warning in warnings:
                print(f"  warning: {warning}")
            if not errors and not warnings:
                print("  OK")
            print()
            total_errors += len(errors)
            total_warnings += len(warnings)

        imported = {f"{entity.name}.xsd" for entity in Einheiten}
        not_imported = sorted(extracted - imported)
        if not_imported:
            print(f"XSD files without imported entity ({len(not_imported)}):")
            print("  " + ", ".join(name[:-4] for name in not_imported) + "\n")

    print(f"summary: {total_errors} error(s), {total_warnings} warning(s)")
    if total_errors:
        print("schema does not match the XSD files")
        return 1
    print("schema matches the XSD files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
