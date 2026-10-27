from dataclasses import dataclass
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
    Marktfunktion = "marktfunktion({{field}})"
    Marktrolle = "Marktrolle({{field}})"
    KatalogList = "katalog_list({{field}})"


@dataclass(frozen=True, eq=False)
class Column:
    """Definition of a database column and its corresponding XML field.

    The name of the enum member doubles as the XML tag and the column name.
    Equality is identity-based: enum members with equal definitions must not
    become aliases of each other.
    """

    type: Type
    not_null: bool = False
    primary_key: bool = False
    udf: SelectUDFs | None = None


class EinheitWasser(Enum):
    EinheitMastrNummer = Column(Type.TEXT, not_null=True, primary_key=True)
    DatumLetzteAktualisierung = Column(Type.TIMESTAMP, not_null=True)
    LokationMaStRNummer = Column(Type.TEXT)
    NetzbetreiberpruefungStatus = Column(Type.INT, udf=SelectUDFs.Katalog)
    NetzbetreiberpruefungDatum = Column(Type.DATE)
    AnlagenbetreiberMastrNummer = Column(Type.TEXT)
    Land = Column(Type.INT, udf=SelectUDFs.Katalog)
    Bundesland = Column(Type.INT, udf=SelectUDFs.Katalog)
    Landkreis = Column(Type.TEXT)
    Gemeinde = Column(Type.TEXT)
    Gemeindeschluessel = Column(Type.TEXT)
    Postleitzahl = Column(Type.TEXT)
    Gemarkung = Column(Type.TEXT)
    FlurFlurstuecknummern = Column(Type.TEXT)
    Strasse = Column(Type.TEXT)
    Hausnummer = Column(Type.TEXT)
    Hausnummer_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Adresszusatz = Column(Type.TEXT)
    Ort = Column(Type.TEXT)
    Laengengrad = Column(Type.NUMERIC)
    Breitengrad = Column(Type.NUMERIC)
    UTM_zone = Column(Type.TEXT)
    UTM_ost = Column(Type.NUMERIC)
    UTM_nord = Column(Type.NUMERIC)
    Registrierungsdatum = Column(Type.DATE)
    GeplantesInbetriebnahmedatum = Column(Type.DATE)
    Inbetriebnahmedatum = Column(Type.DATE)
    DatumEndgueltigeStilllegung = Column(Type.DATE)
    DatumWiederaufnahmeBetrieb = Column(Type.DATE)
    EinheitBetriebsstatus = Column(Type.INT, udf=SelectUDFs.Katalog)
    Weic = Column(Type.TEXT)
    Weic_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    WeicDisplayName = Column(Type.TEXT)
    Kraftwerksnummer = Column(Type.TEXT)
    Kraftwerksnummer_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Energietraeger = Column(Type.INT, udf=SelectUDFs.Katalog)
    Bruttoleistung = Column(Type.NUMERIC)
    Nettonennleistung = Column(Type.NUMERIC)
    FernsteuerbarkeitNb = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    FernsteuerbarkeitDv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Einspeisungsart = Column(Type.INT, udf=SelectUDFs.Katalog)
    GenMastrNummer = Column(Type.TEXT)
    EinheitSystemstatus = Column(Type.INT, udf=SelectUDFs.Katalog)
    BestandsanlageMastrNummer = Column(Type.TEXT)
    NichtVorhandenInMigriertenEinheiten = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    AltAnlagenbetreiberMastrNummer = Column(Type.TEXT)
    DatumDesBetreiberwechsels = Column(Type.DATE)
    DatumRegistrierungDesBetreiberwechsels = Column(Type.DATE)
    NameStromerzeugungseinheit = Column(Type.TEXT)
    ArtDerWasserkraftanlage = Column(Type.INT, udf=SelectUDFs.Katalog)
    MinderungStromerzeugung = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    BestandteilGrenzkraftwerk = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    NettonennleistungDeutschland = Column(Type.NUMERIC)
    ArtDesZuflusses = Column(Type.INT, udf=SelectUDFs.Katalog)
    EegMaStRNummer = Column(Type.TEXT)


