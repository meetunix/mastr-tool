from enum import Enum, auto


class Type(Enum):
    TEXT = (auto(), "text")
    INT = (auto(), "int")
    TIMESTAMP = (auto(), "timestamp")
    DATE = (auto(), "date")
    BOOLEAN = (auto(), "boolean")
    NUMERIC = (auto(), "numeric")


### definitions used to build select queries for exporting
class SelectUDFs(Enum):
    Katalog = "katalog({{field}})"
    Boolean = "boolean_hr({{field}})"
    Energietraeger = "energietraeger({{field}})"
    Netzbetreiberpruefungsstatus = "netzbetreiberpruefungsstatus({{field}})"
    Marktfunktion = "marktfunktion({{field}})"
    Marktrolle = "Marktrolle({{field}})"


# (auto(), SQL-type, NOT NULL, PKEY)
class EinheitWasser(Enum):
    EinheitMastrNummer = (auto(), Type.TEXT, True, True)
    DatumLetzteAktualisierung = (auto(), Type.TIMESTAMP, True, False)
    LokationMaStRNummer = (auto(), Type.TEXT, False, False)
    NetzbetreiberpruefungStatus = (auto(), Type.INT, False, False)
    NetzbetreiberpruefungDatum = (auto(), Type.DATE, False, False)
    AnlagenbetreiberMastrNummer = (auto(), Type.TEXT, False, False)
    Land = (auto(), Type.INT, False, False)
    Bundesland = (auto(), Type.INT, False, False)
    Landkreis = (auto(), Type.TEXT, False, False)
    Gemeinde = (auto(), Type.TEXT, False, False)
    Gemeindeschluessel = (auto(), Type.TEXT, False, False)
    Postleitzahl = (auto(), Type.TEXT, False, False)
    Gemarkung = (auto(), Type.TEXT, False, False)
    FlurFlurstuecknummern = (auto(), Type.TEXT, False, False)
    Strasse = (auto(), Type.TEXT, False, False)
    Hausnummer = (auto(), Type.TEXT, False, False)
    Adresszusatz = (auto(), Type.TEXT, False, False)
    Ort = (auto(), Type.TEXT, False, False)
    Laengengrad = (auto(), Type.NUMERIC, False, False)
    Breitengrad = (auto(), Type.NUMERIC, False, False)
    Registrierungsdatum = (auto(), Type.DATE, False, False)
    GeplantesInbetriebnahmedatum = (auto(), Type.DATE, False, False)
    Inbetriebnahmedatum = (auto(), Type.DATE, False, False)
    DatumEndgueltigeStilllegung = (auto(), Type.DATE, False, False)
    DatumWiederaufnahmeBetrieb = (auto(), Type.DATE, False, False)
    EinheitBetriebsstatus = (auto(), Type.INT, False, False)
    Weic = (auto(), Type.TEXT, False, False)
    WeicDisplayName = (auto(), Type.TEXT, False, False)
    Kraftwerksnummer = (auto(), Type.TEXT, False, False)
    Energietraeger = (auto(), Type.INT, False, False)
    Bruttoleistung = (auto(), Type.NUMERIC, False, False)
    Nettonennleistung = (auto(), Type.NUMERIC, False, False)
    FernsteuerbarkeitNb = (auto(), Type.BOOLEAN, False, False)
    FernsteuerbarkeitDv = (auto(), Type.BOOLEAN, False, False)
    Einspeisungsart = (auto(), Type.INT, False, False)
    GenMastrNummer = (auto(), Type.TEXT, False, False)
    EinheitSystemstatus = (auto(), Type.INT, False, False)
    BestandsanlageMastrNummer = (auto(), Type.TEXT, False, False)
    NichtVorhandenInMigriertenEinheiten = (auto(), Type.BOOLEAN, False, False)
    AltAnlagenbetreiberMastrNummer = (auto(), Type.TEXT, False, False)
    DatumDesBetreiberwechsels = (auto(), Type.DATE, False, False)
    DatumRegistrierungDesBetreiberwechsels = (auto(), Type.DATE, False, False)
    NameStromerzeugungseinheit = (auto(), Type.TEXT, False, False)
    ArtDerWasserkraftanlage = (auto(), Type.INT, False, False)
    MinderungStromerzeugung = (auto(), Type.BOOLEAN, False, False)
    BestandteilGrenzkraftwerk = (auto(), Type.BOOLEAN, False, False)
    NettonennleistungDeutschland = (auto(), Type.NUMERIC, False, False)
    ArtDesZuflusses = (auto(), Type.INT, False, False)
    EegMaStRNummer = (auto(), Type.TEXT, False, False)


