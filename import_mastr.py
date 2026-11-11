#!/usr/bin/env python3
import argparse
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from multiprocessing import get_context
from pathlib import Path
from typing import Dict, List, Set

import psycopg2

from db.db_utils import DBElementWriter, get_db_connection
from db.entities import *
from utils.mastr_logger import get_mastr_logger, LogLevel

logger = get_mastr_logger(LogLevel.INFO)

FILE_PATTERN = re.compile(r"^(.*)_([0-9]{1,3}).xml$")

# read-only role Martin connects with (see db/tiles.sql)
TILES_DB_USER = "tiles_reader"
TILES_DB_PASSWORD_DEFAULT = "tiles"


def get_files(files: Set[Path]) -> Dict[str, List[Path]]:
    """Create a dict with a basic identifier (key) and the ordered list of source files."""
    split_files = {f for f in files if re.match(FILE_PATTERN, f.name)}
    non_split_files = files.difference(split_files)
    result = {}
    for file in split_files:
        match = re.search(FILE_PATTERN, file.name)
        file_id = match.group(1)
        if file_id in result:
            result[file_id].append(file)
        else:
            result[file_id] = [file]
    # sort split files to correct input order
    result = {k: sorted(v, key=lambda x: (len(x.name), x.name)) for (k, v) in result.items()}
    # add non split files to result
    result.update({f.name.split(".xml")[0]: [f] for f in non_split_files})
    return result


def parse_and_write_xml(file: Path, entity: Einheiten, silent: bool) -> None:
    if not silent:
        logger.info(f"import file {file.name}")
    db_writer = DBElementWriter(entity, get_db_connection())
    root = None
    for event, elem in ET.iterparse(file, events=("start", "end")):
        if event == "start":
            if root is None:
                root = elem
            continue
        if elem.tag == entity.value.__name__:
            db_writer.write(elem)
            elem.clear()  # Free memory held by this element
            root.clear()  # Drop the processed record from the growing tree
    db_writer.cleanup()


def create_schema(path_schema: Path) -> None:
    """Write the table definitions. Primary keys and indices are created by
    create_constraints after the data is loaded."""
    s = ""
    curr_column = None
    try:
        for table in Einheiten:
            # unlogged: the tables are rebuilt from the dump on every run, so
            # writing the whole import to the WAL is not needed (after a crash
            # of the database server the tables are empty until the next import)
            s += f"create unlogged table if not exists {table.name} (\n"
            first_col = True
            for col in table.value:
                curr_column = col
                # pad the column name to 56 chars and always append a space,
                # so names longer than the padding stay separated from the type
                s += f"{',' if not first_col else ''}\n{col.name:56s} "  # column
                s += f"{col.value.type.value[1]:16s}"  # data type
                s += f"{'NOT NULL' if col.value.not_null else ''}"  # NULLABLE
                first_col = False
            # no autovacuum during the import: it would scan the tables while
            # they are loaded, and building the primary keys and indices
            # cancels it (logged as "ERROR: canceling autovacuum task").
            # enable_autovacuum turns it on again after vacuum_analyze.
            s += "\n) WITH (autovacuum_enabled = false, toast.autovacuum_enabled = false);\n\n"
    except Exception as e:
        logger.exception("Exception while creating schema")
        sys.stderr.write(f"\nERROR: {e} - {curr_column}\n")
        sys.exit(1)

    path_schema.write_text(s)


