"""Countries: ISO codes, display names, regions, and the patterns used to find
them in author affiliations (where the authors work) and in titles, abstracts
and MeSH headings (where the study was done).

Kept in code rather than taxonomy.yml because YAML reads some ISO codes as
booleans (NO, the code for Norway, became `false` there).
"""
from __future__ import annotations

import re

# code: (display name, region slug, name pattern, demonym pattern or None)
# Name patterns match country names as they appear in affiliations and abstracts.
# Demonyms ("Finnish", "Norwegian") count only for the study setting, never for
# authors, and not when they name a language ("Spanish-speaking", "German version").
_C: dict[str, tuple[str, str, str, str | None]] = {
    # North America
    "US": ("United States", "us", r"United States|\bU\.S\.A?\.?(?=[\s,;)])|\bUSA\b", None),
    "CA": ("Canada", "canada", r"\bCanada\b", r"Canadians?"),
    "PR": ("Puerto Rico", "latin-america", r"Puerto Rico", r"Puerto Ricans?"),
    # UK and Ireland
    "GB": ("United Kingdom", "uk-ireland", r"United Kingdom|\bUK\b|Great Britain|\bEngland\b|\bScotland\b|\bWales\b|Northern Ireland", r"British|Scottish|Welsh"),
    "IE": ("Ireland", "uk-ireland", r"(?<!Northern )\bIreland\b", r"Irish"),
    # Australia, New Zealand and Pacific
    "AU": ("Australia", "australia-nz", r"\bAustralia\b", r"Australians?"),
    "NZ": ("New Zealand", "australia-nz", r"New Zealand|Aotearoa", r"New Zealanders?"),
    "FJ": ("Fiji", "australia-nz", r"\bFiji\b", r"Fijians?"),
    "PG": ("Papua New Guinea", "australia-nz", r"Papua New Guinea", None),
    # Europe
    "DE": ("Germany", "europe", r"\bGermany\b|Deutschland", r"German"),
    "FR": ("France", "europe", r"\bFrance\b", r"French"),
    "ES": ("Spain", "europe", r"\bSpain\b|España", None),
    "IT": ("Italy", "europe", r"\bItaly\b|Italia\b", r"Italians?"),
    "NL": ("Netherlands", "europe", r"Netherlands|\bHolland\b", r"Dutch"),
    "BE": ("Belgium", "europe", r"\bBelgium\b", r"Belgians?|Flemish"),
    "LU": ("Luxembourg", "europe", r"\bLuxembourg\b", None),
    "SE": ("Sweden", "europe", r"\bSweden\b", r"Swedish|Swedes"),
    "NO": ("Norway", "europe", r"\bNorway\b", r"Norwegians?"),
    "DK": ("Denmark", "europe", r"\bDenmark\b", r"Danish|Danes"),
    "FI": ("Finland", "europe", r"\bFinland\b|\bSuomi\b", r"Finnish|Finns"),
    "IS": ("Iceland", "europe", r"\bIceland\b", r"Icelandic"),
    "PL": ("Poland", "europe", r"\bPoland\b|\bPolska\b", r"Polish"),
    "CZ": ("Czechia", "europe", r"Czechia|Czech Republic", r"Czech"),
    "SK": ("Slovakia", "europe", r"\bSlovakia\b", r"Slovak"),
    "AT": ("Austria", "europe", r"\bAustria\b|Österreich", r"Austrians?"),
    "CH": ("Switzerland", "europe", r"Switzerland|\bSchweiz\b|\bSuisse\b", r"Swiss"),
    "PT": ("Portugal", "europe", r"\bPortugal\b", None),
    "GR": ("Greece", "europe", r"\bGreece\b", r"Greek"),
    "CY": ("Cyprus", "europe", r"\bCyprus\b", r"Cypriots?"),
    "MT": ("Malta", "europe", r"\bMalta\b", r"Maltese"),
    "HU": ("Hungary", "europe", r"\bHungary\b", r"Hungarians?"),
    "RO": ("Romania", "europe", r"\bRomania\b", r"Romanians?"),
    "BG": ("Bulgaria", "europe", r"\bBulgaria\b", r"Bulgarians?"),
    "HR": ("Croatia", "europe", r"\bCroatia\b", r"Croatians?"),
    "SI": ("Slovenia", "europe", r"\bSlovenia\b", r"Slovenians?|Slovene"),
    "RS": ("Serbia", "europe", r"\bSerbia\b", r"Serbians?"),
    "BA": ("Bosnia and Herzegovina", "europe", r"Bosnia", r"Bosnians?"),
    "ME": ("Montenegro", "europe", r"\bMontenegro\b", None),
    "MK": ("North Macedonia", "europe", r"Macedonia", None),
    "AL": ("Albania", "europe", r"\bAlbania\b", r"Albanians?"),
    "XK": ("Kosovo", "europe", r"\bKosovo\b", None),
    "EE": ("Estonia", "europe", r"\bEstonia\b", r"Estonians?"),
    "LV": ("Latvia", "europe", r"\bLatvia\b", r"Latvians?"),
    "LT": ("Lithuania", "europe", r"\bLithuania\b", r"Lithuanians?"),
    "UA": ("Ukraine", "europe", r"\bUkraine\b", r"Ukrainians?"),
    "MD": ("Moldova", "europe", r"\bMoldova\b", None),
    "BY": ("Belarus", "europe", r"\bBelarus\b", None),
    "RU": ("Russia", "europe", r"\bRussia\b|Russian Federation", None),
    "TR": ("Türkiye", "europe", r"\bTurkey\b|T[üu]rkiye", r"Turkish"),
    "GE": ("Georgia (country)", "europe", r"Tbilisi", None),
    "AM": ("Armenia", "europe", r"\bArmenia\b", r"Armenians?"),
    "AZ": ("Azerbaijan", "europe", r"\bAzerbaijan\b", None),
    "MC": ("Monaco", "europe", r"\bMonaco\b", None),
    "GI": ("Gibraltar", "europe", r"\bGibraltar\b", None),
    "IM": ("Isle of Man", "uk-ireland", r"Isle of Man", None),
    # Middle East and North Africa
    "IL": ("Israel", "middle-east", r"\bIsrael\b", r"Israelis?"),
    "PS": ("Palestine", "middle-east", r"\bPalestin(e|ian territor)", None),
    "IR": ("Iran", "middle-east", r"\bIran\b", r"Iranians?"),
    "IQ": ("Iraq", "middle-east", r"\bIraq\b", r"Iraqis?"),
    "SA": ("Saudi Arabia", "middle-east", r"Saudi Arabia", r"Saudi"),
    "AE": ("United Arab Emirates", "middle-east", r"United Arab Emirates|\bUAE\b", r"Emirati"),
    "QA": ("Qatar", "middle-east", r"\bQatar\b", None),
    "KW": ("Kuwait", "middle-east", r"\bKuwait\b", None),
    "BH": ("Bahrain", "middle-east", r"\bBahrain\b", None),
    "OM": ("Oman", "middle-east", r"\bOman\b", None),
    "JO": ("Jordan", "middle-east", r"\bJordan\b(?! [A-Z][a-z])", r"Jordanians?"),
    "LB": ("Lebanon", "middle-east", r"\bLebanon\b", r"Lebanese"),
    "SY": ("Syria", "middle-east", r"\bSyria\b", r"Syrians?"),
    "EG": ("Egypt", "middle-east", r"\bEgypt\b", r"Egyptians?"),
    "MA": ("Morocco", "middle-east", r"\bMorocco\b", r"Moroccans?"),
    "DZ": ("Algeria", "middle-east", r"\bAlgeria\b", r"Algerians?"),
    "TN": ("Tunisia", "middle-east", r"\bTunisia\b", r"Tunisians?"),
    "LY": ("Libya", "middle-east", r"\bLibya\b", None),
    # Asia
    "CN": ("China", "asia", r"\bChina\b|People's Republic of China|\bPRC\b", r"Chinese"),
    "HK": ("Hong Kong", "asia", r"Hong Kong", None),
    "MO": ("Macao", "asia", r"\bMaca[ou]\b", r"Macanese"),
    "TW": ("Taiwan", "asia", r"\bTaiwan\b", r"Taiwanese"),
    "JP": ("Japan", "asia", r"\bJapan\b", r"Japanese"),
    "KR": ("South Korea", "asia", r"\bKorea\b", r"Korean"),
    "MN": ("Mongolia", "asia", r"\bMongolia\b", None),
    "SG": ("Singapore", "asia", r"\bSingapore\b", r"Singaporeans?"),
    "MY": ("Malaysia", "asia", r"\bMalaysia\b", r"Malaysians?"),
    "TH": ("Thailand", "asia", r"\bThailand\b", r"Thai"),
    "VN": ("Vietnam", "asia", r"Viet ?nam", r"Vietnamese"),
    "KH": ("Cambodia", "asia", r"\bCambodia\b", r"Cambodians?"),
    "LA": ("Laos", "asia", r"\bLaos\b|Lao PDR", None),
    "MM": ("Myanmar", "asia", r"\bMyanmar\b", None),
    "PH": ("Philippines", "asia", r"Philippines", r"Filipinos?|Filipinas?"),
    "ID": ("Indonesia", "asia", r"\bIndonesia\b", r"Indonesians?"),
    "IN": ("India", "asia", r"\bIndia\b", r"Indian(?! (Gaming|gaming|tribe|tribes|reservation|Health|Ocean|Country)| Regulatory)"),
    "PK": ("Pakistan", "asia", r"\bPakistan\b", r"Pakistanis?"),
    "BD": ("Bangladesh", "asia", r"\bBangladesh\b", r"Bangladeshis?"),
    "LK": ("Sri Lanka", "asia", r"Sri Lanka", r"Sri Lankans?"),
    "NP": ("Nepal", "asia", r"\bNepal\b", r"Nepalese|Nepali"),
    "KZ": ("Kazakhstan", "asia", r"Kazakhstan", None),
    "UZ": ("Uzbekistan", "asia", r"Uzbekistan", None),
    "KG": ("Kyrgyzstan", "asia", r"Kyrgyz", None),
    # Latin America and the Caribbean
    "BR": ("Brazil", "latin-america", r"\bBrazil\b|\bBrasil\b", r"Brazilians?"),
    "MX": ("Mexico", "latin-america", r"\bMexico\b|México", r"Mexicans?"),
    "AR": ("Argentina", "latin-america", r"\bArgentina\b", r"Argentin(e|ians?)"),
    "CL": ("Chile", "latin-america", r"\bChile\b", r"Chileans?"),
    "CO": ("Colombia", "latin-america", r"\bColombia\b", r"Colombians?"),
    "PE": ("Peru", "latin-america", r"\bPer[uú]\b", r"Peruvians?"),
    "UY": ("Uruguay", "latin-america", r"\bUruguay\b", None),
    "PY": ("Paraguay", "latin-america", r"\bParaguay\b", None),
    "VE": ("Venezuela", "latin-america", r"\bVenezuela\b", None),
    "EC": ("Ecuador", "latin-america", r"\bEcuador\b", None),
    "BO": ("Bolivia", "latin-america", r"\bBolivia\b", None),
    "CR": ("Costa Rica", "latin-america", r"Costa Rica", None),
    "PA": ("Panama", "latin-america", r"\bPanam[aá]\b", None),
    "GT": ("Guatemala", "latin-america", r"\bGuatemala\b", None),
    "HN": ("Honduras", "latin-america", r"\bHonduras\b", None),
    "SV": ("El Salvador", "latin-america", r"El Salvador", None),
    "NI": ("Nicaragua", "latin-america", r"\bNicaragua\b", None),
    "CU": ("Cuba", "latin-america", r"\bCuba\b", r"Cubans?"),
    "DO": ("Dominican Republic", "latin-america", r"Dominican Republic", None),
    "JM": ("Jamaica", "latin-america", r"\bJamaica\b", r"Jamaicans?"),
    "TT": ("Trinidad and Tobago", "latin-america", r"Trinidad", None),
    # Sub-Saharan Africa
    "ZA": ("South Africa", "africa", r"South Africa", r"South Africans?"),
    "NG": ("Nigeria", "africa", r"\bNigeria\b", r"Nigerians?"),
    "KE": ("Kenya", "africa", r"\bKenya\b", r"Kenyans?"),
    "GH": ("Ghana", "africa", r"\bGhana\b", r"Ghanaians?"),
    "UG": ("Uganda", "africa", r"\bUganda\b", r"Ugandans?"),
    "TZ": ("Tanzania", "africa", r"\bTanzania\b", r"Tanzanians?"),
    "ET": ("Ethiopia", "africa", r"\bEthiopia\b", r"Ethiopians?"),
    "ZW": ("Zimbabwe", "africa", r"\bZimbabwe\b", r"Zimbabweans?"),
    "ZM": ("Zambia", "africa", r"\bZambia\b", r"Zambians?"),
    "MW": ("Malawi", "africa", r"\bMalawi\b", None),
    "MZ": ("Mozambique", "africa", r"\bMozambique\b", None),
    "BW": ("Botswana", "africa", r"\bBotswana\b", None),
    "NA": ("Namibia", "africa", r"\bNamibia\b", None),
    "RW": ("Rwanda", "africa", r"\bRwanda\b", None),
    "CM": ("Cameroon", "africa", r"\bCameroon\b", r"Cameroonians?"),
    "SN": ("Senegal", "africa", r"\bSenegal\b", None),
    "CI": ("Côte d'Ivoire", "africa", r"C[oô]te d.Ivoire|Ivory Coast", None),
    "SL": ("Sierra Leone", "africa", r"Sierra Leone", None),
    "LR": ("Liberia", "africa", r"\bLiberia\b", None),
    "CD": ("DR Congo", "africa", r"Democratic Republic of (the )?Congo", None),
    "SD": ("Sudan", "africa", r"(?<!South )\bSudan\b", None),
    "SO": ("Somalia", "africa", r"\bSomalia\b", None),
    "BF": ("Burkina Faso", "africa", r"Burkina Faso", None),
    "BJ": ("Benin", "africa", r"\bBenin\b", None),
    "TG": ("Togo", "africa", r"\bTogo\b", None),
    "ML": ("Mali", "africa", r"\bMali\b", None),
    "MU": ("Mauritius", "africa", r"\bMauritius\b", None),
}