class EinheitWind(Enum):
    EinheitMastrNummer = Column(Type.TEXT, not_null=True, primary_key=True)
    DatumLetzteAktualisierung = Column(Type.TIMESTAMP, not_null=True)
    LokationMaStRNummer = Column(Type.TEXT)
    NetzbetreiberpruefungStatus = Column(Type.INT, udf=SelectUDFs.Katalog)
    NetzbetreiberpruefungDatum = Column(Type.DATE)
    AnlagenbetreiberMastrNummer = Column(Type.TEXT)
    Land = Column(Type.INT, udf=SelectUDFs.Katalog)
    Bundesland = Column(Type.INT, udf=SelectUDFs.Katalog)
    Landkreis = Column(Type.TEXT)
    Gemeinde = Column(Type.TEXT)
    Gemeindeschluessel = Column(Type.TEXT)
    Postleitzahl = Column(Type.TEXT)
    Gemarkung = Column(Type.TEXT)
    FlurFlurstuecknummern = Column(Type.TEXT)
    Strasse = Column(Type.TEXT)
    Hausnummer = Column(Type.TEXT)
    Hausnummer_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Ort = Column(Type.TEXT)
    Laengengrad = Column(Type.NUMERIC)
    Breitengrad = Column(Type.NUMERIC)
    UTM_zone = Column(Type.TEXT)
    UTM_ost = Column(Type.NUMERIC)
    UTM_nord = Column(Type.NUMERIC)
    Registrierungsdatum = Column(Type.DATE)
    GeplantesInbetriebnahmedatum = Column(Type.DATE)
    Inbetriebnahmedatum = Column(Type.DATE)
    DatumEndgueltigeStilllegung = Column(Type.DATE)
    DatumBeginnVoruebergehendeStilllegung = Column(Type.DATE)
    DatumWiederaufnahmeBetrieb = Column(Type.DATE)
    EinheitSystemstatus = Column(Type.INT, udf=SelectUDFs.Katalog)
    EinheitBetriebsstatus = Column(Type.INT, udf=SelectUDFs.Katalog)
    NameStromerzeugungseinheit = Column(Type.TEXT)
    Weic = Column(Type.TEXT)
    Weic_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    WeicDisplayName = Column(Type.TEXT)
    Kraftwerksnummer = Column(Type.TEXT)
    Kraftwerksnummer_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Energietraeger = Column(Type.INT, udf=SelectUDFs.Katalog)
    Bruttoleistung = Column(Type.NUMERIC)
    Nettonennleistung = Column(Type.NUMERIC)
    AnschlussAnHoechstOderHochSpannung = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    FernsteuerbarkeitNb = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    FernsteuerbarkeitDv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Einspeisungsart = Column(Type.INT, udf=SelectUDFs.Katalog)
    NameWindpark = Column(Type.TEXT)
    WindAnLandOderAufSee = Column(Type.INT, udf=SelectUDFs.Katalog)
    Seelage = Column(Type.INT, udf=SelectUDFs.Katalog)
    GebietNachDemFlaechenentwicklungsplanNordsee = Column(Type.INT, udf=SelectUDFs.Katalog)
    GebietNachDemFlaechenentwicklungsplanOstsee = Column(Type.INT, udf=SelectUDFs.Katalog)
    Hersteller = Column(Type.INT, udf=SelectUDFs.Katalog)
    Technologie = Column(Type.INT, udf=SelectUDFs.Katalog)
    Typenbezeichnung = Column(Type.TEXT)
    Nabenhoehe = Column(Type.NUMERIC)
    Rotordurchmesser = Column(Type.NUMERIC)
    Rotorblattenteisungssystem = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    AuflageAbschaltungLeistungsbegrenzung = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    AuflagenAbschaltungSchallimmissionsschutzNachts = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    AuflagenAbschaltungSchallimmissionsschutzTagsueber = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    AuflagenAbschaltungSchattenwurf = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    AuflagenAbschaltungTierschutz = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    AuflagenAbschaltungEiswurf = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    AuflagenAbschaltungSonstige = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Nachtkennzeichnung = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Buergerenergie = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Wassertiefe = Column(Type.NUMERIC)
    Kuestenentfernung = Column(Type.NUMERIC)
    EegMaStRNummer = Column(Type.TEXT)