class EinheitWind(Enum):
    EinheitMastrNummer = (auto(), Type.TEXT, True, True, None)
    DatumLetzteAktualisierung = (auto(), Type.TIMESTAMP, True, False, None)
    LokationMaStRNummer = (auto(), Type.TEXT, False, False, None)
    NetzbetreiberpruefungStatus = (auto(), Type.INT, False, False, SelectUDFs.Netzbetreiberpruefungsstatus)
    NetzbetreiberpruefungDatum = (auto(), Type.DATE, False, False, None)
    AnlagenbetreiberMastrNummer = (auto(), Type.TEXT, False, False, None)
    Land = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    Bundesland = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    Landkreis = (auto(), Type.TEXT, False, False, None)
    Gemeinde = (auto(), Type.TEXT, False, False, None)
    Gemeindeschluessel = (auto(), Type.TEXT, False, False, None)
    Postleitzahl = (auto(), Type.TEXT, False, False, None)
    Gemarkung = (auto(), Type.TEXT, False, False, None)
    FlurFlurstuecknummern = (auto(), Type.TEXT, False, False, None)
    Strasse = (auto(), Type.TEXT, False, False, None)
    Hausnummer = (auto(), Type.TEXT, False, False, None)
    Ort = (auto(), Type.TEXT, False, False, None)
    Laengengrad = (auto(), Type.NUMERIC, False, False, None)
    Breitengrad = (auto(), Type.NUMERIC, False, False, None)
    UTM_zone = (auto(), Type.TEXT, False, False, None)
    UTM_ost = (auto(), Type.NUMERIC, False, False, None)
    UTM_nord = (auto(), Type.NUMERIC, False, False, None)
    Registrierungsdatum = (auto(), Type.DATE, False, False, None)
    GeplantesInbetriebnahmedatum = (auto(), Type.DATE, False, False, None)
    Inbetriebnahmedatum = (auto(), Type.DATE, False, False, None)
    DatumEndgueltigeStilllegung = (auto(), Type.DATE, False, False, None)
    DatumBeginnVoruebergehendeStilllegung = (auto(), Type.DATE, False, False, None)
    DatumWiederaufnahmeBetrieb = (auto(), Type.DATE, False, False, None)
    EinheitSystemstatus = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    EinheitBetriebsstatus = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    NameStromerzeugungseinheit = (auto(), Type.TEXT, False, False, None)
    Weic = (auto(), Type.TEXT, False, False, None)
    WeicDisplayName = (auto(), Type.TEXT, False, False, None)
    Kraftwerksnummer = (auto(), Type.TEXT, False, False, None)
    Energietraeger = (auto(), Type.INT, False, False, SelectUDFs.Energietraeger)
    Bruttoleistung = (auto(), Type.NUMERIC, False, False, None)
    Nettonennleistung = (auto(), Type.NUMERIC, False, False, None)
    AnschlussAnHoechstOderHochSpannung = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    FernsteuerbarkeitNb = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    FernsteuerbarkeitDv = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    Einspeisungsart = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    NameWindpark = (auto(), Type.TEXT, False, False, None)
    Lage = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    Seelage = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    ClusterOstsee = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    ClusterNordsee = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    Hersteller = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    Technologie = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    Typenbezeichnung = (auto(), Type.TEXT, False, False, None)
    Nabenhoehe = (auto(), Type.NUMERIC, False, False, None)
    Rotordurchmesser = (auto(), Type.NUMERIC, False, False, None)
    Rotorblattenteisungssystem = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    AuflageAbschaltungLeistungsbegrenzung = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    AuflagenAbschaltungSchallimmissionsschutzNachts = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    AuflagenAbschaltungSchallimmissionsschutzTagsueber = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    AuflagenAbschaltungSchattenwurf = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    AuflagenAbschaltungTierschutz = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    AuflagenAbschaltungEiswurf = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    AuflagenAbschaltungSonstige = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    Nachtkennzeichnung = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    Buergerenergie = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    Wassertiefe = (auto(), Type.NUMERIC, False, False, None)
    Kuestenentfernung = (auto(), Type.NUMERIC, False, False, None)
    EegMaStRNummer = (auto(), Type.TEXT, False, False, None)


