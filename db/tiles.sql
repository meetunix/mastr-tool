-- Mapbox Vector Tiles (MVT) for Martin (martin/config.yaml).
--
-- One function source per unit table: tiles.<traeger>(z, x, y) returns the MVT
-- bytes of one tile. Function sources are used instead of views because
-- download-mastr.sh imports with --cleanup, which drops and recreates the
-- tables - a view would block the DROP TABLE, a plpgsql function resolves the
-- table name on every call and survives the rebuild.
--
-- The functions are SECURITY DEFINER: Martin connects with the read-only role
-- tiles_reader, which only gets USAGE on this schema and EXECUTE on the
-- functions (see the grants at the end of this file). It cannot read the unit
-- tables, and martin/config.yaml publishes no table sources anyway.
--
-- Martin reads the COMMENT ON FUNCTION as TileJSON, so the comment is a JSON
-- object with at least a "description".
--
-- Every function filters with "&&" on the same expression that the GiST index
-- uses (GeomIndices in db/entities.py), so a tile request is an index scan.
-- The partial index condition is repeated in the query, otherwise the planner
-- cannot use the partial index.
--
-- Attributes per feature: mastr_nr, name, park, kw and status plus the common
-- fields (inbetriebnahme, brutto_kw, betreiber, fernsteuerbar_nb/dv,
-- hochspannung, stillgelegt_am) and the fields of the energy carrier. The
-- operator name comes from a LEFT JOIN on Marktakteure: Firmenname, for natural
-- persons the first and last name. Every attribute makes the tiles bigger, so
-- the list is deliberate; catalog values are kept as IDs (the client maps
-- them).
--
-- Solar and Stromspeicher have millions of units: below zoom 10 the points are
-- bundled per grid cell (64 x 64 cells per tile) into one feature with the
-- number of units and the summed power. A single z5 tile would otherwise
-- contain hundreds of thousands of points and grow to several megabytes.
-- The count is cast to bigint: sum(bigint) returns numeric, and ST_AsMVT
-- writes numeric as a string into the value dictionary, so a client would get
-- "1000" instead of 1000.
--
-- Coordinates outside the zoom level (x or y >= 2^z) are answered with an
-- empty tile: ST_TileEnvelope raises for them and Martin turns that into a
-- 500, which looks like a server error for what is a client error.

CREATE SCHEMA IF NOT EXISTS tiles;

-- Pre-aggregated grid for the low zoom tiles: one row per ~1 km cell and
-- layer, holding the number of units and their summed power. A z4 tile of
-- solar aggregates 266k units; scanning them takes 30 s because the GiST
-- index does random heap access over the 2 GB table. The grid is rebuilt by
-- db/grid.sql after every import.
CREATE TABLE IF NOT EXISTS tiles.grid (
    layer text NOT NULL,
    cx integer NOT NULL,
    cy integer NOT NULL,
    anzahl bigint NOT NULL,
    kw double precision,
    PRIMARY KEY (layer, cx, cy)
);

-- Windenergieanlagen
CREATE OR REPLACE FUNCTION tiles.wind(z integer, x integer, y integer)
RETURNS bytea
AS $$
DECLARE
    result bytea;
BEGIN
    IF z < 0 OR z > 30 THEN
        RETURN ''::bytea;
    END IF;
    IF x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
        RETURN ''::bytea;
    END IF;
    -- below z7 a tile would carry thousands of individual points
    IF z < 7 THEN
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        g AS (
            -- cell size = tile width / 64, so the cells line up with the tile
            -- edges and a tile has at most 4096 features
            SELECT ST_XMin(env4326) AS lon0,
                   ST_YMin(env4326) AS lat0,
                   ST_XMax(env4326) AS lon1,
                   ST_YMax(env4326) AS lat1,
                   (ST_XMax(env4326) - ST_XMin(env4326)) / 64.0 AS dlon,
                   (ST_YMax(env4326) - ST_YMin(env4326)) / 64.0 AS dlat
            FROM b
        ),
        cells AS (
            -- the grid holds the units per ~1 km cell (db/grid.sql): a low
            -- zoom tile aggregates a few thousand rows instead of scanning the
            -- unit table, whose GiST index does random heap access
            SELECT floor(((c.cx + 0.5) * 0.01 - 180 - g.lon0) / g.dlon)::int AS cx,
                   floor(((c.cy + 0.5) * 0.01 - 90 - g.lat0) / g.dlat)::int AS cy,
                   sum(c.anzahl)::bigint AS anzahl,
                   sum(c.kw) AS kw
            FROM tiles.grid c, g
            WHERE c.layer = 'wind'
              AND c.cx BETWEEN floor((g.lon0 + 180) / 0.01)::int AND floor((g.lon1 + 180) / 0.01)::int
              AND c.cy BETWEEN floor((g.lat0 + 90) / 0.01)::int AND floor((g.lat1 + 90) / 0.01)::int
            GROUP BY 1, 2
        ),
        f AS (
            -- one projection per cell (at most 4096), not per unit
            SELECT ST_AsMVTGeom(
                       ST_Transform(
                           ST_SetSRID(ST_MakePoint(g.lon0 + (c.cx + 0.5) * g.dlon,
                                                   g.lat0 + (c.cy + 0.5) * g.dlat), 4326),
                           3857),
                       b.env
                   ) AS geom,
                   c.anzahl, c.kw
            FROM cells c, g, b
        )
        SELECT ST_AsMVT(f, 'wind') INTO result FROM f;
    ELSE
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        f AS (
            SELECT ST_AsMVTGeom(
                       ST_Transform(ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326), 3857),
                       b.env
                   ) AS geom,
                   e.einheitmastrnummer AS mastr_nr,
                   e.namestromerzeugungseinheit AS name,
                   e.namewindpark AS park,
                   e.nettonennleistung::float8 AS kw,
                   e.einheitbetriebsstatus AS status,
                   to_char(e.inbetriebnahmedatum, 'YYYY-MM-DD') AS inbetriebnahme,
                   e.bruttoleistung::float8 AS brutto_kw,
                   coalesce(m.firmenname, nullif(concat_ws(' ', m.marktakteurvorname, m.marktakteurnachname), '')) AS betreiber,
                   e.fernsteuerbarkeitnb AS fernsteuerbar_nb,
                   e.fernsteuerbarkeitdv AS fernsteuerbar_dv,
                   e.anschlussanhoechstoderhochspannung AS hochspannung,
                   to_char(e.datumendgueltigestilllegung, 'YYYY-MM-DD') AS stillgelegt_am,
                   e.nabenhoehe::float8 AS nabenhoehe,
                   e.rotordurchmesser::float8 AS rotordurchmesser,
                   e.hersteller AS hersteller,
                   e.typenbezeichnung AS typ,
                   e.windanlandoderaufsee AS offshore,
                   e.buergerenergie AS buergerenergie,
                   e.gemeinde AS gemeinde,
                   e.gemeindeschluessel AS gemeindeschluessel,
                   to_char(e.datumletzteaktualisierung, 'YYYY-MM-DD') AS aktualisiert_am,
                   e.einspeisungsart AS einspeisungsart,
                   e.rotorblattenteisungssystem AS rotorblattenteisung,
                   e.nachtkennzeichnung AS nachtkennzeichnung,
                   e.auflageabschaltungleistungsbegrenzung AS auflage_leistungsbegrenzung,
                   e.auflagenabschaltungschallimmissionsschutznachts AS auflage_schall_nachts,
                   e.auflagenabschaltungschallimmissionsschutztagsueber AS auflage_schall_tagsueber,
                   e.auflagenabschaltungschattenwurf AS auflage_schattenwurf,
                   e.auflagenabschaltungtierschutz AS auflage_tierschutz,
                   e.auflagenabschaltungeiswurf AS auflage_eiswurf,
                   e.auflagenabschaltungsonstige AS auflage_sonstige,
                   e.wassertiefe::float8 AS wassertiefe
            FROM einheitenwind e
            LEFT JOIN marktakteure m ON m.mastrnummer = e.anlagenbetreibermastrnummer
            CROSS JOIN b
            WHERE ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326) && b.env4326
              AND e.breitengrad BETWEEN -90 AND 90
              AND e.laengengrad BETWEEN -180 AND 180
        )
        SELECT ST_AsMVT(f, 'wind') INTO result FROM f;
    END IF;
    RETURN coalesce(result, ''::bytea);
