-- Rebuild the pre-aggregated grid (tiles.grid) the low zoom tiles are built
-- from. Runs after the unit tables are loaded, before the vacuum.
--
-- Cell size 0.01 degrees (~1.1 km), the finest cell the bundled zooms need:
-- solar bundles up to zoom 9, where a tile cell is 360 / 2^9 / 64 = 0.011
-- degrees. cx = floor((lon + 180) / 0.01), cy = floor((lat + 90) / 0.01).
--
-- The tile functions read this table instead of the unit tables: a z4 tile of
-- solar aggregates 266k units, and scanning them costs 30 s because the GiST
-- index does random heap access over the 2 GB table. The grid turns that into
-- a few thousand rows.

TRUNCATE tiles.grid;

INSERT INTO tiles.grid (layer, cx, cy, anzahl, kw)
SELECT 'wind',
       floor((laengengrad::float8 + 180) / 0.01)::int,
       floor((breitengrad::float8 + 90) / 0.01)::int,
       count(*),
       sum(nettonennleistung::float8)
FROM einheitenwind
WHERE breitengrad BETWEEN -90 AND 90 AND laengengrad BETWEEN -180 AND 180
GROUP BY 2, 3;

INSERT INTO tiles.grid (layer, cx, cy, anzahl, kw)
SELECT 'solar',
       floor((laengengrad::float8 + 180) / 0.01)::int,
       floor((breitengrad::float8 + 90) / 0.01)::int,
       count(*),
       sum(nettonennleistung::float8)
FROM einheitensolar
WHERE breitengrad BETWEEN -90 AND 90 AND laengengrad BETWEEN -180 AND 180
GROUP BY 2, 3;

INSERT INTO tiles.grid (layer, cx, cy, anzahl, kw)
SELECT 'biomasse',
       floor((laengengrad::float8 + 180) / 0.01)::int,
       floor((breitengrad::float8 + 90) / 0.01)::int,
       count(*),
       sum(nettonennleistung::float8)
FROM einheitenbiomasse
WHERE breitengrad BETWEEN -90 AND 90 AND laengengrad BETWEEN -180 AND 180
GROUP BY 2, 3;

INSERT INTO tiles.grid (layer, cx, cy, anzahl, kw)
SELECT 'wasser',
       floor((laengengrad::float8 + 180) / 0.01)::int,
       floor((breitengrad::float8 + 90) / 0.01)::int,
       count(*),
       sum(nettonennleistung::float8)
FROM einheitenwasser
WHERE breitengrad BETWEEN -90 AND 90 AND laengengrad BETWEEN -180 AND 180
GROUP BY 2, 3;

INSERT INTO tiles.grid (layer, cx, cy, anzahl, kw)
SELECT 'geothermie',
       floor((laengengrad::float8 + 180) / 0.01)::int,
       floor((breitengrad::float8 + 90) / 0.01)::int,
       count(*),
       sum(nettonennleistung::float8)
FROM einheitengeothermiegrubengasdruckentspannung
WHERE breitengrad BETWEEN -90 AND 90 AND laengengrad BETWEEN -180 AND 180
GROUP BY 2, 3;

INSERT INTO tiles.grid (layer, cx, cy, anzahl, kw)
SELECT 'stromspeicher',
       floor((laengengrad::float8 + 180) / 0.01)::int,
       floor((breitengrad::float8 + 90) / 0.01)::int,
       count(*),
       sum(nettonennleistung::float8)
FROM einheitenstromspeicher
WHERE breitengrad BETWEEN -90 AND 90 AND laengengrad BETWEEN -180 AND 180
GROUP BY 2, 3;

INSERT INTO tiles.grid (layer, cx, cy, anzahl, kw)
SELECT 'kernkraft',
       floor((laengengrad::float8 + 180) / 0.01)::int,
       floor((breitengrad::float8 + 90) / 0.01)::int,
       count(*),
       sum(nettonennleistung::float8)
FROM einheitenkernkraft
WHERE breitengrad BETWEEN -90 AND 90 AND laengengrad BETWEEN -180 AND 180
GROUP BY 2, 3;

INSERT INTO tiles.grid (layer, cx, cy, anzahl, kw)
SELECT 'verbrennung',
       floor((laengengrad::float8 + 180) / 0.01)::int,
       floor((breitengrad::float8 + 90) / 0.01)::int,
       count(*),
       sum(nettonennleistung::float8)
FROM einheitenverbrennung
WHERE breitengrad BETWEEN -90 AND 90 AND laengengrad BETWEEN -180 AND 180
GROUP BY 2, 3;

INSERT INTO tiles.grid (layer, cx, cy, anzahl, kw)
SELECT 'gaserzeuger',
       floor((laengengrad::float8 + 180) / 0.01)::int,
       floor((breitengrad::float8 + 90) / 0.01)::int,
       count(*),
       sum(erzeugungsleistung::float8)
FROM einheitengaserzeuger
WHERE breitengrad BETWEEN -90 AND 90 AND laengengrad BETWEEN -180 AND 180
GROUP BY 2, 3;

INSERT INTO tiles.grid (layer, cx, cy, anzahl, kw)
SELECT 'gasspeicher',
       floor((laengengrad::float8 + 180) / 0.01)::int,
       floor((breitengrad::float8 + 90) / 0.01)::int,
       count(*),
       sum(maximaleeinspeicherleistung::float8)
FROM einheitengasspeicher
WHERE breitengrad BETWEEN -90 AND 90 AND laengengrad BETWEEN -180 AND 180
GROUP BY 2, 3;

INSERT INTO tiles.grid (layer, cx, cy, anzahl, kw)
SELECT 'gasverbraucher',
       floor((laengengrad::float8 + 180) / 0.01)::int,
       floor((breitengrad::float8 + 90) / 0.01)::int,
       count(*),
       sum(maximalegasbezugsleistung::float8)
FROM einheitengasverbraucher
WHERE breitengrad BETWEEN -90 AND 90 AND laengengrad BETWEEN -180 AND 180
GROUP BY 2, 3;

INSERT INTO tiles.grid (layer, cx, cy, anzahl)
SELECT 'stromverbraucher',
       floor((laengengrad::float8 + 180) / 0.01)::int,
       floor((breitengrad::float8 + 90) / 0.01)::int,
       count(*)
FROM einheitenstromverbraucher
WHERE breitengrad BETWEEN -90 AND 90 AND laengengrad BETWEEN -180 AND 180
GROUP BY 2, 3;
