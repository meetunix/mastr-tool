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

CREATE OR REPLACE FUNCTION marktrolle(id integer) RETURNS text AS
$$
    SELECT CASE
        WHEN id = 1
             then 'Übertragungsnetzbetreiber'
        WHEN id = 2
             then 'Anschlussnetzbetreiber'
        WHEN id = 3
             then 'Bilanzkreisverantwortlicher'
        WHEN id = 4
             then 'Bilanzkoordinator'
        WHEN id = 5
             then 'Messstellenbetreiber'
        WHEN id = 6
             then 'Fernleitungsnetzbetreiber (Gas)'
        WHEN id = 7
             then 'Marktgebietsverantwortlicher'
        WHEN id = 8
             then 'Anschlussnetzbetreiber'
        WHEN id = 18
             then 'Stromlieferant, Direktvermarkter, Stromgroßhändler'
        WHEN id = 20
             then 'Bilanzkreisverantwortlicher'
        WHEN id = 21
             then 'Messstellenbetreiber'
        WHEN id = 22
             then 'Bilanzkreisverantwortlicher'
        WHEN id = 23
             then 'Betreiber einer Buchungsplattform für grenzüberschreitende Stromnetzkapazitäten'
        WHEN id = 24
             then 'Börse'
        WHEN id = 25
             then 'OTC-Plattform'
        WHEN id = 26
             then 'Betreiber einer Buchungsplattform für Gasspeicher'
        WHEN id = 27
             then 'Behörde'
        WHEN id = 28
             then 'energiewirtschaftlicher Verband'
        WHEN id = 29
             then 'energiewirtschaftliche Institution'
        WHEN id = 30
             then 'Dienstleister'
        WHEN id = 31
             then 'Sonstige Marktrolle'
        WHEN id = 32
             then 'Messstellenbetreiber'
        WHEN id = 33
             then 'Messstellenbetreiber'
        WHEN id = 35
             then 'Transportkunde'
        WHEN id = 37
             then 'Betreiber einer Buchungsplattform für Gaskapazitäten'
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
