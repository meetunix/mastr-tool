"""Tests for check_tileserver.py: the MVT decoder used by the smoke test.

The decoder is the only non-trivial part of the script. It is checked against
tiles built by hand, so a broken decoder cannot silently report empty tiles.
"""

import struct

import pytest

from check_tileserver import FALLBACK_LAYERS, decode_mvt, deg2tile, expected_layers, percentile


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def field(number: int, wire: int, payload: bytes) -> bytes:
    key = varint((number << 3) | wire)
    return key + varint(len(payload)) + payload if wire == 2 else key + payload


def string_value(text: str) -> bytes:
    return field(1, 2, text.encode())


def double_value(number: float) -> bytes:
    return field(3, 1, struct.pack("<d", number))


def int_value(number: int) -> bytes:
    return field(4, 0, varint(number))


def feature(tags: list[int], geometry: list[int], geom_type: int = 1) -> bytes:
    payload = field(2, 2, b"".join(varint(tag) for tag in tags))
    payload += field(3, 0, varint(geom_type))
    payload += field(4, 2, b"".join(varint(value) for value in geometry))
    return payload


def layer(name: str, keys: list[str], values: list[bytes], features: list[bytes], extent: int = 4096) -> bytes:
    payload = field(1, 2, name.encode())
    for item in features:
        payload += field(2, 2, item)
    for key in keys:
        payload += field(3, 2, key.encode())
    for value in values:
        payload += field(4, 2, value)
    payload += field(5, 0, varint(extent))
    return payload


def tile(layer_payload: bytes) -> bytes:
    return field(3, 2, layer_payload)


def test_decodes_layer_features_and_properties():
    keys = ["mastr_nr", "kw", "status"]
    values = [
        string_value("SEE1"),
        double_value(3000.0),
        int_value(35),
        string_value("SEE2"),
        double_value(2500.0),
    ]
    features = [
        feature([0, 0, 1, 1, 2, 2], [9, 200, 400]),
        feature([0, 3, 1, 4, 2, 2], [9, 300, 500]),
    ]

    layers = decode_mvt(tile(layer("wind", keys, values, features)))

    assert len(layers) == 1
    assert layers[0]["name"] == "wind"
    assert layers[0]["extent"] == 4096
    assert [item["properties"] for item in layers[0]["features"]] == [
        {"mastr_nr": "SEE1", "kw": 3000.0, "status": 35},
        {"mastr_nr": "SEE2", "kw": 2500.0, "status": 35},
    ]


def test_empty_tile_has_no_layers():
    assert decode_mvt(b"") == []


def test_boolean_and_negative_values():
    keys = ["hochspannung", "delta"]
    values = [field(7, 0, varint(1)), field(6, 0, varint(3))]  # bool true, sint64 -2
    data = tile(layer("wind", keys, values, [feature([0, 0, 1, 1], [9, 0, 0])]))

    assert decode_mvt(data)[0]["features"][0]["properties"] == {"hochspannung": True, "delta": -2}


def test_deg2tile_known_coordinates():
    assert deg2tile(0.0, 0.0, 0) == (0, 0)
    assert deg2tile(0.0, 0.0, 1) == (1, 1)
    assert deg2tile(13.405, 52.52, 10) == (550, 335)  # Berlin


def test_percentile_uses_nearest_rank():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(values, 0.5) == 3.0
    assert percentile(values, 0.95) == 5.0
    assert percentile([], 0.5) == 0.0


def test_deg2tile_clamps_to_the_world():
    """Latitudes beyond the web mercator limit (~85.05) must not produce a
    negative y - that would build an invalid tile URL."""
    assert deg2tile(10.0, 90.0, 10) == (540, 0)
    assert deg2tile(10.0, 89.0, 10) == (540, 0)
    assert deg2tile(180.0, 0.0, 4) == (15, 8)
    assert deg2tile(-180.0, 0.0, 4) == (0, 8)


def test_truncated_value_raises_struct_error():
    """A truncated fixed64 is not silently accepted: the callers catch
    struct.error and report the tile as broken."""
    truncated = bytes([0x1A, 0x05, 0x22, 0x03, 0x19, 0x00, 0x00])
    with pytest.raises(struct.error):
        decode_mvt(truncated)


def test_non_packed_tags_are_decoded():
    """The spec says packed, but a repeated varint is valid protobuf too."""
    feature_payload = field(2, 0, varint(0)) + field(2, 0, varint(0)) + field(3, 0, varint(1))
    data = tile(layer("wind", ["mastr_nr"], [string_value("SEE1")], [feature_payload]))

    assert decode_mvt(data)[0]["features"][0]["properties"] == {"mastr_nr": "SEE1"}


def test_fallback_layers_match_the_sql():
    """FALLBACK_LAYERS is only used when db/tiles.sql is missing, but it must
    not drift from the real layer list."""
    assert sorted(FALLBACK_LAYERS) == sorted(expected_layers())
