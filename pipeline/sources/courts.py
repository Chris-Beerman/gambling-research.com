"""Court rulings and federal dockets from CourtListener's search API (v4).
Anonymous access is allowed (about 100 requests a day per address); a free
account token raises the limit. Set COURTLISTENER_API_TOKEN.

Raw shape:
    id, kind ('opinion' | 'docket'), case_name, court, court_id,
    court_jurisdiction (CourtListener code, may be empty), date_filed,
    date_terminated, docket_number, citation, status, url, snippet,
    documents (dockets: recent matching filings), cite_count
"""
from __future__ import annotations

import os
import re
import time

from ..common import clean_text, get, iso, parse_date

CL_API = "https://www.courtlistener.com/api/rest/v4/search/"
CL_SITE = "https://www.courtlistener.com"


def _headers() -> dict:
    token = os.environ.get("COURTLISTENER_API_TOKEN", "").strip()
    return {"Authorization": f"Token {token}"} if token else {}


def fetch_courtlistener(s, cfg: dict, days: int, warnings: list[str] | None = None) -> list[dict]:
    import datetime as dt

    since = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=days)).isoformat()
    headers = _headers()
    out: dict[str, dict] = {}
    max_pages = int(cfg.get("max_pages", 3))
    query = " ".join(str(cfg.get("query", "gambling")).split())
    # highlight=on makes `snippet` the passage that matched rather than the
    # opening lines of the document, which is what the relevance rules need.
    searches = [
        ("o", {"type": "o", "q": query, "order_by": "dateFiled desc", "filed_after": since, "highlight": "on"}),
    ]
    if cfg.get("dockets", True):
        searches.append(("r", {"type": "r", "q": query, "order_by": "entry_date_filed desc", "entry_date_filed_after": since, "highlight": "on"}))
    # Authenticated free accounts are throttled to five requests a minute.
    pause = float(cfg.get("pause_seconds", 13))
    for kind, params in searches:
        url = CL_API
        pages = 0
        while url:
            try:
                r = get(s, url, params=params, headers=headers, timeout=90)
            except RuntimeError as e:
                if not out:
                    raise
                if warnings is not None:
                    warnings.append(f"stopped in type={kind} page {pages + 1} with {len(out)} records: {str(e)[:120]}")
                return list(out.values())
            js = r.json()
            for item in js.get("results", []):
                rec = convert_opinion(item) if kind == "o" else convert_docket(item)
                if rec and rec["id"] not in out:
                    out[rec["id"]] = rec
            url = js.get("next")
            params = None
            pages += 1
            if pages >= max_pages:
                break
            time.sleep(pause)
        time.sleep(pause)
    return list(out.values())


_MARK = re.compile(r"</?mark>")


def _snippet(text: str | None, limit: int = 320) -> str:
    t = clean_text(_MARK.sub("", text or ""))
    t = t.replace("…", " ").strip()
    if len(t) > limit:
        t = t[: limit - 1].rsplit(" ", 1)[0] + " …"
    return t


def convert_opinion(item: dict) -> dict | None:
    cid = item.get("cluster_id")
    name = clean_text(_MARK.sub("", item.get("caseName") or ""))
    if not cid or not name:
        return None
    snippets = [o.get("snippet") for o in (item.get("opinions") or []) if o.get("snippet")]
    cites = item.get("citation") or []
    matched = []
    if "<mark>" in (item.get("caseName") or ""):
        matched.append("name")
    if any("<mark>" in (sn or "") for sn in snippets):
        matched.append("text")
    return {
        "id": f"cl-o-{cid}",
        "kind": "opinion",
        "matched": matched,
        "case_name": name,
        "court": clean_text(item.get("court") or ""),
        "court_id": item.get("court_id") or "",
        "court_jurisdiction": item.get("court_jurisdiction") or "",
        "court_citation": clean_text(_MARK.sub("", item.get("court_citation_string") or "")),
        "date_filed": iso(parse_date(item.get("dateFiled"))),
        "date_terminated": None,
        "docket_number": clean_text(_MARK.sub("", item.get("docketNumber") or "")),
        "citation": cites[0] if cites else "",
        "status": item.get("status") or "",
        "url": CL_SITE + item["absolute_url"] if item.get("absolute_url") else "",
        "snippet": _snippet(snippets[0] if snippets else item.get("syllabus") or ""),
        "documents": [],
        "cite_count": int(item.get("citeCount") or 0),
    }


def convert_docket(item: dict) -> dict | None:
    did = item.get("docket_id")
    name = clean_text(_MARK.sub("", item.get("caseName") or ""))
    if not did or not name:
        return None
    docs = []
    matched = []
    if "<mark>" in (item.get("caseName") or ""):
        matched.append("name")
    for d in item.get("recap_documents") or []:
        raw_desc = d.get("description") or d.get("short_description") or ""
        if "<mark>" in raw_desc or "<mark>" in (d.get("snippet") or ""):
            if "documents" not in matched:
                matched.append("documents")
        desc = clean_text(_MARK.sub("", raw_desc))
        if not desc:
            continue
        docs.append(
            {
                "date": iso(parse_date(d.get("entry_date_filed"))),
                "description": desc[:200],
                "url": CL_SITE + d["absolute_url"] if d.get("absolute_url") else "",
            }
        )
    docs.sort(key=lambda d: d["date"] or "", reverse=True)
    if any("<mark>" in (item.get(f) or "") for f in ("cause", "suitNature", "assignedTo", "referredTo")):
        matched.append("fields")
    suit = clean_text(_MARK.sub("", item.get("suitNature") or ""))
    return {
        "id": f"cl-d-{did}",
        "kind": "docket",
        "matched": matched,
        "suit_nature": suit,
        "case_name": name,
        "court": clean_text(item.get("court") or ""),
        "court_id": item.get("court_id") or "",
        "court_jurisdiction": item.get("court_jurisdiction") or "",
        "court_citation": clean_text(_MARK.sub("", item.get("court_citation_string") or "")),
        "date_filed": iso(parse_date(item.get("dateFiled"))),
        "date_terminated": iso(parse_date(item.get("dateTerminated"))),
        "docket_number": clean_text(_MARK.sub("", item.get("docketNumber") or "")),
        "citation": "",
        "status": "",
        "url": CL_SITE + item["docket_absolute_url"] if item.get("docket_absolute_url") else "",
        "snippet": _snippet(clean_text(_MARK.sub("", item.get("cause") or "")) + (f"; nature of suit: {_MARK.sub('', item.get('suitNature'))}" if item.get("suitNature") else ""), 200),
        "documents": docs[:3],
        "cite_count": 0,
    }
