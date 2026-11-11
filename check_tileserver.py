#!/usr/bin/env python3
"""Smoke test and benchmark for the MaStR tile server (Martin).

Talks to a running server over HTTP and checks what a map client would see:
health, catalog, TileJSON and one decoded tile per layer. Needs nothing but
`requests` and a running server.

    python check_tileserver.py
    python check_tileserver.py --url http://localhost:8082 --zoom 12
    python check_tileserver.py --layer wind --lon 8.5 --lat 50.1 --attributes
    python check_tileserver.py --purge

    python check_tileserver.py --benchmark
    python check_tileserver.py --benchmark --requests 500 --min-zoom 8 --seed 42

Exit code 0 means every check passed. An empty tile is not a failure (Martin
answers it with 204, and the database may not be imported yet); a missing
layer, a broken tile or a wrong content type is.

The benchmark requests random tiles of random layers at random zoom levels
across Germany. Every tile is requested once, so the timings are not dominated
by cache hits; use --purge-first to start from a cold cache.

All requests run on --concurrency workers (default 5) that share a fixed set of
keep-alive connections. The script opens that many connections once instead of
one per request, so the timings do not include a TCP and TLS handshake per tile
and the server is not hit by a burst of short-lived connections.
"""

import argparse
import math
import random
import re
import shutil
import struct
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue

import requests

# keep in sync with db/tiles.sql; read from there when the file is available
FALLBACK_LAYERS = [
    "wind",
    "solar",
    "biomasse",
    "wasser",
    "geothermie",
    "stromspeicher",
    "kernkraft",
    "verbrennung",
    "gaserzeuger",
    "gasspeicher",
    "gasverbraucher",
    "stromverbraucher",
]

MVT_CONTENT_TYPES = {"application/x-protobuf", "application/vnd.mapbox-vector-tile"}

# rough bounding box of Germany, the benchmark picks random points inside it
GERMANY_LON = (5.87, 15.04)
GERMANY_LAT = (47.27, 55.06)

# column widths of the per-layer table
W_LAYER, W_STATUS, W_SIZE, W_FEATURES, W_ATTRS = 22, 6, 9, 8, 10


