from dataclasses import dataclass

import pyproj

@dataclass
class UTM:
    zone: str
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

    def geo_to_utm(self, lat, lon):
        """Convert latitude/longitude to UTM coordinates"""
        # Determine the UTM zone based on longitude
        zone_number = int((lon + 180) / 6) + 1

        # Create the appropriate UTM projection
        utm_crs = pyproj.CRS(f"+proj=utm +zone={zone_number} +datum=WGS84 +units=m +no_defs")

        # Create transformer
        transformer = pyproj.Transformer.from_crs(self.wgs84, utm_crs, always_xy=True)

        # Transform coordinates
        easting, northing = transformer.transform(lon, lat)

        return {
            'zone': zone_number,
            'easting': easting,
            'northing': northing
        }

    def geo_to_gauss_kruger(self, lat, lon):
        """Convert latitude/longitude to Gauss-Krüger (Potsdam) coordinates"""
        # Determine the meridian strip number (3° wide strips in Germany)
        meridian_strip = int((lon + 1.5) / 3)
        central_meridian = meridian_strip * 3

        # Create Gauss-Krüger projection with Potsdam datum, but without explicit transformation parameters
        gk_crs = pyproj.CRS(f"+proj=tmerc +lat_0=0 +lon_0={central_meridian} +k=1 +x_0={meridian_strip * 1000000 + 500000} +y_0=0 +ellps=bessel +units=m")

        # Create transformer
        transformer = pyproj.Transformer.from_crs(self.wgs84, gk_crs, always_xy=True)

        # Transform coordinates
        r_value, h_value = transformer.transform(lon, lat)

        return {
            'meridian_strip': meridian_strip,
            'r_value': r_value,
            'h_value': h_value
        }

if __name__ == '__main__':
    lat, lon = 52.5200, 13.4050
    cc = CoordinateConverter()
    utm = cc.geo_to_utm(lat, lon)
    gk = cc.geo_to_gauss_kruger(lat, lon)
    print(f"UTM: {utm}")
    print(f"GK: {gk}")
