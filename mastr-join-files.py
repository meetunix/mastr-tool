#!/usr/bin/env python3
"""Concatenate the split mastr files from original export."""
import argparse
import codecs
import re
import sys
import time
import shutil
from pathlib import Path
from typing import Dict, List, Set


FILE_PATTERN = re.compile(r"^(.*)_([0-9]{1,3}).xml$")


def concat_to_file(source_files: List[Path], target_file: Path) -> None:
    """Concatenate files to new file, will work with large files."""
    with open(target_file, "wb") as target:
        for f in source_files:
            with open(f, "rb") as source:
                shutil.copyfileobj(source, target)


def concat_to_utf8_file(source_files: List[Path], target_file: Path, buffer_size: int = 67108864) -> None:
    """Concatenate files to a new utf8 encoded file, will work with large files.

    default buffer_size = 64 MiB
    """
    with codecs.open(str(target_file), "w", "utf-8") as target:
        for source_file in source_files:
            with codecs.open(str(source_file), "r", "utf-16") as sourceFile:
                while True:
                    contents = sourceFile.read(buffer_size)
                    if not contents:
                        break
                    target.write(contents)


def get_files_for_concatenation(base_path: Path, files: Set[str]) -> Dict[Path, List[Path]]:
    """Create a dict with new filename (key) and the ordered list of source files."""
    result = {}
    result = {}
    for file in files:
        match = re.search(FILE_PATTERN, file)
        filename, number = match.group(1), int(match.group(2))
        if filename in result:
            result[filename].append(number)
        else:
            result[filename] = [number]
    result = {k: sorted(v) for (k, v) in result.items()}
    result = {k: [f"{k}_{n}.xml" for n in v] for (k, v) in result.items()}
    result = {k: [base_path / Path(n) for n in v] for (k, v) in result.items()}
    result = {base_path / f"{k}.xml": v for (k, v) in result.items()}
    return result


def concat():
    """Main function."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--utf8", action="store_true", default=False)
    parser.add_argument("MSTR_DIR", type=Path, help="The export directory from the Marktstammdatenregister")
    args = parser.parse_args()

    base_path = args.MSTR_DIR
    all_source_file_paths = list(base_path.glob("*.xml"))
    all_file_names = {p.name for p in all_source_file_paths}
    splitted_file_names = {f for f in all_file_names if re.match(FILE_PATTERN, f)}
    concatenated_file_names = all_file_names.difference(splitted_file_names)

    to_concatenate = get_files_for_concatenation(base_path, splitted_file_names)
    concatenated_file_names.union(set(to_concatenate.keys()))

    # concatenate the split files in right order
    if args.utf8:
        for target, sources in to_concatenate.items():
            if not target.exists():
                concat_to_utf8_file(sources, target)
                # TODO only split files are converted to utf-8, needs to be fixed
    else:
        for target, sources in to_concatenate.items():
            if not target.exists():
                concat_to_file(sources, target)

    # delete split files
    for file in splitted_file_names:
        (base_path / Path(file)).unlink()


start_perf = time.perf_counter()
concat()
sys.stdout.write(f"execution time: {time.perf_counter() - start_perf:9.3f} s\n")
