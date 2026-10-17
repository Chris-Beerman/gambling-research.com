"""Trial registries and preregistrations: ClinicalTrials.gov (API v2), ISRCTN
(XML query API) and OSF Registries (API v2). Each fetcher returns a list of
raw dicts in one common shape; pipeline/trackers.py merges them into
data/trials.json.

Common raw shape:
    registry, id, title, status (normalised, see STATUSES), kind
    ('trial' | 'registration'), study_type, phases, enrollment, conditions,
    interventions, sponsor, sponsor_class, collaborators, countries (names),
    start_date, completion_date, first_posted, last_updated, results_posted,
    results_date, summary (raw text), url, registration_type, authors,
    other_ids (e.g. an NCT number quoted by ISRCTN, used to dedupe).
"""
from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET

from ..common import clean_text, get, iso, parse_date

CT_API = "https://clinicaltrials.gov/api/v2/studies"
ISRCTN_API = "https://www.isrctn.com/api/query/format/default"
OSF_API = "https://api.osf.io/v2/registrations/"

# Normalised statuses, in the order the trials page shows them.
STATUSES = {
    "recruiting": "recruiting",
    "not-yet-recruiting": "not yet recruiting",
    "enrolling-by-invitation": "enrolling by invitation",
    "active": "active, not recruiting",
    "completed": "completed",
    "terminated": "terminated",
    "suspended": "suspended",
    "withdrawn": "withdrawn",
    "unknown": "status unknown",
    "registered": "registered",
}

_CT_STATUS = {
    "RECRUITING": "recruiting",
    "NOT_YET_RECRUITING": "not-yet-recruiting",
    "ENROLLING_BY_INVITATION": "enrolling-by-invitation",
    "ACTIVE_NOT_RECRUITING": "active",
    "COMPLETED": "completed",
    "TERMINATED": "terminated",
    "SUSPENDED": "suspended",
    "WITHDRAWN": "withdrawn",
    "UNKNOWN": "unknown",
}

_CT_SPONSOR_CLASS = {
    "NIH": "nih",
    "FED": "us-federal",
    "OTHER_GOV": "government",
    "INDUSTRY": "industry",
    "NETWORK": "network",
    "INDIV": "individual",
    "OTHER": "other",
    "UNKNOWN": "",
}


# ---------------------------------------------------------------- ClinicalTrials.gov
def fetch_clinicaltrials(s, cfg: dict, warnings: list[str] | None = None) -> list[dict]:
    """Every study whose conditions mention gambling, plus studies whose other
    fields mention the configured terms. Relevance is decided later."""
    out: dict[str, dict] = {}
    queries = []
    if cfg.get("cond"):
        queries.append({"query.cond": cfg["cond"]})
    if cfg.get("term"):
        queries.append({"query.term": cfg["term"]})
    for q in queries:
        token = None
        pages = 0
        while True:
            params = dict(q, pageSize=str(cfg.get("page_size", 200)), countTotal="true", format="json")
            if token:
                params["pageToken"] = token
            try:
                r = get(s, CT_API, params=params)
            except RuntimeError as e:
                if not out:
                    raise
                if warnings is not None:
                    warnings.append(f"stopped after {len(out)} studies: {str(e)[:120]}")
                break
            js = r.json()
            for study in js.get("studies", []):
                rec = convert_clinicaltrials(study)
                if rec and rec["id"] not in out:
                    out[rec["id"]] = rec
            token = js.get("nextPageToken")
            pages += 1
            if not token or pages >= int(cfg.get("max_pages", 20)):
                break
            time.sleep(0.3)
    return list(out.values())


def _ds(struct) -> str | None:
    """CT.gov date structs: {"date": "2026-03", "type": "ESTIMATED"}."""
    if isinstance(struct, dict):
        return iso(parse_date(struct.get("date")))
    return iso(parse_date(struct))