END
$$
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
SECURITY DEFINER
SET search_path = public, pg_temp;

COMMENT ON FUNCTION tiles.wind(integer, integer, integer) IS
    '{"description": "Windenergieanlagen aus dem MaStR"}';

-- Solaranlagen: gebündelt unterhalb von Zoom 10
CREATE OR REPLACE FUNCTION tiles.solar(z integer, x integer, y integer)
RETURNS bytea
AS $$
DECLARE
    result bytea;
BEGIN
    IF z < 0 OR z > 30 THEN
        RETURN ''::bytea;
    END IF;
    IF x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
        RETURN ''::bytea;
    END IF;
    -- below z10 a tile would carry thousands of individual points
    IF z < 10 THEN
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        g AS (
            -- cell size = tile width / 64, so the cells line up with the tile
            -- edges and a tile has at most 4096 features
            SELECT ST_XMin(env4326) AS lon0,
                   ST_YMin(env4326) AS lat0,
                   ST_XMax(env4326) AS lon1,
                   ST_YMax(env4326) AS lat1,
                   (ST_XMax(env4326) - ST_XMin(env4326)) / 64.0 AS dlon,
                   (ST_YMax(env4326) - ST_YMin(env4326)) / 64.0 AS dlat
            FROM b
        ),
        cells AS (
            -- the grid holds the units per ~1 km cell (db/grid.sql): a low
            -- zoom tile aggregates a few thousand rows instead of scanning the
            -- unit table, whose GiST index does random heap access
            SELECT floor(((c.cx + 0.5) * 0.01 - 180 - g.lon0) / g.dlon)::int AS cx,
                   floor(((c.cy + 0.5) * 0.01 - 90 - g.lat0) / g.dlat)::int AS cy,
                   sum(c.anzahl)::bigint AS anzahl,
                   sum(c.kw) AS kw
            FROM tiles.grid c, g
            WHERE c.layer = 'solar'
              AND c.cx BETWEEN floor((g.lon0 + 180) / 0.01)::int AND floor((g.lon1 + 180) / 0.01)::int
              AND c.cy BETWEEN floor((g.lat0 + 90) / 0.01)::int AND floor((g.lat1 + 90) / 0.01)::int
            GROUP BY 1, 2
        ),
        f AS (
            -- one projection per cell (at most 4096), not per unit
            SELECT ST_AsMVTGeom(
                       ST_Transform(
                           ST_SetSRID(ST_MakePoint(g.lon0 + (c.cx + 0.5) * g.dlon,
                                                   g.lat0 + (c.cy + 0.5) * g.dlat), 4326),
                           3857),
                       b.env
                   ) AS geom,
                   c.anzahl, c.kw
            FROM cells c, g, b
        )
        SELECT ST_AsMVT(f, 'solar') INTO result FROM f;
    ELSE
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        f AS (
            SELECT ST_AsMVTGeom(
                       ST_Transform(ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326), 3857),
                       b.env
                   ) AS geom,
                   e.einheitmastrnummer AS mastr_nr,
                   e.namestromerzeugungseinheit AS name,
                   e.namedessolarparks AS park,
                   e.nettonennleistung::float8 AS kw,
                   e.einheitbetriebsstatus AS status,
                   to_char(e.inbetriebnahmedatum, 'YYYY-MM-DD') AS inbetriebnahme,
                   e.bruttoleistung::float8 AS brutto_kw,
                   coalesce(m.firmenname, nullif(concat_ws(' ', m.marktakteurvorname, m.marktakteurnachname), '')) AS betreiber,
                   e.fernsteuerbarkeitnb AS fernsteuerbar_nb,
                   e.fernsteuerbarkeitdv AS fernsteuerbar_dv,
                   e.anschlussanhoechstoderhochspannung AS hochspannung,
                   to_char(e.datumendgueltigestilllegung, 'YYYY-MM-DD') AS stillgelegt_am,
                   e.artdersolaranlage AS art,
                   e.anzahlmodule AS module,
                   e.hauptausrichtung AS ausrichtung,
                   e.hauptausrichtungneigungswinkel AS neigung,
                   e.groessederinanspruchgenommenenflaecheinhektar::float8 AS flaeche_ha,
                   e.speicheramgleichenort AS speicher_am_ort,
                   e.buergerenergie AS buergerenergie,
                   e.gemeinde AS gemeinde,
                   e.gemeindeschluessel AS gemeindeschluessel,
                   to_char(e.datumletzteaktualisierung, 'YYYY-MM-DD') AS aktualisiert_am,
                   e.einspeisungsart AS einspeisungsart,
                   e.leistungsbegrenzung AS leistungsbegrenzung,
                   e.nutzungsbereich AS nutzungsbereich,
                   e.solaranlagenkategorie AS solaranlagenkategorie
            FROM einheitensolar e
            LEFT JOIN marktakteure m ON m.mastrnummer = e.anlagenbetreibermastrnummer
            CROSS JOIN b
            WHERE ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326) && b.env4326
              AND e.breitengrad BETWEEN -90 AND 90
              AND e.laengengrad BETWEEN -180 AND 180
        )
        SELECT ST_AsMVT(f, 'solar') INTO result FROM f;
    END IF;
    RETURN coalesce(result, ''::bytea);
END
$$
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
SECURITY DEFINER
SET search_path = public, pg_temp;

COMMENT ON FUNCTION tiles.solar(integer, integer, integer) IS
    '{"description": "Solaranlagen aus dem MaStR, unterhalb von Zoom 10 je Rasterzelle gebündelt (anzahl, kw)"}';

-- Biomasseanlagen
CREATE OR REPLACE FUNCTION tiles.biomasse(z integer, x integer, y integer)
RETURNS bytea
AS $$
DECLARE
    result bytea;
