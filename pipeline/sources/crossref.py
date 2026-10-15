"""Crossref: everything the dedicated gambling journals register."""
from __future__ import annotations

import datetime as dt
import os
import time

from ..common import clean_text, get, iso, norm_doi, parse_date

API = "https://api.crossref.org/journals/{issn}/works"


def fetch(s, cfg: dict, days: int) -> list[dict]:
    mailto = os.environ.get("CROSSREF_MAILTO") or cfg.get("mailto") or ""
    since = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=days)).isoformat()
    out: list[dict] = []
    seen_doi: set[str] = set()
    for j in cfg.get("journals", []):
        for issn in j.get("issn", []):
            offset = 0
            while True:
                params = {"filter": f"from-created-date:{since}", "rows": "100", "offset": str(offset), "sort": "created", "order": "desc"}
                if mailto:
                    params["mailto"] = mailto
                try:
                    r = get(s, API.format(issn=issn), params=params)
                except RuntimeError as e:
                    # A wrong ISSN returns 404; record and move on to the next ISSN.
                    raise RuntimeError(f"{j.get('name')} ({issn}): {e}") from e
                msg = r.json().get("message", {})
                items = msg.get("items", [])
                for it in items:
                    rec = convert(it, j.get("name"))
                    if rec["doi"] and rec["doi"] in seen_doi:
                        continue
                    if rec["doi"]:
                        seen_doi.add(rec["doi"])
                    out.append(rec)
                total = int(msg.get("total-results", 0))
                offset += 100
                time.sleep(0.3)
                if not items or offset >= total:
                    break
    return out


def convert(it: dict, journal_name: str | None) -> dict:
    doi = norm_doi(it.get("DOI"))
    title = clean_text((it.get("title") or [""])[0]).rstrip(".")
    authors, affiliations = [], []
    for a in it.get("author") or []:
        name = " ".join(p for p in [a.get("given"), a.get("family")] if p) or a.get("name")
        if name:
            authors.append(clean_text(name))
        for aff in a.get("affiliation") or []:
            if aff.get("name"):
                affiliations.append(clean_text(aff["name"]))
    published = None
    for key in ("published-online", "published-print", "published", "issued"):
        dp = (it.get(key) or {}).get("date-parts")
        if dp:
            published = parse_date(dp)
            if published:
                break
    created = parse_date(((it.get("created") or {}).get("date-parts")))
    ctype = it.get("type") or "journal-article"
    rtype = {"journal-article": "article", "posted-content": "preprint", "book-chapter": "chapter"}.get(ctype, ctype)
    oa_url = None
    for link in it.get("link") or []:
        if link.get("content-version") == "vor" and "pdf" in (link.get("content-type") or ""):
            oa_url = None  # a publisher PDF link is not evidence of open access; leave to OpenAlex
    return {
        "source": "crossref",
        "doi": doi,
        "pmid": None,
        "pmcid": None,
        "openalex": None,
        "title": title,
        "journal": clean_text((it.get("container-title") or [journal_name or ""])[0]) or journal_name,
        "issn": it.get("ISSN") or [],
        "authors": authors,
        "affiliations": affiliations,
        "countries": [],
        "published": iso(published),
        "created": iso(created),
        "abstract": clean_text(it.get("abstract") or ""),
        "url": f"https://doi.org/{doi}" if doi else it.get("URL"),
        "oa_url": oa_url,
        "type": rtype,
        "language": it.get("language"),
        "retracted": False,
    }