def convert_clinicaltrials(study: dict) -> dict | None:
    ps = study.get("protocolSection") or {}
    ident = ps.get("identificationModule") or {}
    nct = ident.get("nctId")
    if not nct:
        return None
    status = ps.get("statusModule") or {}
    spons = ps.get("sponsorCollaboratorsModule") or {}
    lead = spons.get("leadSponsor") or {}
    design = ps.get("designModule") or {}
    cond = ps.get("conditionsModule") or {}
    arms = ps.get("armsInterventionsModule") or {}
    locs = (ps.get("contactsLocationsModule") or {}).get("locations") or []
    desc = ps.get("descriptionModule") or {}
    countries: list[str] = []
    for loc in locs:
        c = (loc or {}).get("country")
        if c and c not in countries:
            countries.append(c)
    interventions = []
    for iv in arms.get("interventions") or []:
        name = clean_text(iv.get("name") or "")
        if name:
            t = (iv.get("type") or "").replace("_", " ").lower()
            interventions.append(f"{t}: {name}" if t else name)
    phases = [p for p in (design.get("phases") or []) if p and p != "NA"]
    enrollment = (design.get("enrollmentInfo") or {}).get("count")
    results_date = _ds(status.get("resultsFirstPostDateStruct"))
    return {
        "registry": "clinicaltrials",
        "id": nct,
        "kind": "trial",
        "title": clean_text(ident.get("briefTitle") or ident.get("officialTitle") or ""),
        "official_title": clean_text(ident.get("officialTitle") or ""),
        "status": _CT_STATUS.get(status.get("overallStatus") or "", "unknown"),
        "study_type": (design.get("studyType") or "").lower(),
        "phases": [p.replace("PHASE", "phase ").replace("EARLY_", "early ").lower() for p in phases],
        "enrollment": int(enrollment) if isinstance(enrollment, (int, float)) else None,
        "conditions": [clean_text(c) for c in (cond.get("conditions") or []) if c],
        "keywords": [clean_text(k) for k in (cond.get("keywords") or []) if k],
        "interventions": interventions[:6],
        "sponsor": clean_text(lead.get("name") or ""),
        "sponsor_class": _CT_SPONSOR_CLASS.get(lead.get("class") or "", ""),
        "collaborators": [clean_text(c.get("name") or "") for c in (spons.get("collaborators") or []) if c.get("name")][:6],
        "countries": countries,
        "start_date": _ds(status.get("startDateStruct")),
        "completion_date": _ds(status.get("primaryCompletionDateStruct")) or _ds(status.get("completionDateStruct")),
        "first_posted": _ds(status.get("studyFirstPostDateStruct")),
        "last_updated": _ds(status.get("lastUpdatePostDateStruct")),
        "results_posted": bool(study.get("hasResults")) or bool(results_date),
        "results_date": results_date,
        "summary": clean_text(desc.get("briefSummary") or ""),
        "url": f"https://clinicaltrials.gov/study/{nct}",
        "registration_type": "",
        "authors": [],
        "other_ids": [],
    }


# ---------------------------------------------------------------- ISRCTN
_NS = {"i": "http://www.67bricks.com/isrctn"}


def fetch_isrctn(s, cfg: dict) -> list[dict]:
    out: dict[str, dict] = {}
    offset = 0
    limit = int(cfg.get("limit", 100))
    while True:
        r = get(s, ISRCTN_API, params={"q": cfg.get("query", "gambling"), "limit": str(limit), "offset": str(offset)}, timeout=90)
        recs, total = parse_isrctn(r.content)
        new = 0
        for rec in recs:
            if rec["id"] not in out:
                out[rec["id"]] = rec
                new += 1
        offset += limit
        if new == 0 or offset >= total or offset > 2000:
            break
        time.sleep(0.5)
    return list(out.values())


def _t(el, path: str) -> str:
    if el is None:
        return ""
    node = el.find(path, _NS)
    return clean_text(node.text if node is not None and node.text else "")


def parse_isrctn(content: bytes, today=None) -> tuple[list[dict], int]:
    import datetime as dt

    today = today or dt.datetime.now(dt.timezone.utc).date()
    root = ET.fromstring(content)
    total = int(root.get("totalCount") or 0)
    out = []
    for full in root.findall("i:fullTrial", _NS):
        trial = full.find("i:trial", _NS)
        if trial is None:
            continue
        num = _t(trial, "i:isrctn")
        if not num:
            continue
        isrctn = f"ISRCTN{num}"
        desc = trial.find("i:trialDescription", _NS)
        design = trial.find("i:trialDesign", _NS)
        parts = trial.find("i:participants", _NS)
        start = parse_date(_t(parts, "i:recruitmentStart"))
        rec_end = parse_date(_t(parts, "i:recruitmentEnd"))
        end = parse_date(_t(design, "i:overallEndDate"))
        override = (_t(parts, "i:recruitmentStatusOverride") or _t(parts, "i:recruitmentStartStatusOverride")).lower()
        if "stopped" in override or "terminated" in override:
            status = "terminated"
        elif "suspended" in override:
            status = "suspended"
        elif end and end < today:
            status = "completed"
        elif start and start > today:
            status = "not-yet-recruiting"
        elif start and (not rec_end or rec_end >= today):
            status = "recruiting"
        elif rec_end and rec_end < today:
            status = "active"
        else:
            status = "unknown"
        countries = [clean_text(c.text or "") for c in parts.findall("i:recruitmentCountries/i:country", _NS)] if parts is not None else []
        conditions = [clean_text(c.text or "") for c in trial.findall("i:conditions/i:condition/i:description", _NS)]
        interventions = []
        for iv in trial.findall("i:interventions/i:intervention", _NS):
            t = _t(iv, "i:interventionType")
            d = _t(iv, "i:description")
            if t or d:
                interventions.append(f"{t.lower()}: {d[:80]}".strip(": ") if d else t.lower())
        sponsor = _t(full, "i:sponsor/i:organisation")
        funders = [clean_text(f.text or "") for f in full.findall("i:funder/i:name", _NS)]
        pi = ""
        for c in full.findall("i:contact", _NS):
            types = [clean_text(t.text or "") for t in c.findall("i:contactTypes/i:contactType", _NS)]
            if any("Principal" in t for t in types):
                pi = f"{_t(c, 'i:forename')} {_t(c, 'i:surname')}".strip()
                break
        enrol = _t(parts, "i:totalFinalEnrolment") or _t(parts, "i:targetEnrolment")
        try:
            enrollment = int(float(enrol)) if enrol else None
        except ValueError:
            enrollment = None
        results = trial.find("i:results", _NS)
        results_posted = bool(_t(results, "i:basicReport") or _t(results, "i:plainEnglishReport") or (_t(results, "i:publicationStage").lower() == "results"))
        nct = _t(trial, "i:externalRefs/i:clinicalTrialsGovNumber")
        other = [nct] if nct.upper().startswith("NCT") else []
        commercial = _t(full, "i:sponsor/i:commercialStatus").lower()
        isrctn_el = trial.find("i:isrctn", _NS)
        assigned = trial.get("publicIdentifierDateAssigned") or (isrctn_el.get("dateAssigned") if isrctn_el is not None else None)
        out.append(
            {
                "registry": "isrctn",
                "id": isrctn,
                "kind": "trial",
                "title": _t(desc, "i:title") or _t(desc, "i:scientificTitle"),
                "official_title": _t(desc, "i:scientificTitle"),
                "status": status,
                "study_type": _t(design, "i:primaryStudyDesign").lower(),
                "phases": [],
                "enrollment": enrollment,
                "conditions": conditions,
                "keywords": [],
                "interventions": interventions[:6],
                "sponsor": sponsor,
                "sponsor_class": "industry" if "commercial" == commercial else ("other" if sponsor else ""),
                "collaborators": funders[:6],
                "countries": countries,
                "start_date": iso(start),
                "completion_date": iso(end),
                "first_posted": iso(parse_date(assigned)),
                "last_updated": iso(parse_date(trial.get("lastUpdated"))),
                "results_posted": results_posted,
                "results_date": None,
                "summary": _t(desc, "i:plainEnglishSummary"),
                "url": f"https://www.isrctn.com/{isrctn}",
                "registration_type": "",
                "authors": [pi] if pi else [],
                "other_ids": other,
            }
        )
    return out, total


