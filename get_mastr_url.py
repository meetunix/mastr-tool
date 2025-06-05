#!/usr/bin/env python3
# script returns 20 if source file has not been changed since last check
import argparse
import sys
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup


def get_remote_etag(url: str) -> Optional[str]:
    headers = {'user-agent': 'mastr-tool'}
    try:
        r = requests.head(url, headers=headers)
        return r.headers["etag"]
    except Exception:
        return None


def get_local_etag(etag_path: Path) -> Optional[str]:
    return etag_path.read_text(encoding="utf-8") if etag_path.exists() and etag_path.is_file() else None


def is_etag_new(local_etag_path: Path, mastr_url: str) -> bool:
    remote_etag = get_remote_etag(mastr_url)
    local_etag = get_local_etag(local_etag_path)

    # print(f"{local_etag} <-> {remote_etag}")

    if remote_etag is None:
        return False

    if local_etag is None:
        local_etag_path.write_text(remote_etag)
        return False

    if local_etag != remote_etag:
        local_etag_path.write_text(remote_etag)
        return True
    else:
        return False


def main() -> None:
    URL = "https://www.marktstammdatenregister.de/MaStR/Datendownload"
    page = requests.get(URL)
    local_etag_path = Path("/mnt/cache/etag.txt")
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True, help="Path to cache directory")
    args = parser.parse_args()

    soup = BeautifulSoup(page.content, "html.parser")

    # extract url from first link with specific class (always the newest )
    ahref = soup.find_all("a", class_="btn btn-primary text-right")[0]
    mastr_url = ahref["href"]

    etag_file = args.cache_dir / Path("etag.txt")
    if is_etag_new(etag_file, mastr_url):
        print(mastr_url)
    else:
        print(mastr_url)
        sys.exit(20)


if __name__ == '__main__':
    main()
