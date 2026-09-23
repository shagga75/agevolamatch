"""Controlled vocabularies observed in the incentivi.gov.it Open Data feed.

Every value here was taken from a full dump of the live dataset (5,896 records,
inspected 2026-09-23), not guessed from documentation. See docs/sources.md for
the field-mapping table this file implements.
"""

from __future__ import annotations

from enum import StrEnum


class OpportunityStatus(StrEnum):
    """Computed from open/close dates at ingest time; the source has no status field."""

    OPEN = "open"
    UPCOMING = "upcoming"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class OpportunitySourceName(StrEnum):
    INCENTIVI_GOV_IT = "incentivi_gov_it"
    INVITALIA = "invitalia"
    ANAC = "anac"
    TED_EUROPA = "ted_europa"


class IncentiveScope(StrEnum):
    """Obiettivo_Finalita - 13 distinct values observed, 0% null."""

    INVESTMENT_SUPPORT = "Sostegno investimenti"
    LIQUIDITY_SUPPORT = "Sostegno liquidità"
    INTERNATIONALIZATION = "Internazionalizzazione"
    INNOVATION_RESEARCH = "Innovazione e ricerca"
    STARTUP_DEVELOPMENT = "Start up/Sviluppo d'impresa"
    DIGITALIZATION = "Digitalizzazione"
    ECOLOGICAL_TRANSITION = "Transizione ecologica"
    BUSINESS_CRISIS = "Crisi d'impresa"
    SOCIAL_INCLUSION = "Inclusione sociale"
    YOUTH_ENTREPRENEURSHIP = "Imprenditoria giovanile"
    WOMEN_ENTREPRENEURSHIP = "Imprenditoria femminile"
    TRAINING = "Formazione (lavoro, occupazione, riqualificazione professionale dei lavoratori)"
    CAPITAL_STRENGTHENING = "Rafforzamento del capitale"


class CompanySize(StrEnum):
    """Dimensioni - 5 distinct values observed, 0% null."""

    MICRO = "Microimpresa"
    SMALL = "Piccola Impresa"
    MEDIUM = "Media Impresa"
    LARGE = "Grande Impresa"
    UNCLASSIFIED = "Non classificabile/classificato"


class BeneficiaryType(StrEnum):
    """Tipologia_Soggetto - 16 distinct values observed, 0% null.

    NOTE: "SU/PMI innovativa" bundles "startup innovativa" and "PMI innovativa"
    into a single value - the source does not distinguish them. See
    docs/sources.md for how matching handles this ambiguity.
    """

    IMPRESA = "Impresa"
    COOPERATIVA_NONPROFIT = "Cooperative/Associazioni Non Profit"
    CONSORZIO = "Consorzio"
    RETE_IMPRESA = "Rete d'impresa"
    ENTE_PUBBLICO = "Ente Pubblico"
    STARTUP_O_PMI_INNOVATIVA = "Impresa - SU/PMI innovativa"
    IMPRESA_DA_COSTITUIRE_ALTRO = "Impresa da costituire - Altro"
    PROFESSIONISTA = "Professionista"
    UNIVERSITA_ENTE_RICERCA = "Università/Ente di Ricerca"
    CITTADINO = "Cittadino"
    IMPRESA_FEMMINILE = "Impresa - prevalenza femminile"
    IMPRESA_GIOVANILE = "Impresa - prevalenza giovanile"
    IMPRESA_DA_COSTITUIRE_GIOVANILE = "Impresa da costituire - Giovanile"
    IMPRESA_DA_COSTITUIRE_FEMMINILE = "Impresa da costituire - Femminile"
    ISTITUTO_FINANZIARIO = "Istituto finanziario"
    ASSOCIAZIONE_PROFESSIONISTI = "Associazione fra professionisti"


class SupportForm(StrEnum):
    """Forma_agevolazione - 6 distinct values observed, 0% null."""

    GRANT = "Contributo/Fondo perduto"
    SUBSIDIZED_LOAN = "Prestito/Anticipo rimborsabile"
    TAX_RELIEF = "Agevolazione fiscale"
    RISK_CAPITAL = "Capitale di rischio"
    GUARANTEE = "Interventi a garanzia"
    SOCIAL_CONTRIBUTION_REDUCTION = "Riduzione dei contributi di previdenza sociale"