# Places below country level that name a country unambiguously in an abstract
# or a MeSH heading ("Ontario", "New Jersey", "Victorian gamblers"). Georgia,
# Washington and Victoria are left out: each is too often something else.
_SUBNATIONAL = {
    "US": r"Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|\bMaine\b|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|\bOhio\b|Oklahoma|\bOregon\b|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|\bTexas\b|\bUtah\b|Vermont|Virginia|Wisconsin|Wyoming|Las Vegas|Atlantic City|Chicago",
    "CA": r"Ontario|Quebec|Québec|British Columbia|Alberta|Manitoba|Saskatchewan|Nova Scotia|New Brunswick|Newfoundland",
    "AU": r"New South Wales|Queensland|Tasmania|South Australia|Western Australia|Northern Territory|Australian Capital Territory|Victorian\b|Melbourne|Sydney",
    "GB": r"London\b",
    "ES": r"Catalonia|Andalusia|Madrid\b|Barcelona",
    "CN": r"Guangdong|Shanghai|Beijing",
}

LANGUAGE_FOLLOWERS = r"[\s-]*(speaking|speakers?|language|version|translation|adaptation|translated|-?language|text|lexicon|dictionary)"

COUNTRY_NAMES = {code: v[0] for code, v in _C.items()}
CODE_TO_REGION = {code: v[1] for code, v in _C.items()}