class SessionPool:
    """A fixed set of requests.Session objects, each holding one keep-alive
    connection.

    A session is not thread safe, so a worker borrows one for the duration of a
    request. The pool size is the concurrency limit: the script opens that many
    connections once and reuses them, instead of a new connection (and a new
    TLS handshake) for every tile.
    """

    def __init__(self, size: int):
        self._sessions: Queue[requests.Session] = Queue()
        for _ in range(size):
            session = requests.Session()
            # one connection per session, so the pool size is the limit
            adapter = requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            self._sessions.put(session)

    def __enter__(self) -> "SessionPool":
        return self

    def __exit__(self, *exc_info) -> None:
        while not self._sessions.empty():
            self._sessions.get_nowait().close()

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Send one request on a borrowed session. The response body is read
        before the session goes back to the pool, so the connection is free
        again when the caller gets the response."""
        session = self._sessions.get()
        try:
            return session.request(method, url, **kwargs)
        finally:
            self._sessions.put(session)


# --- Mapbox Vector Tile decoding (protobuf, no external dependency) ---------


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7


def _fields(buf: bytes):
    """Yield (field number, wire type, value) of one protobuf message."""
    pos = 0
    while pos < len(buf):
        key, pos = _varint(buf, pos)
        field, wire = key >> 3, key & 0x07
        if wire == 0:
            value, pos = _varint(buf, pos)
        elif wire == 1:
            value, pos = buf[pos : pos + 8], pos + 8
        elif wire == 2:
            length, pos = _varint(buf, pos)
            value, pos = buf[pos : pos + length], pos + length
        elif wire == 5:
            value, pos = buf[pos : pos + 4], pos + 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        yield field, wire, value


def _decode_value(buf: bytes):
    for field, _, raw in _fields(buf):
        if field == 1:
            return raw.decode()
        if field == 2:
            return struct.unpack("<f", raw)[0]
        if field == 3:
            return struct.unpack("<d", raw)[0]
        if field == 4:
            return raw - (1 << 64) if raw >= 1 << 63 else raw
        if field == 5:
            return raw
        if field == 6:
            return (raw >> 1) ^ -(raw & 1)
        if field == 7:
            return bool(raw)
    return None


def _decode_feature(buf: bytes) -> tuple[list[int], int]:
    tags, geom_type = [], 0
    for field, wire, raw in _fields(buf):
        if field == 2:  # tags: packed uint32, or one varint per entry
            if wire == 2:
                pos = 0
                while pos < len(raw):
                    tag, pos = _varint(raw, pos)
                    tags.append(tag)
            else:
                tags.append(raw)
        elif field == 3:
            geom_type = raw
    return tags, geom_type


def decode_mvt(data: bytes) -> list[dict]:
    """Decode a tile into [{name, extent, features: [{type, properties}]}]."""
    layers = []
    for field, _, raw in _fields(data):
        if field != 3:  # Tile.layers
            continue
        name, extent, keys, values, features = None, 4096, [], [], []
        for lfield, _, lraw in _fields(raw):
            if lfield == 1:
                name = lraw.decode()
            elif lfield == 2:
                features.append(_decode_feature(lraw))
            elif lfield == 3:
                keys.append(lraw.decode())
            elif lfield == 4:
                values.append(_decode_value(lraw))
            elif lfield == 5:
                extent = lraw
        decoded = []
        for tags, geom_type in features:
            properties = {keys[tags[i]]: values[tags[i + 1]] for i in range(0, len(tags) - 1, 2)}
            decoded.append({"type": geom_type, "properties": properties})
        layers.append({"name": name, "extent": extent, "features": decoded})
    return layers


# --- helpers ----------------------------------------------------------------


def deg2tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """Web mercator tile containing the coordinate (XYZ scheme)."""
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    # latitudes beyond the web mercator limit (~85.05) give a negative y
    return max(0, min(x, n - 1)), max(0, min(y, n - 1))


def expected_layers() -> list[str]:
    """Layer names from db/tiles.sql, so the list cannot drift."""
    sql = Path(__file__).resolve().parent / "db" / "tiles.sql"
    if not sql.exists():
        return FALLBACK_LAYERS
    return re.findall(r"CREATE OR REPLACE FUNCTION tiles\.(\w+)\(", sql.read_text())


def human_size(num: float) -> str:
    if num >= 1024 * 1024:
        return f"{num / 1024 / 1024:.1f} MB"
    return f"{num / 1024:.1f} kB" if num >= 1024 else f"{num:.0f} B"


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile of an already sorted list."""
    if not values:
        return 0.0
    return values[min(len(values) - 1, int(round(fraction * (len(values) - 1))))]


def table_row(layer: str, status: str, size: str, features: str, attributes: str) -> str:
    return (
        f"{layer:<{W_LAYER}} {status:>{W_STATUS}} {size:>{W_SIZE}} "
        f"{features:>{W_FEATURES}} {attributes:>{W_ATTRS}}"
    )


def label(name: str, value: str) -> str:
    return f"{name:<16} {value}"


def purge_sources(pool: SessionPool, base: str, sources: list[str], timeout: float, concurrency: int) -> int:
    """DELETE /cache/{source} for every layer; returns the number of purges
    that answered 200."""

    def purge(source: str) -> int | None:
        try:
            return pool.request("DELETE", f"{base}/cache/{source}", timeout=timeout).status_code
        except requests.RequestException:
            return None

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        return sum(1 for code in executor.map(purge, sources) if code == 200)


