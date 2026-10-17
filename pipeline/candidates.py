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


def write_candidates(papers: list[dict], news: list[dict], today: dt.date, days: int = 7, trials: list[dict] | None = None, bills: list[dict] | None = None, cases: list[dict] | None = None) -> dict:
    site = load_yaml("site.yml")
    core = {j.lower() for j in site.get("core_journals", [])}
    since = (today - dt.timedelta(days=days)).isoformat()
    # Trackers: what changed this week, for the digest's policy and trials notes.
    wk_trials = [t for t in (trials or []) if (t.get("first_seen") or "") >= since or (t.get("status_changed") or "") >= since]
    wk_bills = [b for b in (bills or []) if (b.get("latest_action_date") or "") >= since]
    stage_order = {"enacted": 0, "vetoed": 1, "passed-both": 2, "passed-one": 3, "reported": 4}
    wk_bills.sort(key=lambda b: (stage_order.get(b.get("stage"), 9), b.get("latest_action_date") or ""), reverse=False)
    wk_cases = [c for c in (cases or []) if (c.get("latest_activity") or "") >= since]
    level_order = {"scotus": 0, "federal-appellate": 1, "state-supreme": 2, "federal-district": 3, "state-appellate": 4}
    wk_cases.sort(key=lambda c: (level_order.get(c.get("court_level"), 9), c.get("latest_activity") or ""))
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
        "trials": [{k: t.get(k) for k in ("id", "registry_label", "kind", "title", "status", "previous_status", "status_changed", "sponsor", "country_names", "start_date", "completion_date", "enrollment", "results_posted", "summary", "url", "first_seen")} for t in wk_trials[:30]],
        "bills": [{k: b.get(k) for k in ("id", "jurisdiction", "identifier", "title", "stage", "previous_stage", "latest_action_date", "latest_action", "url", "topics")} for b in wk_bills[:60]],
        "cases": [{k: c.get(k) for k in ("id", "kind", "case_name", "court", "court_level", "date_filed", "latest_activity", "citation", "snippet", "documents", "url")} for c in wk_cases[:40]],
    }
    save_json(DATA_DIR / "weekly" / "latest.json", out)
    if today.weekday() == 0:  # keep a dated copy each Monday
        save_json(DATA_DIR / "weekly" / f"{today.isoformat()}.json", out)
    return out