BEGIN
    IF z < 0 OR z > 30 THEN
        RETURN ''::bytea;
    END IF;
    IF x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
        RETURN ''::bytea;
    END IF;
    -- below z7 a tile would carry thousands of individual points
    IF z < 7 THEN
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        g AS (
            -- cell size = tile width / 64, so the cells line up with the tile
            -- edges and a tile has at most 4096 features
            SELECT ST_XMin(env4326) AS lon0,
                   ST_YMin(env4326) AS lat0,
                   ST_XMax(env4326) AS lon1,
                   ST_YMax(env4326) AS lat1,
                   (ST_XMax(env4326) - ST_XMin(env4326)) / 64.0 AS dlon,
                   (ST_YMax(env4326) - ST_YMin(env4326)) / 64.0 AS dlat
            FROM b
        ),
        cells AS (
            -- the grid holds the units per ~1 km cell (db/grid.sql): a low
            -- zoom tile aggregates a few thousand rows instead of scanning the
            -- unit table, whose GiST index does random heap access
            SELECT floor(((c.cx + 0.5) * 0.01 - 180 - g.lon0) / g.dlon)::int AS cx,
                   floor(((c.cy + 0.5) * 0.01 - 90 - g.lat0) / g.dlat)::int AS cy,
                   sum(c.anzahl)::bigint AS anzahl,
                   sum(c.kw) AS kw
            FROM tiles.grid c, g
            WHERE c.layer = 'biomasse'
              AND c.cx BETWEEN floor((g.lon0 + 180) / 0.01)::int AND floor((g.lon1 + 180) / 0.01)::int
              AND c.cy BETWEEN floor((g.lat0 + 90) / 0.01)::int AND floor((g.lat1 + 90) / 0.01)::int
            GROUP BY 1, 2
        ),
        f AS (
            -- one projection per cell (at most 4096), not per unit
            SELECT ST_AsMVTGeom(
                       ST_Transform(
                           ST_SetSRID(ST_MakePoint(g.lon0 + (c.cx + 0.5) * g.dlon,
                                                   g.lat0 + (c.cy + 0.5) * g.dlat), 4326),
                           3857),
                       b.env
                   ) AS geom,
                   c.anzahl, c.kw
            FROM cells c, g, b
        )
        SELECT ST_AsMVT(f, 'biomasse') INTO result FROM f;
    ELSE
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        f AS (
            SELECT ST_AsMVTGeom(
                       ST_Transform(ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326), 3857),
                       b.env
                   ) AS geom,
                   e.einheitmastrnummer AS mastr_nr,
                   e.namestromerzeugungseinheit AS name,
                   e.nettonennleistung::float8 AS kw,
                   e.einheitbetriebsstatus AS status,
                   to_char(e.inbetriebnahmedatum, 'YYYY-MM-DD') AS inbetriebnahme,
                   e.bruttoleistung::float8 AS brutto_kw,
                   coalesce(m.firmenname, nullif(concat_ws(' ', m.marktakteurvorname, m.marktakteurnachname), '')) AS betreiber,
                   e.fernsteuerbarkeitnb AS fernsteuerbar_nb,
                   e.fernsteuerbarkeitdv AS fernsteuerbar_dv,
                   e.anschlussanhoechstoderhochspannung AS hochspannung,
                   to_char(e.datumendgueltigestilllegung, 'YYYY-MM-DD') AS stillgelegt_am,
                   e.hauptbrennstoff AS brennstoff,
                   e.biomasseart AS biomasseart,
                   e.technologie AS technologie,
                   e.gemeinde AS gemeinde,
                   e.gemeindeschluessel AS gemeindeschluessel,
                   to_char(e.datumletzteaktualisierung, 'YYYY-MM-DD') AS aktualisiert_am,
                   e.einspeisungsart AS einspeisungsart,
                   e.netzreservezugeordnet AS netzreserve,
                   e.kapazitaetsreservezugeordnet AS kapazitaetsreserve
            FROM einheitenbiomasse e
            LEFT JOIN marktakteure m ON m.mastrnummer = e.anlagenbetreibermastrnummer
            CROSS JOIN b
            WHERE ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326) && b.env4326
              AND e.breitengrad BETWEEN -90 AND 90
              AND e.laengengrad BETWEEN -180 AND 180
        )
        SELECT ST_AsMVT(f, 'biomasse') INTO result FROM f;
    END IF;
    RETURN coalesce(result, ''::bytea);
END
$$
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
SECURITY DEFINER
SET search_path = public, pg_temp;

COMMENT ON FUNCTION tiles.biomasse(integer, integer, integer) IS
    '{"description": "Biomasseanlagen aus dem MaStR"}';

-- Wasserkraftanlagen
CREATE OR REPLACE FUNCTION tiles.wasser(z integer, x integer, y integer)
RETURNS bytea
AS $$
DECLARE
    result bytea;
BEGIN
    IF z < 0 OR z > 30 THEN
        RETURN ''::bytea;
    END IF;
    IF x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
        RETURN ''::bytea;
    END IF;
    -- below z7 a tile would carry thousands of individual points
    IF z < 7 THEN
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        g AS (
            -- cell size = tile width / 64, so the cells line up with the tile
            -- edges and a tile has at most 4096 features
            SELECT ST_XMin(env4326) AS lon0,
                   ST_YMin(env4326) AS lat0,
                   ST_XMax(env4326) AS lon1,
                   ST_YMax(env4326) AS lat1,
                   (ST_XMax(env4326) - ST_XMin(env4326)) / 64.0 AS dlon,
                   (ST_YMax(env4326) - ST_YMin(env4326)) / 64.0 AS dlat
            FROM b
        ),
        cells AS (
            -- the grid holds the units per ~1 km cell (db/grid.sql): a low
            -- zoom tile aggregates a few thousand rows instead of scanning the
            -- unit table, whose GiST index does random heap access
            SELECT floor(((c.cx + 0.5) * 0.01 - 180 - g.lon0) / g.dlon)::int AS cx,
                   floor(((c.cy + 0.5) * 0.01 - 90 - g.lat0) / g.dlat)::int AS cy,
                   sum(c.anzahl)::bigint AS anzahl,
                   sum(c.kw) AS kw
            FROM tiles.grid c, g
            WHERE c.layer = 'wasser'
              AND c.cx BETWEEN floor((g.lon0 + 180) / 0.01)::int AND floor((g.lon1 + 180) / 0.01)::int
              AND c.cy BETWEEN floor((g.lat0 + 90) / 0.01)::int AND floor((g.lat1 + 90) / 0.01)::int
            GROUP BY 1, 2
        ),
        f AS (
            -- one projection per cell (at most 4096), not per unit
            SELECT ST_AsMVTGeom(
                       ST_Transform(
                           ST_SetSRID(ST_MakePoint(g.lon0 + (c.cx + 0.5) * g.dlon,
                                                   g.lat0 + (c.cy + 0.5) * g.dlat), 4326),
                           3857),
                       b.env
                   ) AS geom,
                   c.anzahl, c.kw
            FROM cells c, g, b
        )
        SELECT ST_AsMVT(f, 'wasser') INTO result FROM f;
    ELSE
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        f AS (
            SELECT ST_AsMVTGeom(
                       ST_Transform(ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326), 3857),
                       b.env
                   ) AS geom,
                   e.einheitmastrnummer AS mastr_nr,
                   e.namestromerzeugungseinheit AS name,
                   e.namekraftwerk AS park,
                   e.nettonennleistung::float8 AS kw,
                   e.einheitbetriebsstatus AS status,
                   to_char(e.inbetriebnahmedatum, 'YYYY-MM-DD') AS inbetriebnahme,
                   e.bruttoleistung::float8 AS brutto_kw,
                   coalesce(m.firmenname, nullif(concat_ws(' ', m.marktakteurvorname, m.marktakteurnachname), '')) AS betreiber,
                   e.fernsteuerbarkeitnb AS fernsteuerbar_nb,
                   e.fernsteuerbarkeitdv AS fernsteuerbar_dv,
                   e.anschlussanhoechstoderhochspannung AS hochspannung,
                   to_char(e.datumendgueltigestilllegung, 'YYYY-MM-DD') AS stillgelegt_am,
                   e.artderwasserkraftanlage AS art,
                   e.gemeinde AS gemeinde,
                   e.gemeindeschluessel AS gemeindeschluessel,
                   to_char(e.datumletzteaktualisierung, 'YYYY-MM-DD') AS aktualisiert_am,
                   e.einspeisungsart AS einspeisungsart,
                   e.netzreservezugeordnet AS netzreserve,
                   e.kapazitaetsreservezugeordnet AS kapazitaetsreserve,
                   e.artdeszuflusses AS art_des_zuflusses,
                   e.minderungstromerzeugung AS minderung_stromerzeugung,
                   e.bestandteilgrenzkraftwerk AS bestandteil_grenzkraftwerk
            FROM einheitenwasser e
            LEFT JOIN marktakteure m ON m.mastrnummer = e.anlagenbetreibermastrnummer
            CROSS JOIN b
            WHERE ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326) && b.env4326
              AND e.breitengrad BETWEEN -90 AND 90
              AND e.laengengrad BETWEEN -180 AND 180
        )
        SELECT ST_AsMVT(f, 'wasser') INTO result FROM f;
    END IF;
    RETURN coalesce(result, ''::bytea);
END
$$
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
SECURITY DEFINER
SET search_path = public, pg_temp;

