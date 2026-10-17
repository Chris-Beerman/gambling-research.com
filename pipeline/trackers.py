"""Merge raw trial, bill and court records into data/trials.json,
data/bills.json and data/cases.json: relevance, tagging, derived fields
(bill stage, court level), first_seen, and retention."""
from __future__ import annotations

import datetime as dt
import re

from .common import summarize
from .normalize import Taxonomy
from .sources.trials import STATUSES

# ---------------------------------------------------------------- countries
COUNTRY_CODES = {
    "united states": "US", "usa": "US", "canada": "CA", "united kingdom": "GB", "england": "GB", "scotland": "GB", "wales": "GB",
    "northern ireland": "GB", "ireland": "IE", "australia": "AU", "new zealand": "NZ", "germany": "DE", "france": "FR", "spain": "ES",
    "italy": "IT", "netherlands": "NL", "belgium": "BE", "sweden": "SE", "norway": "NO", "denmark": "DK", "finland": "FI", "iceland": "IS",
    "poland": "PL", "czechia": "CZ", "czech republic": "CZ", "austria": "AT", "switzerland": "CH", "portugal": "PT", "greece": "GR",
    "hungary": "HU", "romania": "RO", "croatia": "HR", "slovenia": "SI", "slovakia": "SK", "estonia": "EE", "latvia": "LV", "lithuania": "LT",
    "luxembourg": "LU", "malta": "MT", "cyprus": "CY", "ukraine": "UA", "serbia": "RS", "russia": "RU", "russian federation": "RU",
    "china": "CN", "japan": "JP", "korea, republic of": "KR", "south korea": "KR", "korea": "KR", "taiwan": "TW", "hong kong": "HK", "macao": "MO",
    "macau": "MO", "singapore": "SG", "malaysia": "MY", "thailand": "TH", "vietnam": "VN", "viet nam": "VN", "philippines": "PH", "indonesia": "ID",
    "india": "IN", "pakistan": "PK", "bangladesh": "BD", "sri lanka": "LK", "nepal": "NP", "israel": "IL", "turkey": "TR", "türkiye": "TR",
    "iran": "IR", "iran, islamic republic of": "IR", "saudi arabia": "SA", "united arab emirates": "AE", "qatar": "QA", "lebanon": "LB",
    "brazil": "BR", "mexico": "MX", "argentina": "AR", "chile": "CL", "colombia": "CO", "peru": "PE", "uruguay": "UY", "puerto rico": "PR",
    "south africa": "ZA", "nigeria": "NG", "kenya": "KE", "ghana": "GH", "uganda": "UG", "tanzania": "TZ", "ethiopia": "ET", "egypt": "EG",
}


def country_codes(names: list[str]) -> list[str]:
    out: list[str] = []
    for n in names:
        code = COUNTRY_CODES.get((n or "").strip().lower())
        if code and code not in out:
            out.append(code)
    return out


