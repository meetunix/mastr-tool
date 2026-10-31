CREATE OR REPLACE FUNCTION katalog(integer) RETURNS text AS
$$
    SELECT wert FROM katalogwerte WHERE id = $1
$$
    LANGUAGE SQL
    IMMUTABLE
    RETURNS NULL ON NULL INPUT;

CREATE OR REPLACE FUNCTION marktfunktion(id integer) RETURNS text AS
$$
    SELECT CASE
        WHEN id = 1
             then 'Stromnetzbetreiber'
        WHEN id = 2
             then 'Anlagenbetreiber'
        WHEN id = 3
             then 'Akteur im Strommarkt'
        WHEN id = 4
             then 'Organisierter Marktplatz'
        WHEN id = 5
             then 'Behörde, Verband, Institution'
        WHEN id = 6
             then 'Sonstiger Marktakteur'
        WHEN id = 7
             then 'Bundesnetzagentur'
        WHEN id = 8
             then 'Gasnetzbetreiber'
        WHEN id = 9
             then 'Akteur im Gasmarkt'
        WHEN id = 10
             then 'Supportpartner'
             else 'unbekannt'
           end
$$
    LANGUAGE SQL
    IMMUTABLE
    RETURNS NULL ON NULL INPUT;

CREATE OR REPLACE FUNCTION boolean_hr(b boolean) returns text as
$$
    SELECT CASE
        WHEN b = true
             then 'ja'
             else 'nein'
           end
$$
    LANGUAGE SQL
    IMMUTABLE
    RETURNS NULL ON NULL INPUT;

CREATE OR REPLACE FUNCTION katalog_list(ids text) RETURNS text AS
$$
    SELECT string_agg(katalogwert, ', ' ORDER BY ord)
    FROM (
        SELECT katalog(x::integer) AS katalogwert, ord
        FROM unnest(regexp_split_to_array(ids, '[^0-9]+')) WITH ORDINALITY AS u(x, ord)
        WHERE x <> ''
    ) AS mapped
$$
    LANGUAGE SQL
    IMMUTABLE
    RETURNS NULL ON NULL INPUT;
