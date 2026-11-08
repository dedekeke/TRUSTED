"""Value-level patterns, checksums and small dictionaries used by the tier-1 rules.

Everything here is generic domain knowledge (Finnish identifier formats, ISO standards, common names),
not values copied from the labelled catalog.
"""
from __future__ import annotations

import re


_HETU_RX = re.compile(r"^(\d{2})(\d{2})(\d{2})([-+A-FU-Y]?)(\d{3})([0-9A-Y])$")
_HETU_CHECK = "0123456789ABCDEFHJKLMNPRSTUVWXY"


def hetu_valid(v: str) -> bool:
    """Finnish personal identity code (DDMMYYCZZZQ) with its mod-31 check character."""
    m = _HETU_RX.match(v.strip().upper())
    if not m:
        return False
    dd, mm, yy, _, zzz, q = m.groups()
    if not (1 <= int(dd) <= 31 and 1 <= int(mm) <= 12):
        return False
    return _HETU_CHECK[int(dd + mm + yy + zzz) % 31] == q


def hetu_shape(v: str) -> bool:
    return bool(_HETU_RX.match(v.strip().upper()))


def luhn_valid(v: str) -> bool:
    d = re.sub(r"[\s-]", "", v)
    if not d.isdigit() or not 12 <= len(d) <= 19:
        return False
    s, alt = 0, False
    for ch in reversed(d):
        n = int(ch)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        s += n
        alt = not alt
    return s % 10 == 0


def iban_valid(v: str) -> bool:
    s = re.sub(r"\s", "", v).upper()
    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", s):
        return False
    r = s[4:] + s[:4]
    num = "".join(str(int(ch, 36)) for ch in r)
    return int(num) % 97 == 1


RX = {
    "EMAIL": re.compile(r"^[\w.+'-]+@[\w-]+(\.[\w-]+)+$"),
    "EMAIL_LIST": re.compile(r"^[\w.+'-]+@[\w-]+(\.[\w-]+)+([;,|]\s*[\w.+'-]+@[\w-]+(\.[\w-]+)+)+$"),
    "IBAN": re.compile(r"^[A-Z]{2}\d{2}(\s?[A-Z0-9]{4}){2,7}(\s?[A-Z0-9]{1,4})?$"),
    "PAN": re.compile(r"^(\d[ -]?){12,18}\d$"),
    "PAN_MASKED": re.compile(r"^(\d{4,6}|\*{4})[ -]?[\*xX#]{2,}[ \*xX#-]*\d{4}$"),
    "PHONE": re.compile(r"^(\+|00)?358[\s-]?\(?0?\)?\d{1,3}([\s-]?\d{2,4}){1,4}$|^0\d{1,3}([\s-]?\d{2,4}){2,4}$"),
    "IPV4": re.compile(r"^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$"),
    "IPV6": re.compile(r"^[0-9a-fA-F]{1,4}(:[0-9a-fA-F]{0,4}){2,7}$"),
    "CIDR": re.compile(r"^\d{1,3}(\.\d{1,3}){3}/\d{1,2}$"),
    "MAC": re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$"),
    "PLATE": re.compile(r"^[A-ZÅÄÖ]{2,3}-\d{1,3}$"),
    "URL": re.compile(r"^(https?|ftp)://\S+$", re.I),
    "DOMAIN": re.compile(r"^(?=.{4,253}$)([a-z0-9-]{1,63}\.)+[a-z]{2,24}\.?$", re.I),
    "USER_AGENT": re.compile(r"^(Mozilla|Opera|curl|python-requests|Microsoft|Outlook|okhttp|Dalvik)/", re.I),
    "HEX_HASH": re.compile(r"^[0-9a-fA-F]{32}$|^[0-9a-fA-F]{40}$|^[0-9a-fA-F]{64}$"),
    "UUID": re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"),
    "ICD10": re.compile(r"^[A-TV-Z]\d{2}(\.\d{1,2})?[A-Z]?$"),
    "POSTCODE_FI": re.compile(r"^\d{5}$"),
    "STREET_ADDRESS": re.compile(
        r"^[A-ZÅÄÖ][\wåäöÅÄÖé'.-]+(\s[A-ZÅÄÖa-zåäö][\wåäöÅÄÖ'.-]+){0,2}\s\d{1,4}[a-z]?(\s?[A-Z](\s?\d{1,3})?)?"
        r"(\s?(as\.?|bst\.?)\s?\d+)?(,\s*\d{5}(\s+[A-ZÅÄÖ][\wåäöÅÄÖ-]+)?)?$"),
    "BOOL": re.compile(r"^(true|false|yes|no|y|n|0|1|t|f|kyllä|ei|ja|nej)$", re.I),
    "INT": re.compile(r"^-?\d+$"),
    "NUMBER": re.compile(r"^-?(\d{1,3}([  ]\d{3})+|\d+)([.,]\d+)?$"),
    "COORD": re.compile(r"^-?\d{1,3}\.\d{4,}$"),
    "PERSON_NAME_SHAPE": re.compile(r"^[A-ZÅÄÖÉ][a-zåäöéüA-ZÅÄÖ'-]*[a-zåäöéü]([\s,]+[A-ZÅÄÖÉ][a-zåäöéüA-ZÅÄÖ'-]*[a-zåäöéü]){1,3}$"),
    "SINGLE_CAP_WORD": re.compile(r"^[A-ZÅÄÖÉ][a-zåäöéü'-]+(-[A-ZÅÄÖ][a-zåäöéü]+)?$"),
    "HOSTNAME": re.compile(r"^[A-Z]{2,4}-[A-Z]{3,}(-\d{1,6})?$|^[A-Z]{3,10}\d{2,3}$|"
                           r"^[a-z0-9-]+\.(corp|local|lan|internal|ad)(\.[a-z]+)*$", re.I),
    "PREFIXED_ID": re.compile(r"^[A-Za-z]{1,6}[-_]?\d{3,}([-_]\d+)?$"),
    "LANG_CODE": re.compile(r"^(fi|sv|en|ru|et|ar|so|de|fr|es|fa|ku|uk|vi|zh|th|tr|sq|pl|other)$", re.I),
}

