"""Nightly fetch: pull every configured source, update data/papers.json,
data/news.json, data/trials.json, data/bills.json and data/cases.json, and
record what happened in data/fetch_log.json.

    python -m pipeline.fetch            # normal nightly window
    python -m pipeline.fetch --backfill # first run / rebuild: wider window, first_seen from source dates
    python -m pipeline.fetch --only pubmed,news
    python -m pipeline.fetch --only trials,bills,courts
    python -m pipeline.fetch --rebuild  # re-read the literature from `backfill_from` and re-tag everything

A rebuild also starts on its own when the rules version in config/taxonomy.yml
or `backfill_from` in config/sources.yml differs from what data/index_meta.json
records about the last rebuild.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import traceback

from .candidates import write_candidates
from .common import DATA_DIR, load_json, load_yaml, now_utc_iso, save_json, session, today_utc
from .normalize import Taxonomy, update_index, update_news
from .sources import bills as bills_src
from .sources import courts as courts_src
from .sources import crossref, feeds, openalex, pubmed
from .sources import trials as trials_src
from .trackers import update_bills, update_cases, update_trials


def months(start: dt.date, end: dt.date):
    """(first day, last day) of each calendar month from start to end, newest first."""
    out = []
    cur = dt.date(start.year, start.month, 1)
    while cur <= end:
        nxt = dt.date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        out.append((max(cur, start), min(nxt - dt.timedelta(days=1), end)))
        cur = nxt
    return list(reversed(out))


def by_month(fn, start: dt.date, end: dt.date, warnings: list[str]) -> list[dict]:
    """Run a date-range fetch a month at a time; a failed month is a warning, not a lost source."""
    out: list[dict] = []
    for a, b in months(start, end):
        try:
            out += fn(a, b)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{a:%Y-%m}: {type(e).__name__}: {str(e)[:120]}")
            print(f"    {a:%Y-%m}: FAILED {e}", file=sys.stderr)
    return out


def rebuild_needed(meta: dict, tax: Taxonomy, sources_cfg: dict) -> str | None:
    want_from = str(sources_cfg.get("backfill_from") or "")
    if meta.get("rules_version") != tax.version:
        return f"rules version {meta.get('rules_version')} -> {tax.version}"
    if want_from and (meta.get("coverage_from") or "9999") > want_from:
        return f"coverage from {meta.get('coverage_from')} -> {want_from}"
    return None


def run(backfill: bool = False, only: set[str] | None = None, rebuild: bool = False) -> int:
    sources_cfg = load_yaml("sources.yml")
    tax = Taxonomy(load_yaml("taxonomy.yml"))
    today = today_utc()
    meta = load_json(DATA_DIR / "index_meta.json", {})
    papers = load_json(DATA_DIR / "papers.json", [])
    if not rebuild and not only:
        why = rebuild_needed(meta, tax, sources_cfg)
        if why:
            print(f"rebuild: {why}", file=sys.stderr)
            rebuild = True
    rebuild_from = dt.date.fromisoformat(str(sources_cfg.get("backfill_from") or (today - dt.timedelta(days=365)).isoformat()))
    news = load_json(DATA_DIR / "news.json", [])
    trials = load_json(DATA_DIR / "trials.json", [])
    bills = load_json(DATA_DIR / "bills.json", [])
    cases = load_json(DATA_DIR / "cases.json", [])
    if not papers:
        backfill = True
    # A tracker with no data yet backfills on its first run whatever the mode.
    bf_trials, bf_bills, bf_cases = backfill or not trials, backfill or not bills, backfill or not cases
    s = session()
    log = {"started": now_utc_iso(), "mode": "rebuild" if rebuild else "backfill" if backfill else "nightly", "sources": []}
    raw_papers: list[dict] = []
    raw_news: list[dict] = []
    raw_trials: list[dict] = []
    raw_bills: list[dict] = []
    raw_cases: list[dict] = []

    def want(name: str) -> bool:
        return not only or name in only

    def record(name: str, kind: str, fn, with_warnings: bool = False):
        entry = {"id": name, "kind": kind, "ok": False, "items": 0, "error": None, "warning": None}
        warnings: list[str] = []
        try:
            items = fn(warnings) if with_warnings else fn()
            entry["ok"] = True
            entry["items"] = len(items)
            if warnings:
                entry["warning"] = "; ".join(warnings)[:400]
            print(f"  {name}: {len(items)} items" + (f" (warnings: {entry['warning']})" if warnings else ""), file=sys.stderr)
            return items
        except Exception as e:  # noqa: BLE001
            entry["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            print(f"  {name}: FAILED {entry['error']}", file=sys.stderr)
            traceback.print_exc(limit=2)
            return []
        finally:
            log["sources"].append(entry)

    def window(cfg: dict, bf: bool, default_days: int = 7, default_backfill: int = 365) -> int:
        return int(cfg.get("backfill_days", default_backfill)) if bf else int(cfg.get("days", default_days))

    print(f"fetch ({log['mode']})", file=sys.stderr)
    core_complete = True  # every core source returned its whole window (a rebuild may then remove studies)

    def core(name: str, nightly_fn, range_fn):
        nonlocal core_complete
        if rebuild:
            items = record(name, "papers", lambda w: by_month(range_fn, rebuild_from, today, w), with_warnings=True)
        else:
            items = record(name, "papers", nightly_fn)
        entry = log["sources"][-1]
        if not entry["ok"] or entry["warning"]:
            core_complete = False
        return items

    if want("pubmed") and sources_cfg.get("pubmed", {}).get("enabled"):
        cfg = sources_cfg["pubmed"]
        raw_papers += core("pubmed", lambda: pubmed.fetch(s, cfg, cfg["backfill_days"] if backfill else cfg["days"]), lambda a, b: pubmed.fetch_range(s, cfg, a, b))
    if want("openalex") and sources_cfg.get("openalex", {}).get("enabled"):
        cfg = sources_cfg["openalex"]
        raw_papers += core("openalex", lambda: openalex.fetch(s, cfg, cfg["backfill_days"] if backfill else cfg["days"]), lambda a, b: openalex.fetch_range(s, cfg, a, b))
    if want("crossref") and sources_cfg.get("crossref", {}).get("enabled"):
        cfg = sources_cfg["crossref"]
        if rebuild:
            raw_papers += record("crossref", "papers", lambda w: crossref.fetch_range(s, cfg, rebuild_from, today, w), with_warnings=True)
        else:
            raw_papers += record("crossref", "papers", lambda w: crossref.fetch(s, cfg, cfg["backfill_days"] if backfill else cfg["days"], w), with_warnings=True)
        if not log["sources"][-1]["ok"]:
            core_complete = False
    if rebuild:
        # Studies already in the index that the searches did not return again
        # (published before backfill_from, found through a feed, or since edited)
        # are re-read by identifier so the new rules see their full abstracts.
        got_doi = {r["doi"] for r in raw_papers if r.get("doi")}
        got_pmid = {r["pmid"] for r in raw_papers if r.get("pmid")}
        missing = [p for p in papers if not ((p.get("doi") and p["doi"] in got_doi) or (p.get("pmid") and p["pmid"] in got_pmid))]
        pmids = [p["pmid"] for p in missing if p.get("pmid")]
        dois = [p["doi"] for p in missing if p.get("doi")]
        if pmids and sources_cfg.get("pubmed", {}).get("enabled"):
            raw_papers += record("pubmed:by-id", "papers", lambda: pubmed.fetch_ids(s, pmids))
        if dois and sources_cfg.get("openalex", {}).get("enabled"):
            raw_papers += record("openalex:by-doi", "papers", lambda: openalex.fetch_dois(s, sources_cfg["openalex"], dois))
            got_doi = {r["doi"] for r in raw_papers if r.get("doi")}
        rest = [d for d in dois if d not in got_doi][:400]
        if rest and sources_cfg.get("crossref", {}).get("enabled"):
            raw_papers += record("crossref:by-doi", "papers", lambda w: crossref.fetch_dois(s, sources_cfg["crossref"], rest, w), with_warnings=True)
        for e in log["sources"]:
            if e["id"].endswith(("by-id", "by-doi")) and not e["ok"]:
                core_complete = False
    if want("journals"):
        for feed in sources_cfg.get("journal_feeds", []):
            if feed.get("enabled", True):
                raw_papers += record(f"feed:{feed['id']}", "papers", lambda f=feed: feeds.fetch_journal_feed(s, f))
    if want("news"):
        for feed in sources_cfg.get("news_feeds", []):
            if feed.get("enabled", True):
                raw_news += record(f"news:{feed['id']}", "news", lambda f=feed: feeds.fetch_news_feed(s, f))

    tcfg = sources_cfg.get("trials", {})
    refreshed: set[str] = set()  # registries fetched in full this run

    def full(name: str):
        """Mark a registry as fully refreshed when its fetch succeeded without warnings."""
        entry = log["sources"][-1]
        if entry["id"] == f"trials:{name}" and entry["ok"] and not entry["warning"]:
            refreshed.add(name)

    if want("trials"):
        if tcfg.get("clinicaltrials", {}).get("enabled"):
            raw_trials += record("trials:clinicaltrials", "trials", lambda w: trials_src.fetch_clinicaltrials(s, tcfg["clinicaltrials"], w), with_warnings=True)
            full("clinicaltrials")
        if tcfg.get("isrctn", {}).get("enabled"):
            raw_trials += record("trials:isrctn", "trials", lambda: trials_src.fetch_isrctn(s, tcfg["isrctn"]))
            full("isrctn")
        if tcfg.get("osf", {}).get("enabled"):
            raw_trials += record("trials:osf", "trials", lambda w: trials_src.fetch_osf(s, tcfg["osf"], w), with_warnings=True)
            full("osf")
    bcfg = sources_cfg.get("bills", {})
    if want("bills"):
        if bcfg.get("openstates", {}).get("enabled"):
            cfg = dict(bcfg["openstates"])
            if bf_bills and cfg.get("backfill_max_pages"):
                cfg["max_pages"] = cfg["backfill_max_pages"]
            raw_bills += record("bills:openstates", "bills", lambda w, cfg=cfg: bills_src.fetch_openstates(s, cfg, window(cfg, bf_bills), w), with_warnings=True)
        if bcfg.get("congress", {}).get("enabled"):
            cfg = bcfg["congress"]
            raw_bills += record("bills:congress", "bills", lambda w: bills_src.fetch_congress(s, cfg, window(cfg, bf_bills), tax.bills_include, bills, w), with_warnings=True)
    ccfg = sources_cfg.get("courts", {})
    if want("courts") and ccfg.get("courtlistener", {}).get("enabled"):
        cfg = dict(ccfg["courtlistener"])
        if bf_cases and cfg.get("backfill_max_pages"):
            cfg["max_pages"] = cfg["backfill_max_pages"]
        raw_cases += record("courts:courtlistener", "cases", lambda w, cfg=cfg: courts_src.fetch_courtlistener(s, cfg, window(cfg, bf_cases, 7, 180), w), with_warnings=True)

    # A rebuild that could not read every source re-tags what it got but removes
    # nothing it did not see; the next night tries again.
    full_rebuild = rebuild and core_complete
    papers, pstats = update_index(papers, raw_papers, tax, today, backfill or rebuild, rebuild=full_rebuild)
    if full_rebuild:
        meta = {"rules_version": tax.version, "coverage_from": rebuild_from.isoformat(), "rebuilt": now_utc_iso()}
        save_json(DATA_DIR / "index_meta.json", meta)
    elif rebuild:
        print("rebuild incomplete: a core source failed or missed a month; studies were re-tagged but none removed", file=sys.stderr)
    log["rebuild"] = {"requested": rebuild, "complete": full_rebuild} if rebuild else None
    news, nstats = update_news(news, raw_news, tax, today, int(sources_cfg.get("news_max_per_source_per_day", 10)))
    trials, tstats = update_trials(trials, raw_trials, tax, today, bf_trials, refreshed)
    bills, bstats = update_bills(bills, raw_bills, tax, today, bf_bills)
    cases, cstats = update_cases(cases, raw_cases, tax, today, bf_cases)
    log["papers"] = pstats
    log["news"] = nstats
    log["trials"] = tstats
    log["bills"] = bstats
    log["cases"] = cstats
    log["finished"] = now_utc_iso()
    log["papers_total"] = len(papers)
    log["news_total"] = len(news)
    # Keep a short history of runs for the methodology page.
    history = load_json(DATA_DIR / "fetch_log.json", {}).get("history", [])
    history = (
        [
            {
                "finished": log["finished"], "mode": log["mode"], "added": pstats["added"], "news_added": nstats["added"],
                "trials_added": tstats["added"], "bills_added": bstats["added"], "cases_added": cstats["added"],
                "failed": sum(1 for e in log["sources"] if not e["ok"]),
            }
        ]
        + history
    )[:30]
    log["history"] = history
    save_json(DATA_DIR / "papers.json", papers)
    save_json(DATA_DIR / "news.json", news)
    save_json(DATA_DIR / "trials.json", trials)
    save_json(DATA_DIR / "bills.json", bills)
    save_json(DATA_DIR / "cases.json", cases)
    save_json(DATA_DIR / "fetch_log.json", log)
    write_candidates(papers, news, today, trials=trials, bills=bills, cases=cases)
    print(f"papers: {pstats}\nnews: {nstats}\ntrials: {tstats}\nbills: {bstats}\ncases: {cstats}", file=sys.stderr)
    failed = [e["id"] for e in log["sources"] if not e["ok"]]
    if failed:
        print(f"failed sources: {', '.join(failed)}", file=sys.stderr)
    # Fail the run only if nothing at all could be fetched.
    return 0 if any(e["ok"] for e in log["sources"]) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--rebuild", action="store_true", help="re-read every study from backfill_from and re-apply the rules")
    ap.add_argument("--only", default="", help="comma-separated: pubmed,openalex,crossref,journals,news,trials,bills,courts")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()} or None
    return run(backfill=args.backfill, only=only, rebuild=args.rebuild)


if __name__ == "__main__":
    sys.exit(main())