class EinheitSolar(Enum):
    EinheitMastrNummer = (auto(), Type.TEXT, True, True, None)
    DatumLetzteAktualisierung = (auto(), Type.TIMESTAMP, True, False, None)
    LokationMaStRNummer = (auto(), Type.TEXT, False, False, None)
    NetzbetreiberpruefungStatus = (auto(), Type.INT, False, False, SelectUDFs.Netzbetreiberpruefungsstatus)
    NetzbetreiberpruefungDatum = (auto(), Type.DATE, False, False, None)
    AnlagenbetreiberMastrNummer = (auto(), Type.TEXT, False, False, None)
    Land = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    Bundesland = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    Landkreis = (auto(), Type.TEXT, False, False, None)
    Gemeinde = (auto(), Type.TEXT, False, False, None)
    Gemeindeschluessel = (auto(), Type.TEXT, False, False, None)
    Gemarkung = (auto(), Type.TEXT, False, False, None)
    FlurFlurstuecknummern = (auto(), Type.TEXT, False, False, None)
    Postleitzahl = (auto(), Type.TEXT, False, False, None)
    Strasse = (auto(), Type.TEXT, False, False, None)
    Hausnummer = (auto(), Type.TEXT, False, False, None)
    Ort = (auto(), Type.TEXT, False, False, None)
    Laengengrad = (auto(), Type.NUMERIC, False, False, None)
    Breitengrad = (auto(), Type.NUMERIC, False, False, None)
    Registrierungsdatum = (auto(), Type.DATE, False, False, None)
    GeplantesInbetriebnahmedatum = (auto(), Type.DATE, False, False, None)
    Inbetriebnahmedatum = (auto(), Type.DATE, False, False, None)
    DatumEndgueltigeStilllegung = (auto(), Type.DATE, False, False, None)
    DatumBeginnVoruebergehendeStilllegung = (auto(), Type.DATE, False, False, None)
    DatumWiederaufnahmeBetrieb = (auto(), Type.DATE, False, False, None)
    EinheitBetriebsstatus = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    BestandsanlageMastrNummer = (auto(), Type.TEXT, False, False, None)
    NameStromerzeugungseinheit = (auto(), Type.TEXT, False, False, None)
    Weic = (auto(), Type.TEXT, False, False, None)
    WeicDisplayName = (auto(), Type.TEXT, False, False, None)
    Kraftwerksnummer = (auto(), Type.TEXT, False, False, None)
    Energietraeger = (auto(), Type.INT, False, False, SelectUDFs.Energietraeger)
    Bruttoleistung = (auto(), Type.NUMERIC, False, False, None)
    Nettonennleistung = (auto(), Type.NUMERIC, False, False, None)
    Einsatzverantwortlicher = (auto(), Type.TEXT, False, False, None)
    FernsteuerbarkeitNb = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    FernsteuerbarkeitDv = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    Einspeisungsart = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    GenMastrNummer = (auto(), Type.TEXT, False, False, None)
    EinheitSystemstatus = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    Energieträger = (auto(), Type.INT, False, False, SelectUDFs.Energietraeger)
    AnschlussAnHoechstOderHochSpannung = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    zugeordneteWirkleistungWechselrichter = (auto(), Type.NUMERIC, False, False, None)
    AnzahlModule = (auto(), Type.INT, False, False, None)
    Lage = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    Leistungsbegrenzung = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    EinheitlicheAusrichtungUndNeigungswinkel = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    Hauptausrichtung = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    HauptausrichtungNeigungswinkel = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    Nebenausrichtung = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    NebenausrichtungNeigungswinkel = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    InAnspruchGenommeneFlaeche = (auto(), Type.NUMERIC, False, False, None)
    # ArtDerFlaecheIds = (auto(), Type.TEXT, False, False, SelectUDFs.Katalog) # todo - composite-value-field -> needs specific udf
    InAnspruchGenommeneAckerflaeche = (auto(), Type.NUMERIC, False, False, None)
    Nutzungsbereich = (auto(), Type.INT, False, False, SelectUDFs.Katalog)
    Buergerenergie = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    EegMaStRNummer = (auto(), Type.TEXT, False, False, None)