DATE_RXS = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{1,2}\.\d{1,2}\.(\d{2}|\d{4})$"),
    re.compile(r"^\d{1,2}/\d{1,2}/(\d{2}|\d{4})$"),
    re.compile(r"^\d{4}/\d{2}/\d{2}$"),
    re.compile(r"^\d{8}$"),
]
MONTH_RXS = [re.compile(r"^\d{4}-\d{2}$"), re.compile(r"^\d{4}-W\d{2}$"), re.compile(r"^\d{4}-\d{2}/\d$"),
             re.compile(r"^\d{4}[-/]\d{4}$"), re.compile(r"^\d{4}[KS]$"), re.compile(r"^(19|20)\d{2}$")]
TS_RXS = [
    re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$"),
    re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}[:.]\d{2}([:.]\d{2})?$"),
    re.compile(r"^\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}(:\d{2})?$"),
]

SEX_VALUES = {"m", "f", "n", "x", "male", "female", "other", "mies", "nainen", "man", "kvinna", "u", "unknown",
              "1", "2"}

MUNICIPALITIES = {
    "turku", "åbo", "kaarina", "s:t karins", "naantali", "nådendal", "raisio", "reso", "lieto", "lundo", "salo",
    "uusikaupunki", "nystad", "parainen", "pargas", "masku", "nousiainen", "nousis", "mynämäki", "virmo", "rusko",
    "paimio", "pemar", "sauvo", "sagu", "loimaa", "aura", "pöytyä", "marttila", "koski tl", "somero", "laitila",
    "pyhäranta", "taivassalo", "tövsala", "kustavi", "gustavs", "vehmaa", "kemiönsaari", "kimitoön", "oripää",
    "tarvasjoki", "mietoinen", "askainen", "merimasku", "rymättylä", "velkua", "nauvo", "korppoo", "houtskari",
    "iniö", "halikko", "perniö", "kisko", "suomusjärvi", "särkisalo", "kiikala", "kuusjoki", "muurla", "pertteli",
    "helsinki", "helsingfors", "espoo", "vantaa", "tampere", "pori", "rauma", "eura", "eurajoki", "säkylä",
    "huittinen", "forssa", "hanko", "raasepori", "lohja", "mariehamn", "maarianhamina", "kotka", "lahti", "oulu",
    "jyväskylä", "kuopio", "vaasa", "joensuu", "seinäjoki", "hämeenlinna", "porvoo",
}

