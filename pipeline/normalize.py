"""Merge raw records into the canonical index, dedupe, score relevance, tag."""
from __future__ import annotations

import datetime as dt
import re

from .common import norm_title, stable_id, summarize


class Taxonomy:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        rel = cfg.get("relevance", {})
        self.strong = [re.compile(p, re.I) for p in rel.get("strong", [])]
        self.weak = [re.compile(p, re.I) for p in rel.get("weak", [])]
        self.exclude = [re.compile(p, re.I) for p in rel.get("exclude_contexts", [])]
        self.topics = [(t["slug"], t["label"], [re.compile(p, re.I) for p in t["patterns"]]) for t in cfg.get("topics", [])]
        self.designs = [(d["slug"], d["label"], [re.compile(p, re.I) for p in d["patterns"]]) for d in cfg.get("designs", [])]
        self.regions = cfg.get("regions", {})
        self.code_to_region = {}
        for slug, r in self.regions.items():
            for c in r.get("codes", []):
                self.code_to_region[c] = slug
        self.country_patterns = [(code, re.compile(p)) for code, p in cfg.get("country_patterns", {}).items()]
        self.news_include = [re.compile(p, re.I) for p in cfg.get("news_include", [])]
        self.news_exclude = [re.compile(p, re.I) for p in cfg.get("news_exclude", [])]
        self.news_categories = [(c["slug"], c["label"], [re.compile(p, re.I) for p in c["patterns"]]) for c in cfg.get("news_categories", [])]

    # ---- papers -------------------------------------------------------
    def relevance(self, text: str) -> str | None:
        """'high', 'low' or None (drop)."""
        cleaned = text
        for ex in self.exclude:
            cleaned = ex.sub(" ", cleaned)
        if any(p.search(cleaned) for p in self.strong):
            return "high"
        # Weak terms are checked on the original text so that excluded contexts
        # (a lottery used as a survey incentive) still land on the borderline list.
        if any(p.search(text) for p in self.weak):
            return "low"
        return None

    def tag(self, text: str) -> tuple[list[str], list[str]]:
        topics = [slug for slug, _, pats in self.topics if any(p.search(text) for p in pats)]
        designs = [slug for slug, _, pats in self.designs if any(p.search(text) for p in pats)]
        return topics, designs

    def countries_from_affiliations(self, affiliations: list[str]) -> list[str]:
        found: list[str] = []
        blob = " ; ".join(affiliations)
        for code, pat in self.country_patterns:
            if pat.search(blob) and code not in found:
                found.append(code)
        return found

    def regions_for(self, countries: list[str]) -> list[str]:
        out: list[str] = []
        for c in countries:
            r = self.code_to_region.get(c)
            if r and r not in out:
                out.append(r)
        return out

    def topic_label(self, slug: str) -> str:
        for s, label, _ in self.topics:
            if s == slug:
                return label
        return slug

    def design_label(self, slug: str) -> str:
        for s, label, _ in self.designs:
            if s == slug:
                return label
        return slug

    # ---- news ---------------------------------------------------------
    def news_keep(self, text: str) -> bool:
        if any(p.search(text) for p in self.news_exclude):
            return False
        return any(p.search(text) for p in self.news_include)

    def news_categorize(self, text: str, kind: str) -> tuple[list[str], str]:
        cats = [slug for slug, _, pats in self.news_categories if any(p.search(text) for p in pats)]
        if not cats:
            cats = ["industry" if kind in ("trade", "industry") else "regulation" if kind in ("regulator", "court") else "public-health" if kind == "public-health" else "industry"]
        return cats, cats[0]

    def news_label(self, slug: str) -> str:
        for s, label, _ in self.news_categories:
            if s == slug:
                return label
        return slug


# ----------------------------------------------------------------------
def key_for(rec: dict) -> str:
    if rec.get("doi"):
        return "doi:" + rec["doi"]
    if rec.get("pmid"):
        return "pmid:" + str(rec["pmid"])
    t = norm_title(rec.get("title", ""))
    return "title:" + stable_id(t[:200])


