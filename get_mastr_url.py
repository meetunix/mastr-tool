#!/usr/bin/env python3
# script prints the dump URL (first line) and its remote ETag (second line, empty if unknown)
# script returns 20 if source file has not been changed since the last successful pipeline run
import argparse
import sys
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup


def get_remote_etag(url: str) -> Optional[str]:
    headers = {"user-agent": "mastr-tool"}
    try:
        r = requests.head(url, headers=headers)
        return r.headers["etag"]
    except Exception:
        return None


def get_local_etag(etag_path: Path) -> Optional[str]:
    # strip: download-mastr.sh writes the file with a trailing newline
    return etag_path.read_text(encoding="utf-8").strip() if etag_path.exists() and etag_path.is_file() else None


def is_etag_new(local_etag_path: Path, remote_etag: Optional[str]) -> bool:
    """Compare the remote ETag with the ETag of the last successful pipeline
    run. The local ETag file is not written here: download-mastr.sh stores it
    only after the whole pipeline succeeded, so a failed run is retried at
    the next check."""
    if remote_etag is None:
        return False

    return get_local_etag(local_etag_path) != remote_etag


def main() -> None:
    URL = "https://www.marktstammdatenregister.de/MaStR/Datendownload"
    page = requests.get(URL)
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True, help="Path to cache directory")
    args = parser.parse_args()

    soup = BeautifulSoup(page.content, "html.parser")

    # extract url from first link with specific class (always the newest )
    ahref = soup.find_all("a", class_="btn btn-primary text-right")[0]
    mastr_url = ahref["href"]

    etag_file = args.cache_dir / Path("etag.txt")
    remote_etag = get_remote_etag(mastr_url)
    print(mastr_url)
    print(remote_etag or "")
    if not is_etag_new(etag_file, remote_etag):
        sys.exit(20)


if __name__ == "__main__":
    main()