COMMENT ON FUNCTION tiles.wasser(integer, integer, integer) IS
    '{"description": "Wasserkraftanlagen aus dem MaStR"}';

-- Geothermie, Grubengas, Druckentspannung
CREATE OR REPLACE FUNCTION tiles.geothermie(z integer, x integer, y integer)
RETURNS bytea
AS $$
DECLARE
    result bytea;
BEGIN
    IF z < 0 OR z > 30 THEN
        RETURN ''::bytea;
    END IF;
    IF x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
        RETURN ''::bytea;
    END IF;
    -- below z7 a tile would carry thousands of individual points
    IF z < 7 THEN
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        g AS (
            -- cell size = tile width / 64, so the cells line up with the tile
            -- edges and a tile has at most 4096 features
            SELECT ST_XMin(env4326) AS lon0,
                   ST_YMin(env4326) AS lat0,
                   ST_XMax(env4326) AS lon1,
                   ST_YMax(env4326) AS lat1,
                   (ST_XMax(env4326) - ST_XMin(env4326)) / 64.0 AS dlon,
                   (ST_YMax(env4326) - ST_YMin(env4326)) / 64.0 AS dlat
            FROM b
        ),
        cells AS (
            -- the grid holds the units per ~1 km cell (db/grid.sql): a low
            -- zoom tile aggregates a few thousand rows instead of scanning the
            -- unit table, whose GiST index does random heap access
            SELECT floor(((c.cx + 0.5) * 0.01 - 180 - g.lon0) / g.dlon)::int AS cx,
                   floor(((c.cy + 0.5) * 0.01 - 90 - g.lat0) / g.dlat)::int AS cy,
                   sum(c.anzahl)::bigint AS anzahl,
                   sum(c.kw) AS kw
            FROM tiles.grid c, g
            WHERE c.layer = 'geothermie'
              AND c.cx BETWEEN floor((g.lon0 + 180) / 0.01)::int AND floor((g.lon1 + 180) / 0.01)::int
              AND c.cy BETWEEN floor((g.lat0 + 90) / 0.01)::int AND floor((g.lat1 + 90) / 0.01)::int
            GROUP BY 1, 2
        ),
        f AS (
            -- one projection per cell (at most 4096), not per unit
            SELECT ST_AsMVTGeom(
                       ST_Transform(
                           ST_SetSRID(ST_MakePoint(g.lon0 + (c.cx + 0.5) * g.dlon,
                                                   g.lat0 + (c.cy + 0.5) * g.dlat), 4326),
                           3857),
                       b.env
                   ) AS geom,
                   c.anzahl, c.kw
            FROM cells c, g, b
        )
        SELECT ST_AsMVT(f, 'geothermie') INTO result FROM f;
    ELSE
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        f AS (
            SELECT ST_AsMVTGeom(
                       ST_Transform(ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326), 3857),
                       b.env
                   ) AS geom,
                   e.einheitmastrnummer AS mastr_nr,
                   e.namestromerzeugungseinheit AS name,
                   e.nettonennleistung::float8 AS kw,
                   e.einheitbetriebsstatus AS status,
                   to_char(e.inbetriebnahmedatum, 'YYYY-MM-DD') AS inbetriebnahme,
                   e.bruttoleistung::float8 AS brutto_kw,
                   coalesce(m.firmenname, nullif(concat_ws(' ', m.marktakteurvorname, m.marktakteurnachname), '')) AS betreiber,
                   e.fernsteuerbarkeitnb AS fernsteuerbar_nb,
                   e.fernsteuerbarkeitdv AS fernsteuerbar_dv,
                   e.anschlussanhoechstoderhochspannung AS hochspannung,
                   to_char(e.datumendgueltigestilllegung, 'YYYY-MM-DD') AS stillgelegt_am,
                   e.technologie AS technologie,
                   e.gemeinde AS gemeinde,
                   e.gemeindeschluessel AS gemeindeschluessel,
                   to_char(e.datumletzteaktualisierung, 'YYYY-MM-DD') AS aktualisiert_am,
                   e.einspeisungsart AS einspeisungsart,
                   e.netzreservezugeordnet AS netzreserve,
                   e.kapazitaetsreservezugeordnet AS kapazitaetsreserve
            FROM einheitengeothermiegrubengasdruckentspannung e
            LEFT JOIN marktakteure m ON m.mastrnummer = e.anlagenbetreibermastrnummer
            CROSS JOIN b
            WHERE ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326) && b.env4326
              AND e.breitengrad BETWEEN -90 AND 90
              AND e.laengengrad BETWEEN -180 AND 180
        )
        SELECT ST_AsMVT(f, 'geothermie') INTO result FROM f;
    END IF;
    RETURN coalesce(result, ''::bytea);
END
$$
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
SECURITY DEFINER
SET search_path = public, pg_temp;

COMMENT ON FUNCTION tiles.geothermie(integer, integer, integer) IS
    '{"description": "Geothermie-, Grubengas- und Druckentspannungsanlagen aus dem MaStR"}';

-- Stromspeicher: gebündelt unterhalb von Zoom 10
CREATE OR REPLACE FUNCTION tiles.stromspeicher(z integer, x integer, y integer)
RETURNS bytea
AS $$
DECLARE
    result bytea;
BEGIN
    IF z < 0 OR z > 30 THEN
        RETURN ''::bytea;
    END IF;
    IF x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
        RETURN ''::bytea;
    END IF;
    -- below z10 a tile would carry thousands of individual points
    IF z < 10 THEN
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        g AS (
            -- cell size = tile width / 64, so the cells line up with the tile
            -- edges and a tile has at most 4096 features
            SELECT ST_XMin(env4326) AS lon0,
                   ST_YMin(env4326) AS lat0,
                   ST_XMax(env4326) AS lon1,
                   ST_YMax(env4326) AS lat1,
                   (ST_XMax(env4326) - ST_XMin(env4326)) / 64.0 AS dlon,
                   (ST_YMax(env4326) - ST_YMin(env4326)) / 64.0 AS dlat
            FROM b
        ),
        cells AS (
            -- the grid holds the units per ~1 km cell (db/grid.sql): a low
            -- zoom tile aggregates a few thousand rows instead of scanning the
            -- unit table, whose GiST index does random heap access
            SELECT floor(((c.cx + 0.5) * 0.01 - 180 - g.lon0) / g.dlon)::int AS cx,
                   floor(((c.cy + 0.5) * 0.01 - 90 - g.lat0) / g.dlat)::int AS cy,
                   sum(c.anzahl)::bigint AS anzahl,
                   sum(c.kw) AS kw
            FROM tiles.grid c, g
            WHERE c.layer = 'stromspeicher'
              AND c.cx BETWEEN floor((g.lon0 + 180) / 0.01)::int AND floor((g.lon1 + 180) / 0.01)::int
              AND c.cy BETWEEN floor((g.lat0 + 90) / 0.01)::int AND floor((g.lat1 + 90) / 0.01)::int
            GROUP BY 1, 2
        ),
        f AS (
            -- one projection per cell (at most 4096), not per unit
            SELECT ST_AsMVTGeom(
                       ST_Transform(
                           ST_SetSRID(ST_MakePoint(g.lon0 + (c.cx + 0.5) * g.dlon,
                                                   g.lat0 + (c.cy + 0.5) * g.dlat), 4326),
                           3857),
                       b.env
                   ) AS geom,
                   c.anzahl, c.kw
            FROM cells c, g, b
        )
        SELECT ST_AsMVT(f, 'stromspeicher') INTO result FROM f;
    ELSE
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        f AS (
            SELECT ST_AsMVTGeom(
                       ST_Transform(ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326), 3857),
                       b.env
                   ) AS geom,
                   e.einheitmastrnummer AS mastr_nr,
                   e.namestromerzeugungseinheit AS name,
                   e.nettonennleistung::float8 AS kw,
                   e.einheitbetriebsstatus AS status,
                   to_char(e.inbetriebnahmedatum, 'YYYY-MM-DD') AS inbetriebnahme,
                   e.bruttoleistung::float8 AS brutto_kw,
                   coalesce(m.firmenname, nullif(concat_ws(' ', m.marktakteurvorname, m.marktakteurnachname), '')) AS betreiber,
                   e.fernsteuerbarkeitnb AS fernsteuerbar_nb,
                   e.fernsteuerbarkeitdv AS fernsteuerbar_dv,
                   e.anschlussanhoechstoderhochspannung AS hochspannung,
                   to_char(e.datumendgueltigestilllegung, 'YYYY-MM-DD') AS stillgelegt_am,
                   e.batterietechnologie AS batterietechnologie,
                   e.acdckoppelung AS acdc,
                   e.einsatzort AS einsatzort,
                   e.pumpspeichertechnologie AS pumpspeicher,
                   e.notstromaggregat AS notstrom,
                   e.zugeordnentewirkleistungwechselrichter::float8 AS wechselrichter,
                   e.gemeinde AS gemeinde,
                   e.gemeindeschluessel AS gemeindeschluessel,
                   to_char(e.datumletzteaktualisierung, 'YYYY-MM-DD') AS aktualisiert_am,
                   e.einspeisungsart AS einspeisungsart,
                   e.netzreservezugeordnet AS netzreserve,
                   e.kapazitaetsreservezugeordnet AS kapazitaetsreserve,
                   e.technologie AS technologie,
                   e.eeganlagentyp AS eeg_anlagentyp,
                   e.pumpbetriebleistungsaufnahme::float8 AS pumpbetrieb_leistungsaufnahme
            FROM einheitenstromspeicher e
            LEFT JOIN marktakteure m ON m.mastrnummer = e.anlagenbetreibermastrnummer
            CROSS JOIN b
            WHERE ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326) && b.env4326
              AND e.breitengrad BETWEEN -90 AND 90
              AND e.laengengrad BETWEEN -180 AND 180
        )
        SELECT ST_AsMVT(f, 'stromspeicher') INTO result FROM f;
    END IF;
    RETURN coalesce(result, ''::bytea);
