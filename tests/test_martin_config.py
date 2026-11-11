"""Tests for the Martin configuration (martin/config.yaml).

The tile server is configured by a file, not by environment variables: the
schema filter, the source id format and the disabled cache are only available
there. docker compose mounts martin/config.yaml, the Helm chart ships
charts/mastr-tool/files/martin.yaml - both must stay identical.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_CONFIG = ROOT / "martin" / "config.yaml"
CHART_CONFIG = ROOT / "charts" / "mastr-tool" / "files" / "martin.yaml"

# built from parts so this test does not match itself
LEGACY_NAMES = ("pg_" + "tileserv", "pg-" + "tileserv", "pram" + "sey")


def config_lines() -> list[str]:
    """The effective lines of the config: comments and blank lines removed."""
    return [
        line.strip()
        for line in COMPOSE_CONFIG.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


class TestConfigFiles:
    def test_compose_and_chart_config_are_identical(self):
        """One file is mounted by compose, the other one is packaged into the
        Helm chart: they must not drift apart."""
        assert COMPOSE_CONFIG.read_text() == CHART_CONFIG.read_text()


class TestPostgresSources:
    def test_only_the_tiles_schema_is_published(self):
        assert "from_schemas: [tiles]" in config_lines()

    def test_no_table_sources(self):
        """The unit tables must not be published, only the tile functions."""
        assert "tables: false" in config_lines()

    def test_source_id_is_schema_dot_function(self):
        """The source id is the URL path: /tiles.wind/{z}/{x}/{y}."""
        assert 'source_id_format: "{schema}.{function}"' in config_lines()

    def test_connection_string_comes_from_the_environment(self):
        """The password is not part of the file: compose and the chart pass
        MARTIN_DATABASE_URL."""
        assert "connection_string: ${MARTIN_DATABASE_URL}" in config_lines()


class TestServer:
    def test_cache_is_enabled_with_a_ttl(self):
        """A cache without an expiry would serve stale tiles after an import -
        the TTL is what makes the cache safe."""
        lines = config_lines()
        assert "cache: disable" not in lines
        assert "size_mb: 512" in lines
        assert "tile_size_mb: 512" in lines
        assert "tile_expiry: 12h" in lines

    def test_cache_skips_the_overzoom_levels(self):
        """Clients overzoom beyond z14, so caching those tiles only wastes RAM."""
        assert "maxzoom: 14" in config_lines()

    def test_cache_control_is_set(self):
        assert 'cache_control: "public, max-age=3600"' in config_lines()

    def test_web_ui_is_disabled(self):
        assert "web_ui: disable" in config_lines()

    def test_cache_purge_endpoint_is_enabled(self):
        """download-mastr.sh purges the cache after every import - without the
        endpoint the map would show the old data until the TTL expires."""
        assert "purge_cache: true" in config_lines()

    def test_listen_addresses_can_be_overridden(self):
        """The Helm chart passes martin.containerPort as MARTIN_LISTEN_ADDRESSES."""
        assert "listen_addresses: ${MARTIN_LISTEN_ADDRESSES:-0.0.0.0:7800}" in config_lines()


class TestNoLegacyTileServer:
    def test_no_legacy_tile_server_artifacts_remain(self):
        """The tile server was switched to Martin - no leftovers of the old one
        in code, configuration, templates or documentation."""
        suffixes = {".py", ".sql", ".yaml", ".yml", ".sh", ".md", ".txt", ".tpl"}
        skipped_dirs = {".git", ".venv", "__pycache__", ".idea", "node_modules"}
        offenders = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            if skipped_dirs & set(path.relative_to(ROOT).parts):
                continue
            text = path.read_text(errors="ignore")
            offenders += [f"{path.relative_to(ROOT)}: {name}" for name in LEGACY_NAMES if name in text]
        assert not offenders, offenders