class EinheitSolar(Enum):
    EinheitMastrNummer = Column(Type.TEXT, not_null=True, primary_key=True)
    DatumLetzteAktualisierung = Column(Type.TIMESTAMP, not_null=True)
    LokationMaStRNummer = Column(Type.TEXT)
    NetzbetreiberpruefungStatus = Column(Type.INT, udf=SelectUDFs.Katalog)
    NetzbetreiberpruefungDatum = Column(Type.DATE)
    AnlagenbetreiberMastrNummer = Column(Type.TEXT)
    Land = Column(Type.INT, udf=SelectUDFs.Katalog)
    Bundesland = Column(Type.INT, udf=SelectUDFs.Katalog)
    Landkreis = Column(Type.TEXT)
    Gemeinde = Column(Type.TEXT)
    Gemeindeschluessel = Column(Type.TEXT)
    Gemarkung = Column(Type.TEXT)
    FlurFlurstuecknummern = Column(Type.TEXT)
    Postleitzahl = Column(Type.TEXT)
    Strasse = Column(Type.TEXT)
    Hausnummer = Column(Type.TEXT)
    Hausnummer_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Ort = Column(Type.TEXT)
    Laengengrad = Column(Type.NUMERIC)
    Breitengrad = Column(Type.NUMERIC)
    UTM_zone = Column(Type.TEXT)
    UTM_ost = Column(Type.NUMERIC)
    UTM_nord = Column(Type.NUMERIC)
    Registrierungsdatum = Column(Type.DATE)
    GeplantesInbetriebnahmedatum = Column(Type.DATE)
    Inbetriebnahmedatum = Column(Type.DATE)
    DatumEndgueltigeStilllegung = Column(Type.DATE)
    DatumBeginnVoruebergehendeStilllegung = Column(Type.DATE)
    DatumWiederaufnahmeBetrieb = Column(Type.DATE)
    EinheitBetriebsstatus = Column(Type.INT, udf=SelectUDFs.Katalog)
    BestandsanlageMastrNummer = Column(Type.TEXT)
    NameStromerzeugungseinheit = Column(Type.TEXT)
    Weic = Column(Type.TEXT)
    Weic_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    WeicDisplayName = Column(Type.TEXT)
    Kraftwerksnummer = Column(Type.TEXT)
    Kraftwerksnummer_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Energietraeger = Column(Type.INT, udf=SelectUDFs.Katalog)
    Bruttoleistung = Column(Type.NUMERIC)
    Nettonennleistung = Column(Type.NUMERIC)
    Einsatzverantwortlicher = Column(Type.TEXT)
    FernsteuerbarkeitNb = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    FernsteuerbarkeitDv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Einspeisungsart = Column(Type.INT, udf=SelectUDFs.Katalog)
    GenMastrNummer = Column(Type.TEXT)
    EinheitSystemstatus = Column(Type.INT, udf=SelectUDFs.Katalog)
    AnschlussAnHoechstOderHochSpannung = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    ZugeordneteWirkleistungWechselrichter = Column(Type.NUMERIC)
    AnzahlModule = Column(Type.INT)
    ArtDerSolaranlage = Column(Type.INT, udf=SelectUDFs.Katalog)
    Leistungsbegrenzung = Column(Type.INT, udf=SelectUDFs.Katalog)
    EinheitlicheAusrichtungUndNeigungswinkel = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Hauptausrichtung = Column(Type.INT, udf=SelectUDFs.Katalog)
    HauptausrichtungNeigungswinkel = Column(Type.INT, udf=SelectUDFs.Katalog)
    Nebenausrichtung = Column(Type.INT, udf=SelectUDFs.Katalog)
    NebenausrichtungNeigungswinkel = Column(Type.INT, udf=SelectUDFs.Katalog)
    GroesseDerInAnspruchGenommenenFlaecheInHektar = Column(Type.NUMERIC)
    UeberwiegendeNutzungsartDerFlaecheVorErrichtung = Column(Type.INT, udf=SelectUDFs.Katalog)
    VorherigerNutzungsartenbereichDerFlaeche = Column(Type.INT, udf=SelectUDFs.Katalog)
    ZusaetzlicheMerkmaleDerFlaecheUndDerAktuellenFlaechennutzung = Column(Type.TEXT, udf=SelectUDFs.KatalogList)
    Nutzungsbereich = Column(Type.INT, udf=SelectUDFs.Katalog)
    Buergerenergie = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    EegMaStRNummer = Column(Type.TEXT)