class EinheitenBiomasse(Enum):
    EinheitMastrNummer = (auto(), Type.TEXT, True, True)
    DatumLetzteAktualisierung = (auto(), Type.TIMESTAMP, True, False)
    LokationMaStRNummer = (auto(), Type.TEXT, False, False)
    NetzbetreiberpruefungStatus = (auto(), Type.INT, False, False)
    NetzbetreiberpruefungDatum = (auto(), Type.DATE, False, False)
    AnlagenbetreiberMastrNummer = (auto(), Type.TEXT, False, False)
    Land = (auto(), Type.INT, False, False)
    Bundesland = (auto(), Type.INT, False, False)
    Landkreis = (auto(), Type.TEXT, False, False)
    Gemeinde = (auto(), Type.TEXT, False, False)
    Gemeindeschluessel = (auto(), Type.TEXT, False, False)
    Postleitzahl = (auto(), Type.TEXT, False, False)
    Strasse = (auto(), Type.TEXT, False, False)
    Hausnummer = (auto(), Type.TEXT, False, False)
    Ort = (auto(), Type.TEXT, False, False)
    Laengengrad = (auto(), Type.NUMERIC, False, False)
    Breitengrad = (auto(), Type.NUMERIC, False, False)
    Registrierungsdatum = (auto(), Type.DATE, False, False)
    GeplantesInbetriebnahmedatum = (auto(), Type.DATE, False, False)
    Inbetriebnahmedatum = (auto(), Type.DATE, False, False)
    DatumEndgueltigeStilllegung = (auto(), Type.DATE, False, False)
    DatumBeginnVoruebergehendeStilllegung = (auto(), Type.DATE, False, False)
    DatumWiederaufnahmeBetrieb = (auto(), Type.DATE, False, False)
    EinheitBetriebsstatus = (auto(), Type.INT, False, False)
    BestandsanlageMastrNummer = (auto(), Type.TEXT, False, False)
    NameStromerzeugungseinheit = (auto(), Type.TEXT, False, False)
    Weic = (auto(), Type.TEXT, False, False)
    Kraftwerksnummer = (auto(), Type.TEXT, False, False)
    Bruttoleistung = (auto(), Type.NUMERIC, False, False)
    Nettonennleistung = (auto(), Type.NUMERIC, False, False)
    Einsatzverantwortlicher = (auto(), Type.TEXT, False, False)
    FernsteuerbarkeitNb = (auto(), Type.BOOLEAN, False, False)
    FernsteuerbarkeitDv = (auto(), Type.BOOLEAN, False, False)
    Einspeisungsart = (auto(), Type.INT, False, False)
    GenMastrNummer = (auto(), Type.TEXT, False, False)  # maybe defaults until here
    Hauptbrennstoff = (auto(), Type.INT, False, False)  # katalog kategorie: BiomasseBrennstoff
    Biomasseart = (auto(), Type.INT, False, False)  # katalog kategorie: BiomasseArt
    Technologie = (auto(), Type.INT, False, False)  # katalog kategorie: TechnologieVerbrennungsanlage
    EegMaStRNummer = (auto(), Type.TEXT, False, False)
    KwkMaStRNummer = (auto(), Type.TEXT, False, False)