def benchmark_tile(pool: SessionPool, base: str, sample: tuple[str, int, int, int], timeout: float):
    """Request and decode one tile; returns (result, failure)."""
    layer, zoom, x, y = sample
    source = f"tiles.{layer}"
    started = time.perf_counter()
    try:
        response = pool.request("GET", f"{base}/{source}/{zoom}/{x}/{y}", timeout=timeout)
    except requests.RequestException as exc:
        return None, f"{source} z{zoom} {x}/{y}: {exc}"
    elapsed = (time.perf_counter() - started) * 1000

    if response.status_code not in (200, 204):
        return None, f"{source} z{zoom} {x}/{y}: HTTP {response.status_code}"
    features = 0
    if response.status_code == 200:
        try:
            features = sum(len(item["features"]) for item in decode_mvt(response.content))
        except (ValueError, IndexError, UnicodeDecodeError, struct.error) as exc:
            return None, f"{source} z{zoom} {x}/{y}: cannot decode the tile ({exc})"
    return {
        "layer": source,
        "zoom": zoom,
        "x": x,
        "y": y,
        "ms": elapsed,
        "bytes": len(response.content),
        "features": features,
    }, None


def run_benchmark(args, base: str, layers: list[str], failures: list[str], pool: SessionPool) -> int:
    """Request random tiles of random layers at random zooms across Germany."""
    seed = args.seed if args.seed is not None else random.randrange(1_000_000)
    rng = random.Random(seed)

    if args.purge_first:
        purged = purge_sources(pool, base, [f"tiles.{name}" for name in layers], args.timeout, args.concurrency)
        print(label("purge", f"{purged}/{len(layers)} sources purged"))

    print(
        f"\nbenchmark: up to {args.requests} unique tiles, zoom {args.min_zoom}-{args.max_zoom}, "
        f"{len(layers)} layers, seed {seed}, {args.concurrency} connections"
    )

    samples: list[tuple[str, int, int, int]] = []
    seen: set[tuple[str, int, int, int]] = set()
    attempts = 0
    while len(samples) < args.requests and attempts < args.requests * 50:
        attempts += 1
        layer = rng.choice(layers)
        zoom = rng.randint(args.min_zoom, args.max_zoom)
        x, y = deg2tile(rng.uniform(*GERMANY_LON), rng.uniform(*GERMANY_LAT), zoom)
        if (layer, zoom, x, y) in seen:
            continue
        seen.add((layer, zoom, x, y))
        samples.append((layer, zoom, x, y))

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(benchmark_tile, pool, base, sample, args.timeout) for sample in samples]
        for future in futures:
            result, failure = future.result()
            if failure:
                failures.append(failure)
            else:
                results.append(result)

    if not results:
        print("no tile could be requested")
        return 1
    if len(results) < args.requests:
        print(f"only {len(results)} unique tiles exist in that zoom range")

    header = f"{'zoom':>4} {'tiles':>6} {'p50':>9} {'p95':>9} {'max':>9} {'feat/tile':>9} {'size/tile':>9}"
    print(f"\n{header}")
    print("-" * len(header))

    def summary_row(name: str, rows: list[dict]) -> str:
        times = sorted(item["ms"] for item in rows)
        return (
            f"{name:>4} {len(rows):>6} {percentile(times, 0.5):>9.1f} {percentile(times, 0.95):>9.1f} "
            f"{times[-1]:>9.1f} {sum(item['features'] for item in rows) / len(rows):>9.0f} "
            f"{human_size(sum(item['bytes'] for item in rows) / len(rows)):>9}"
        )

    for zoom in sorted({item["zoom"] for item in results}):
        print(summary_row(str(zoom), [item for item in results if item["zoom"] == zoom]))
    print("-" * len(header))
    print(summary_row("all", results))

    total_bytes = sum(item["bytes"] for item in results)
    total_features = sum(item["features"] for item in results)
    total_seconds = sum(item["ms"] for item in results) / 1000
    print(
        f"\ntotal {human_size(total_bytes)}, {total_features} features, "
        f"{len(results)} tiles in {total_seconds:.1f} s"
    )

    print("\nslowest")
    for item in sorted(results, key=lambda row: row["ms"], reverse=True)[:5]:
        print(
            f"  {item['layer']:<22} z{item['zoom']:<2} {item['x']}/{item['y']:<6} "
            f"{item['ms']:>9.1f} ms {item['features']:>6} features {human_size(item['bytes']):>9}"
        )

    if failures:
        print(f"\n{len(failures)} check(s) failed:")
        for failure in failures[:20]:
            print(f"  - {failure}")
        return 1
    print("\nall requests succeeded")
    return 0