def create_constraints(path_constraints: Path) -> None:
    """Write the primary keys and indices. They are created after the data is
    loaded: building a B-tree once from the full table is much cheaper than
    updating it row by row during the import."""
    s = ""
    for table in Einheiten:
        primary_key = [col.name for col in table.value if col.value.primary_key]
        if primary_key:
            # skipped if the table already has a primary key (import into
            # tables created with --schema)
            s += (
                f"DO $$ BEGIN\n"
                f"    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid = '{table.name}'::regclass AND contype = 'p') THEN\n"
                f"        ALTER TABLE {table.name} ADD PRIMARY KEY ({', '.join(primary_key)});\n"
                f"    END IF;\n"
                f"END $$;\n\n"
            )
    for index in Indices:
        # plain index on the raw column: the state export filters by the
        # catalog ID ("WHERE <table>.bundesland = <id>"). An expression
        # index on katalog(<column>) is not possible in PostgreSQL -
        # functions that access tables cannot run during CREATE INDEX.
        s += (
            f"CREATE INDEX IF NOT EXISTS {index.name}_{index.value.name}_idx "
            f"ON {index.name}({index.value.name});\n\n"
        )
    for index in MapIndices:
        # partial covering index for the maps page of mastr-app (see MapIndices)
        columns = [*MAP_INDEX_COLUMNS, *(column.name for column in index.value)]
        s += (
            f"CREATE INDEX IF NOT EXISTS {index.name}_map_idx ON {index.name}({MAP_INDEX_KEY}) "
            f"INCLUDE ({', '.join(columns)}) WHERE {MAP_INDEX_CONDITION};\n\n"
        )
    for table in GeomIndices:
        # GiST index on the point built from the coordinates for the tile
        # functions (db/tiles.sql): they filter with "&&" on exactly this
        # expression. The tile queries repeat the partial condition, otherwise
        # the planner cannot use the partial index.
        s += (
            f"CREATE INDEX IF NOT EXISTS {table.name}_geom_idx ON {table.name} "
            f"USING GIST ({GEOM_INDEX_EXPRESSION}) WHERE {MAP_INDEX_CONDITION};\n\n"
        )

    path_constraints.write_text(s)


def create_tiles_role() -> None:
    """Create the read-only role Martin connects with (idempotent).

    The role only gets USAGE on the tiles schema and EXECUTE on the tile
    functions (db/tiles.sql), it cannot read the unit tables. Without
    CREATEROLE - e.g. the managed role of a CloudNativePG cluster - an
    administrator has to create the role; the import continues without it.
    """
    password = os.environ.get("TILES_DB_PASSWORD", TILES_DB_PASSWORD_DEFAULT)
    conn = get_db_connection()
    try:
        with conn.cursor() as curr:
            curr.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (TILES_DB_USER,))
            exists = curr.fetchone() is not None
            # the password is set on every run: TILES_DB_PASSWORD is the single
            # source of truth for the connection of the tile server. The role
            # name is a constant, only the password is a parameter.
            statement = "ALTER ROLE" if exists else "CREATE ROLE"
            curr.execute(f"{statement} {TILES_DB_USER} WITH LOGIN PASSWORD %s", (password,))
        conn.commit()
        logger.info(f"role {TILES_DB_USER} for Martin is ready")
    except psycopg2.errors.InsufficientPrivilege:
        conn.rollback()
        logger.warning(
            f"cannot create role {TILES_DB_USER} (no CREATEROLE): create it manually, "
            f"otherwise Martin cannot read the tiles schema"
        )
    finally:
        conn.close()


def write_schema(path_schema: Path, path_udf: Path, path_tiles: Path) -> None:
    """Create the tables, the UDFs and the tile functions. The read-only role
    for Martin is created first: db/tiles.sql grants it access."""
    create_tiles_role()
    conn = get_db_connection()
    with conn.cursor() as curr:
        # the tables are created first: the SQL-language UDF katalog()
        # references the katalogwerte table, which must exist when the
        # function is created
        schema = path_schema.read_text() + "\n" + path_udf.read_text() + "\n" + path_tiles.read_text()
        curr.execute(schema)
        conn.commit()


def write_constraints(path_constraints: Path) -> None:
    conn = get_db_connection()
    with conn.cursor() as curr:
        # more memory than the default 64MB speeds up building the indices
        curr.execute("SET maintenance_work_mem = '256MB'")
        curr.execute(path_constraints.read_text())
        conn.commit()
    conn.close()