class AnlageEegWind(Enum):
    EegMaStRNummer = (auto(), Type.TEXT, True, True)
    DatumLetzteAktualisierung = (auto(), Type.TIMESTAMP, True, False)
    Registrierungsdatum = (auto(), Type.DATE, False, False)
    EegInbetriebnahmedatum = (auto(), Type.DATE, False, False)
    AnlagenkennzifferAnlagenregister = (auto(), Type.TEXT, False, False)
    AnlagenkennzifferAnlagenregister_nv = (auto(), Type.BOOLEAN, False, False)
    AnlagenschluesselEeg = (auto(), Type.TEXT, False, False)
    PrototypAnlage = (auto(), Type.BOOLEAN, False, False)
    PilotAnlage = (auto(), Type.BOOLEAN, False, False)
    InstallierteLeistung = (auto(), Type.NUMERIC, False, False)
    VerhaeltnisErtragsschaetzungReferenzertrag = (auto(), Type.NUMERIC, False, False)
    VerhaeltnisErtragsschaetzungReferenzertrag_nv = (auto(), Type.BOOLEAN, False, False)
    VerhaeltnisReferenzertragErtrag5Jahre = (auto(), Type.NUMERIC, False, False)
    VerhaeltnisReferenzertragErtrag5Jahre_nv = (auto(), Type.BOOLEAN, False, False)
    VerhaeltnisReferenzertragErtrag10Jahre = (auto(), Type.NUMERIC, False, False)
    VerhaeltnisReferenzertragErtrag10Jahr_nv = (auto(), Type.BOOLEAN, False, False)
    VerhaeltnisReferenzertragErtrag15Jahre = (auto(), Type.NUMERIC, False, False)
    VerhaeltnisReferenzertragErtrag15Jahre_nv = (auto(), Type.BOOLEAN, False, False)
    AusschreibungZuschlag = (auto(), Type.BOOLEAN, False, False)
    Zuschlagsnummer = (auto(), Type.TEXT, False, False)
    AnlageBetriebsstatus = (auto(), Type.INT, False, False)
    VerknuepfteEinheitenMaStRNummern = (auto(), Type.TEXT, False, False)