def check_layer(pool: SessionPool, base: str, name: str, zoom: int, x: int, y: int, timeout: float):
    """Request and decode one tile; returns (row, failures, ms, attributes)."""
    source = f"tiles.{name}"
    problems: list[str] = []
    started = time.perf_counter()
    try:
        response = pool.request("GET", f"{base}/{source}/{zoom}/{x}/{y}", timeout=timeout)
    except requests.RequestException as exc:
        return table_row(source, "-", "-", "-", "-"), [f"{source}: {exc}"], None, None
    elapsed = (time.perf_counter() - started) * 1000

    # Martin answers a tile without features with 204 No Content
    if response.status_code == 204:
        return table_row(source, "204", "-", "0", "-"), problems, elapsed, None
    if response.status_code != 200:
        return (
            table_row(source, str(response.status_code), "-", "-", "-"),
            [f"{source}: HTTP {response.status_code}"],
            elapsed,
            None,
        )

    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    if content_type not in MVT_CONTENT_TYPES:
        problems.append(f"{source}: unexpected content type {content_type!r}")

    try:
        decoded = decode_mvt(response.content)
    except (ValueError, IndexError, UnicodeDecodeError, struct.error) as exc:
        problems.append(f"{source}: cannot decode the tile ({exc})")
        return table_row(source, "200", human_size(len(response.content)), "-", "-"), problems, elapsed, None

    features = [feature for layer in decoded for feature in layer["features"]]
    names = sorted({key for feature in features for key in feature["properties"]})
    if decoded and decoded[0]["name"] != name:
        problems.append(f"{source}: MVT layer is named {decoded[0]['name']!r}")
    row = table_row(source, "200", human_size(len(response.content)), str(len(features)), str(len(names)))
    return row, problems, elapsed, names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--url", default="http://127.0.0.1:8082", help="base URL of the tile server (default: http://127.0.0.1:8082)"
    )
    parser.add_argument("--zoom", type=int, default=10, help="zoom level of the test tile (default: 10)")
    parser.add_argument("--lon", type=float, default=10.45, help="longitude of the test tile (default: 10.45)")
    parser.add_argument("--lat", type=float, default=51.16, help="latitude of the test tile (default: 51.16)")
    parser.add_argument("--layer", action="append", help="only test this layer (repeatable)")
    parser.add_argument("--timeout", type=float, default=30.0, help="request timeout in seconds (default: 30)")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="parallel requests and keep-alive connections (default: 5)",
    )
    parser.add_argument("--attributes", action="store_true", help="list the feature attributes of every layer")
    parser.add_argument("--purge", action="store_true", help="also test DELETE /cache/{source}")
    parser.add_argument("--benchmark", action="store_true", help="benchmark random tiles instead of the smoke test")
    parser.add_argument("--requests", type=int, default=100, help="unique tiles in the benchmark (default: 100)")
    parser.add_argument("--min-zoom", type=int, default=0, help="lowest benchmark zoom (default: 0)")
    parser.add_argument("--max-zoom", type=int, default=14, help="highest benchmark zoom (default: 14)")
    parser.add_argument("--seed", type=int, help="random seed of the benchmark (default: random)")
    parser.add_argument("--purge-first", action="store_true", help="purge the cache before the benchmark")
    args = parser.parse_args()

    if not 0 <= args.zoom <= 22:
        parser.error("--zoom must be between 0 and 22")
    if not 0 <= args.min_zoom <= args.max_zoom <= 22:
        parser.error("--min-zoom/--max-zoom must satisfy 0 <= min <= max <= 22")
    if args.requests < 1:
        parser.error("--requests must be at least 1")
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")

    base = args.url.rstrip("/")
    x, y = deg2tile(args.lon, args.lat, args.zoom)
    failures: list[str] = []

    print(f"Martin tile server: {base}")
    if not args.benchmark:
        print(f"tile: z{args.zoom} x{x} y{y} (lon {args.lon}, lat {args.lat})")
    print()

    with SessionPool(args.concurrency) as pool:
        # --- health -----------------------------------------------------
        try:
            response = pool.request("GET", f"{base}/health", timeout=args.timeout)
        except requests.RequestException as exc:
            print(label("health", f"FAILED: cannot reach {base}: {exc}"))
            return 1
        if response.status_code != 200:
            failures.append(f"health returned {response.status_code}")
        print(label("health", f"{response.status_code} {response.text.strip()[:40]}"))

        # --- catalog ----------------------------------------------------
        try:
            catalog = pool.request("GET", f"{base}/catalog", timeout=args.timeout).json()
        except (requests.RequestException, ValueError) as exc:
            print(label("catalog", f"FAILED: {exc}"))
            return 1
        published = sorted(catalog.get("tiles", {}))
        expected = expected_layers()
        missing = [f"tiles.{name}" for name in expected if f"tiles.{name}" not in published]
        if missing:
            failures.append(f"missing layers: {', '.join(missing)}")
        print(label("catalog", f"{len(published)} sources" + (f", missing: {', '.join(missing)}" if missing else "")))

        layers = args.layer or expected
        if not layers:
            print(label("layers", "none found - is db/tiles.sql present?"))
            return 1
        if args.benchmark:
            return run_benchmark(args, base, layers, failures, pool)

        # --- tiles ------------------------------------------------------
        print()
        print(table_row("layer", "status", "size", "features", "attributes"))
        print("-" * (W_LAYER + W_STATUS + W_SIZE + W_FEATURES + W_ATTRS + 4))
        timings: dict[str, float] = {}
        attributes: dict[str, list[str]] = {}
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            outcomes = list(
                executor.map(lambda name: check_layer(pool, base, name, args.zoom, x, y, args.timeout), layers)
            )
        for name, (row, problems, elapsed, names) in zip(layers, outcomes):
            print(row)
            failures.extend(problems)
            if elapsed is not None:
                timings[f"tiles.{name}"] = elapsed
            if names:
                attributes[f"tiles.{name}"] = names

        # --- attributes -------------------------------------------------
        if args.attributes:
            print("\nattributes")
            # wrap to the terminal width, the list is long for the big layers
            width = max(40, shutil.get_terminal_size((100, 24)).columns - W_LAYER - 3)
            for source, names in attributes.items():
                if not names:
                    continue
                lines = textwrap.wrap(", ".join(names), width=width) or ["-"]
                print(f"  {source:<{W_LAYER}} {lines[0]}")
                for line in lines[1:]:
                    print(f"  {'':<{W_LAYER}} {line}")

        # --- headers and cache ------------------------------------------
        first = f"tiles.{layers[0]}"
        try:
            started = time.perf_counter()
            response = pool.request("GET", f"{base}/{first}/{args.zoom}/{x}/{y}", timeout=args.timeout)
            again = (time.perf_counter() - started) * 1000
            cache_control = response.headers.get("cache-control", "")
            content_type = response.headers.get("content-type", "")
            if not cache_control:
                failures.append("no Cache-Control header on the tile")
            print()
            print(label("cache-control", cache_control or "-"))
            print(label("content-type", content_type or "-"))
            if first in timings:
                print(label("cache", f"{first}: {timings[first]:.1f} ms, then {again:.1f} ms"))
        except requests.RequestException as exc:
            failures.append(f"header check failed: {exc}")

        # --- purge ------------------------------------------------------
        if args.purge:
            print("\npurge")
            sources = [f"tiles.{name}" for name in layers]

            def purge(source: str):
                try:
                    response = pool.request("DELETE", f"{base}/cache/{source}", timeout=args.timeout)
                    return response.status_code, response.text.strip()[:60], None
                except requests.RequestException as exc:
                    return None, None, str(exc)

            with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                outcomes = list(executor.map(purge, sources))
            for source, (status, text, error) in zip(sources, outcomes):
                if error:
                    print(f"  {source:<{W_LAYER}} FAILED: {error}")
                    failures.append(f"purge {source}: {error}")
                    continue
                print(f"  {source:<{W_LAYER}} {status} {text}")
                if status != 200:
                    failures.append(f"purge {source}: HTTP {status}")

    # --- summary --------------------------------------------------------
    if failures:
        print(f"\n{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
