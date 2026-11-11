# Technische Details: Tile-Server, PostGIS und CloudNativePG

Aufbau und Betrieb des Tile-Servers sowie die dafür nötigen Datenbank-Anpassungen. Die Bedienung – öffentlicher
Server, QGIS, MapLibre – steht in der [README](../README.md#tile-server-mapbox-vector-tiles).

## Adressen

| Adresse                       | Inhalt                                           |
|-------------------------------|--------------------------------------------------|
| `GET /health`                 | Healthcheck, `200 OK`                            |
| `GET /catalog`                | alle Quellen (Layer)                             |
| `GET /tiles.wind`             | TileJSON einer Quelle (Kachel-URL, Beschreibung) |
| `GET /tiles.wind/{z}/{x}/{y}` | die Kachel                                       |

Ein Layer je Energieträger: `wind`, `solar`, `biomasse`, `wasser`, `geothermie`, `stromspeicher`, `kernkraft`,
`verbrennung`, `gaserzeuger`, `gasspeicher`, `gasverbraucher`, `stromverbraucher` – jeweils als Quelle `tiles.<layer>`.
Die Kachel-URL hat keine Endung; `…/{z}/{x}/{y}.pbf` leitet mit `301` auf die endungslose URL um, ebenso ein
`/tiles/`-Präfix. Die Vorschau-Karte der Web-UI ist standardmäßig aus (`web_ui: disable`), zum Testen Martin mit
`--webui enableforall` starten.

## PostGIS

Die Kacheln brauchen PostGIS: das Image `postgres:18` ist deshalb durch `postgis/postgis:18-3.6` ersetzt (Compose und
Helm). Das Image baut auf dem offiziellen Postgres-Image auf, das bestehende Datenverzeichnis funktioniert also weiter,
ein Dump und Restore ist nicht nötig. `CREATE EXTENSION IF NOT EXISTS postgis;` steht in `db/udf.sql`.

Statt einer gespeicherten Geometriespalte gibt es nur einen GiST-Index auf dem aus den Koordinaten berechneten Punkt
(`GeomIndices` in `db/entities.py`, angelegt in `write_constraints()` von `import_mastr.py`). Der Import bleibt damit
unverändert, zusätzlicher Plattenplatz entsteht nur für den Index (grob 50–70 Byte je Einheit mit Koordinaten).

## Funktionen statt Tabellen oder Views

Die Layer sind Function Sources aus `db/tiles.sql`: pro Energieträger eine Funktion `tiles.<traeger>(z, x, y)`, die mit
`ST_AsMVT` die Kachelbytes zurückgibt. Eine View würde den `DROP TABLE` beim Import mit `--cleanup` blockieren, eine
plpgsql-Funktion übersteht den Neuaufbau. Die Funktionen sind `SECURITY DEFINER` mit festem `search_path`; Martin
verbindet sich mit der Rolle `tiles_reader`, die nur `USAGE` auf das Schema `tiles` und `EXECUTE` auf die Funktionen
hat. Sie kann die Einheiten-Tabellen nicht lesen, und `martin/config.yaml` veröffentlicht mit `tables: false`
grundsätzlich keine Tabellen.

Martin liest den `COMMENT ON FUNCTION` als TileJSON, die Kommentare in `db/tiles.sql` sind deshalb JSON-Objekte mit
einer `description`. Neue Layer erscheinen ohne Neustart: Martin liest den Katalog alle 10 Minuten neu ein
(`reload_interval`).

Die Rolle legt `import_mastr.py` an (`create_tiles_role`, Passwort aus `TILES_DB_PASSWORD`, Standard `tiles`). Ohne
`CREATEROLE` – etwa bei einer CloudNativePG-Rolle – muss sie einmalig von einem Administrator angelegt werden, der
Import läuft dann mit einer Warnung weiter.

## Attribute und Bündelung

Jedes Feature hat `mastr_nr`, `name`, `kw`, `status` und – wo vorhanden – `park` (Windpark, Solarpark, Kraftwerk).
`kw` ist die Nettonennleistung (bei Gaserzeugern, Gas- und Stromspeichern die jeweilige Leistungsspalte des MaStR),
`status` die Katalog-ID des Betriebsstatus.

Dazu kommen für alle Layer `inbetriebnahme` und `stillgelegt_am` (ISO-Datum als Text), `betreiber` (Firmenname des
Anlagenbetreibers aus `Marktakteure`, bei natürlichen Personen Vor- und Nachname, per `LEFT JOIN`) sowie – in den acht
Strom-Erzeugungs- und Speichertabellen – `brutto_kw`, `fernsteuerbar_nb`, `fernsteuerbar_dv` und `hochspannung`.
Die Gas- und Verbrauchertabellen kennen diese Spalten im MaStR nicht, dort fehlen sie.

Je Energieträger zusätzlich:

| Layer              | Felder                                                                                       |
|--------------------|----------------------------------------------------------------------------------------------|
| `wind`             | `nabenhoehe`, `rotordurchmesser`, `hersteller`, `typ`, `offshore`, `buergerenergie`          |
| `solar`            | `art`, `module`, `ausrichtung`, `neigung`, `flaeche_ha`, `speicher_am_ort`, `buergerenergie` |
| `biomasse`         | `brennstoff`, `biomasseart`, `technologie`                                                   |
| `wasser`           | `art`                                                                                        |
| `geothermie`       | `technologie`                                                                                |
| `stromspeicher`    | `batterietechnologie`, `acdc`, `einsatzort`, `pumpspeicher`, `notstrom`, `wechselrichter`    |
| `kernkraft`        | `block`, `technologie`                                                                       |
| `verbrennung`      | `brennstoff`, `kombibetrieb`, `einsatzort`, `notstrom`, `block`                              |
| `gaserzeuger`      | `technologie`                                                                                |
| `gasspeicher`      | `speicherart`, `arbeitsgasvolumen`, `ausspeicherleistung`                                    |
| `gasverbraucher`   | `dient_der_stromerzeugung`                                                                   |
| `stromverbraucher` | `anzahl_groesser_50mw`                                                                       |

Katalogwerte (`status`, `art`, `brennstoff`, `hersteller`, `technologie`, …) bleiben IDs, der Client mappt sie – das
spart Bytes gegenüber `katalog()`. Die Auswahl steht in `db/tiles.sql`.

Solar und Stromspeicher haben Millionen Einheiten. Unterhalb von Zoom 10 bündelt die Funktion die Punkte deshalb je
Rasterzelle (64 × 64 Zellen pro Kachel) zu einem Feature mit `anzahl` und `kw`; darüber kommt jeder Punkt einzeln.
Für Wind, Kernkraft, Wasser und die übrigen Layer ist das nicht nötig.

Mit den zusätzlichen Attributen sind die Kacheln deutlich größer als vorher: eine z10-Kachel mit rund 10.000
Solaranlagen liegt unkomprimiert im Bereich einiger hundert KB bis etwa 1 MB. Wenn das zu langsam wird, hebt man die
Bündelungsgrenze in `tiles.solar` und `tiles.stromspeicher` von `z < 10` auf `z < 11` oder `z < 12`.

Filter pro Anfrage (z. B. `…/{z}/{x}/{y}?min_kw=1000`) sind mit Martin über einen vierten Parameter `query json`
möglich; die Layer hier verzichten darauf, damit die Kacheln klein bleiben.

## Betrieb

In `docker-compose.yaml` läuft Martin auf `127.0.0.1:8082` (Container-Port 7800); die Konfiguration liegt in
`martin/config.yaml` und wird
schreibgeschützt nach `/etc/martin/config.yaml` gemountet. In Produktion gehört Martin hinter einen Reverse Proxy, etwa
den Apache aus `httpd-static` (`/tiles/` → `martin:7800`) oder den Ingress aus dem Helm-Chart (`martin.ingress`). CORS
ist per Default für alle Origins erlaubt.

Im Helm-Chart: `martin.enabled`, `martin.image`, `martin.containerPort`, `martin.dbPassword`, `martin.service` und
`martin.ingress`. Die Konfigurationsdatei steckt als ConfigMap im Chart (`charts/mastr-tool/files/martin.yaml`,
identisch
zu `martin/config.yaml`); Verbindungs-URL und Port kommen über `MARTIN_DATABASE_URL` und `MARTIN_LISTEN_ADDRESSES` aus
der Umgebung. Das Deployment wartet im Standalone-Modus auf die Datenbank.

Der Kachel-Cache ist auf 1 GiB und eine TTL von 12 h konfiguriert (`cache` in `martin/config.yaml`). Nach jedem Import
leert `download-mastr.sh` ihn über `DELETE /cache/{source_id}` (Endpunkt `endpoints.purge_cache`), damit die Karte
sofort die neuen Daten zeigt. Die TTL ist nur noch das Sicherheitsnetz, falls der Purge nicht durchgeht; während des
mehrstündigen Imports selbst liefert der Cache weiter die alten Kacheln, statt mit Fehlern zu antworten.

Die Adresse des Tile-Servers für den Purge kommt aus `MARTIN_URL` (Compose: `http://martin:7800`, im Chart
`http://<release>-martin:7800`). Ist sie leer oder Martin nicht erreichbar, wird nur gewarnt – der Import läuft
weiter.

Ein Memory-Limit für den Container muss über 1 GiB Luft lassen – bei `limits.memory: 1Gi` würde Martin durch den Cache
selbst in den OOM-Kill laufen. Die PMTiles-, Font- und Sprite-Caches bleiben leer, ihre Budgets werden nicht vorab
belegt.

## Datenbankauszug `mastr-latest.sql`

`pg_dump` schreibt die PostGIS-Extension und die GiST-Indizes mit, wer den Auszug einspielt, braucht also PostGIS.
Das Schema `tiles` ist ausgeschlossen (`--exclude-schema=tiles`): die Funktionen sind deploymentspezifisch und werden
bei jedem Import neu angelegt. `--exclude-extension` hilft nicht, weil die Indizes auf den Einheiten-Tabellen die
PostGIS-Funktionen benötigen.

## CloudNativePG

Die verwaltete Rolle `mastr` ist kein Superuser und hat kein `CREATEROLE`. Extension und Rolle müssen dort einmalig
vom Administrator angelegt werden (siehe `charts/mastr-tool/values-cnpg.yaml`):

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE ROLE tiles_reader LOGIN PASSWORD 'tiles';
```

