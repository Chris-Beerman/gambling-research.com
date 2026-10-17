"""Legislation: state bills from Open States (API v3, free key) and federal
bills found through GovInfo's bill-text listings and detailed through the
Congress.gov API (one free api.data.gov key serves both).

Raw shape (both levels):
    id, level ('state' | 'federal'), jurisdiction, jurisdiction_code, session,
    identifier, title, abstract, classification, subjects, sponsors,
    introduced, latest_action_date, latest_action, latest_passage_date,
    actions (list of {date, description, classification, chamber}),
    url, source_url, updated
"""
from __future__ import annotations

import os
import re
import time

from ..common import clean_text, get, iso, parse_date

OPENSTATES_API = "https://v3.openstates.org/bills"
GOVINFO_API = "https://api.govinfo.gov"
CONGRESS_API = "https://api.congress.gov/v3"
DEMO_KEY = "DEMO_KEY"  # api.data.gov's shared demo key: 30 requests an hour, for a first look only


# ---------------------------------------------------------------- Open States
def fetch_openstates(s, cfg: dict, days: int, warnings: list[str] | None = None) -> list[dict]:
    api_key = os.environ.get("OPENSTATES_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Open States needs a free API key (openstates.org/accounts/profile); set the OPENSTATES_API_KEY repository secret")
    import datetime as dt

    since = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=days)).isoformat()
    headers = {"X-API-KEY": api_key}
    out: dict[str, dict] = {}
    max_pages = int(cfg.get("max_pages", 5))
    for q in cfg.get("queries", ["gambling"]):
        page = 1
        while True:
            params = [("q", q), ("sort", "updated_desc"), ("updated_since", since), ("per_page", "20"), ("page", str(page))]
            params += [("include", x) for x in ("abstracts", "actions", "sponsorships", "sources")]
            try:
                r = get(s, OPENSTATES_API, params=params, headers=headers, timeout=60)
            except RuntimeError as e:
                if not out:
                    raise
                if warnings is not None:
                    warnings.append(f"stopped at '{q}' page {page} with {len(out)} bills: {str(e)[:120]}")
                return list(out.values())
            js = r.json()
            for b in js.get("results", []):
                rec = convert_openstates(b)
                if rec and rec["id"] not in out:
                    out[rec["id"]] = rec
            pg = js.get("pagination") or {}
            if page >= int(pg.get("max_page") or 1) or page >= max_pages:
                break
            page += 1
            time.sleep(1.1)  # free keys are limited to about one request a second
        time.sleep(1.1)
    return list(out.values())


_JURIS_CODE = re.compile(r"/(?:state|district|territory):([a-z]{2})/")


def convert_openstates(b: dict) -> dict | None:
    bid = b.get("id")
    if not bid or not b.get("title"):
        return None
    jur = b.get("jurisdiction") or {}
    m = _JURIS_CODE.search(jur.get("id") or "")
    actions = []
    for a in b.get("actions") or []:
        org = (a.get("organization") or {})
        actions.append(
            {
                "date": iso(parse_date(a.get("date"))),
                "description": clean_text(a.get("description") or ""),
                "classification": list(a.get("classification") or []),
                "chamber": org.get("classification") or "",
            }
        )
    actions.sort(key=lambda a: a["date"] or "")
    sponsors = []
    for sp in b.get("sponsorships") or []:
        name = clean_text(sp.get("name") or "")
        if name and name not in sponsors:
            sponsors.append(name)
    abstracts = [clean_text(x.get("abstract") or "") for x in (b.get("abstracts") or []) if x.get("abstract")]
    sources = [x.get("url") for x in (b.get("sources") or []) if x.get("url")]
    return {
        "id": bid,
        "level": "state",
        "jurisdiction": jur.get("name") or "",
        "jurisdiction_code": m.group(1) if m else "",
        "session": b.get("session") or "",
        "identifier": b.get("identifier") or "",
        "title": clean_text(b["title"]),
        "abstract": max(abstracts, key=len) if abstracts else "",
        "classification": (b.get("classification") or ["bill"])[0],
        "subjects": [clean_text(x) for x in (b.get("subject") or [])][:12],
        "sponsors": sponsors[:6],
        "introduced": iso(parse_date(b.get("first_action_date"))),
        "latest_action_date": iso(parse_date(b.get("latest_action_date"))),
        "latest_action": clean_text(b.get("latest_action_description") or ""),
        "latest_passage_date": iso(parse_date(b.get("latest_passage_date"))),
        "actions": actions[-40:],
        "url": b.get("openstates_url") or "",
        "source_url": sources[0] if sources else "",
        "updated": iso(parse_date(b.get("updated_at"))),
    }


# ---------------------------------------------------------------- Congress
_PKG = re.compile(r"^BILLS-(\d+)(hr|hres|hjres|hconres|s|sres|sjres|sconres)(\d+)([a-z]+)$")
_TYPE_LABEL = {"hr": "H.R.", "s": "S.", "hres": "H.Res.", "sres": "S.Res.", "hjres": "H.J.Res.", "sjres": "S.J.Res.", "hconres": "H.Con.Res.", "sconres": "S.Con.Res."}


def _data_gov_key() -> tuple[str, bool]:
    key = os.environ.get("CONGRESS_API_KEY", "").strip()
    if key:
        return key, False
    return DEMO_KEY, True


