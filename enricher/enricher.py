from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

import pyproj


@dataclass
class UTM:
    zone: int
    easting: float
    northing: float


@dataclass
class GaussKrueger:
    strip: int
    easting: float
    northing: float


class CoordinateConverter:

    def __init__(self):
        # Define common coordinate systems
        self.wgs84 = pyproj.CRS.from_epsg(4326)  # Standard WGS84 (lat/lon)
        # building a transformer costs ~200 µs, the transformation itself
        # less than 1 µs per point - one transformer per zone is reused
        self._utm_transformers: dict[int, pyproj.Transformer] = {}

    @staticmethod
    def utm_zone(lon) -> int:
        """Determine the UTM zone based on longitude"""
        return int((lon + 180) / 6) + 1

    def _utm_transformer(self, zone_number: int) -> pyproj.Transformer:
        transformer = self._utm_transformers.get(zone_number)
        if transformer is None:
            utm_crs = pyproj.CRS(f"+proj=utm +zone={zone_number} +datum=WGS84 +units=m +no_defs")
            transformer = pyproj.Transformer.from_crs(self.wgs84, utm_crs, always_xy=True)
            self._utm_transformers[zone_number] = transformer
        return transformer

    def geo_to_utm(self, lat, lon) -> UTM:
        """Convert latitude/longitude to UTM coordinates"""
        return self.geo_to_utm_batch([lat], [lon])[0]

    def geo_to_utm_batch(self, lats: Sequence, lons: Sequence) -> list[UTM]:
        """Convert many latitude/longitude pairs to UTM coordinates: one
        vectorised transformation per UTM zone instead of one call per point."""
        indices_by_zone: dict[int, list[int]] = defaultdict(list)
        for i, lon in enumerate(lons):
            indices_by_zone[self.utm_zone(lon)].append(i)

        result: list[UTM | None] = [None] * len(lons)
        for zone_number, indices in indices_by_zone.items():
            eastings, northings = self._utm_transformer(zone_number).transform(
                [float(lons[i]) for i in indices], [float(lats[i]) for i in indices]
            )
            for i, easting, northing in zip(indices, eastings, northings):
                result[i] = UTM(zone=zone_number, easting=easting, northing=northing)
        return result

    def geo_to_gauss_kruger(self, lat, lon) -> GaussKrueger:
        """Convert latitude/longitude to Gauss-Krüger (Potsdam) coordinates"""
        # Determine the meridian strip number (3° wide strips in Germany)
        meridian_strip = int((lon + 1.5) / 3)
        central_meridian = meridian_strip * 3

        # Create Gauss-Krüger projection with Potsdam datum, but without explicit transformation parameters
        gk_crs = pyproj.CRS(
            f"+proj=tmerc +lat_0=0 +lon_0={central_meridian} +k=1 +x_0={meridian_strip * 1000000 + 500000} +y_0=0 +ellps=bessel +units=m"
        )

        # Create transformer
        transformer = pyproj.Transformer.from_crs(self.wgs84, gk_crs, always_xy=True)

        # Transform coordinates
        r_value, h_value = transformer.transform(lon, lat)

        return GaussKrueger(strip=meridian_strip, easting=r_value, northing=h_value)


if __name__ == "__main__":
    pass