# ---------------------------------------------------------------- trials
def update_trials(existing: list[dict], raw: list[dict], tax: Taxonomy, today: dt.date, backfill: bool, refreshed: set[str] | None = None) -> tuple[list[dict], dict]:
    """`refreshed` names the registries whose fetch succeeded in full: records
    of those registries that the fetch no longer returns (deleted, or no longer
    matching after a rule change) are removed. Registries that failed keep
    their old records."""
    by_id = {t["id"]: t for t in existing}
    if refreshed:
        returned = {r["id"] for r in raw}
        removed = [k for k, t in by_id.items() if t.get("registry") in refreshed and k not in returned]
        for k in removed:
            del by_id[k]
    else:
        removed = []
    # ISRCTN records that quote an NCT number are the same trial; keep the CT.gov copy.
    ct_ids = {r["id"].upper() for r in raw if r.get("registry") == "clinicaltrials"} | {k.upper() for k in by_id if k.upper().startswith("NCT")}
    added = updated = dropped = 0
    for r in raw:
        if r["registry"] == "isrctn" and any(o.upper() in ct_ids for o in r.get("other_ids") or []):
            continue
        text = " ".join([r.get("title") or "", r.get("official_title") or "", " ".join(r.get("conditions") or []), " ".join(r.get("keywords") or []), r.get("summary") or ""])
        # Keep a record when its title or conditions name the subject, or the rest of
        # the record mentions it at least twice (one mention is usually a gambling task
        # used as a measure, or gambling listed among many outcomes).
        rel, title_hit, hits = tax.assess(f"{r.get('title') or ''} {' '.join(r.get('conditions') or [])}", f"{r.get('official_title') or ''} {' '.join(r.get('keywords') or [])} {r.get('summary') or ''}")
        if rel != "high" or not (title_hit or hits >= 2):
            dropped += 1
            continue
        topics, designs = tax.tag(text)
        codes = country_codes(r.get("countries") or [])
        prev = by_id.get(r["id"])
        rec = {
            "id": r["id"],
            "registry": r["registry"],
            "registry_label": {"clinicaltrials": "ClinicalTrials.gov", "isrctn": "ISRCTN", "osf": "OSF Registries"}.get(r["registry"], r["registry"]),
            "kind": r.get("kind") or "trial",
            "title": r.get("title") or "",
            "status": r.get("status") if r.get("status") in STATUSES else "unknown",
            "study_type": r.get("study_type") or "",
            "phases": r.get("phases") or [],
            "enrollment": r.get("enrollment"),
            "conditions": (r.get("conditions") or [])[:6],
            "interventions": (r.get("interventions") or [])[:6],
            "sponsor": r.get("sponsor") or "",
            "sponsor_class": r.get("sponsor_class") or "",
            "collaborators": (r.get("collaborators") or [])[:6],
            "countries": codes,
            "country_names": (r.get("countries") or [])[:8],
            "regions": tax.regions_for(codes),
            "start_date": r.get("start_date"),
            "completion_date": r.get("completion_date"),
            "first_posted": r.get("first_posted"),
            "last_updated": r.get("last_updated"),
            "results_posted": bool(r.get("results_posted")),
            "results_date": r.get("results_date"),
            "summary": summarize(r.get("summary") or "", 300),
            "url": r.get("url") or "",
            "registration_type": r.get("registration_type") or "",
            "authors": (r.get("authors") or [])[:8],
            "topics": topics,
            "designs": designs,
            "first_seen": (prev or {}).get("first_seen") or today.isoformat(),
            "status_changed": (prev or {}).get("status_changed"),
        }
        if prev is None and backfill and rec.get("first_posted"):
            rec["first_seen"] = min(rec["first_posted"], today.isoformat())
        if prev is not None and prev.get("status") != rec["status"]:
            rec["status_changed"] = today.isoformat()
            rec["previous_status"] = prev.get("status")
        elif prev is not None and prev.get("previous_status"):
            rec["previous_status"] = prev["previous_status"]
        if prev is None:
            added += 1
        else:
            updated += 1
        by_id[rec["id"]] = rec
    trials = list(by_id.values())
    trials.sort(key=lambda t: (t.get("last_updated") or t.get("first_posted") or "", t["title"]), reverse=True)
    return trials, {"raw": len(raw), "added": added, "updated": updated, "dropped_irrelevant": dropped, "removed": len(removed), "total": len(trials)}


# ---------------------------------------------------------------- bills
STAGES = [
    ("enacted", "enacted"),
    ("vetoed", "vetoed"),
    ("passed-both", "passed both chambers"),
    ("passed-one", "passed one chamber"),
    ("reported", "reported from committee"),
    ("committee", "in committee"),
    ("introduced", "introduced"),
    ("failed", "failed or withdrawn"),
]
STAGE_LABEL = dict(STAGES)
STAGE_RANK = {s: i for i, (s, _) in enumerate(STAGES)}


def stage_from_actions(actions: list[dict], latest_action: str) -> str:
    cls = [c for a in actions for c in (a.get("classification") or [])]
    if "became-law" in cls or "executive-signature" in cls or "veto-override-passage" in cls:
        return "enacted"
    if "executive-veto" in cls or "executive-veto-line-item" in cls:
        return "vetoed"
    if "withdrawal" in cls:
        return "failed"
    chambers = {a.get("chamber") for a in actions if "passage" in (a.get("classification") or [])}
    chambers.discard("")
    chambers.discard(None)
    if "legislature" in chambers or len(chambers) >= 2:
        return "passed-both"
    if "passage" in cls:
        return "passed-one"
    if "failure" in cls and "passage" not in cls:
        return "failed"
    if any(c.startswith("committee-passage") for c in cls):
        return "reported"
    if "referral-committee" in cls:
        return "committee"
    if cls:
        return "introduced"
    return stage_from_text(latest_action)


_STAGE_TEXT = [
    ("enacted", r"became public law|signed by (the )?president|became law|signed by governor|approved by (the )?governor|chaptered|act no\.|public act"),
    ("vetoed", r"\bvetoed\b|veto message"),
    ("passed-both", r"presented to (the )?president|cleared for white house|passed both|sent to (the )?governor|enrolled and (presented|delivered)|to governor"),
    ("passed-one", r"passed (house|senate|assembly)|passed/agreed to in (house|senate)|received in the (house|senate)|third reading - passed|read third time and passed|engrossed"),
    ("reported", r"reported (by|from|favorably|out of)|ordered to be reported|placed on (the )?(union|senate|house|legislative|consent) calendar|do pass"),
    ("committee", r"referred to|committee referral|assigned to|in committee|hearing"),
    ("failed", r"\bfailed\b|died in|indefinitely postponed|withdrawn|tabled|session sine die"),
    ("introduced", r"introduced|first reading|read first time|prefiled|filed"),
]


