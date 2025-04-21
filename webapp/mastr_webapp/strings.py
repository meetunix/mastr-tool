"""
String definitions for the frontend.
"""

from .constants import *

from bidict import bidict

static_table_states = bidict(
    {
        TABLE_SOURCE_ENTITY_URL.WIND_MV: "Mecklenburg-Vorpommern",
        TABLE_SOURCE_ENTITY_URL.WIND_NI: "Niedersachsen",
        TABLE_SOURCE_ENTITY_URL.WIND_BY: "Bayern",
        TABLE_SOURCE_ENTITY_URL.WIND_BW: "Baden-Württemberg",
        TABLE_SOURCE_ENTITY_URL.WIND_HE: "Hessen",
        TABLE_SOURCE_ENTITY_URL.WIND_SH: "Schleswig-Holstein",
        TABLE_SOURCE_ENTITY_URL.WIND_HH: "Hamburg",
        TABLE_SOURCE_ENTITY_URL.WIND_HB: "Bremen",
        TABLE_SOURCE_ENTITY_URL.WIND_ST: "Sachsen-Anhalt",
        TABLE_SOURCE_ENTITY_URL.WIND_SA: "Sachsen",
        TABLE_SOURCE_ENTITY_URL.WIND_BB: "Brandenburg",
        TABLE_SOURCE_ENTITY_URL.WIND_TH: "Thüringen",
        TABLE_SOURCE_ENTITY_URL.WIND_RP: "Rheinland-Pfalz",
        TABLE_SOURCE_ENTITY_URL.WIND_BE: "Berlin",
        TABLE_SOURCE_ENTITY_URL.WIND_NW: "Nordrhein-Westfalen",
        TABLE_SOURCE_ENTITY_URL.WIND_SL: "Saarland",
    }
)