COUNTRIES = {"finland", "suomi", "sweden", "ruotsi", "estonia", "germany", "russia", "united states", "netherlands",
             "united kingdom", "france", "spain", "norway", "denmark", "poland", "china", "india", "nigeria",
             "brazil", "ukraine", "romania", "vietnam", "fi", "se", "ee", "de", "ru", "us", "nl", "gb", "fr", "es",
             "no", "dk", "pl", "cn", "in", "ng", "br", "ua", "ro", "vn", "it", "ch", "ie", "be", "at"}

ORG_SUFFIX = re.compile(r"\b(oy|oyj|ab|ky|tmi|ry|ltd|inc|gmbh|llc|plc|ay|osk|sr|kunta|kaupunki|stad|bank|pankki)\b\.?$",
                        re.I)

FIRST_NAMES = set("""
aada aino aleksi anna anne annika antti anu ari arja arto eero eetu eino elias elina ella ellen emilia emma
erkki esa essi eveliina hanna hannu harri heikki heli helmi henna henrik hilja iida ilkka ilmari inkeri irma
jaana jani janne jari jarmo jenni jesse joel johanna johannes jonna joona joonas jouni juha juho jukka julia
juuso jyrki kaarina kaisa kalle kari katja kerttu kimmo kirsi kristiina kristian kristina kustaa laura lauri
leena leo liisa linnea lotta lumi maija marja marjatta markku marko markus martti matias matti mika mikael
mikko minna mirja niklas niko noora olli oliver onni oona oskari otto paavo pasi pekka pentti petri petra
pia pirjo raimo riikka riitta rasmus sami sanna santeri sara satu seppo siiri sofia susanna taneli tapani
tapio teemu terhi timo tomi topias tuomas tuula tuuli ulla valtteri veera veikko venla ville väinö
aleksanteri josefiina matias mika britt alma oscar stefan narin ananya hugo axel elsa saga wilma alva ebba
erik lars nils karl johan anders per maria margareta kerstin birgitta ingrid astrid gustav fredrik viktor
""".split())

SURNAME_SUFFIX = re.compile(
    r"(nen|la|lä|mäki|maki|koski|niemi|salo|lahti|vaara|kallio|korpi|aho|oja|järvi|jarvi|joki|harju|"
    r"berg|ström|strom|lund|qvist|kvist|gren|holm|sson|man|ius|ranta|virta|lehto|nurmi|saari|mies)$", re.I)


