#!/usr/bin/env python3
import argparse
import time
from dataclasses import dataclass
from multiprocessing import Pool
from typing import Optional

from db.db_utils import get_db_connection
from db.entities import *
from enum import Enum
from pathlib import Path

import pandas as pd
import polars as pl


def timer(func):
    def helper_function(*args, **kwargs):
        print(f"start {func.__name__}")
        start = time.perf_counter()
        func(*args, **kwargs)
        print(f"{func.__name__} took {time.perf_counter() - start:.3f} s")

    return helper_function


class MastrEnricher:

    def __init__(self, connection, concurrency: int):
        self.conn = connection
        self.concurrency = concurrency


@timer
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=4, help="Number of parallel export processes (default: 4)")
    args = parser.parse_args()

    connection = get_db_connection()
    enricher = MastrEnricher(connection, args.concurrency)
    for mastr_einheit in Einheiten:
        print(f"--- {mastr_einheit.name} ---")


if __name__ == "__main__":
    main()
