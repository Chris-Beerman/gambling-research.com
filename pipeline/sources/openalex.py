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


def _key() -> str:
    # OpenAlex has required an API key on every request since February 13, 2026.
    # Keys are free: https://openalex.org/settings/api. Set the OPENALEX_API_KEY repository secret.
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OpenAlex needs a free API key (openalex.org/settings/api); set the OPENALEX_API_KEY repository secret")
    return api_key


def _base_filter(cfg: dict) -> str:
    search = " ".join(str(cfg["search"]).split())
    filt = f"title_and_abstract.search:{search},type:{cfg.get('types', 'article|review|letter|editorial')}"
    if cfg.get("source_types"):
        filt += f",primary_location.source.type:{cfg['source_types']}"
    return filt


def fetch(s, cfg: dict, days: int) -> list[dict]:
    """Nightly: works published in the last `days` days."""
    since = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=days)).isoformat()
    return _list(s, cfg, f"{_base_filter(cfg)},from_publication_date:{since}")


def fetch_range(s, cfg: dict, start: dt.date, end: dt.date) -> list[dict]:
    """Backfill: works published between two dates (inclusive), a month at a time."""
    return _list(s, cfg, f"{_base_filter(cfg)},from_publication_date:{start.isoformat()},to_publication_date:{end.isoformat()}")


def fetch_dois(s, cfg: dict, dois: list[str]) -> list[dict]:
    """Re-read known works by DOI, 50 per request (used when the tagging rules change)."""
    out: list[dict] = []
    dois = [d for d in dict.fromkeys(dois) if d and "|" not in d and "," not in d]
    for i in range(0, len(dois), 50):
        chunk = dois[i : i + 50]
        out += _list(s, cfg, "doi:" + "|".join(f"https://doi.org/{d}" for d in chunk), per_page=50)
    return out


def _list(s, cfg: dict, filt: str, per_page: int = 200) -> list[dict]:
    api_key = _key()
    mailto = os.environ.get("OPENALEX_MAILTO") or cfg.get("mailto") or ""
    cursor = "*"
    out: list[dict] = []
    while cursor:
        params = {"filter": filt, "per-page": str(per_page), "cursor": cursor, "select": SELECT, "api_key": api_key}
        if mailto:
            params["mailto"] = mailto
        r = get(s, API, params=params)
        js = r.json()
        results = js.get("results", [])
        for w in results:
            out.append(convert(w))
        cursor = (js.get("meta") or {}).get("next_cursor") if results else None
        time.sleep(0.2)
        if len(out) > 8000:  # safety valve
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
