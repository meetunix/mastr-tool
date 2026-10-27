"""Invariants of the schema definitions in db/entities.py.

These tests need no fixtures: everything is checked against the enum
definitions themselves. They guard the couplings that broke in the past
(e.g. the "EinheiteBiomasse" class-name typo and enum-value aliasing).
"""

from db.entities import (
    Column,
    Einheiten,
    EinheitenGeoEnrichment,
    Indices,
    SelectUDFs,
    Type,
)

ALL_ENTITIES = list(Einheiten)


def test_all_members_are_columns():
    for entity in ALL_ENTITIES:
        for column in entity.value:
            assert isinstance(column.value, Column), f"{entity.name}.{column.name}"


def test_column_attributes_are_well_formed():
    for entity in ALL_ENTITIES:
        for column in entity.value:
            definition = column.value
            assert isinstance(definition.type, Type)
            assert isinstance(definition.not_null, bool)
            assert isinstance(definition.primary_key, bool)
            assert definition.udf is None or isinstance(definition.udf, SelectUDFs)


def test_exactly_one_not_null_primary_key_per_table():
    for entity in ALL_ENTITIES:
        primary_keys = [c for c in entity.value if c.value.primary_key]
        assert len(primary_keys) == 1, f"{entity.name} has {len(primary_keys)} primary keys"
        assert primary_keys[0].value.not_null, f"{entity.name} primary key is nullable"


def test_no_enum_value_aliasing():
    """Enum members with equal dataclass values must not collapse into aliases.

    Regression test: with a plain frozen dataclass, every ``Column(Type.TEXT)``
    compared equal and silently turned the other members into aliases.
    """
    for entity in ALL_ENTITIES:
        for column in entity.value:
            assert entity.value[column.name] is column, f"{entity.name}.{column.name} is an alias"


def test_einheiten_member_to_class_mapping():
    """The Einheiten member name is the XML file/table name, the class name is
    the XML record tag - both couplings are load-bearing for the import."""
    expected = {
        "EinheitenWasser": "EinheitWasser",
        "EinheitenWind": "EinheitWind",
        "EinheitenSolar": "EinheitSolar",
        "EinheitenBiomasse": "EinheitBiomasse",
        "AnlagenEegWind": "AnlageEegWind",
        "AnlagenEegSolar": "AnlageEegSolar",
        "AnlagenEegBiomasse": "AnlageEegBiomasse",
        "AnlagenEegWasser": "AnlageEegWasser",
        "AnlagenEegSpeicher": "AnlageEegSpeicher",
        "AnlagenEegGeothermieGrubengasDruckentspannung": "AnlageEegGeothermieGrubengasDruckentspannung",
        "Marktakteure": "Marktakteur",
        "Katalogwerte": "Katalogwert",
        "Katalogkategorien": "Katalogkategorie",
    }
    assert {e.name for e in ALL_ENTITIES} == set(expected)
    for member_name, class_name in expected.items():
        assert Einheiten[member_name].value.__name__ == class_name


def test_indices_reference_existing_columns():
    for index in Indices:
        entity_class = Einheiten[index.name].value
        assert index.value in entity_class, f"index {index.name} references a missing column"


def test_nv_fields_have_their_main_field():
    for entity in ALL_ENTITIES:
        names = {c.name for c in entity.value}
        for name in names:
            if name.endswith("_nv"):
                assert name[:-3] in names, f"{entity.name}.{name} has no main field"


def test_geo_enrichment_entities_are_imported_entities():
    for entity in EinheitenGeoEnrichment:
        assert entity.name in Einheiten.__members__


def test_udf_template_placeholders():
    for udf in SelectUDFs:
        assert "{{field}}" in udf.value, f"{udf.name} template has no field placeholder"
