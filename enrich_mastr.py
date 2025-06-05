#!/usr/bin/env python3
import argparse
import time
import traceback
from pathlib import Path

from db.db_utils import get_db_connection
from db.entities import *
from enricher.cache import Cache
from multiprocessing import Pool

from enricher.enricher import CoordinateConverter, UTM

from loguru import logger


def timer(func):
    def helper_function(*args, **kwargs):
        logger.info(f"start {func.__name__}")
        start = time.perf_counter()
        func(*args, **kwargs)
        logger.info(f"{func.__name__} took {time.perf_counter() - start:.3f} s")

    return helper_function


class MastrCoordinateConverter:
    """Helper class for multiprocessing of geo to utm coordinate conversions."""

    def __init__(self):
        self.converter = CoordinateConverter()

    def geo_to_utm(self, lat, lon) -> UTM:
        return self.converter.geo_to_utm(lat, lon)


class MastrEnricher:

    def __init__(self, connection, cache_path: Path, concurrency: int):
        self.conn = connection
        self._concurrency = concurrency
        self.converter = CoordinateConverter()
        self._cache_path = cache_path
        self._cache_file = cache_path / Path(f"enricher_cache.pkl")
        self._cache = Cache.load(self._cache_file)
        self._process_pool = Pool(processes=concurrency)

    @timer
    def enrich_utm_coordinates(self, table):

        processed_rows = 0
        cursor = self.conn.cursor()

        coord_converter = MastrCoordinateConverter()

        try:
            start = time.perf_counter()
            cursor.execute(
                f"""
                    SELECT einheitmastrnummer, Breitengrad, Laengengrad 
                    FROM {table} 
                    WHERE Breitengrad IS NOT NULL 
                    AND Laengengrad IS NOT NULL
                """
            )

            rows = cursor.fetchall()
            #print(f"Fetched {len(rows)} rows in table {table} in {time.perf_counter() - start:.3f} s")

            start = time.perf_counter()
            # Process in batches for better performance
            batch_size = 1000
            for i in range(0, len(rows), batch_size):  # type: ignore
                batch = rows[i : i + batch_size]
                updates = []

                # separate pre-computed UTM coordinates from those that need to be computed
                need_calculation = {}
                for row in batch:
                    row_id, lat, lon = row

                    if (lat, lon) in self._cache:
                        utm = self._cache.get((lat, lon))
                        # already cached utm coordinates will directly be inserted into the database
                        updates.append((utm.zone, utm.easting, utm.northing, row_id))
                    else:
                        # not cached coordinates are pushed into a job queue and will be computed and cached for future use
                        need_calculation[row_id] = (lat, lon)

                # calculate the non-cached coordinates in separate processes
                processes = {}
                for row_id in need_calculation.keys():
                    processes[row_id] = self._process_pool.apply_async(
                        coord_converter.geo_to_utm,
                        need_calculation[row_id],
                    )
                # get calculated utm coordinates and prepare them for db write and store to cache
                for row_id in need_calculation.keys():
                    utm = processes[row_id].get()
                    updates.append((utm.zone, utm.easting, utm.northing, row_id))
                    self._cache.set(need_calculation[row_id], utm)

                # Update the database with UTM coordinates
                if updates:
                    cursor.executemany(
                        f"""
                            UPDATE {table}
                            SET UTM_zone = %s, UTM_ost = %s, UTM_nord = %s
                            WHERE einheitmastrnummer = %s
                        """,
                        updates,
                    )

                    processed_rows += len(updates)
            #print(f"Processed {processed_rows} rows in table {table} in {time.perf_counter() - start:.3f} s")

            self.conn.commit()
            #print(f"Processed {processed_rows} rows in table {table}")

        except Exception as e:
            self.conn.rollback()
            logger.exception(f"Error processing table {table}")

        self._cache.store(self._cache_file)
        cursor.close()
        return processed_rows

    def cleanup(self) -> None:
        self._process_pool.close()


@timer
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Some compute intense calculations are calculated with max concurrency processes",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="Path to the cache directory for the enricher caches",
    )
    args = parser.parse_args()

    connection = get_db_connection()
    enricher = MastrEnricher(connection, args.cache_dir, args.concurrency)
    logger.info(f"Enriching UTM coordinates for Mastr tables in {args.concurrency} parallel processes")
    for mastr_einheit in EinheitenGeoEnrichment:
        logger.info(f"--- {mastr_einheit.name} ---")
        enricher.enrich_utm_coordinates(mastr_einheit.name)
    enricher.cleanup()


if __name__ == "__main__":
    main()
