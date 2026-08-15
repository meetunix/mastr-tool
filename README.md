# mastr-tool

Werkzeuge für den automatischen Download, den Datenbankimport und die Konvertierung
des [Marktstammdatenregisters der Bundesnetzagentur](https://www.marktstammdatenregister.de/MaStR). Diese Werkzeuge sind
die Datengrundlage und damit notwendig für den Betrieb der [mastr-app](https://codeberg.org/nachtsieb/mastr-app).

Die mastr-app kann unter https://mastr.nachtsieb.de ausprobiert werden.

## Verwendung mit docker-compose

### Funktionsweise von mastr-tool

`mastr-tool` lädt die Marktstammdatenregister-Daten der Bundesnetzagentur herunter, importiert sie in eine
PostgreSQL-Datenbank, reichert sie an und konvertiert sie in handhabbare Formate. Die Architektur ist in zwei Bereiche
geteilt:

- **`mastr-tool`** – das Backend. Führt den Scheduler aus, der die Pipeline betreibt: Dump-Download, DB-Import,
  Anreicherung und CSV-/Parquet-/Excel-Export. Die Ergebnisse stellt es über den Service `mastr-static` via http bereit.
- **`mastr-app`** – das Frontend. Eine WebUI, die die exportierten Daten visualisiert. Sie greift auf `mastr-static` zu,
  um die konvertierten Dateien zu laden.

#### Die Pipeline im Detail

1. **Dump-Download**: Der Scheduler prüft alle 30 Minuten, ob ein aktualisierter MaStR-Dump bei der Bundesnetzagentur
   vorliegt. Nur dann wird neu heruntergeladen und die Konvertierung durchgeführt.
2. **DB-Import**: Die riesigen XML-Dateien des Dumps werden in PostgreSQL importiert.
3. **Enrichment**: Für alle Einheiten mit Koordinaten werden UTM-Koordinaten berechnet und in der Datenbank ergänzt
   (Zone, Ostwert, Nordwert). Bereits berechnete Koordinaten werden zwischengespeichert, um Rechenzeit bei zukünftigen
   Konvertierungen zu sparen.
4. **Export**: Die angereicherten Daten werden konvertiert in:
    - **CSV**
    - **Parquet**
    - **Excel** (`.xlsx`, nicht für Solar, da zu groß)

### Voraussetzungen

- Docker mit Compose-Plugin
- **Mindestens 70 GiB freier Speicher** – der größte Anteil entfällt auf den unkomprimierten MaStR-Dump (aktuell ca. 60
  GiB, wächst über die Zeit).

### Konfiguration (`.env`)

Man legt eine `.env` neben der `docker-compose.yaml` an:

```env
# Cache-Verzeichnis (Dump, entpackte XML-Dateien, Enricher-Cache)
MASTR_CACHE_DIR=/pfad/zum/cache

# Export-Verzeichnis (CSV-, Parquet- und Excel-Exporte)
MASTR_OUTPUT_DIR=/pfad/zum/export
```

### Zwei Compose-Dateien

Es gibt zwei Compose-Dateien für unterschiedliche Anwendungsfälle:

| Datei                         | Services                                        | Anwendung                                                                           |
|-------------------------------|-------------------------------------------------|-------------------------------------------------------------------------------------|
| `docker-compose.yaml`         | `mastr-tool`, `db`, `mastr-static`, `mastr-app` | Vollbetrieb inkl. WebUI                                                             |
| `docker-compose.convert.yaml` | `mastr-tool`, `db`                              | Nur (regelmäßige) Konvertierung ohne web-app und http-Zugriff auf exportierte Daten |

#### Vollbetrieb inkl. WebUI

```bash
docker compose -f docker-compose.yaml up -d --build
```

Startet alle Services. Die WebUI ist unter `127.0.0.1:8081` erreichbar, die exportierten Dateien unter `127.0.0.1:8080`.

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
