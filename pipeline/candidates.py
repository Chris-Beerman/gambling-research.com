"""Weekly digest candidates: a ranked shortlist of the past seven days, written
to data/weekly/latest.json for whoever drafts the digest (person or scheduled
task). Ranking is a transparent heuristic, not a judgment of quality."""
from __future__ import annotations

import datetime as dt

from .common import DATA_DIR, load_yaml, save_json


def score(p: dict, core: set[str]) -> tuple[int, list[str]]:
    s, why = 0, []
    if (p.get("journal") or "").lower() in core:
        s += 3
        why.append("core journal")
    d = set(p.get("designs") or [])
    if "trial" in d:
        s += 3
        why.append("trial")
    if "review" in d:
        s += 2
        why.append("review")
    if "behavioral-data" in d or "longitudinal" in d:
        s += 1
        why.append("longitudinal or behavioral data")
    if p.get("oa_url"):
        s += 1
        why.append("free full text")
    if "us" in (p.get("regions") or []):
        s += 1
        why.append("US")
    t = set(p.get("topics") or [])
    if t & {"sports-betting", "prediction-markets", "self-exclusion", "advertising", "treatment", "policy"}:
        s += 1
        why.append("priority topic")
    if "commentary" in d and "trial" not in d:
        s -= 1
    if p.get("relevance") == "low":
        s -= 3
    if p.get("retracted"):
        s -= 10
    return s, why


def write_candidates(papers: list[dict], news: list[dict], today: dt.date, days: int = 7) -> dict:
    site = load_yaml("site.yml")
    core = {j.lower() for j in site.get("core_journals", [])}
    since = (today - dt.timedelta(days=days)).isoformat()
    week = [p for p in papers if (p.get("first_seen") or "") >= since and p.get("relevance") == "high"]
    ranked = []
    for p in week:
        s, why = score(p, core)
        ranked.append(dict(p, score=s, why=why))
    ranked.sort(key=lambda p: (-p["score"], p.get("first_seen") or "", p["title"]))
    top = ranked[:40]
    wk_news = [n for n in news if (n.get("published") or "") >= since and n.get("primary") in ("public-health", "regulation", "prediction-markets", "research")]
    out = {
        "generated": today.isoformat(),
        "window": {"from": since, "to": today.isoformat()},
        "new_studies": len(week),
        "candidates": [
            {k: p.get(k) for k in ("id", "title", "journal", "authors", "published", "first_seen", "summary", "url", "oa_url", "topics", "designs", "regions", "score", "why")}
            for p in top
        ],
        "news": [{k: n.get(k) for k in ("title", "url", "source", "published", "primary", "summary")} for n in wk_news[:60]],
    }
    save_json(DATA_DIR / "weekly" / "latest.json", out)
    if today.weekday() == 0:  # keep a dated copy each Monday
        save_json(DATA_DIR / "weekly" / f"{today.isoformat()}.json", out)
    return out