class EligibleCost(StrEnum):
    """Costi_Ammessi - 7 distinct values observed, 0% null."""

    SERVICES_PATENTS_LICENSES = "Servizi, brevetti e licenze"
    OVERHEADS = "Spese generali/altri oneri"
    PLANTS_MACHINERY_EQUIPMENT = "Impianti/Macchinari/Attrezzature"
    PERSONNEL_COST = "Costo del personale"
    BUILDINGS_LAND = "Fabbricati e terreni"
    RAW_MATERIALS_GOODS = "Materie prime, di consumo e merci"
    PROFESSIONAL_TRAINING = "Formazione Professionale"


class ActivitySector(StrEnum):
    """Settore_Attivita - 21 distinct values observed, 4.8% null. Informative only:
    ATECO codes (when present) are the authoritative field for hard filtering."""

    COMMERCIO = "Commercio"
    ALTRI_SERVIZI = "Altri servizi"
    ARTIGIANATO = "Artigianato"
    TURISMO = "Turismo"
    RISTORAZIONE = "Ristorazione"
    AGROALIMENTARE = "Agroalimentare"
    ALBERGHIERO = "Alberghiero"
    CULTURA = "Cultura"
    MODA_TESSILE = "Moda e Tessile"
    MOBILI_LEGNO_CARTA = "Mobili, Legno e Carta"
    MECCANICA = "Meccanica"
    EDILIZIA = "Edilizia"
    ELETTRONICA = "Elettronica"
    ICT = "ICT"
    SERVIZI_TRASPORTO = "Servizi di trasporto"
    METALLURGIA = "Metallurgia"
    AUTOVEICOLI_TRASPORTO = "Autoveicoli e altri mezzi di trasporto"
    AGRICOLTURA_SILVICOLTURA_PESCA = "Agricoltura, silvicoltura e pesca"
    CHIMICA_FARMACEUTICA = "Chimica e Farmaceutica"
    SALUTE = "Salute"
    ENERGIA_ACQUA_RIFIUTI = "Fornitura Energia, Acqua e gestione Rifiuti"


class Region(StrEnum):
    """Regioni - 21 distinct values observed (20 Italian regions + 'Estero'), 0.1% null."""

    ABRUZZO = "Abruzzo"
    BASILICATA = "Basilicata"
    CALABRIA = "Calabria"
    CAMPANIA = "Campania"
    EMILIA_ROMAGNA = "Emilia-Romagna"
    FRIULI_VENEZIA_GIULIA = "Friuli-Venezia Giulia"
    LAZIO = "Lazio"
    LIGURIA = "Liguria"
    LOMBARDIA = "Lombardia"
    MARCHE = "Marche"
    MOLISE = "Molise"
    PIEMONTE = "Piemonte"
    PUGLIA = "Puglia"
    SARDEGNA = "Sardegna"
    SICILIA = "Sicilia"
    TOSCANA = "Toscana"
    TRENTINO_ALTO_ADIGE = "Trentino-Alto Adige/Südtirol"
    UMBRIA = "Umbria"
    VALLE_DAOSTA = "Valle d'Aosta/Vallée d'Aoste"
    VENETO = "Veneto"
    ESTERO = "Estero"


class SpecialTerritory(StrEnum):
    """Ambito_territoriale - 6 distinct values observed, 87.9% null."""

    AREE_INTERNE = "Aree interne"
    ZES = "ZES"
    NON_APPLICABILE = "Non applicabile"
    ZONE_SISMICHE = "Zone sismiche"
    ZONE_FRANCHE = "Zone franche"
    EMERGENZA_CLIMATICA = "Emergenza climatica"


class LegalForm(StrEnum):
    """Legal form of a company profile - not sourced from incentivi.gov.it
    (that dataset has no company registry data); used only for CompanyProfile.

    ASSOCIAZIONE covers APS, ODV, ONLUS and other Terzo Settore associations -
    the source's Tipologia_Soggetto vocabulary has no value distinguishing
    these from cooperatives, so both map to BeneficiaryType.COOPERATIVA_NONPROFIT
    ("Cooperative/Associazioni Non Profit") in matching/filters.py. Confirmed
    against 13 real incentives mentioning APS/ODV/Terzo Settore in the live
    dataset (2026-09-23) - none uses a more specific beneficiary type."""

    SRL = "srl"
    SRLS = "srls"
    SPA = "spa"
    SNC = "snc"
    SAS = "sas"
    DITTA_INDIVIDUALE = "ditta_individuale"
    COOPERATIVA = "cooperativa"
    ASSOCIAZIONE = "associazione"
    ALTRO = "altro"


class AtecoVersion(StrEnum):
    ATECO_2007 = "2007"
    ATECO_2025 = "2025"