SOURCE_PRIORITY = {"pubmed": 3, "crossref": 2, "openalex": 1}


def _prio(source: str) -> int:
    return SOURCE_PRIORITY.get(source.split(":")[0], 0)


def merge_raw(raw: list[dict]) -> dict[str, dict]:
    """Group raw records by DOI/PMID/title, merging fields by source priority."""
    groups: dict[str, dict] = {}
    pmid_to_key: dict[str, str] = {}
    title_to_key: dict[str, str] = {}
    for rec in raw:
        if not rec.get("title"):
            continue
        key = key_for(rec)
        # Link records that lack a DOI to an existing DOI group via PMID or title.
        if not key.startswith("doi:"):
            if rec.get("pmid") and rec["pmid"] in pmid_to_key:
                key = pmid_to_key[rec["pmid"]]
            else:
                nt = norm_title(rec["title"])[:200]
                if nt in title_to_key:
                    key = title_to_key[nt]
        g = groups.get(key)
        if g is None:
            g = {"sources": [], "_recs": []}
            groups[key] = g
        g["_recs"].append(rec)
        if rec["source"] not in g["sources"]:
            g["sources"].append(rec["source"])
        if rec.get("pmid"):
            pmid_to_key[rec["pmid"]] = key
        title_to_key[norm_title(rec["title"])[:200]] = key
    return groups


def canonical(key: str, group: dict, tax: Taxonomy, today: dt.date, existing: dict | None) -> dict | None:
    recs = sorted(group["_recs"], key=lambda r: -_prio(r["source"]))

    def first(field, pred=lambda v: bool(v)):
        for r in recs:
            v = r.get(field)
            if pred(v):
                return v
        return None

    title = first("title")
    abstract = max((r.get("abstract") or "" for r in recs), key=len)
    text = f"{title}. {abstract}"
    rel = tax.relevance(text)
    if rel is None:
        return None
    countries: list[str] = []
    for r in recs:
        for c in r.get("countries") or []:
            if c not in countries:
                countries.append(c)
    if not countries:
        affs = [a for r in recs for a in (r.get("affiliations") or [])]
        countries = tax.countries_from_affiliations(affs)
    topics, designs = tax.tag(text)
    rtype = first("type") or "article"
    if rtype in ("letter", "editorial") and "commentary" not in designs:
        designs.append("commentary")
    if rtype == "review" and "review" not in designs:
        designs.append("review")
    published = first("published")
    created = first("created")
    doi = first("doi")
    pmid = first("pmid")
    pmcid = first("pmcid")
    oa_url = first("oa_url")
    if not oa_url and pmcid:
        oa_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
    url = f"https://doi.org/{doi}" if doi else first("url")
    if existing and existing.get("first_seen"):
        first_seen = existing["first_seen"]
    else:
        # Nightly runs: today. Backfill (no existing index): the most recent date the sources give.
        first_seen = today.isoformat()
    rec = {
        "id": key,
        "doi": doi,
        "pmid": pmid,
        "pmcid": pmcid,
        "openalex": first("openalex"),
        "title": title,
        "journal": first("journal") or "",
        "authors": (first("authors") or [])[:50],
        "published": published,
        "year": int(published[:4]) if published else None,
        "created": created,
        "first_seen": first_seen,
        "summary": summarize(abstract) if abstract else "",
        "url": url,
        "oa_url": oa_url,
        "sources": group["sources"],
        "type": rtype,
        "topics": topics,
        "designs": designs,
        "countries": countries,
        "regions": tax.regions_for(countries),
        "language": first("language"),
        "relevance": rel,
        "retracted": any(r.get("retracted") for r in recs),
    }
    return rec