END
$$
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
SECURITY DEFINER
SET search_path = public, pg_temp;

COMMENT ON FUNCTION tiles.stromspeicher(integer, integer, integer) IS
    '{"description": "Stromspeicher aus dem MaStR, unterhalb von Zoom 10 je Rasterzelle gebündelt (anzahl, kw)"}';

-- Kernkraftwerke
CREATE OR REPLACE FUNCTION tiles.kernkraft(z integer, x integer, y integer)
RETURNS bytea
AS $$
DECLARE
    result bytea;
BEGIN
    IF z < 0 OR z > 30 THEN
        RETURN ''::bytea;
    END IF;
    IF x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
        RETURN ''::bytea;
    END IF;
    -- below z7 a tile would carry thousands of individual points
    IF z < 7 THEN
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        g AS (
            -- cell size = tile width / 64, so the cells line up with the tile
            -- edges and a tile has at most 4096 features
            SELECT ST_XMin(env4326) AS lon0,
                   ST_YMin(env4326) AS lat0,
                   ST_XMax(env4326) AS lon1,
                   ST_YMax(env4326) AS lat1,
                   (ST_XMax(env4326) - ST_XMin(env4326)) / 64.0 AS dlon,
                   (ST_YMax(env4326) - ST_YMin(env4326)) / 64.0 AS dlat
            FROM b
        ),
        cells AS (
            -- the grid holds the units per ~1 km cell (db/grid.sql): a low
            -- zoom tile aggregates a few thousand rows instead of scanning the
            -- unit table, whose GiST index does random heap access
            SELECT floor(((c.cx + 0.5) * 0.01 - 180 - g.lon0) / g.dlon)::int AS cx,
                   floor(((c.cy + 0.5) * 0.01 - 90 - g.lat0) / g.dlat)::int AS cy,
                   sum(c.anzahl)::bigint AS anzahl,
                   sum(c.kw) AS kw
            FROM tiles.grid c, g
            WHERE c.layer = 'kernkraft'
              AND c.cx BETWEEN floor((g.lon0 + 180) / 0.01)::int AND floor((g.lon1 + 180) / 0.01)::int
              AND c.cy BETWEEN floor((g.lat0 + 90) / 0.01)::int AND floor((g.lat1 + 90) / 0.01)::int
            GROUP BY 1, 2
        ),
        f AS (
            -- one projection per cell (at most 4096), not per unit
            SELECT ST_AsMVTGeom(
                       ST_Transform(
                           ST_SetSRID(ST_MakePoint(g.lon0 + (c.cx + 0.5) * g.dlon,
                                                   g.lat0 + (c.cy + 0.5) * g.dlat), 4326),
                           3857),
                       b.env
                   ) AS geom,
                   c.anzahl, c.kw
            FROM cells c, g, b
        )
        SELECT ST_AsMVT(f, 'kernkraft') INTO result FROM f;
    ELSE
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        f AS (
            SELECT ST_AsMVTGeom(
                       ST_Transform(ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326), 3857),
                       b.env
                   ) AS geom,
                   e.einheitmastrnummer AS mastr_nr,
                   e.namestromerzeugungseinheit AS name,
                   e.namekraftwerk AS park,
                   e.nettonennleistung::float8 AS kw,
                   e.einheitbetriebsstatus AS status,
                   to_char(e.inbetriebnahmedatum, 'YYYY-MM-DD') AS inbetriebnahme,
                   e.bruttoleistung::float8 AS brutto_kw,
                   coalesce(m.firmenname, nullif(concat_ws(' ', m.marktakteurvorname, m.marktakteurnachname), '')) AS betreiber,
                   e.fernsteuerbarkeitnb AS fernsteuerbar_nb,
                   e.fernsteuerbarkeitdv AS fernsteuerbar_dv,
                   e.anschlussanhoechstoderhochspannung AS hochspannung,
                   to_char(e.datumendgueltigestilllegung, 'YYYY-MM-DD') AS stillgelegt_am,
                   e.namekraftwerksblock AS block,
                   e.technologie AS technologie,
                   e.gemeinde AS gemeinde,
                   e.gemeindeschluessel AS gemeindeschluessel,
                   to_char(e.datumletzteaktualisierung, 'YYYY-MM-DD') AS aktualisiert_am,
                   e.einspeisungsart AS einspeisungsart,
                   e.netzreservezugeordnet AS netzreserve,
                   e.kapazitaetsreservezugeordnet AS kapazitaetsreserve
            FROM einheitenkernkraft e
            LEFT JOIN marktakteure m ON m.mastrnummer = e.anlagenbetreibermastrnummer
            CROSS JOIN b
            WHERE ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326) && b.env4326
              AND e.breitengrad BETWEEN -90 AND 90
              AND e.laengengrad BETWEEN -180 AND 180
        )
        SELECT ST_AsMVT(f, 'kernkraft') INTO result FROM f;
    END IF;
    RETURN coalesce(result, ''::bytea);
END
$$
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
SECURITY DEFINER
SET search_path = public, pg_temp;

COMMENT ON FUNCTION tiles.kernkraft(integer, integer, integer) IS
    '{"description": "Kernkraftwerke aus dem MaStR"}';

-- Verbrennungsanlagen
CREATE OR REPLACE FUNCTION tiles.verbrennung(z integer, x integer, y integer)
RETURNS bytea
AS $$
DECLARE
    result bytea;