# ---------------------------------------------------------------- OSF Registries
def fetch_osf(s, cfg: dict, warnings: list[str] | None = None) -> list[dict]:
    """Public registrations whose title or description contains a term.
    OSF's API filters strings case-insensitively by substring; a comma-separated
    field list ORs the fields."""
    headers = {}
    token = os.environ.get("OSF_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    out: dict[str, dict] = {}
    for term in cfg.get("terms", ["gambling"]):
        for fields in ("title,description", "title"):
            url = OSF_API
            params = {f"filter[{fields}]": term, "page[size]": "100", "sort": "-date_registered", "embed": "contributors"}
            pages = 0
            ok = True
            while url:
                try:
                    r = get(s, url, params=params, headers=headers, timeout=90)
                except RuntimeError as e:
                    if fields == "title,description" and "400" in str(e):
                        ok = False  # fall back to the title-only filter
                        break
                    if not out:
                        raise
                    if warnings is not None:
                        warnings.append(f"stopped at '{term}' with {len(out)} registrations: {str(e)[:120]}")
                    return list(out.values())
                js = r.json()
                for item in js.get("data", []):
                    rec = convert_osf(item)
                    if rec and rec["id"] not in out:
                        out[rec["id"]] = rec
                url = (js.get("links") or {}).get("next")
                params = None  # the next link carries its own query string
                pages += 1
                if pages >= int(cfg.get("max_pages", 5)):
                    break
                time.sleep(0.5)
            if ok:
                break
        time.sleep(0.5)
    return list(out.values())


def convert_osf(item: dict) -> dict | None:
    a = item.get("attributes") or {}
    rid = item.get("id")
    if not rid or a.get("withdrawn") or a.get("public") is False:
        return None
    authors = []
    for c in (((item.get("embeds") or {}).get("contributors") or {}).get("data") or []):
        user = (((c.get("embeds") or {}).get("users") or {}).get("data") or {})
        name = ((user.get("attributes") or {}).get("full_name") or "").strip()
        if name:
            authors.append(name)
    date_reg = iso(parse_date(a.get("date_registered")))
    return {
        "registry": "osf",
        "id": f"osf:{rid}",
        "kind": "registration",
        "title": clean_text(a.get("title") or ""),
        "official_title": "",
        "status": "registered",
        "study_type": "",
        "phases": [],
        "enrollment": None,
        "conditions": [],
        "keywords": [clean_text(t) for t in (a.get("tags") or []) if t][:10],
        "interventions": [],
        "sponsor": "",
        "sponsor_class": "",
        "collaborators": [],
        "countries": [],
        "start_date": None,
        "completion_date": None,
        "first_posted": date_reg,
        "last_updated": iso(parse_date(a.get("date_modified"))) or date_reg,
        "results_posted": False,
        "results_date": None,
        "summary": clean_text(a.get("description") or ""),
        "url": ((item.get("links") or {}).get("html")) or f"https://osf.io/{rid}/",
        "registration_type": clean_text(a.get("registration_supplement") or ""),
        "authors": authors[:8],
        "other_ids": [],
        "embargoed": bool(a.get("embargoed")),
    }
