#!/usr/bin/env python3
import argparse
import re
import sys
import time

from multiprocessing import Pool
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Dict, List, Set
from db.entities import *
from db.db_utils import DBElementWriter, get_db_connection

from utils.mastr_logger import get_mastr_logger, LogLevel

logger = get_mastr_logger(LogLevel.INFO)

FILE_PATTERN = re.compile(r"^(.*)_([0-9]{1,3}).xml$")


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
    for event, elem in ET.iterparse(file, events=("start", "end")):
        if event == "end" and elem.tag == entity.value.__name__:
            db_writer.write(elem)
    db_writer.cleanup()


def create_schema(path_schema: Path) -> None:
    s = ""
    i = ""
    curr_column = None
    try:
        for table in Einheiten:
            s += f"create table if not exists {table.name} (\n"
            first_col = True
            for col in table.value:
                curr_column = col
                s += f"{',' if not first_col else ''}\n{col.name:56s}"  # column
                s += f"{col.value[1].value[1]:16s}"  # data type
                s += f"{'NOT NULL' if col.value[2] else '':16s}"  # NULLABLE
                s += f"{'PRIMARY KEY' if col.value[3] else ''}"  # PKEY
                first_col = False
            s += "\n);\n\n"
        for index in Indices:
            i += f"CREATE INDEX IF NOT EXISTS {index.value.name}_idx ON {index.name}({index.value.name});\n\n"
        s += i
    except Exception as e:
        logger.exception("Exception while creating schema")
        sys.stderr.write(f"\nERROR: {e} - {curr_column}\n")
        sys.exit(1)

    path_schema.write_text(s)


def write_schema(path_schema: Path, path_udf: Path) -> None:
    conn = get_db_connection()
    with conn.cursor() as curr:
        schema = path_schema.read_text() + "\n" + path_udf.read_text()
        curr.execute(schema)
        conn.commit()


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

    if args.cleanup:
        delete_tables()

    if args.schema:
        create_schema(path_schema)
        write_schema(path_schema, path_udf)
        sys.exit(0)

    base_path = args.MSTR_DIR
    all_file_paths = set(base_path.glob("*.xml"))
    entities_files = get_files(all_file_paths)

    create_schema(path_schema)
    write_schema(path_schema, path_udf)

    with Pool(processes=args.concurrency) as pool:
        processes = []
        for curr_entity in Einheiten:
            for file in entities_files[curr_entity.name]:
                processes.append(
                    pool.apply_async(
                        parse_and_write_xml,
                        (file, curr_entity, args.silent),
                    )
                )

        for proc in processes:
            proc.get()


if __name__ == "__main__":
    start_perf = time.perf_counter()
    main()
    logger.info(f"db import execution time: {time.perf_counter() - start_perf:9.3f} s")