def update_index(existing: list[dict], raw: list[dict], tax: Taxonomy, today: dt.date, backfill: bool) -> tuple[list[dict], dict]:
    """Return the updated index and a small stats dict."""
    by_id = {p["id"]: p for p in existing}
    by_doi = {p["doi"]: p for p in existing if p.get("doi")}
    by_pmid = {p["pmid"]: p for p in existing if p.get("pmid")}
    by_title = {norm_title(p["title"])[:200]: p for p in existing}
    groups = merge_raw(raw)
    added = updated = dropped = 0
    for key, group in groups.items():
        sample = group["_recs"][0]
        prev = by_id.get(key)
        if prev is None:
            for r in group["_recs"]:
                if r.get("doi") and r["doi"] in by_doi:
                    prev = by_doi[r["doi"]]
                    break
                if r.get("pmid") and r["pmid"] in by_pmid:
                    prev = by_pmid[r["pmid"]]
                    break
            if prev is None:
                prev = by_title.get(norm_title(sample["title"])[:200])
        rec = canonical(key, group, tax, today, prev)
        if rec is None:
            dropped += 1
            continue
        if prev is not None:
            # Keep the original id and first_seen; refresh everything else, union sources.
            rec["id"] = prev["id"]
            rec["first_seen"] = prev.get("first_seen") or rec["first_seen"]
            rec["sources"] = sorted(set(prev.get("sources", [])) | set(rec["sources"]))
            for f in ("summary", "oa_url", "pmid", "pmcid", "openalex", "doi", "published"):
                if not rec.get(f) and prev.get(f):
                    rec[f] = prev[f]
            if rec.get("published"):
                rec["year"] = int(rec["published"][:4])
            by_id[prev["id"]] = rec
            updated += 1
        else:
            if backfill:
                basis = rec.get("created") or rec.get("published")
                if basis:
                    try:
                        d = dt.date.fromisoformat(basis[:10])
                        rec["first_seen"] = min(d, today).isoformat()
                    except ValueError:
                        pass
            by_id[rec["id"]] = rec
            added += 1
        if rec.get("doi"):
            by_doi[rec["doi"]] = rec
        if rec.get("pmid"):
            by_pmid[rec["pmid"]] = rec
        by_title[norm_title(rec["title"])[:200]] = rec
    papers = list(by_id.values())
    papers.sort(key=lambda p: (p.get("first_seen") or "", p.get("published") or "", p["title"]), reverse=True)
    return papers, {"raw": len(raw), "groups": len(groups), "added": added, "updated": updated, "dropped_irrelevant": dropped, "total": len(papers)}


def update_news(existing: list[dict], raw: list[dict], tax: Taxonomy, today: dt.date, max_per_source_day: int, keep_days: int = 400) -> tuple[list[dict], dict]:
    by_id = {n["id"]: n for n in existing}
    seen_titles = {norm_title(n["title"])[:120] for n in existing}
    added = dropped = 0
    cutoff = (today - dt.timedelta(days=keep_days)).isoformat()
    for item in raw:
        if item["id"] in by_id:
            continue
        nt = norm_title(item["title"])[:120]
        if nt in seen_titles:
            continue
        text = f"{item['title']} {item.get('summary', '')}"
        if not tax.news_keep(text):
            dropped += 1
            continue
        cats, primary = tax.news_categorize(text, item.get("kind", "press"))
        item = dict(item, categories=cats, primary=primary, first_seen=today.isoformat())
        if not item.get("published"):
            item["published"] = today.isoformat()
        by_id[item["id"]] = item
        seen_titles.add(nt)
        added += 1
    news = [n for n in by_id.values() if (n.get("published") or "") >= cutoff]
    news.sort(key=lambda n: (n.get("published") or "", n.get("first_seen") or ""), reverse=True)
    # Per-source-per-day cap (keeps the first N seen).
    counts: dict[tuple[str, str], int] = {}
    capped = []
    for n in news:
        k = (n.get("feed_id", ""), (n.get("published") or "")[:10])
        counts[k] = counts.get(k, 0) + 1
        if counts[k] <= max_per_source_day:
            capped.append(n)
    return capped, {"raw": len(raw), "added": added, "dropped_irrelevant": dropped, "total": len(capped)}