_NAME_RE = {code: re.compile(v[2]) for code, v in _C.items()}
_DEMONYM_RE = {code: re.compile(rf"\b(?:{v[3]})\b(?!{LANGUAGE_FOLLOWERS})") for code, v in _C.items() if v[3]}
_SUB_RE = {code: re.compile(p) for code, p in _SUBNATIONAL.items()}
# "American adults", "American college students": a US setting. A bare "American"
# is too often an organisation ("American Psychiatric Association") or a compound
# ("African American", "Latin American").
_US_DEMONYM = re.compile(r"(?<!African )(?<!Latin )(?<!North )(?<!South )(?<!Native )(?<!Asian )(?<!Central )(?<!Indian )\bAmericans?\b(?= (adults|adolescents|youth|college|university|students|states|sample|population|gamblers|bettors|veterans|men|women|households|consumers|sports|workers|military|service|survey|respondents))|\bU\.S\. (states|adults|adolescents|youth|college|sample|population|gamblers|bettors|veterans|survey)|\bUS (states|adults|adolescents|youth|college|sample|population|gamblers|bettors|veterans|survey)")
# A US postal address in an affiliation string: ", IL 60607".
_US_ADDRESS = re.compile(r", (AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC) \d{5}")


def normalise_code(c) -> str | None:
    """Clean a country code from any source. YAML and some APIs turn "NO" into
    False; OpenAlex sometimes reports lower case."""
    if c is False:
        return "NO"
    if not isinstance(c, str):
        return None
    c = c.strip().upper()
    if c == "UK":
        c = "GB"
    return c if len(c) == 2 and c.isalpha() else None