NAME_HINTS = [
    (r"hetu|ssn|national_?id|personal_?id|henkilotunnus|personbeteckning", "direct_identifier", "NATIONAL_ID", .9),
    (r"(^|_)(full_?)?name$|first_?names?|last_?name|surname|given_?name|display_?name|holder_?name|_name$",
     "direct_identifier", "PERSON_NAME", .6),
    (r"e_?mail|(^|_)upn$|_upn$|sender$|recipients?$", "direct_identifier", "EMAIL", .75),
    (r"phone|mobile|gsm|puhelin", "direct_identifier", "PHONE", .8),
    (r"(street|home)_?address|(^|_)address$|osoite", "direct_identifier", "STREET_ADDRESS", .75),
    (r"iban|bank_?account|account_?no", "direct_identifier", "IBAN", .85),
    (r"(^|_)pan$|card_?(number|pan)", "direct_identifier", "PAYMENT_CARD", .85),
    (r"plate|rekisteri", "direct_identifier", "LICENSE_PLATE", .85),
    (r"(^|_)ip($|_)|_ip$|ip_?address", "technical_identifier", "IP_ADDRESS", .8),
    (r"(^|_)mac($|_)", "technical_identifier", "MAC_ADDRESS", .85),
    (r"host_?name|device_?name|(^|_)host$", "technical_identifier", "HOSTNAME", .75),
    (r"user_?agent", "technical_identifier", "USER_AGENT", .85),
    (r"imei", "technical_identifier", "IMEI", .9),
    (r"metering_?point|gsrn|meter_?id", "technical_identifier", "METER_ID", .85),
    (r"session_?id|correlation_?id|smtp_?message_?id", "technical_identifier", "RECORD_ID", .6),
    (r"birth|(^|_)dob$|syntym", "quasi_identifier", "BIRTH_DATE", .85),
    (r"(^|_)age($|_)|age_?band", "quasi_identifier", "AGE", .75),
    (r"(^|_)sex$|gender|sukupuoli", "quasi_identifier", "SEX", .85),
    (r"postcode|zip|postal|postinumero", "quasi_identifier", "POSTCODE", .8),
    (r"municipality|(^|_)city$|kunta", "quasi_identifier", "MUNICIPALITY", .7),
    (r"(^|_)(lat|lon|lng|latitude|longitude)$", "quasi_identifier", "GPS_COORDINATE", .75),
    (r"language|kieli", "quasi_identifier", "LANGUAGE", .7),
    (r"occupation|job_?title|profession|ammatti", "quasi_identifier", "OCCUPATION", .7),
    (r"employer|department|school_?(name|code)|organi[sz]ation", "quasi_identifier", "ORG_NAME", .6),
    (r"(_ts|_utc|timestamp|_time|_at)$|^ts$", "quasi_identifier", "TIMESTAMP", .6),
    (r"date$|_date|(^|_)since$|_start$|_end$", "quasi_identifier", "DATE", .55),
    (r"icd|diagnos", "sensitive_attribute", "DIAGNOSIS_CODE", .85),
    (r"triage|disposition|readmit|(^|_)los_|medical|health|special_?support|disabilit|accessibility|sick|"
     r"sairaus|abnormal|excused", "sensitive_attribute", "HEALTH_DATA", .75),
    (r"systolic|diastolic|heart_?rate|resp_?rate|temp_c|spo2|pain|glucose|bmi|blood", "sensitive_attribute",
     "MEASUREMENT", .75),
    (r"income|salary|wage|palkka|default|debt|late_?payment|payment_?plan|kyc|pep_?flag|credit|union_?fee|"
     r"cost_?estimate|tax", "sensitive_attribute", "FINANCIAL_DATA", .75),
    (r"religion|ethnic|second_?language|migrant|nationality", "sensitive_attribute", "SOCIAL_DATA", .75),
    (r"(^|_)grade|points|unexcused|late_?arrivals|(^|_)status$", "sensitive_attribute", "EDUCATION_DATA", .5),
    (r"note|text|description|message|comment|subject|complaint|body|resolution|command_?line|file_?path",
     "free_text", "FREE_TEXT", .65),
    (r"(^|_)url$|uri$", "free_text", "URL", .7),
    (r"domain|(^|_)query$|fqdn", "quasi_identifier", "URL", .6),
]

ID_SUBTYPE_HINTS = [
    (r"customer|client|asiakas", "CUSTOMER_ID"),
    (r"student|learner|pupil", "STUDENT_ID"),
    (r"staff|employee|agent|physician|author|handler|officer|emp", "EMPLOYEE_ID"),
    (r"patient", "PATIENT_ID"),
    (r"card", "CARD_ID"),
    (r"device|bike|vehicle|unit", "DEVICE_ID"),
    (r"account|contract|reference", "ACCOUNT_ID"),
    (r"meter", "METER_ID"),
    (r"property|kiinteist", "PROPERTY_ID"),
]

ROLES = ["direct_identifier", "quasi_identifier", "sensitive_attribute", "technical_identifier", "free_text",
         "record_key", "non_sensitive"]

SUBTYPES = """PERSON_NAME NATIONAL_ID EMAIL PHONE STREET_ADDRESS POSTCODE MUNICIPALITY GPS_COORDINATE
LOCATION_NAME BIRTH_DATE AGE SEX LANGUAGE NATIONALITY IBAN PAYMENT_CARD CUSTOMER_ID ACCOUNT_ID EMPLOYEE_ID
STUDENT_ID PATIENT_ID CARD_ID DEVICE_ID IP_ADDRESS MAC_ADDRESS IMEI HOSTNAME USERNAME URL USER_AGENT
LICENSE_PLATE PROPERTY_ID METER_ID TIMESTAMP DATE DURATION HEALTH_DATA DIAGNOSIS_CODE FINANCIAL_DATA
EDUCATION_DATA SOCIAL_DATA OCCUPATION ORG_NAME MEASUREMENT CATEGORY AGGREGATE SECRET FREE_TEXT RECORD_ID
OTHER""".split()