def stage_from_text(text: str) -> str:
    t = (text or "").lower()
    for stage, pat in _STAGE_TEXT:
        if re.search(pat, t):
            return stage
    return "introduced"


def update_bills(existing: list[dict], raw: list[dict], tax: Taxonomy, today: dt.date, backfill: bool, keep_days: int = 730) -> tuple[list[dict], dict]:
    by_id = {b["id"]: b for b in existing}
    added = updated = dropped = 0
    for r in raw:
        text = f"{r.get('title') or ''} {r.get('abstract') or ''} {' '.join(r.get('subjects') or [])}"
        if not tax.bills_keep(text):
            dropped += 1
            continue
        topics, _ = tax.tag(text)
        stage = stage_from_actions(r.get("actions") or [], r.get("latest_action") or "") if r.get("actions") else stage_from_text(r.get("latest_action") or "")
        prev = by_id.get(r["id"])
        rec = {
            "id": r["id"],
            "level": r.get("level") or "state",
            "jurisdiction": r.get("jurisdiction") or "",
            "jurisdiction_code": r.get("jurisdiction_code") or "",
            "session": r.get("session") or "",
            "identifier": r.get("identifier") or "",
            "title": r.get("title") or "",
            "abstract": summarize(r.get("abstract") or "", 320),
            "classification": r.get("classification") or "bill",
            "subjects": r.get("subjects") or [],
            "sponsors": r.get("sponsors") or [],
            "introduced": r.get("introduced"),
            "latest_action_date": r.get("latest_action_date") or r.get("introduced"),
            "latest_action": r.get("latest_action") or "",
            "latest_passage_date": r.get("latest_passage_date"),
            "stage": stage,
            "stage_label": STAGE_LABEL.get(stage, stage),
            "url": r.get("url") or "",
            "source_url": r.get("source_url") or "",
            "topics": topics,
            "updated": r.get("updated") or today.isoformat(),
            "first_seen": (prev or {}).get("first_seen") or today.isoformat(),
            "stage_changed": (prev or {}).get("stage_changed"),
        }
        for f in ("congress", "bill_type", "number"):
            if r.get(f) is not None:
                rec[f] = r[f]
        if prev is None and backfill and rec.get("introduced"):
            rec["first_seen"] = min(rec["introduced"], today.isoformat())
        if prev is not None and prev.get("stage") != stage:
            rec["stage_changed"] = today.isoformat()
            rec["previous_stage"] = prev.get("stage")
        elif prev is not None and prev.get("previous_stage"):
            rec["previous_stage"] = prev["previous_stage"]
        if prev is None:
            added += 1
        else:
            updated += 1
        by_id[rec["id"]] = rec
    cutoff = (today - dt.timedelta(days=keep_days)).isoformat()
    bills = [b for b in by_id.values() if (b.get("latest_action_date") or b.get("first_seen") or "") >= cutoff]
    bills.sort(key=lambda b: (b.get("latest_action_date") or "", b.get("jurisdiction") or "", b.get("identifier") or ""), reverse=True)
    return bills, {"raw": len(raw), "added": added, "updated": updated, "dropped_irrelevant": dropped, "total": len(bills)}


# ---------------------------------------------------------------- courts
COURT_LEVELS = [
    ("scotus", "Supreme Court"),
    ("federal-appellate", "federal appellate"),
    ("federal-district", "federal district"),
    ("federal-bankruptcy", "federal bankruptcy"),
    ("federal-other", "other federal"),
    ("state-supreme", "state supreme"),
    ("state-appellate", "state appellate"),
    ("state-trial", "state trial"),
    ("tribal", "tribal"),
    ("other", "other"),
]
COURT_LEVEL_LABEL = dict(COURT_LEVELS)
_JUR_TO_LEVEL = {"F": "federal-appellate", "FD": "federal-district", "FB": "federal-bankruptcy", "FBP": "federal-bankruptcy", "FS": "federal-other", "S": "state-supreme", "SA": "state-appellate", "ST": "state-trial", "SS": "state-trial", "TRS": "tribal", "TRA": "tribal", "TRT": "tribal", "TRX": "tribal"}
_FED_APP = re.compile(r"^ca(\d{1,2}|dc|fc)$")
_FED_DIST = re.compile(r"^[a-z]{2,4}d$")
_FED_BANK = re.compile(r"^[a-z]{2,4}b$")