class EinheitBiomasse(Enum):
    EinheitMastrNummer = Column(Type.TEXT, not_null=True, primary_key=True)
    DatumLetzteAktualisierung = Column(Type.TIMESTAMP, not_null=True)
    LokationMaStRNummer = Column(Type.TEXT)
    NetzbetreiberpruefungStatus = Column(Type.INT, udf=SelectUDFs.Katalog)
    NetzbetreiberpruefungDatum = Column(Type.DATE)
    AnlagenbetreiberMastrNummer = Column(Type.TEXT)
    Land = Column(Type.INT, udf=SelectUDFs.Katalog)
    Bundesland = Column(Type.INT, udf=SelectUDFs.Katalog)
    Landkreis = Column(Type.TEXT)
    Gemeinde = Column(Type.TEXT)
    Gemeindeschluessel = Column(Type.TEXT)
    Postleitzahl = Column(Type.TEXT)
    Strasse = Column(Type.TEXT)
    Hausnummer = Column(Type.TEXT)
    Hausnummer_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Ort = Column(Type.TEXT)
    Laengengrad = Column(Type.NUMERIC)
    Breitengrad = Column(Type.NUMERIC)
    UTM_zone = Column(Type.TEXT)
    UTM_ost = Column(Type.NUMERIC)
    UTM_nord = Column(Type.NUMERIC)
    Registrierungsdatum = Column(Type.DATE)
    GeplantesInbetriebnahmedatum = Column(Type.DATE)
    Inbetriebnahmedatum = Column(Type.DATE)
    DatumEndgueltigeStilllegung = Column(Type.DATE)
    DatumBeginnVoruebergehendeStilllegung = Column(Type.DATE)
    DatumWiederaufnahmeBetrieb = Column(Type.DATE)
    EinheitBetriebsstatus = Column(Type.INT, udf=SelectUDFs.Katalog)
    BestandsanlageMastrNummer = Column(Type.TEXT)
    NameStromerzeugungseinheit = Column(Type.TEXT)
    Weic = Column(Type.TEXT)
    Weic_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Kraftwerksnummer = Column(Type.TEXT)
    Kraftwerksnummer_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Bruttoleistung = Column(Type.NUMERIC)
    Nettonennleistung = Column(Type.NUMERIC)
    Einsatzverantwortlicher = Column(Type.TEXT)
    FernsteuerbarkeitNb = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    FernsteuerbarkeitDv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Einspeisungsart = Column(Type.INT, udf=SelectUDFs.Katalog)
    GenMastrNummer = Column(Type.TEXT)  # maybe defaults until here
    Hauptbrennstoff = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog kategorie: BiomasseBrennstoff
    Biomasseart = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog kategorie: BiomasseArt
    Technologie = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog kategorie: TechnologieVerbrennungsanlage
    EegMaStRNummer = Column(Type.TEXT)
    KwkMaStRNummer = Column(Type.TEXT)


