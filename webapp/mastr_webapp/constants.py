from enum import Enum
from unittest.mock import DEFAULT

MASTR_STATIC_URL = "https://mastr-static.nachtsieb.de"
MASTR_STATIC_EXPORTS_URL = MASTR_STATIC_URL + "/exports/"
MASTR_SOURCE_URL = "https://www.marktstammdatenregister.de/MaStR/Datendownload"

__IMPORT_TIMESTAMP_PATH = "/import_timestamp"
__DUMP_DATE_PATH = "/dump_date"

IMPORT_TIMESTAMP_URL = MASTR_STATIC_EXPORTS_URL + __IMPORT_TIMESTAMP_PATH
DUMP_DATE_URL = MASTR_STATIC_EXPORTS_URL + __DUMP_DATE_PATH


# todo -> correct names
class EnergySources(Enum):
    WIND = "Wind-Einheiten"
    BIO = "Biomasse-Einheiten"
    SOLAR = "Solar-Einheiten"
    KERN = "Kernkraft-Einheiten"
    WASSER = "Wasser-Einheiten"
    VERBRENNUNG = "Verbrennung-Einheiten"


_states = {
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "BW": "Baden-Wuerttemberg",
    "BY": "Bayern",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "NW": "Nordrhein-westfalen",
    "SA": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "BE": "Berlin",
    "HE": "Hessen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "TH": "Thueringen",
}

_nation = {"DE": "Deutschland"}


class DownloadFormats(Enum):
    PARQUET = ".parq"
    CSV = ".csv"
    EXCEL = ".xlsx"


DEFAULT_ENTITY_VALUE = "DE"  # this entity is available for all energy sources

WIND_ENTITES = {}
WIND_ENTITES.update(_nation)
WIND_ENTITES.update(_states)

SOLAR_ENTITES = {}
SOLAR_ENTITES.update(_nation)
SOLAR_ENTITES.update(_states)

VERBRENNUNG_ENTITES = {}
VERBRENNUNG_ENTITES.update(_nation)
VERBRENNUNG_ENTITES.update(_states)

BIO_ENTITES = {}
BIO_ENTITES.update(_nation)

KERN_ENTITES = {}
KERN_ENTITES.update(_nation)

WASSER_ENTITES = {}
WASSER_ENTITES.update(_nation)

ENTITY_MAP = {
    EnergySources.WIND: WIND_ENTITES,
    EnergySources.SOLAR: SOLAR_ENTITES,
    EnergySources.BIO: BIO_ENTITES,
    EnergySources.KERN: KERN_ENTITES,
    EnergySources.WASSER: WASSER_ENTITES,
    EnergySources.VERBRENNUNG: VERBRENNUNG_ENTITES,
}


class TABLE_SOURCE_ENTITY_URL(Enum):
    WIND_MV = MASTR_STATIC_EXPORTS_URL + "wind_mecklenburg-vorpommern.csv"
    WIND_NI = MASTR_STATIC_EXPORTS_URL + "wind_niedersachsen.csv"
    WIND_BW = MASTR_STATIC_EXPORTS_URL + "wind_baden-wuerttemberg.csv"
    WIND_BY = MASTR_STATIC_EXPORTS_URL + "wind_bayern.csv"
    WIND_BB = MASTR_STATIC_EXPORTS_URL + "wind_brandenburg.csv"
    WIND_HB = MASTR_STATIC_EXPORTS_URL + "wind_bremen.csv"
    WIND_HH = MASTR_STATIC_EXPORTS_URL + "wind_hamburg.csv"
    WIND_NW = MASTR_STATIC_EXPORTS_URL + "wind_nordrhein-westfalen.csv"
    WIND_SA = MASTR_STATIC_EXPORTS_URL + "wind_sachsen.csv"
    WIND_ST = MASTR_STATIC_EXPORTS_URL + "wind_sachsen-anhalt.csv"
    WIND_SH = MASTR_STATIC_EXPORTS_URL + "wind_schleswig-holstein.csv"
    WIND_BE = MASTR_STATIC_EXPORTS_URL + "wind_berlin.csv"
    WIND_HE = MASTR_STATIC_EXPORTS_URL + "wind_hessen.csv"
    WIND_RP = MASTR_STATIC_EXPORTS_URL + "wind_rheinland-pfalz.csv"
    WIND_SL = MASTR_STATIC_EXPORTS_URL + "wind_saarland.csv"
    WIND_TH = MASTR_STATIC_EXPORTS_URL + "wind_thueringen.csv"


if __name__ == "__main__":
    print(ENTITY_MAP[EnergySources.WIND])
