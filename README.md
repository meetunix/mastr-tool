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
mindestens PostgreSQL 16, **zusätzlich wird PostGIS benötigt**, siehe [docs/technical.md](docs/technical.md)).
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
PostgreSQL-Datenbank, reichert sie an und konvertiert sie in handhabbare Formate. Die Architektur besteht aus drei
Teilen:

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
   Primärschlüssel und Indizes angelegt, darunter partielle Indizes für die Kartenseite der mastr-app und GiST-Indizes
   für den Tile-Server (siehe [docs/technical.md](docs/technical.md)). In einer bestehenden Datenbank legt
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

### Start

```bash
docker compose up -d --build
```

Startet alle Services. Die WebUI ist unter `127.0.0.1:8081` erreichbar, die exportierten Dateien unter `127.0.0.1:8080`,
der Tile-Server unter `127.0.0.1:8082` (siehe [Tile-Server](#tile-server-mapbox-vector-tiles)).

Nur importieren und exportieren, ohne Webserver und WebUI:

```bash
docker compose up -d mastr-tool db
```

Die Exporte landen dann im konfigurierten `MASTR_OUTPUT_DIR`; ohne `mastr-static` gibt es keinen http-Zugriff darauf.
Auch hier wird alle 30 Minuten geprüft, ob ein neuer Dump bei der Bundesnetzagentur vorliegt.

### Logs

```bash
docker compose logs -f mastr-tool
```

## Tile-Server (Mapbox Vector Tiles)

[Martin](https://maplibre.org/martin/) liefert die Einheiten mit Koordinaten als Mapbox Vector Tiles (MVT) aus –
zusätzlich zu den Downloads, live aus der Datenbank. MVT enthält nur die Punkte, die Hintergrundkarte kommt vom Client
(OSM, basemap.de, …). Als Client funktionieren MapLibre, OpenLayers, Leaflet (mit Plugin) und QGIS.

### Öffentlicher Server

Eine öffentliche Instanz läuft unter **https://mastr-tile.nachtsieb.de** – ohne Schlüssel, CORS offen, mit denselben
Layern wie ein eigenes Deployment:

| Adresse                                                  | Inhalt                |
|----------------------------------------------------------|-----------------------|
| `https://mastr-tile.nachtsieb.de/catalog`                | alle Layer            |
| `https://mastr-tile.nachtsieb.de/tiles.wind`             | TileJSON einer Quelle |
| `https://mastr-tile.nachtsieb.de/tiles.wind/{z}/{x}/{y}` | die Kachel            |

**QGIS** (≥ 3.22): *Layer → Add Layer → Add Vector Tile Layer → New Generic Connection*, URL
`https://mastr-tile.nachtsieb.de/tiles.wind/{z}/{x}/{y}`, Zoom 0–14, Style URL leer. Danach in den
Layer-Eigenschaften unter *Symbology* den Sub-Layer `wind` wählen – ohne Symbologie bleibt die Ebene unsichtbar.
Für die anderen Energieträger nur `tiles.wind` ersetzen.

**MapLibre** bindet die Kacheln als Vektorquelle ein:

```js
map.addSource("mastr-wind", {
  type: "vector",
  tiles: ["https://mastr-tile.nachtsieb.de/tiles.wind/{z}/{x}/{y}"],
  minzoom: 0,
  maxzoom: 14,
});
map.addLayer({ id: "mastr-wind", type: "circle", source: "mastr-wind", "source-layer": "wind" });
```

Die Hintergrundkarte kommt vom Client (OSM, basemap.de, …), MVT enthält nur die Punkte. Die Daten stammen aus dem
zuletzt importierten Dump; der Cache kann sie bis zu 12 h halten.

### Eigenes Deployment

Im eigenen Deployment läuft der Server unter `127.0.0.1:8082` (Compose) bzw. über den Ingress des Helm-Charts, ein
Layer je Energieträger als Quelle `tiles.<layer>`. Aufbau, Endpunkte, PostGIS, Attribute, Cache und Betrieb stehen in
**[docs/technical.md](docs/technical.md)**.

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