class AnlageEegWind(Enum):
    EegMaStRNummer = Column(Type.TEXT, not_null=True, primary_key=True)
    DatumLetzteAktualisierung = Column(Type.TIMESTAMP, not_null=True)
    Registrierungsdatum = Column(Type.DATE)
    EegInbetriebnahmedatum = Column(Type.DATE)
    AnlagenkennzifferAnlagenregister = Column(Type.TEXT)
    AnlagenkennzifferAnlagenregister_nv = Column(Type.BOOLEAN)
    AnlagenschluesselEeg = Column(Type.TEXT)
    AnlagenschluesselEeg_nv = Column(Type.BOOLEAN)
    PrototypAnlage = Column(Type.BOOLEAN)
    PilotAnlage = Column(Type.BOOLEAN)
    InstallierteLeistung = Column(Type.NUMERIC)
    VerhaeltnisErtragsschaetzungReferenzertrag = Column(Type.NUMERIC)
    VerhaeltnisErtragsschaetzungReferenzertrag_nv = Column(Type.BOOLEAN)
    VerhaeltnisReferenzertragErtrag5Jahre = Column(Type.NUMERIC)
    VerhaeltnisReferenzertragErtrag5Jahre_nv = Column(Type.BOOLEAN)
    VerhaeltnisReferenzertragErtrag10Jahre = Column(Type.NUMERIC)
    VerhaeltnisReferenzertragErtrag10Jahre_nv = Column(Type.BOOLEAN)
    VerhaeltnisReferenzertragErtrag15Jahre = Column(Type.NUMERIC)
    VerhaeltnisReferenzertragErtrag15Jahre_nv = Column(Type.BOOLEAN)
    AusschreibungZuschlag = Column(Type.BOOLEAN)
    Zuschlagsnummer = Column(Type.TEXT)
    AnlageBetriebsstatus = Column(Type.INT)
    VerknuepfteEinheitenMaStRNummern = Column(Type.TEXT)


class AnlageEegSolar(Enum):
    EegMaStRNummer = Column(Type.TEXT, not_null=True, primary_key=True)
    DatumLetzteAktualisierung = Column(Type.TIMESTAMP, not_null=True)
    Registrierungsdatum = Column(Type.DATE)
    EegInbetriebnahmedatum = Column(Type.DATE)
    InanspruchnahmeZahlungNachEeg = Column(Type.BOOLEAN)
    AnlagenschluesselEeg = Column(Type.TEXT)
    AnlagenschluesselEeg_nv = Column(Type.BOOLEAN)
    AnlagenkennzifferAnlagenregister = Column(Type.TEXT)
    AnlagenkennzifferAnlagenregister_nv = Column(Type.BOOLEAN)
    InstallierteLeistung = Column(Type.NUMERIC)
    RegistrierungsnummerPvMeldeportal = Column(Type.TEXT)
    RegistrierungsnummerPvMeldeportal_nv = Column(Type.BOOLEAN)
    MieterstromZugeordnet = Column(Type.BOOLEAN)
    MieterstromMeldedatum = Column(Type.DATE)
    MieterstromErsteZuordnungZuschlag = Column(Type.DATE)
    AusschreibungZuschlag = Column(Type.BOOLEAN)
    ZugeordneteGebotsmenge = Column(Type.NUMERIC)
    Zuschlagsnummer = Column(Type.TEXT)
    AnlageBetriebsstatus = Column(Type.INT)
    VerknuepfteEinheitenMaStRNummern = Column(Type.TEXT)


class AnlageEegBiomasse(Enum):
    EegMaStRNummer = Column(Type.TEXT, not_null=True, primary_key=True)
    DatumLetzteAktualisierung = Column(Type.TIMESTAMP, not_null=True)
    Registrierungsdatum = Column(Type.DATE)
    EegInbetriebnahmedatum = Column(Type.DATE)
    AnlagenschluesselEeg = Column(Type.TEXT)
    AnlagenschluesselEeg_nv = Column(Type.BOOLEAN)
    AnlagenkennzifferAnlagenregister = Column(Type.TEXT)
    AnlagenkennzifferAnlagenregister_nv = Column(Type.BOOLEAN)
    InstallierteLeistung = Column(Type.NUMERIC)
    AusschliesslicheVerwendungBiomasse = Column(Type.BOOLEAN)
    AusschreibungZuschlag = Column(Type.BOOLEAN)
    Zuschlagsnummer = Column(Type.TEXT)
    BiogasInanspruchnahmeFlexiPraemie = Column(Type.BOOLEAN)
    BiogasDatumInanspruchnahmeFlexiPraemie = Column(Type.DATE)
    BiogasLeistungserhoehung = Column(Type.BOOLEAN)
    BiogasDatumLeistungserhoehung = Column(Type.DATE)
    BiogasUmfangLeistungserhoehung = Column(Type.NUMERIC)
    BiogasGaserzeugungskapazitaet = Column(Type.NUMERIC)
    BiogasGaserzeugungskapazitaet_nv = Column(Type.BOOLEAN)
    BiogasHoechstbemessungsleistung = Column(Type.NUMERIC)
    BiomethanErstmaligerEinsatz = Column(Type.DATE)
    BiomethanErstmaligerEinsatz_nv = Column(Type.BOOLEAN)
    AnlageBetriebsstatus = Column(Type.INT)
    VerknuepfteEinheitenMaStRNummern = Column(Type.TEXT)