BEGIN
    IF z < 0 OR z > 30 THEN
        RETURN ''::bytea;
    END IF;
    IF x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
        RETURN ''::bytea;
    END IF;
    -- below z7 a tile would carry thousands of individual points
    IF z < 7 THEN
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        g AS (
            -- cell size = tile width / 64, so the cells line up with the tile
            -- edges and a tile has at most 4096 features
            SELECT ST_XMin(env4326) AS lon0,
                   ST_YMin(env4326) AS lat0,
                   ST_XMax(env4326) AS lon1,
                   ST_YMax(env4326) AS lat1,
                   (ST_XMax(env4326) - ST_XMin(env4326)) / 64.0 AS dlon,
                   (ST_YMax(env4326) - ST_YMin(env4326)) / 64.0 AS dlat
            FROM b
        ),
        cells AS (
            -- the grid holds the units per ~1 km cell (db/grid.sql): a low
            -- zoom tile aggregates a few thousand rows instead of scanning the
            -- unit table, whose GiST index does random heap access
            SELECT floor(((c.cx + 0.5) * 0.01 - 180 - g.lon0) / g.dlon)::int AS cx,
                   floor(((c.cy + 0.5) * 0.01 - 90 - g.lat0) / g.dlat)::int AS cy,
                   sum(c.anzahl)::bigint AS anzahl,
                   sum(c.kw) AS kw
            FROM tiles.grid c, g
            WHERE c.layer = 'verbrennung'
              AND c.cx BETWEEN floor((g.lon0 + 180) / 0.01)::int AND floor((g.lon1 + 180) / 0.01)::int
              AND c.cy BETWEEN floor((g.lat0 + 90) / 0.01)::int AND floor((g.lat1 + 90) / 0.01)::int
            GROUP BY 1, 2
        ),
        f AS (
            -- one projection per cell (at most 4096), not per unit
            SELECT ST_AsMVTGeom(
                       ST_Transform(
                           ST_SetSRID(ST_MakePoint(g.lon0 + (c.cx + 0.5) * g.dlon,
                                                   g.lat0 + (c.cy + 0.5) * g.dlat), 4326),
                           3857),
                       b.env
                   ) AS geom,
                   c.anzahl, c.kw
            FROM cells c, g, b
        )
        SELECT ST_AsMVT(f, 'verbrennung') INTO result FROM f;
    ELSE
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        f AS (
            SELECT ST_AsMVTGeom(
                       ST_Transform(ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326), 3857),
                       b.env
                   ) AS geom,
                   e.einheitmastrnummer AS mastr_nr,
                   e.namestromerzeugungseinheit AS name,
                   e.namekraftwerk AS park,
                   e.nettonennleistung::float8 AS kw,
                   e.einheitbetriebsstatus AS status,
                   to_char(e.inbetriebnahmedatum, 'YYYY-MM-DD') AS inbetriebnahme,
                   e.bruttoleistung::float8 AS brutto_kw,
                   coalesce(m.firmenname, nullif(concat_ws(' ', m.marktakteurvorname, m.marktakteurnachname), '')) AS betreiber,
                   e.fernsteuerbarkeitnb AS fernsteuerbar_nb,
                   e.fernsteuerbarkeitdv AS fernsteuerbar_dv,
                   e.anschlussanhoechstoderhochspannung AS hochspannung,
                   to_char(e.datumendgueltigestilllegung, 'YYYY-MM-DD') AS stillgelegt_am,
                   e.hauptbrennstoff AS brennstoff,
                   e.anlageistimkombibetrieb AS kombibetrieb,
                   e.einsatzort AS einsatzort,
                   e.notstromaggregat AS notstrom,
                   e.namekraftwerksblock AS block,
                   e.gemeinde AS gemeinde,
                   e.gemeindeschluessel AS gemeindeschluessel,
                   to_char(e.datumletzteaktualisierung, 'YYYY-MM-DD') AS aktualisiert_am,
                   e.einspeisungsart AS einspeisungsart,
                   e.netzreservezugeordnet AS netzreserve,
                   e.kapazitaetsreservezugeordnet AS kapazitaetsreserve,
                   e.weitererhauptbrennstoff AS weiterer_hauptbrennstoff,
                   e.technologie AS technologie,
                   to_char(e.datumbaubeginn, 'YYYY-MM-DD') AS datum_baubeginn,
                   to_char(e.sicherheitsbereitschaftabdatum, 'YYYY-MM-DD') AS sicherheitsbereitschaft_ab
            FROM einheitenverbrennung e
            LEFT JOIN marktakteure m ON m.mastrnummer = e.anlagenbetreibermastrnummer
            CROSS JOIN b
            WHERE ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326) && b.env4326
              AND e.breitengrad BETWEEN -90 AND 90
              AND e.laengengrad BETWEEN -180 AND 180
        )
        SELECT ST_AsMVT(f, 'verbrennung') INTO result FROM f;
    END IF;
    RETURN coalesce(result, ''::bytea);
END
$$
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
SECURITY DEFINER
SET search_path = public, pg_temp;

COMMENT ON FUNCTION tiles.verbrennung(integer, integer, integer) IS
    '{"description": "Verbrennungsanlagen aus dem MaStR"}';

-- Gaserzeuger (die Leistungsspalte heisst hier Erzeugungsleistung)
CREATE OR REPLACE FUNCTION tiles.gaserzeuger(z integer, x integer, y integer)
RETURNS bytea
AS $$
DECLARE
    result bytea;
BEGIN
    IF z < 0 OR z > 30 THEN
        RETURN ''::bytea;
    END IF;
    IF x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
        RETURN ''::bytea;
    END IF;
    -- below z7 a tile would carry thousands of individual points
    IF z < 7 THEN
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        g AS (
            -- cell size = tile width / 64, so the cells line up with the tile
            -- edges and a tile has at most 4096 features
            SELECT ST_XMin(env4326) AS lon0,
                   ST_YMin(env4326) AS lat0,
                   ST_XMax(env4326) AS lon1,
                   ST_YMax(env4326) AS lat1,
                   (ST_XMax(env4326) - ST_XMin(env4326)) / 64.0 AS dlon,
                   (ST_YMax(env4326) - ST_YMin(env4326)) / 64.0 AS dlat
            FROM b
        ),
        cells AS (
            -- the grid holds the units per ~1 km cell (db/grid.sql): a low
            -- zoom tile aggregates a few thousand rows instead of scanning the
            -- unit table, whose GiST index does random heap access
            SELECT floor(((c.cx + 0.5) * 0.01 - 180 - g.lon0) / g.dlon)::int AS cx,
                   floor(((c.cy + 0.5) * 0.01 - 90 - g.lat0) / g.dlat)::int AS cy,
                   sum(c.anzahl)::bigint AS anzahl,
                   sum(c.kw) AS kw
            FROM tiles.grid c, g
            WHERE c.layer = 'gaserzeuger'
              AND c.cx BETWEEN floor((g.lon0 + 180) / 0.01)::int AND floor((g.lon1 + 180) / 0.01)::int
              AND c.cy BETWEEN floor((g.lat0 + 90) / 0.01)::int AND floor((g.lat1 + 90) / 0.01)::int
            GROUP BY 1, 2
        ),
        f AS (
            -- one projection per cell (at most 4096), not per unit
            SELECT ST_AsMVTGeom(
                       ST_Transform(
                           ST_SetSRID(ST_MakePoint(g.lon0 + (c.cx + 0.5) * g.dlon,
                                                   g.lat0 + (c.cy + 0.5) * g.dlat), 4326),
                           3857),
                       b.env
                   ) AS geom,
                   c.anzahl, c.kw
            FROM cells c, g, b
        )
        SELECT ST_AsMVT(f, 'gaserzeuger') INTO result FROM f;
    ELSE
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        f AS (
            SELECT ST_AsMVTGeom(
                       ST_Transform(ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326), 3857),
                       b.env
                   ) AS geom,
                   e.einheitmastrnummer AS mastr_nr,
                   e.namegaserzeugungseinheit AS name,
                   e.erzeugungsleistung::float8 AS kw,
                   e.einheitbetriebsstatus AS status,
                   to_char(e.inbetriebnahmedatum, 'YYYY-MM-DD') AS inbetriebnahme,
                   coalesce(m.firmenname, nullif(concat_ws(' ', m.marktakteurvorname, m.marktakteurnachname), '')) AS betreiber,
                   to_char(e.datumendgueltigestilllegung, 'YYYY-MM-DD') AS stillgelegt_am,
                   e.technologie AS technologie,
                   e.gemeinde AS gemeinde,
                   e.gemeindeschluessel AS gemeindeschluessel,
                   to_char(e.datumletzteaktualisierung, 'YYYY-MM-DD') AS aktualisiert_am
            FROM einheitengaserzeuger e
            LEFT JOIN marktakteure m ON m.mastrnummer = e.anlagenbetreibermastrnummer
            CROSS JOIN b
            WHERE ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326) && b.env4326
              AND e.breitengrad BETWEEN -90 AND 90
              AND e.laengengrad BETWEEN -180 AND 180
        )
        SELECT ST_AsMVT(f, 'gaserzeuger') INTO result FROM f;
    END IF;
    RETURN coalesce(result, ''::bytea);