def from_affiliations(affiliations: list[str]) -> list[str]:
    """Where the authors work: country names (and US postal addresses) in affiliation strings."""
    blob = " ; ".join(a for a in affiliations if a)
    found: list[str] = []
    if not blob:
        return found
    for code, pat in _NAME_RE.items():
        if pat.search(blob) and code not in found:
            found.append(code)
    if "US" not in found and _US_ADDRESS.search(blob):
        found.append("US")
    # "Northern Ireland" is the UK; "New Mexico" is the US; "South Sudan" is not Sudan.
    if "MX" in found and re.search(r"New Mexico", blob) and not re.search(r"(?<!New )\bMexico\b", blob):
        found.remove("MX")
    return found


def mentioned(text: str, demonyms: bool = True) -> list[str]:
    """Countries a title or abstract names, in order of first mention."""
    if not text:
        return []
    hits: list[tuple[int, str]] = []
    for code, pat in _NAME_RE.items():
        m = pat.search(text)
        if m:
            hits.append((m.start(), code))
    if demonyms:
        for code, pat in _DEMONYM_RE.items():
            m = pat.search(text)
            if m:
                hits.append((m.start(), code))
        m = _US_DEMONYM.search(text)
        if m:
            hits.append((m.start(), "US"))
    for code, pat in _SUB_RE.items():
        m = pat.search(text)
        if m:
            hits.append((m.start(), code))
    hits.sort()
    out: list[str] = []
    for _, code in hits:
        if code not in out:
            out.append(code)
    if "MX" in out and re.search(r"New Mexico", text) and not re.search(r"(?<!New )\bMexico\b", text):
        out.remove("MX")
    # "Chinese gamblers in Macao" is Macao, not mainland China.
    if "CN" in out and ({"MO", "HK", "TW"} & set(out)) and not _NAME_RE["CN"].search(text):
        out.remove("CN")
    return out


def from_mesh(headings: list[str]) -> list[str]:
    """MeSH geographic headings ("Finland", "Ontario", "Iran") name where a study was done."""
    out: list[str] = []
    for h in headings or []:
        for code in mentioned(h, demonyms=False):
            if code not in out:
                out.append(code)
    return out