class AnlageEegWasser(Enum):
    EegMaStRNummer = Column(Type.TEXT, not_null=True, primary_key=True)
    DatumLetzteAktualisierung = Column(Type.TIMESTAMP, not_null=True)
    Registrierungsdatum = Column(Type.DATE)
    EegInbetriebnahmedatum = Column(Type.DATE)
    AnlagenschluesselEeg = Column(Type.TEXT)
    AnlagenschluesselEeg_nv = Column(Type.BOOLEAN)
    AnlagenkennzifferAnlagenregister = Column(Type.TEXT)
    AnlagenkennzifferAnlagenregister_nv = Column(Type.BOOLEAN)
    InstallierteLeistung = Column(Type.NUMERIC)
    AnlageBetriebsstatus = Column(Type.INT)
    ErtuechtigungIds = Column(Type.TEXT)
    VerknuepfteEinheitenMaStRNummern = Column(Type.TEXT)


class AnlageEegSpeicher(Enum):
    EegMaStRNummer = Column(Type.TEXT, not_null=True, primary_key=True)
    DatumLetzteAktualisierung = Column(Type.TIMESTAMP, not_null=True)
    Registrierungsdatum = Column(Type.DATE)
    EegInbetriebnahmedatum = Column(Type.DATE)
    AnlagenschluesselEeg = Column(Type.TEXT)
    AnlagenschluesselEeg_nv = Column(Type.BOOLEAN)
    AusschreibungZuschlag = Column(Type.BOOLEAN)
    Zuschlagsnummer = Column(Type.TEXT)
    VerknuepfteEinheitenMaStRNummern = Column(Type.TEXT)


class AnlageEegGeothermieGrubengasDruckentspannung(Enum):
    EegMaStRNummer = Column(Type.TEXT, not_null=True, primary_key=True)
    DatumLetzteAktualisierung = Column(Type.TIMESTAMP, not_null=True)
    Registrierungsdatum = Column(Type.DATE)
    EegInbetriebnahmedatum = Column(Type.DATE)
    AnlagenschluesselEeg = Column(Type.TEXT)
    AnlagenschluesselEeg_nv = Column(Type.BOOLEAN)
    AnlagenkennzifferAnlagenregister = Column(Type.TEXT)
    AnlagenkennzifferAnlagenregister_nv = Column(Type.BOOLEAN)
    InstallierteLeistung = Column(Type.NUMERIC)
    AnlageBetriebsstatus = Column(Type.INT)
    VerknuepfteEinheitenMaStRNummern = Column(Type.TEXT)


