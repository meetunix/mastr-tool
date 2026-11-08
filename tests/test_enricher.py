"""Tests for the enricher: coordinate conversion with known values and the
batch conversion used by the import. No fixture files are needed -
coordinates are well-known constants.
"""

import random
from decimal import Decimal

import pyproj

from enricher.enricher import UTM, CoordinateConverter


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


class TestGeoToUtmBatch:
    def reference(self, lat, lon) -> UTM:
        """The original per-point conversion (new CRS and transformer per call)."""
        zone = int((lon + 180) / 6) + 1
        utm_crs = pyproj.CRS(f"+proj=utm +zone={zone} +datum=WGS84 +units=m +no_defs")
        transformer = pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(4326), utm_crs, always_xy=True)
        easting, northing = transformer.transform(lon, lat)
        return UTM(zone=zone, easting=easting, northing=northing)

    def test_batch_is_identical_to_per_point_conversion(self):
        rnd = random.Random(1)
        points = [(Decimal(f"{rnd.uniform(47, 55):.7f}"), Decimal(f"{rnd.uniform(5, 16):.7f}")) for _ in range(500)]
        # zone boundaries
        points += [(Decimal("50"), Decimal(lon)) for lon in ("6", "5.9999999", "12.0000000", "11.9999999", "18")]
        result = CoordinateConverter().geo_to_utm_batch([p[0] for p in points], [p[1] for p in points])
        assert result == [self.reference(lat, lon) for lat, lon in points]

    def test_empty_batch(self):
        assert CoordinateConverter().geo_to_utm_batch([], []) == []

    def test_one_transformer_per_zone(self):
        converter = CoordinateConverter()
        converter.geo_to_utm_batch([50.0, 51.0, 52.0], [7.0, 8.0, 13.0])
        converter.geo_to_utm(53.0, 9.0)
        assert sorted(converter._utm_transformers) == [32, 33]