def refresh_tile_grid(path_grid: Path) -> None:
    """Rebuild the pre-aggregated grid the low zoom tiles are built from
    (db/grid.sql). Runs after the unit tables are loaded: the tile functions
    read the grid instead of scanning the unit tables."""
    conn = get_db_connection()
    with conn.cursor() as curr:
        curr.execute(path_grid.read_text())
        conn.commit()
    conn.close()


def vacuum_analyze() -> None:
    """Collect planner statistics and set the visibility map of the freshly
    loaded tables before they are exported."""
    conn = get_db_connection()
    # VACUUM cannot run inside a transaction block
    conn.autocommit = True
    with conn.cursor() as curr:
        for table in Einheiten:
            # PARALLEL 0: freshly loaded tables have no dead rows, and a
            # parallel vacuum reserves its memory in /dev/shm (64MB in
            # containers by default), which fails on Postgres up to 16
            curr.execute(f"VACUUM (ANALYZE, PARALLEL 0) {table.name}")
        curr.execute("VACUUM (ANALYZE, PARALLEL 0) tiles.grid")
    conn.close()


def enable_autovacuum() -> None:
    """Turn autovacuum on again (disabled by create_schema for the import)."""
    conn = get_db_connection()
    with conn.cursor() as curr:
        for table in Einheiten:
            curr.execute(f"ALTER TABLE {table.name} RESET (autovacuum_enabled, toast.autovacuum_enabled)")
        conn.commit()
    conn.close()


def delete_tables() -> None:
    drop_stmt = ""
    for table in Einheiten:
        drop_stmt += f"drop table if exists {table.name};\n"
    conn = get_db_connection()
    with conn.cursor() as curr:
        curr.execute(drop_stmt)
        conn.commit()


def main():
    path_udf = Path("db/udf.sql")
    path_tiles = Path("db/tiles.sql")
    path_grid = Path("db/grid.sql")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=4, help="Number of parallel import processes (default: 4)")
    parser.add_argument(
        "--schema", action="store_true", help=f"Just create and write the schema to the cache directory."
    )
    parser.add_argument("--silent", action="store_true", help=f"no output on stdout")
    parser.add_argument("--cleanup", action="store_true", help=f"delete tables first")
    parser.add_argument("MSTR_DIR", type=Path, help="The export directory from the Marktstammdatenregister")
    parser.add_argument("--cache-dir", type=Path, help="Path to the cache director", required=True)
    args = parser.parse_args()
    path_schema = args.cache_dir / Path("./auto-schema.sql")
    path_constraints = args.cache_dir / Path("./auto-schema-constraints.sql")

    if args.cleanup:
        delete_tables()

    create_schema(path_schema)
    create_constraints(path_constraints)

    if args.schema:
        write_schema(path_schema, path_udf, path_tiles)
        write_constraints(path_constraints)
        enable_autovacuum()
        sys.exit(0)

    base_path = args.MSTR_DIR
    all_file_paths = set(base_path.glob("*.xml"))
    entities_files = get_files(all_file_paths)

    write_schema(path_schema, path_udf, path_tiles)

    # forkserver on every Python version: with "fork" (the Linux default up
    # to Python 3.13) a child can inherit locks held by threads of the parent
    with get_context("forkserver").Pool(processes=args.concurrency) as pool:
        processes = []
        for curr_entity in Einheiten:
            entity_files = entities_files.get(curr_entity.name, [])
            if not entity_files:
                logger.warning(f"no source files found for entity {curr_entity.name}, skipping")
                continue
            for file in entity_files:
                processes.append(
                    pool.apply_async(
                        parse_and_write_xml,
                        (file, curr_entity, args.silent),
                    )
                )

        for proc in processes:
            proc.get()

    logger.info("create primary keys and indices")
    write_constraints(path_constraints)
    logger.info("rebuild the tile grid")
    refresh_tile_grid(path_grid)
    logger.info("vacuum and analyze tables")
    vacuum_analyze()
    enable_autovacuum()


if __name__ == "__main__":
    start_perf = time.perf_counter()
    main()
    logger.info(f"db import execution time: {time.perf_counter() - start_perf:9.3f} s")