END
$$
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
SECURITY DEFINER
SET search_path = public, pg_temp;

COMMENT ON FUNCTION tiles.gaserzeuger(integer, integer, integer) IS
    '{"description": "Gaserzeuger aus dem MaStR"}';

-- Gasspeicher (Leistung: maximale Einspeicherleistung)
CREATE OR REPLACE FUNCTION tiles.gasspeicher(z integer, x integer, y integer)
RETURNS bytea
AS $$
DECLARE
    result bytea;
BEGIN
    IF z < 0 OR z > 30 THEN
        RETURN ''::bytea;
    END IF;
    IF x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
        RETURN ''::bytea;
    END IF;
    -- below z7 a tile would carry thousands of individual points
    IF z < 7 THEN
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        g AS (
            -- cell size = tile width / 64, so the cells line up with the tile
            -- edges and a tile has at most 4096 features
            SELECT ST_XMin(env4326) AS lon0,
                   ST_YMin(env4326) AS lat0,
                   ST_XMax(env4326) AS lon1,
                   ST_YMax(env4326) AS lat1,
                   (ST_XMax(env4326) - ST_XMin(env4326)) / 64.0 AS dlon,
                   (ST_YMax(env4326) - ST_YMin(env4326)) / 64.0 AS dlat
            FROM b
        ),
        cells AS (
            -- the grid holds the units per ~1 km cell (db/grid.sql): a low
            -- zoom tile aggregates a few thousand rows instead of scanning the
            -- unit table, whose GiST index does random heap access
            SELECT floor(((c.cx + 0.5) * 0.01 - 180 - g.lon0) / g.dlon)::int AS cx,
                   floor(((c.cy + 0.5) * 0.01 - 90 - g.lat0) / g.dlat)::int AS cy,
                   sum(c.anzahl)::bigint AS anzahl,
                   sum(c.kw) AS kw
            FROM tiles.grid c, g
            WHERE c.layer = 'gasspeicher'
              AND c.cx BETWEEN floor((g.lon0 + 180) / 0.01)::int AND floor((g.lon1 + 180) / 0.01)::int
              AND c.cy BETWEEN floor((g.lat0 + 90) / 0.01)::int AND floor((g.lat1 + 90) / 0.01)::int
            GROUP BY 1, 2
        ),
        f AS (
            -- one projection per cell (at most 4096), not per unit
            SELECT ST_AsMVTGeom(
                       ST_Transform(
                           ST_SetSRID(ST_MakePoint(g.lon0 + (c.cx + 0.5) * g.dlon,
                                                   g.lat0 + (c.cy + 0.5) * g.dlat), 4326),
                           3857),
                       b.env
                   ) AS geom,
                   c.anzahl, c.kw
            FROM cells c, g, b
        )
        SELECT ST_AsMVT(f, 'gasspeicher') INTO result FROM f;
    ELSE
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        f AS (
            SELECT ST_AsMVTGeom(
                       ST_Transform(ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326), 3857),
                       b.env
                   ) AS geom,
                   e.einheitmastrnummer AS mastr_nr,
                   e.namegasspeicher AS name,
                   e.maximaleeinspeicherleistung::float8 AS kw,
                   e.einheitbetriebsstatus AS status,
                   to_char(e.inbetriebnahmedatum, 'YYYY-MM-DD') AS inbetriebnahme,
                   coalesce(m.firmenname, nullif(concat_ws(' ', m.marktakteurvorname, m.marktakteurnachname), '')) AS betreiber,
                   to_char(e.datumendgueltigestilllegung, 'YYYY-MM-DD') AS stillgelegt_am,
                   e.speicherart AS speicherart,
                   e.maximalnutzbaresarbeitsgasvolumen::float8 AS arbeitsgasvolumen,
                   e.maximaleausspeicherleistung::float8 AS ausspeicherleistung,
                   e.gemeinde AS gemeinde,
                   e.gemeindeschluessel AS gemeindeschluessel,
                   to_char(e.datumletzteaktualisierung, 'YYYY-MM-DD') AS aktualisiert_am,
                   e.durchschnittlicherbrennwert::float8 AS brennwert
            FROM einheitengasspeicher e
            LEFT JOIN marktakteure m ON m.mastrnummer = e.anlagenbetreibermastrnummer
            CROSS JOIN b
            WHERE ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326) && b.env4326
              AND e.breitengrad BETWEEN -90 AND 90
              AND e.laengengrad BETWEEN -180 AND 180
        )
        SELECT ST_AsMVT(f, 'gasspeicher') INTO result FROM f;
    END IF;
    RETURN coalesce(result, ''::bytea);
END
$$
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
SECURITY DEFINER
SET search_path = public, pg_temp;

COMMENT ON FUNCTION tiles.gasspeicher(integer, integer, integer) IS
    '{"description": "Gasspeicher aus dem MaStR"}';

-- Gasverbraucher (Leistung: maximale Gasbezugsleistung)
CREATE OR REPLACE FUNCTION tiles.gasverbraucher(z integer, x integer, y integer)
RETURNS bytea
AS $$
DECLARE
    result bytea;