class Marktakteur(Enum):
    MastrNummer = Column(Type.TEXT, not_null=True, primary_key=True)
    DatumLetzeAktualisierung = Column(Type.TIMESTAMP)
    Personenart = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog
    MarktakteurAnrede = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog
    MarktakteurTitel = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog
    MarktakteurVorname = Column(Type.TEXT)
    MarktakteurNachname = Column(Type.TEXT)
    Firmenname = Column(Type.TEXT)
    Marktfunktion = Column(Type.INT, udf=SelectUDFs.Marktfunktion)  # systemkatalog marktfunktion
    Rechtsform = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog
    SonstigeRechtsform = Column(Type.TEXT)
    Marktrollen = Column(Type.TEXT)  # composit-objekt
    Land = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog
    Region = Column(Type.TEXT)
    Strasse = Column(Type.TEXT)
    Hausnummer = Column(Type.TEXT)
    Hausnummer_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Adresszusatz = Column(Type.TEXT)
    Postleitzahl = Column(Type.TEXT)
    Ort = Column(Type.TEXT)
    Bundesland = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog
    Nuts2 = Column(Type.TEXT)
    Email = Column(Type.TEXT)
    Telefon = Column(Type.TEXT)
    Webseite = Column(Type.TEXT)
    Webseite_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Registergericht = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog
    RegistergerichtAusland = Column(Type.TEXT)
    Registernummer = Column(Type.TEXT)
    RegisternummerAusland = Column(Type.TEXT)
    Taetigkeitsbeginn = Column(Type.DATE)
    Taetigkeitsende = Column(Type.DATE)
    AcerCode = Column(Type.TEXT)
    AcerCode_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Umsatzsteueridentifikationsnummer = Column(Type.TEXT)
    Umsatzsteueridentifikationsnummer_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    BundesnetzagenturBetriebsnummer = Column(Type.TEXT)
    BundesnetzagenturBetriebsnummer_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    LandAnZustelladresse = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog
    PostleitzahlAnZustelladresse = Column(Type.TEXT)
    OrtAnZustelladresse = Column(Type.TEXT)
    StrasseAnZustelladresse = Column(Type.TEXT)
    HausnummerAnZustelladresse = Column(Type.TEXT)
    HausnummerAnZustelladresse_nv = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    AdresszusatzAnZustelladresse = Column(Type.TEXT)
    Kmu = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    RegistrierungsdatumMarktakteur = Column(Type.TIMESTAMP)
    HauptwirtdschaftszweigAbteilung = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog
    HauptwirtdschaftszweigGruppe = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog
    HauptwirtdschaftszweigAbschnitt = Column(Type.INT, udf=SelectUDFs.Katalog)  # katalog
    Direktvermarktungsunternehmen = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    BelieferungVonLetztverbrauchernStrom = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    BelieferungHaushaltskundenStrom = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Gasgrosshaendler = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    Stromgrosshaendler = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    BelieferungVonLetztverbrauchernGas = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)
    BelieferungHaushaltskundenGas = Column(Type.BOOLEAN, udf=SelectUDFs.Boolean)


class Katalogwert(Enum):
    Id = Column(Type.INT, not_null=True, primary_key=True)
    Wert = Column(Type.TEXT)
    KatalogKategorieId = Column(Type.INT)


class Katalogkategorie(Enum):
    Id = Column(Type.INT, not_null=True, primary_key=True)
    Name = Column(Type.TEXT)


class Einheiten(Enum):
    EinheitenWasser = EinheitWasser
    EinheitenWind = EinheitWind
    EinheitenSolar = EinheitSolar
    EinheitenBiomasse = EinheitBiomasse
    AnlagenEegWind = AnlageEegWind
    AnlagenEegSolar = AnlageEegSolar
    AnlagenEegBiomasse = AnlageEegBiomasse
    AnlagenEegWasser = AnlageEegWasser
    AnlagenEegSpeicher = AnlageEegSpeicher
    AnlagenEegGeothermieGrubengasDruckentspannung = AnlageEegGeothermieGrubengasDruckentspannung
    Marktakteure = Marktakteur
    Katalogwerte = Katalogwert
    Katalogkategorien = Katalogkategorie


class EinheitenGeoEnrichment(Enum):
    """Einheiten for geo coordinates enrichment"""

    EinheitenWasser = EinheitWasser
    EinheitenWind = EinheitWind
    EinheitenSolar = EinheitSolar
    EinheitenBiomasse = EinheitBiomasse


# create additional indices
class Indices(Enum):
    Marktakteure = Marktakteur.Personenart
    Katalogwerte = Katalogwert.KatalogKategorieId
    EinheitenWind = EinheitWind.Bundesland
    EinheitenSolar = EinheitSolar.Bundesland
    EinheitenWasser = EinheitWasser.Bundesland
    EinheitenBiomasse = EinheitBiomasse.Bundesland


if __name__ == "__main__":

    for ent in EinheitWind:
        print(ent.name, ent.value)

    for e in Einheiten:
        print(type(e.value))
        for entity in e.value:
            print(f"{entity.name:42} ->  {entity.value.type}")

    # print(EinheitWind(3).name)