def fetch_congress(s, cfg: dict, days: int, include_patterns: list, known: list[dict] | None = None, warnings: list[str] | None = None) -> list[dict]:
    """Find bills by their official titles in GovInfo's listing of bill texts
    modified in the window, then fetch each bill's status from Congress.gov.
    Known federal bills are refreshed a few at a time so their latest action
    stays current between text versions."""
    import datetime as dt

    key, demo = _data_gov_key()
    budget = int(cfg.get("demo_budget", 25)) if demo else int(cfg.get("max_requests", 400))
    if demo and warnings is not None:
        warnings.append("using api.data.gov's shared DEMO_KEY (set the CONGRESS_API_KEY repository secret for a real key)")
    since = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=days)).isoformat()
    requests_made = 0
    wanted: dict[tuple[str, str, str], dict] = {}
    url = f"{GOVINFO_API}/collections/BILLS/{since}T00:00:00Z"
    params = {"pageSize": "1000", "offsetMark": "*", "api_key": key}
    pages = 0
    while url and requests_made < budget:
        r = get(s, url, params=params, timeout=90)
        requests_made += 1
        js = r.json()
        for pkg in js.get("packages", []):
            m = _PKG.match(pkg.get("packageId") or "")
            title = clean_text(pkg.get("title") or "")
            if not m or not title:
                continue
            if not any(p.search(title) for p in include_patterns):
                continue
            k = (m.group(1), m.group(2), m.group(3))
            if k not in wanted:
                wanted[k] = {"title": title, "date_issued": pkg.get("dateIssued")}
        url = js.get("nextPage")
        params = {"api_key": key} if url and "api_key" not in url else None
        pages += 1
        if pages >= int(cfg.get("max_pages", 8)):
            break
        time.sleep(0.3)
    # Refresh known bills: oldest-refreshed first, a handful a night.
    refresh: list[tuple[str, str, str]] = []
    for b in sorted(known or [], key=lambda x: x.get("updated") or ""):
        if b.get("level") != "federal":
            continue
        k = (str(b.get("congress") or ""), b.get("bill_type") or "", str(b.get("number") or ""))
        if all(k) and k not in wanted:
            refresh.append(k)
    refresh = refresh[: int(cfg.get("refresh_per_run", 30))]
    official = {k: v["title"] for k, v in wanted.items()}
    for b in known or []:
        k = (str(b.get("congress") or ""), b.get("bill_type") or "", str(b.get("number") or ""))
        if k in refresh and b.get("abstract"):
            official[k] = b["abstract"]
    out = []
    for k in list(wanted) + refresh:
        if requests_made >= budget:
            if warnings is not None:
                warnings.append(f"request budget reached ({budget}); {len(wanted) + len(refresh) - len(out)} bills left for the next run")
            break
        congress, btype, number = k
        try:
            r = get(s, f"{CONGRESS_API}/bill/{congress}/{btype}/{number}", params={"api_key": key, "format": "json"}, timeout=60)
        except RuntimeError as e:
            requests_made += 1
            if "429" in str(e):
                if warnings is not None:
                    warnings.append(f"rate limited at {btype}{number} after {len(out)} bills; the rest wait for the next run")
                break
            if warnings is not None:
                warnings.append(f"{btype}{number}: {str(e)[:80]}")
            continue
        requests_made += 1
        rec = convert_congress((r.json() or {}).get("bill") or {}, congress, btype, number, official.get(k, ""))
        if rec:
            out.append(rec)
        time.sleep(0.3)
    return out


def convert_congress(bill: dict, congress: str, btype: str, number: str, official_title: str = "") -> dict | None:
    """Congress.gov's `title` is the short title when one exists ("SAFE Bet
    Act"); the official title from GovInfo, which says what the bill does, is
    kept as the abstract so that relevance and search can see it."""
    title = clean_text(bill.get("title") or "") or clean_text(official_title)
    if not title:
        return None
    official_title = clean_text(official_title)
    if official_title.lower() == title.lower():
        official_title = ""
    latest = bill.get("latestAction") or {}
    sponsors = [clean_text(sp.get("fullName") or "") for sp in (bill.get("sponsors") or []) if sp.get("fullName")]
    policy = ((bill.get("policyArea") or {}).get("name") or "").strip()
    n = int(congress)
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return {
        "id": f"us-{congress}-{btype}-{number}",
        "level": "federal",
        "jurisdiction": "United States",
        "jurisdiction_code": "us",
        "session": f"{n}{suffix} Congress",
        "identifier": f"{_TYPE_LABEL.get(btype, btype.upper())} {number}",
        "title": title,
        "abstract": official_title,
        "classification": "resolution" if "res" in btype else "bill",
        "subjects": [policy] if policy else [],
        "sponsors": sponsors[:6],
        "introduced": iso(parse_date(bill.get("introducedDate"))),
        "latest_action_date": iso(parse_date(latest.get("actionDate"))),
        "latest_action": clean_text(latest.get("text") or ""),
        "latest_passage_date": None,
        "actions": [],
        "url": bill.get("legislationUrl") or f"https://www.congress.gov/bill/{n}{suffix}-congress/{_CONGRESS_PATH.get(btype, btype)}/{number}",
        "source_url": "",
        "updated": iso(parse_date(bill.get("updateDate"))),
        "congress": n,
        "bill_type": btype,
        "number": int(number),
    }


_CONGRESS_PATH = {"hr": "house-bill", "s": "senate-bill", "hres": "house-resolution", "sres": "senate-resolution", "hjres": "house-joint-resolution", "sjres": "senate-joint-resolution", "hconres": "house-concurrent-resolution", "sconres": "senate-concurrent-resolution"}