class Marktakteur(Enum):
    MastrNummer = (auto(), Type.TEXT, True, True, None)
    DatumLetzteAktualisierung = (auto(), Type.TIMESTAMP, False, False, None)
    Id = (auto(), Type.INT, False, False, None)
    Personenart = (auto(), Type.INT, False, False, SelectUDFs.Katalog)  # katalog
    MarktakteurAnrede = (auto(), Type.INT, False, False, SelectUDFs.Katalog)  # katalog
    MarktakteurTitel = (auto(), Type.INT, False, False, SelectUDFs.Katalog)  # katalog
    MarktakteurVorname = (auto(), Type.TEXT, False, False, None)
    MarktakteurNachname = (auto(), Type.TEXT, False, False, None)
    Firmenname = (auto(), Type.TEXT, False, False, None)
    Marktfunktion = (auto(), Type.INT, False, False, SelectUDFs.Marktfunktion)  # systemkatalog marktfunktion
    Rechtsform = (auto(), Type.INT, False, False, SelectUDFs.Katalog)  # katalog
    SonstigeRechtsform = (auto(), Type.TEXT, False, False, None)
    Marktrollen = (auto(), Type.TEXT, False, False, None)  # composit-objekt
    Marktakteursvertreter = (auto(), Type.TEXT, False, False, None)
    Land = (auto(), Type.INT, False, False, SelectUDFs.Katalog)  # katalog
    Region = (auto(), Type.TEXT, False, False, None)
    Strasse = (auto(), Type.TEXT, False, False, None)
    Hausnummer = (auto(), Type.TEXT, False, False, None)
    Adresszusatz = (auto(), Type.TEXT, False, False, None)
    Postleitzahl = (auto(), Type.TEXT, False, False, None)
    Ort = (auto(), Type.TEXT, False, False, None)
    Bundesland = (auto(), Type.INT, False, False, SelectUDFs.Katalog)  # katalog
    Nuts2 = (auto(), Type.TEXT, False, False, None)
    Email = (auto(), Type.TEXT, False, False, None)
    Telefon = (auto(), Type.TEXT, False, False, None)
    Webseite = (auto(), Type.TEXT, False, False, None)
    Registergericht = (auto(), Type.INT, False, False, SelectUDFs.Katalog)  # katalog
    RegistergerichtAusland = (auto(), Type.TEXT, False, False, None)
    Registernummer = (auto(), Type.TEXT, False, False, None)
    RegisternummerAusland = (auto(), Type.TEXT, False, False, None)
    Taetigkeitsbeginn = (auto(), Type.DATE, False, False, None)
    Taetigkeitsende = (auto(), Type.DATE, False, False, None)
    AcerCode = (auto(), Type.TEXT, False, False, None)
    Umsatzsteueridentifikationsnummer = (auto(), Type.TEXT, False, False, None)
    BundesnetzagenturBetriebsnummer = (auto(), Type.TEXT, False, False, None)
    LandAnZustelladresse = (auto(), Type.INT, False, False, SelectUDFs.Katalog)  # katalog
    PostleitzahlAnZustelladresse = (auto(), Type.TEXT, False, False, None)
    OrtAnZustelladresse = (auto(), Type.TEXT, False, False, None)
    StrasseAnZustelladresse = (auto(), Type.TEXT, False, False, None)
    HausnummerAnZustelladresse = (auto(), Type.TEXT, False, False, None)
    AdresszusatzAnZustelladresse = (auto(), Type.TEXT, False, False, None)
    Kmu = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    EmailVMav = (auto(), Type.TEXT, False, False, None)
    RegistrierungsdatumMarktakteur = (auto(), Type.TIMESTAMP, False, False, None)
    HauptwirtdschaftszweigAbteilung = (auto(), Type.INT, False, False, SelectUDFs.Katalog)  # katalog
    HauptwirtdschaftszweigGruppe = (auto(), Type.INT, False, False, SelectUDFs.Katalog)  # katalog
    HauptwirtdschaftszweigAbschnitt = (auto(), Type.INT, False, False, SelectUDFs.Katalog)  # katalog
    Direktvermarktungsunternehmen = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    BelieferungVonLetztverbrauchernStrom = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    BelieferungHaushaltskundenStrom = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    Gasgrosshaendler = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    Stromgrosshaendler = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    BelieferungVonLetztverbrauchernGas = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)
    BelieferungHaushaltskundenGas = (auto(), Type.BOOLEAN, False, False, SelectUDFs.Boolean)


class Katalogwert(Enum):
    Id = (auto(), Type.INT, True, True)
    Wert = (auto(), Type.TEXT, False, False)
    KatalogKategorieId = (auto(), Type.INT, False, False)


class Katalogkategorie(Enum):
    Id = (auto(), Type.INT, True, True)
    Name = (auto(), Type.TEXT, False, False)


class Einheiten(Enum):
    EinheitenWasser = EinheitWasser
    EinheitenWind = EinheitWind
    EinheitenSolar = EinheitSolar
    EinheitenBiomasse = EinheitenBiomasse
    AnlagenEegWind = AnlageEegWind
    Marktakteure = Marktakteur
    Katalogwerte = Katalogwert
    Katalogkategorien = Katalogkategorie


# create additional indices
class Indices(Enum):
    Marktakteure = Marktakteur.Personenart
    Katalogwerte = Katalogwert.KatalogKategorieId
    EinheitenWind = EinheitWind.Bundesland
    EinheitenSolar = EinheitSolar.Bundesland
    EinheitenWasser = EinheitWasser.Bundesland
    EinheitenBiomasse = EinheitenBiomasse.Bundesland


if __name__ == "__main__":

    for ent in EinheitWind:
        print(ent.name, ent.value)

    for e in Einheiten:
        print(type(e.value))
        for entity in e.value:
            print(f"{entity.name:42} ->  {entity.value[1]}")

    # print(EinheitWind(3).name)