def court_level(court_id: str, jurisdiction: str) -> str:
    cid = (court_id or "").lower()
    if cid == "scotus":
        return "scotus"
    if jurisdiction in _JUR_TO_LEVEL:
        return _JUR_TO_LEVEL[jurisdiction]
    if _FED_APP.match(cid):
        return "federal-appellate"
    if _FED_DIST.match(cid):
        return "federal-district"
    if _FED_BANK.match(cid):
        return "federal-bankruptcy"
    if cid in ("cofc", "uscfc", "tax", "cit", "fiscr", "fisc", "jpml", "mspb"):
        return "federal-other"
    return "other"


# PACER "nature of suit" codes for cases that name a casino or sportsbook as a
# party but are not about gambling: personal injury and property torts, civil
# rights and employment, prisoner petitions, labour, social security, immigration.
_SUIT_EXCLUDE = {
    "310", "315", "320", "330", "340", "345", "350", "355", "360", "362", "365", "367", "368", "375", "380", "385",
    "440", "441", "442", "443", "444", "445", "446", "448", "462", "463", "465", "510", "530", "535", "540", "550", "555", "560",
    "710", "720", "740", "751", "790", "791", "861", "862", "863", "864", "865",
}


def docket_noise(r: dict, level: str) -> bool:
    """Dockets whose only link to gambling is a party's name, in a kind of case
    that is not about gambling."""
    if r.get("kind") != "docket":
        return False
    code = (r.get("suit_nature") or "").strip()[:3]
    if code in _SUIT_EXCLUDE:
        return True
    matched = r.get("matched") or []
    if level == "federal-bankruptcy" and matched == ["name"]:
        return True  # a debtor surnamed Casino, or a resort's adversary proceeding
    return False


def update_cases(existing: list[dict], raw: list[dict], tax: Taxonomy, today: dt.date, backfill: bool, keep_days: int = 730) -> tuple[list[dict], dict]:
    by_id = {c["id"]: c for c in existing}
    added = updated = dropped = 0
    for r in raw:
        docs = r.get("documents") or []
        text = " ".join([r.get("case_name") or "", r.get("snippet") or ""] + [d.get("description") or "" for d in docs])
        level = court_level(r.get("court_id") or "", r.get("court_jurisdiction") or "")
        if not tax.cases_keep(text) or docket_noise(r, level):
            dropped += 1
            continue
        topics, _ = tax.tag(text)
        prev = by_id.get(r["id"])
        latest_doc = docs[0]["date"] if docs and docs[0].get("date") else None
        rec = {
            "id": r["id"],
            "kind": r.get("kind") or "opinion",
            "case_name": r.get("case_name") or "",
            "court": r.get("court") or "",
            "court_id": r.get("court_id") or "",
            "court_citation": r.get("court_citation") or "",
            "court_level": level,
            "court_level_label": COURT_LEVEL_LABEL.get(level, level),
            "date_filed": r.get("date_filed"),
            "date_terminated": r.get("date_terminated"),
            "latest_activity": latest_doc or r.get("date_filed"),
            "docket_number": r.get("docket_number") or "",
            "citation": r.get("citation") or "",
            "status": r.get("status") or "",
            "url": r.get("url") or "",
            "snippet": r.get("snippet") or "",
            "suit_nature": r.get("suit_nature") or "",
            "documents": docs[:3],
            "cite_count": r.get("cite_count") or 0,
            "topics": topics,
            "first_seen": (prev or {}).get("first_seen") or today.isoformat(),
        }
        if prev is None and backfill and rec.get("latest_activity"):
            rec["first_seen"] = min(rec["latest_activity"], today.isoformat())
        if prev is not None:
            # Keep older filings we saw before so a docket's recent history accumulates.
            seen_urls = {d.get("url") for d in rec["documents"]}
            for d in prev.get("documents") or []:
                if d.get("url") not in seen_urls:
                    rec["documents"].append(d)
            rec["documents"].sort(key=lambda d: d.get("date") or "", reverse=True)
            rec["documents"] = rec["documents"][:5]
            updated += 1
        else:
            added += 1
        by_id[rec["id"]] = rec
    cutoff = (today - dt.timedelta(days=keep_days)).isoformat()
    cases = [c for c in by_id.values() if (c.get("latest_activity") or c.get("first_seen") or "") >= cutoff]
    cases.sort(key=lambda c: (c.get("latest_activity") or "", c.get("case_name") or ""), reverse=True)
    return cases, {"raw": len(raw), "added": added, "updated": updated, "dropped_irrelevant": dropped, "total": len(cases)}
