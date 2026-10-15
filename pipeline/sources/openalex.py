"""OpenAlex works API (free, no key; a mailto gets the polite pool)."""
from __future__ import annotations

import datetime as dt
import os
import time

from ..common import clean_text, get, iso, norm_doi, parse_date

API = "https://api.openalex.org/works"
SELECT = ",".join(
    [
        "id", "doi", "title", "display_name", "publication_date", "publication_year", "type",
        "primary_location", "open_access", "authorships", "abstract_inverted_index", "language",
        "is_retracted", "ids", "created_date",
    ]
)


def fetch(s, cfg: dict, days: int) -> list[dict]:
    mailto = os.environ.get("OPENALEX_MAILTO") or cfg.get("mailto") or ""
    since = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=days)).isoformat()
    search = " ".join(str(cfg["search"]).split())
    filt = f"title_and_abstract.search:{search},from_publication_date:{since},type:{cfg.get('types', 'article|review|preprint')}"
    cursor = "*"
    out: list[dict] = []
    while cursor:
        params = {"filter": filt, "per-page": "200", "cursor": cursor, "select": SELECT}
        if mailto:
            params["mailto"] = mailto
        r = get(s, API, params=params)
        js = r.json()
        for w in js.get("results", []):
            out.append(convert(w))
        cursor = (js.get("meta") or {}).get("next_cursor")
        time.sleep(0.2)
        if len(out) > 5000:  # safety valve
            break
    return out


def invert_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return clean_text(" ".join(w for _, w in positions))


def convert(w: dict) -> dict:
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    oa = w.get("open_access") or {}
    authors, countries, affiliations = [], [], []
    for a in w.get("authorships") or []:
        name = (a.get("author") or {}).get("display_name")
        if name:
            authors.append(name)
        for c in a.get("countries") or []:
            if c and c not in countries:
                countries.append(c)
        for inst in a.get("institutions") or []:
            cc = inst.get("country_code")
            if cc and cc not in countries:
                countries.append(cc)
            if inst.get("display_name"):
                affiliations.append(inst["display_name"])
    ids = w.get("ids") or {}
    pmid = (ids.get("pmid") or "").rsplit("/", 1)[-1] or None
    pmcid = (ids.get("pmcid") or "").rsplit("/", 1)[-1] or None
    doi = norm_doi(w.get("doi"))
    issns = src.get("issn") or ([src["issn_l"]] if src.get("issn_l") else [])
    return {
        "source": "openalex",
        "doi": doi,
        "pmid": pmid,
        "pmcid": pmcid,
        "openalex": (w.get("id") or "").rsplit("/", 1)[-1] or None,
        "title": clean_text(w.get("title") or w.get("display_name") or "").rstrip("."),
        "journal": clean_text(src.get("display_name") or ""),
        "issn": issns,
        "authors": authors,
        "affiliations": affiliations,
        "countries": countries,
        "published": iso(parse_date(w.get("publication_date"))),
        "created": iso(parse_date(w.get("created_date"))),
        "abstract": invert_abstract(w.get("abstract_inverted_index")),
        "url": f"https://doi.org/{doi}" if doi else (loc.get("landing_page_url") or w.get("id")),
        "oa_url": oa.get("oa_url") or None,
        "type": w.get("type"),
        "language": w.get("language"),
        "retracted": bool(w.get("is_retracted")),
    }