BEGIN
    IF z < 0 OR z > 30 THEN
        RETURN ''::bytea;
    END IF;
    IF x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
        RETURN ''::bytea;
    END IF;
    -- below z7 a tile would carry thousands of individual points
    IF z < 7 THEN
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        g AS (
            -- cell size = tile width / 64, so the cells line up with the tile
            -- edges and a tile has at most 4096 features
            SELECT ST_XMin(env4326) AS lon0,
                   ST_YMin(env4326) AS lat0,
                   ST_XMax(env4326) AS lon1,
                   ST_YMax(env4326) AS lat1,
                   (ST_XMax(env4326) - ST_XMin(env4326)) / 64.0 AS dlon,
                   (ST_YMax(env4326) - ST_YMin(env4326)) / 64.0 AS dlat
            FROM b
        ),
        cells AS (
            -- the grid holds the units per ~1 km cell (db/grid.sql): a low
            -- zoom tile aggregates a few thousand rows instead of scanning the
            -- unit table, whose GiST index does random heap access
            SELECT floor(((c.cx + 0.5) * 0.01 - 180 - g.lon0) / g.dlon)::int AS cx,
                   floor(((c.cy + 0.5) * 0.01 - 90 - g.lat0) / g.dlat)::int AS cy,
                   sum(c.anzahl)::bigint AS anzahl,
                   sum(c.kw) AS kw
            FROM tiles.grid c, g
            WHERE c.layer = 'gasverbraucher'
              AND c.cx BETWEEN floor((g.lon0 + 180) / 0.01)::int AND floor((g.lon1 + 180) / 0.01)::int
              AND c.cy BETWEEN floor((g.lat0 + 90) / 0.01)::int AND floor((g.lat1 + 90) / 0.01)::int
            GROUP BY 1, 2
        ),
        f AS (
            -- one projection per cell (at most 4096), not per unit
            SELECT ST_AsMVTGeom(
                       ST_Transform(
                           ST_SetSRID(ST_MakePoint(g.lon0 + (c.cx + 0.5) * g.dlon,
                                                   g.lat0 + (c.cy + 0.5) * g.dlat), 4326),
                           3857),
                       b.env
                   ) AS geom,
                   c.anzahl, c.kw
            FROM cells c, g, b
        )
        SELECT ST_AsMVT(f, 'gasverbraucher') INTO result FROM f;
    ELSE
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        f AS (
            SELECT ST_AsMVTGeom(
                       ST_Transform(ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326), 3857),
                       b.env
                   ) AS geom,
                   e.einheitmastrnummer AS mastr_nr,
                   e.namegasverbrauchsseinheit AS name,
                   e.maximalegasbezugsleistung::float8 AS kw,
                   e.einheitbetriebsstatus AS status,
                   to_char(e.inbetriebnahmedatum, 'YYYY-MM-DD') AS inbetriebnahme,
                   coalesce(m.firmenname, nullif(concat_ws(' ', m.marktakteurvorname, m.marktakteurnachname), '')) AS betreiber,
                   to_char(e.datumendgueltigestilllegung, 'YYYY-MM-DD') AS stillgelegt_am,
                   e.einheitdientderstromerzeugung AS dient_der_stromerzeugung,
                   e.gemeinde AS gemeinde,
                   e.gemeindeschluessel AS gemeindeschluessel,
                   to_char(e.datumletzteaktualisierung, 'YYYY-MM-DD') AS aktualisiert_am
            FROM einheitengasverbraucher e
            LEFT JOIN marktakteure m ON m.mastrnummer = e.anlagenbetreibermastrnummer
            CROSS JOIN b
            WHERE ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326) && b.env4326
              AND e.breitengrad BETWEEN -90 AND 90
              AND e.laengengrad BETWEEN -180 AND 180
        )
        SELECT ST_AsMVT(f, 'gasverbraucher') INTO result FROM f;
    END IF;
    RETURN coalesce(result, ''::bytea);
END
$$
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
SECURITY DEFINER
SET search_path = public, pg_temp;

COMMENT ON FUNCTION tiles.gasverbraucher(integer, integer, integer) IS
    '{"description": "Gasverbraucher aus dem MaStR"}';

-- Stromverbraucher (keine Leistungsspalte im MaStR)
CREATE OR REPLACE FUNCTION tiles.stromverbraucher(z integer, x integer, y integer)
RETURNS bytea
AS $$
DECLARE
    result bytea;
BEGIN
    IF z < 0 OR z > 30 THEN
        RETURN ''::bytea;
    END IF;
    IF x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
        RETURN ''::bytea;
    END IF;
    -- below z7 a tile would carry thousands of individual points
    IF z < 7 THEN
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        g AS (
            -- cell size = tile width / 64, so the cells line up with the tile
            -- edges and a tile has at most 4096 features
            SELECT ST_XMin(env4326) AS lon0,
                   ST_YMin(env4326) AS lat0,
                   ST_XMax(env4326) AS lon1,
                   ST_YMax(env4326) AS lat1,
                   (ST_XMax(env4326) - ST_XMin(env4326)) / 64.0 AS dlon,
                   (ST_YMax(env4326) - ST_YMin(env4326)) / 64.0 AS dlat
            FROM b
        ),
        cells AS (
            -- the grid holds the units per ~1 km cell (db/grid.sql): a low
            -- zoom tile aggregates a few thousand rows instead of scanning the
            -- unit table, whose GiST index does random heap access
            SELECT floor(((c.cx + 0.5) * 0.01 - 180 - g.lon0) / g.dlon)::int AS cx,
                   floor(((c.cy + 0.5) * 0.01 - 90 - g.lat0) / g.dlat)::int AS cy,
                   sum(c.anzahl)::bigint AS anzahl
            FROM tiles.grid c, g
            WHERE c.layer = 'stromverbraucher'
              AND c.cx BETWEEN floor((g.lon0 + 180) / 0.01)::int AND floor((g.lon1 + 180) / 0.01)::int
              AND c.cy BETWEEN floor((g.lat0 + 90) / 0.01)::int AND floor((g.lat1 + 90) / 0.01)::int
            GROUP BY 1, 2
        ),
        f AS (
            -- one projection per cell (at most 4096), not per unit
            SELECT ST_AsMVTGeom(
                       ST_Transform(
                           ST_SetSRID(ST_MakePoint(g.lon0 + (c.cx + 0.5) * g.dlon,
                                                   g.lat0 + (c.cy + 0.5) * g.dlat), 4326),
                           3857),
                       b.env
                   ) AS geom,
                   c.anzahl
            FROM cells c, g, b
        )
        SELECT ST_AsMVT(f, 'stromverbraucher') INTO result FROM f;
    ELSE
        WITH b AS (
            SELECT ST_TileEnvelope(z, x, y) AS env,
                   ST_Transform(ST_TileEnvelope(z, x, y), 4326) AS env4326
        ),
        f AS (
            SELECT ST_AsMVTGeom(
                       ST_Transform(ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326), 3857),
                       b.env
                   ) AS geom,
                   e.einheitmastrnummer AS mastr_nr,
                   e.namestromverbrauchseinheit AS name,
                   e.einheitbetriebsstatus AS status,
                   to_char(e.inbetriebnahmedatum, 'YYYY-MM-DD') AS inbetriebnahme,
                   coalesce(m.firmenname, nullif(concat_ws(' ', m.marktakteurvorname, m.marktakteurnachname), '')) AS betreiber,
                   to_char(e.datumendgueltigestilllegung, 'YYYY-MM-DD') AS stillgelegt_am,
                   e.anzahlstromverbrauchseinheitengroesser50mw AS anzahl_groesser_50mw,
                   e.gemeinde AS gemeinde,
                   e.gemeindeschluessel AS gemeindeschluessel,
                   to_char(e.datumletzteaktualisierung, 'YYYY-MM-DD') AS aktualisiert_am
            FROM einheitenstromverbraucher e
            LEFT JOIN marktakteure m ON m.mastrnummer = e.anlagenbetreibermastrnummer
            CROSS JOIN b
            WHERE ST_SetSRID(ST_MakePoint(e.laengengrad::float8, e.breitengrad::float8), 4326) && b.env4326
              AND e.breitengrad BETWEEN -90 AND 90
              AND e.laengengrad BETWEEN -180 AND 180
        )
        SELECT ST_AsMVT(f, 'stromverbraucher') INTO result FROM f;
    END IF;
    RETURN coalesce(result, ''::bytea);
END
$$
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
SECURITY DEFINER
SET search_path = public, pg_temp;

COMMENT ON FUNCTION tiles.stromverbraucher(integer, integer, integer) IS
    '{"description": "Stromverbrauchseinheiten aus dem MaStR"}';

-- The read-only role for Martin is created by import_mastr.py
-- (create_tiles_role). Without CREATEROLE (e.g. a CloudNativePG managed role)
-- an administrator has to create it once; the grants are then applied by the
-- next import.
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'tiles_reader') THEN
        -- EXECUTE is granted to PUBLIC by default: revoke it, so only the
        -- tile server role can call the functions
        REVOKE ALL ON ALL FUNCTIONS IN SCHEMA tiles FROM PUBLIC;
        GRANT USAGE ON SCHEMA tiles TO tiles_reader;
        GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA tiles TO tiles_reader;
        -- defense in depth: USAGE on public is granted to PUBLIC by default,
        -- so this only drops direct grants. What keeps the unit tables out of
        -- the tile server is the missing SELECT privilege (Martin only
        -- publishes tables the connection may read).
        REVOKE ALL ON SCHEMA public FROM tiles_reader;
    END IF;
END $$;
