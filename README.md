# mastr-tool

Werkzeuge für den automatischen Download, den Datenbankimport und die Konvertierung
des [Marktstammdatenregisters der Bundesnetzagentur](https://www.marktstammdatenregister.de/MaStR). Diese Werkzeuge sind
die Datengrundlage und damit notwendig für den Betrieb der [mastr-app](https://codeberg.org/nachtsieb/mastr-app).

Die mastr-app kann unter https://mastr.nachtsieb.de ausprobiert werden.

Der komplette, durch die Bundesnetzagentur bereit gestellte Dump wird in eine PostgreSQL-Datenbank konvertiert und
die Einheiten der zwölf Energieträger (Wind, Solar, Biomasse, Wasser, Geothermie/Grubengas/Druckentspannung,
Stromspeicher, Kernkraft, Verbrennung, Gaserzeuger, Gasspeicher, Gasverbraucher, Stromverbraucher) werden in andere
Formate konvertiert. Der komplette Datenbankauszug steht nach der Konvertierung ebenfalls zum Download bereit
(Datei `mastr-latest.sql`: zstd-komprimiertes `pg_dump`-Archiv im Custom-Format, Einspielen mit `pg_restore`,
mindestens PostgreSQL 16, **zusätzlich wird PostGIS benötigt**, siehe [Tile-Server](#tile-server-mapbox-vector-tiles)).
Beim Import werden derzeit die GEO-Koordinaten (Längen-, Breitengrad)
zusätzlich um UTM-Koordinaten erweitert, sodass 3 neue Spalten hinzugefügt werden: `utm_zone, utm_ost, utm_nord`.

Zusätzlich liefert [Martin](https://maplibre.org/martin/) die Einheiten mit Koordinaten als Mapbox Vector Tiles (MVT)
für Kartenclients aus – live aus der Datenbank, mit einem In-Memory-Cache für die Kacheln.

Die Tabellen werden bei jedem Import aus dem Dump neu aufgebaut und sind deshalb `UNLOGGED` (kein WAL beim Import):
Nach einem Absturz des Datenbankservers sind sie bis zum nächsten Import leer, und `pg_restore` legt sie ebenfalls als
`UNLOGGED` an.

Wenn man nur die den aktuellen Stand des Marktstammdatenregisters konvertieren, Anreichern und die Daten im Anschluss
über http://localhost:8080 herunterladen möchte, reicht mastr-tool aus. Die WebUI mastr-app ist nicht notwendig.

## Verwendung mit docker-compose

### Funktionsweise von mastr-tool

`mastr-tool` lädt die Marktstammdatenregister-Daten der Bundesnetzagentur herunter, importiert sie in eine
PostgreSQL-Datenbank, reichert sie an und konvertiert sie in handhabbare Formate. Die Architektur ist in zwei Bereiche
geteilt:

- **`mastr-tool`** – das Backend. Führt den Scheduler aus, der die Pipeline betreibt: Dump-Download, DB-Import,
  Anreicherung und CSV-/Parquet-/Excel-Export. Die Ergebnisse stellt es über den Service `mastr-static` via http bereit.
- **`martin`** – der Tile-Server. Liefert die Einheiten mit Koordinaten als Mapbox Vector Tiles (MVT) für
  Kartenclients, siehe [Tile-Server](#tile-server-mapbox-vector-tiles).
- **`mastr-app`** – das Frontend. Eine WebUI, die die exportierten Daten visualisiert. Sie greift auf `mastr-static` zu,
  um die konvertierten Dateien zu laden. Die Kartenseite liest ihre Daten lesend direkt aus der Datenbank.

#### Die Pipeline im Detail

1. **Dump-Download**: Der Scheduler prüft alle 30 Minuten, ob ein aktualisierter MaStR-Dump bei der Bundesnetzagentur
   vorliegt. Nur dann wird neu heruntergeladen und die Konvertierung durchgeführt. Ein Dump gilt erst als verarbeitet,
   wenn die komplette Pipeline erfolgreich war – ein fehlgeschlagener Lauf wird bei der nächsten Prüfung wiederholt
   (ohne erneuten Download).
2. **DB-Import mit Enrichment**: Die riesigen XML-Dateien des Dumps werden in PostgreSQL importiert. Dabei werden für
   alle Einheiten mit Koordinaten UTM-Koordinaten berechnet (Zone, Ostwert, Nordwert). Nach dem Laden werden
   Primärschlüssel und Indizes angelegt, darunter partielle Indizes für die Kartenseite der mastr-app (Einheiten mit
   Koordinaten je Bundesland, `MapIndices` in `db/entities.py`) und GiST-Indizes auf dem aus den Koordinaten
   berechneten Punkt für den Tile-Server (`GeomIndices`). In einer bestehenden Datenbank legt
   `python import_mastr.py --schema --cache-dir <dir> <dir>` fehlende Schlüssel und Indizes an, ohne Daten zu
   importieren.
3. **Export**: Die angereicherten Daten werden konvertiert in:
    - **CSV**
    - **Parquet**
    - **Excel** (`.xlsx`, nicht für Solar und Stromspeicher, da zu groß; Zahlen und Datumswerte als typisierte Zellen)

### Voraussetzungen

- Docker mit Compose-Plugin
- **Mindestens 70 GiB freier Speicher** – der größte Anteil entfällt auf den unkomprimierten MaStR-Dump (aktuell ca. 60
  GiB, wächst über die Zeit).

### Konfiguration (`.env`)

Man legt eine `.env` neben der `docker-compose.yaml` an:

```env
# Cache-Verzeichnis (Dump, entpackte XML-Dateien)
MASTR_CACHE_DIR=/pfad/zum/cache

# Export-Verzeichnis (CSV-, Parquet- und Excel-Exporte)
MASTR_OUTPUT_DIR=/pfad/zum/export

# Anzahl paralleler Prozesse für Import und Export (leer = CPU-Kerne minus eins)
MASTR_CONCURRENCY=

# Vorhandenen Dump ohne Download-Prüfung verwenden (einmaliger Pipeline-Lauf, Container bleibt danach im Leerlauf)
MASTR_FORCE_USING_EXISTING_DUMP=false

# Import (inkl. Anreicherung) und Export komplett überspringen (z.B. Neustart ohne Datenbank- oder Export-Änderungen)
MASTR_SKIP_IMPORT_AND_EXPORT=false

# Passwort der schreibgeschützten Rolle tiles_reader für den Tile-Server (Standard: tiles)
TILES_DB_PASSWORD=tiles
```

### Zwei Compose-Dateien

Es gibt zwei Compose-Dateien für unterschiedliche Anwendungsfälle:

| Datei                         | Services                                                  | Anwendung                                                                           |
|-------------------------------|-----------------------------------------------------------|-------------------------------------------------------------------------------------|
| `docker-compose.yaml`         | `mastr-tool`, `db`, `mastr-static`, `martin`, `mastr-app` | Vollbetrieb inkl. WebUI und Tile-Server                                             |
| `docker-compose.convert.yaml` | `mastr-tool`, `db`                                        | Nur (regelmäßige) Konvertierung ohne web-app und http-Zugriff auf exportierte Daten |

#### Vollbetrieb inkl. WebUI

```bash
docker compose -f docker-compose.yaml up -d --build
```

Startet alle Services. Die WebUI ist unter `127.0.0.1:8081` erreichbar, die exportierten Dateien unter `127.0.0.1:8080`,
der Tile-Server unter `127.0.0.1:7800` (siehe [Tile-Server](#tile-server-mapbox-vector-tiles)).

#### Nur Daten konvertieren

```bash
docker compose -f docker-compose.convert.yaml up -d --build
```

Startet nur `mastr-tool` und `db`. Die Exporte landen im
konfigurierten `MASTR_OUTPUT_DIR`. Ohne `mastr-static` und `mastr-app` gibt es keinen Webserver-Zugriff auf die
Dateien – sie liegen direkt im gemounteten Verzeichnis. Auch hier wird alle 30 Minuten geprüft, ob ein neuer Dump bei
der Bundesnetzagentur vorliegt.

### Logs

```bash
docker compose -f docker-compose.convert.yaml logs -f mastr-tool
```

## Tile-Server (Mapbox Vector Tiles)

[Martin](https://maplibre.org/martin/) liefert die Einheiten mit Koordinaten als Mapbox Vector Tiles (MVT) aus –
zusätzlich zu den Downloads. Die Kacheln werden live aus der Datenbank erzeugt und zwölf Stunden im In-Memory-Cache
von Martin gehalten (1 GiB, `tile_expiry: 12h`, `maxzoom: 14`); Browser und Proxys bekommen zusätzlich
`Cache-Control: public, max-age=3600`. MVT enthält nur die Punkte, die Hintergrundkarte kommt vom Client
(OSM, basemap.de, …). Als Client funktionieren MapLibre, OpenLayers, Leaflet (mit Plugin) und QGIS.

### Adressen

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

### PostGIS

Die Kacheln brauchen PostGIS: das Image `postgres:18` ist deshalb durch `postgis/postgis:18-3.6` ersetzt (Compose und
Helm). Das Image baut auf dem offiziellen Postgres-Image auf, das bestehende Datenverzeichnis funktioniert also weiter,
ein Dump und Restore ist nicht nötig. `CREATE EXTENSION IF NOT EXISTS postgis;` steht in `db/udf.sql`.

Statt einer gespeicherten Geometriespalte gibt es nur einen GiST-Index auf dem aus den Koordinaten berechneten Punkt
(`GeomIndices` in `db/entities.py`, angelegt in `write_constraints()` von `import_mastr.py`). Der Import bleibt damit
unverändert, zusätzlicher Plattenplatz entsteht nur für den Index (grob 50–70 Byte je Einheit mit Koordinaten).

### Funktionen statt Tabellen oder Views

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

### Attribute und Bündelung

Jedes Feature hat `mastr_nr`, `name`, `kw`, `status` und – wo vorhanden – `park` (Windpark, Solarpark, Kraftwerk).
`kw` ist die Nettonennleistung (bei Gaserzeugern, Gas- und Stromspeichern die jeweilige Leistungsspalte des MaStR),
`status` die Katalog-ID des Betriebsstatus.

Dazu kommen für alle Layer `inbetriebnahme` und `stillgelegt_am` (ISO-Datum als Text), `betreiber` (Firmenname des
Anlagenbetreibers aus `Marktakteure`, bei natürlichen Personen Vor- und Nachname, per `LEFT JOIN`) sowie – in den acht
Strom-Erzeugungs- und Speichertabellen – `brutto_kw`, `fernsteuerbar_nb`, `fernsteuerbar_dv` und `hochspannung`.
Die Gas- und Verbrauchertabellen kennen diese Spalten im MaStR nicht, dort fehlen sie.

Je Energieträger zusätzlich:

| Layer | Felder |
|---|---|
| `wind` | `nabenhoehe`, `rotordurchmesser`, `hersteller`, `typ`, `offshore`, `buergerenergie` |
| `solar` | `art`, `module`, `ausrichtung`, `neigung`, `flaeche_ha`, `speicher_am_ort`, `buergerenergie` |
| `biomasse` | `brennstoff`, `biomasseart`, `technologie` |
| `wasser` | `art` |
| `geothermie` | `technologie` |
| `stromspeicher` | `batterietechnologie`, `acdc`, `einsatzort`, `pumpspeicher`, `notstrom`, `wechselrichter` |
| `kernkraft` | `block`, `technologie` |
| `verbrennung` | `brennstoff`, `kombibetrieb`, `einsatzort`, `notstrom`, `block` |
| `gaserzeuger` | `technologie` |
| `gasspeicher` | `speicherart`, `arbeitsgasvolumen`, `ausspeicherleistung` |
| `gasverbraucher` | `dient_der_stromerzeugung` |
| `stromverbraucher` | `anzahl_groesser_50mw` |

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

### Betrieb

In `docker-compose.yaml` läuft Martin auf `127.0.0.1:7800`; die Konfiguration liegt in `martin/config.yaml` und wird
schreibgeschützt nach `/etc/martin/config.yaml` gemountet. In Produktion gehört Martin hinter einen Reverse Proxy, etwa
den Apache aus `httpd-static` (`/tiles/` → `martin:7800`) oder den Ingress aus dem Helm-Chart (`martin.ingress`). CORS
ist per Default für alle Origins erlaubt.

Im Helm-Chart: `martin.enabled`, `martin.image`, `martin.containerPort`, `martin.dbPassword`, `martin.service` und
`martin.ingress`. Die Konfigurationsdatei steckt als ConfigMap im Chart (`charts/mastr-tool/files/martin.yaml`, identisch
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

### Datenbankauszug `mastr-latest.sql`

`pg_dump` schreibt die PostGIS-Extension und die GiST-Indizes mit, wer den Auszug einspielt, braucht also PostGIS.
Das Schema `tiles` ist ausgeschlossen (`--exclude-schema=tiles`): die Funktionen sind deploymentspezifisch und werden
bei jedem Import neu angelegt. `--exclude-extension` hilft nicht, weil die Indizes auf den Einheiten-Tabellen die
PostGIS-Funktionen benötigen.

### CloudNativePG

Die verwaltete Rolle `mastr` ist kein Superuser und hat kein `CREATEROLE`. Extension und Rolle müssen dort einmalig
vom Administrator angelegt werden (siehe `charts/mastr-tool/values-cnpg.yaml`):

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE ROLE tiles_reader LOGIN PASSWORD 'tiles';
```

## Deployment auf Kubernetes

mastr-tool wird über das Helm-Chart in [`charts/mastr-tool`](charts/mastr-tool) deployt. Es bringt den
Backend-Scheduler (`mastr-tool`), den http-Server für die Exporte (`mastr-static`), den Tile-Server (`martin`)
und eine eigenständige PostgreSQL-Datenbank mit. **Nicht enthalten ist `mastr-app`** – die WebUI besitzt ein eigenes
Helm-Chart im [mastr-app-Repository](https://codeberg.org/nachtsieb/mastr-app) und wird separat installiert.

### Voraussetzungen

- Kubernetes-Cluster mit einem Ingress-Controller
- `helm` >= 3
- Eine `StorageClass`, die `ReadWriteMany` unterstützt (für das `output`-PVC, damit `mastr-static` die von
  `mastr-tool` geschriebenen Exporte lesen kann). Alternativ beide Pods über Affinity auf denselben Knoten
  legen und `ReadWriteOnce` verwenden.

### Installation

```bash
# Chart-Abhängigkeiten (falls vorhanden) aktualisieren
helm dependency build charts/mastr-tool

# Eigene Werte anpassen (siehe Minimal-Beispiel unten) und installieren
helm install mastr charts/mastr-tool -n mastr --create-namespace -f my-values.yaml
```

### Upgrade

```bash
helm upgrade mastr charts/mastr-tool -n mastr -f my-values.yaml
```

### Minimale `my-values.yaml`

```yaml
mastrTool:
  image:
    repository: nachtsieb/mastr-tool
    tag: latest
  forceUsingExistingDump: false
  resources: {}

mastrStatic:
  enabled: true
  image:
    repository: nachtsieb/mastr-static
    tag: latest
  service:
    type: ClusterIP
    port: 8080
  ingress:
    enabled: true
    className: ""                 # leer = Cluster-Default-Ingress-Class
    annotations: {}
    hosts:
      - host: mastr-static.example.com
        paths:
          - path: /
            pathType: Prefix

martin:
  enabled: true
  image:
    repository: ghcr.io/maplibre/martin
    tag: "1.16.1"
  dbPassword: "change-me-please"  # Passwort der Rolle tiles_reader
  service:
    type: ClusterIP
    port: 7800
  ingress:
    enabled: false
    hosts:
      - host: mastr-tiles.example.com
        paths:
          - path: /
            pathType: Prefix

database:
  mode: standalone
  port: 5432
  standalone:
    image:
      repository: postgis/postgis
      tag: "18-3.6"
    user: mastr
    password: "change-me-please"
    name: mastr
    storage: 50Gi
    storageClassName: ""
    resources: {}

persistence:
  cache:
    size: 80Gi
    storageClassName: ""
    accessModes: [ReadWriteOnce]
  output:
    size: 20Gi
    storageClassName: ""          # musst be RWX StorageClass
    accessModes: [ReadWriteMany]
```
