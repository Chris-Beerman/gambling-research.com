"""RSS/Atom feeds: journal tables of contents and news."""
from __future__ import annotations

import re

import feedparser

from ..common import clean_text, get, iso, norm_doi, parse_date, stable_id

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.I)


def _entry_date(e):
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        v = e.get(key)
        if v:
            d = parse_date(v)
            if d:
                return d
    for key in ("published", "updated", "dc_date"):
        v = e.get(key)
        if v:
            d = parse_date(v)
            if d:
                return d
    return None


def _doi_from_entry(e) -> str | None:
    for key in ("prism_doi", "dc_identifier", "id", "link"):
        v = e.get(key)
        if v:
            m = DOI_RE.search(str(v))
            if m:
                return norm_doi(m.group(0).rstrip(".)"))
    for l in e.get("links") or []:
        m = DOI_RE.search(l.get("href", ""))
        if m:
            return norm_doi(m.group(0).rstrip(".)"))
    return None


def fetch_journal_feed(s, feed: dict) -> list[dict]:
    r = get(s, feed["url"], timeout=45)
    parsed = feedparser.parse(r.content)
    if parsed.get("bozo") and not parsed.get("entries"):
        raise RuntimeError(f"feed could not be parsed: {parsed.get('bozo_exception')}")
    out = []
    for e in parsed.entries:
        title = clean_text(e.get("title") or "").rstrip(".")
        if not title:
            continue
        doi = _doi_from_entry(e)
        authors = [clean_text(a.get("name", "")) for a in (e.get("authors") or []) if a.get("name")]
        if not authors and e.get("author"):
            authors = [clean_text(e["author"])]
        if len(authors) == 1 and ("," in authors[0] or " and " in authors[0]):
            # OJS and Springer feeds put every author in one dc:creator string.
            parts = [a.strip() for a in re.split(r",\s*|;\s*|\s+and\s+", authors[0]) if a.strip()]
            if all(len(x.split()) <= 5 for x in parts):
                authors = parts
        summary = clean_text(e.get("summary") or (e.get("content") or [{}])[0].get("value", ""))
        d = _entry_date(e)
        out.append(
            {
                "source": f"feed:{feed['id']}",
                "doi": doi,
                "pmid": None,
                "pmcid": None,
                "openalex": None,
                "title": title,
                "journal": feed.get("name"),
                "issn": [],
                "authors": authors,
                "affiliations": [],
                "countries": [],
                "published": iso(d),
                "created": iso(d),
                "abstract": summary,
                "url": f"https://doi.org/{doi}" if doi else e.get("link"),
                "oa_url": None,
                "type": "preprint" if "medrxiv" in feed["id"] else "article",
                "language": None,
                "retracted": False,
            }
        )
    return out


def fetch_news_feed(s, feed: dict) -> list[dict]:
    r = get(s, feed["url"], timeout=45)
    parsed = feedparser.parse(r.content)
    if parsed.get("bozo") and not parsed.get("entries"):
        raise RuntimeError(f"feed could not be parsed: {parsed.get('bozo_exception')}")
    out = []
    for e in parsed.entries:
        title = clean_text(e.get("title") or "")
        link = e.get("link") or ""
        if not title or not link:
            continue
        # Google News titles end with " - Publisher"; keep the publisher as the source name.
        source_name = feed.get("name", "")
        if feed["id"].startswith("gnews"):
            src = (e.get("source") or {}).get("title")
            if src:
                source_name = clean_text(src)
            title = re.sub(r"\s+-\s+[^-]{2,60}$", "", title)
        summary = clean_text(e.get("summary") or "")
        summary = re.sub(r"\s*(Read more|Continue reading|The post .* appeared first on .*)$", "", summary, flags=re.I)
        d = _entry_date(e)
        out.append(
            {
                "id": stable_id(link),
                "title": title,
                "url": link,
                "source": source_name,
                "feed_id": feed["id"],
                "kind": feed.get("kind", "press"),
                "published": iso(d),
                "summary": summary[:220].rsplit(" ", 1)[0] + ("…" if len(summary) > 220 else "") if summary else "",
            }
        )
    return out
