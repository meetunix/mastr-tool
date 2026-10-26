"""Tests for the enricher: coordinate conversion with known values and the
cache roundtrip. No fixture files are needed - coordinates are well-known
constants and the cache is exercised with temporary files.
"""

from enricher.cache import Cache
from enricher.enricher import CoordinateConverter


class TestGeoToUtm:
    def test_berlin_is_in_zone_33(self):
        utm = CoordinateConverter().geo_to_utm(52.516275, 13.377704)
        assert utm.zone == 33
        assert 380000 < utm.easting < 400000
        assert 5_700_000 < utm.northing < 5_950_000

    def test_zone_boundaries(self):
        converter = CoordinateConverter()
        assert converter.geo_to_utm(50.0, 6.0).zone == 32
        assert converter.geo_to_utm(50.0, 12.0).zone == 33
        assert converter.geo_to_utm(50.0, 18.0).zone == 34

    def test_easting_northing_are_floats(self):
        utm = CoordinateConverter().geo_to_utm(52.516275, 13.377704)
        assert isinstance(utm.easting, float)
        assert isinstance(utm.northing, float)


class TestGeoToGaussKrueger:
    def test_meridian_strip_for_mid_germany(self):
        gk = CoordinateConverter().geo_to_gauss_kruger(50.0, 8.5)
        assert gk.strip == 3
        assert 3_400_000 < gk.easting < 3_600_000
        assert 5_000_000 < gk.northing < 6_000_000


class TestCache:
    def test_set_get_contains_len(self):
        cache = Cache()
        assert cache.set("a", 1) is True
        assert cache.get("a") == 1
        assert "a" in cache
        assert len(cache) == 1
        assert cache.get("missing", "default") == "default"

    def test_delete_and_clear(self):
        cache = Cache()
        cache.set("a", 1)
        assert cache.delete("a") is True
        assert cache.delete("a") is False
        cache.set("b", 2)
        cache.clear()
        assert len(cache) == 0

    def test_max_size_rejects_new_keys(self):
        cache = Cache(max_size=2)
        assert cache.set("a", 1) is True
        assert cache.set("b", 2) is True
        assert cache.set("c", 3) is False  # full and new
        assert cache.set("a", 10) is True  # existing key still allowed

    def test_store_load_roundtrip(self, tmp_path):
        cache = Cache()
        cache.set((52.5, 13.4), "utm-33")
        cache_file = tmp_path / "enricher_cache.pkl"
        cache.store(cache_file)

        loaded = Cache.load(cache_file)
        assert loaded.get((52.5, 13.4)) == "utm-33"

    def test_load_missing_file_returns_empty_cache(self, tmp_path):
        loaded = Cache.load(tmp_path / "does-not-exist.pkl")
        assert len(loaded) == 0

    def test_load_empty_file_returns_empty_cache(self, tmp_path):
        cache_file = tmp_path / "empty.pkl"
        cache_file.write_bytes(b"")
        loaded = Cache.load(cache_file)
        assert len(loaded) == 0

    def test_load_corrupted_file_returns_empty_cache(self, tmp_path):
        cache_file = tmp_path / "corrupt.pkl"
        cache_file.write_bytes(b"this is not a pickle")
        loaded = Cache.load(cache_file)
        assert len(loaded) == 0
