"""Nightly fetch: pull every configured source, update data/papers.json and
data/news.json, record what happened in data/fetch_log.json.

    python -m pipeline.fetch            # normal nightly window
    python -m pipeline.fetch --backfill # first run / rebuild: wider window, first_seen from source dates
    python -m pipeline.fetch --only pubmed,news
"""
from __future__ import annotations

import argparse
import sys
import traceback

from .candidates import write_candidates
from .common import DATA_DIR, load_json, load_yaml, now_utc_iso, save_json, session, today_utc
from .normalize import Taxonomy, update_index, update_news
from .sources import crossref, feeds, openalex, pubmed


def run(backfill: bool = False, only: set[str] | None = None) -> int:
    sources_cfg = load_yaml("sources.yml")
    tax = Taxonomy(load_yaml("taxonomy.yml"))
    today = today_utc()
    papers = load_json(DATA_DIR / "papers.json", [])
    news = load_json(DATA_DIR / "news.json", [])
    if not papers:
        backfill = True
    s = session()
    log = {"started": now_utc_iso(), "mode": "backfill" if backfill else "nightly", "sources": []}
    raw_papers: list[dict] = []
    raw_news: list[dict] = []

    def want(name: str) -> bool:
        return not only or name in only

    def record(name: str, kind: str, fn):
        entry = {"id": name, "kind": kind, "ok": False, "items": 0, "error": None, "warning": None}
        warnings: list[str] = []
        try:
            items = fn(warnings) if name == "crossref" else fn()
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

    print(f"fetch ({log['mode']})", file=sys.stderr)
    if want("pubmed") and sources_cfg.get("pubmed", {}).get("enabled"):
        cfg = sources_cfg["pubmed"]
        raw_papers += record("pubmed", "papers", lambda: pubmed.fetch(s, cfg, cfg["backfill_days"] if backfill else cfg["days"]))
    if want("openalex") and sources_cfg.get("openalex", {}).get("enabled"):
        cfg = sources_cfg["openalex"]
        raw_papers += record("openalex", "papers", lambda: openalex.fetch(s, cfg, cfg["backfill_days"] if backfill else cfg["days"]))
    if want("crossref") and sources_cfg.get("crossref", {}).get("enabled"):
        cfg = sources_cfg["crossref"]
        raw_papers += record("crossref", "papers", lambda w: crossref.fetch(s, cfg, cfg["backfill_days"] if backfill else cfg["days"], w))
    if want("journals"):
        for feed in sources_cfg.get("journal_feeds", []):
            if feed.get("enabled", True):
                raw_papers += record(f"feed:{feed['id']}", "papers", lambda f=feed: feeds.fetch_journal_feed(s, f))
    if want("news"):
        for feed in sources_cfg.get("news_feeds", []):
            if feed.get("enabled", True):
                raw_news += record(f"news:{feed['id']}", "news", lambda f=feed: feeds.fetch_news_feed(s, f))

    papers, pstats = update_index(papers, raw_papers, tax, today, backfill)
    news, nstats = update_news(news, raw_news, tax, today, int(sources_cfg.get("news_max_per_source_per_day", 10)))
    log["papers"] = pstats
    log["news"] = nstats
    log["finished"] = now_utc_iso()
    log["papers_total"] = len(papers)
    log["news_total"] = len(news)
    # Keep a short history of runs for the methodology page.
    history = load_json(DATA_DIR / "fetch_log.json", {}).get("history", [])
    history = ([{"finished": log["finished"], "mode": log["mode"], "added": pstats["added"], "news_added": nstats["added"], "failed": sum(1 for e in log["sources"] if not e["ok"])}] + history)[:30]
    log["history"] = history
    save_json(DATA_DIR / "papers.json", papers)
    save_json(DATA_DIR / "news.json", news)
    save_json(DATA_DIR / "fetch_log.json", log)
    write_candidates(papers, news, today)
    print(f"papers: {pstats}\nnews: {nstats}", file=sys.stderr)
    failed = [e["id"] for e in log["sources"] if not e["ok"]]
    if failed:
        print(f"failed sources: {', '.join(failed)}", file=sys.stderr)
    # Fail the run only if nothing at all could be fetched.
    return 0 if any(e["ok"] for e in log["sources"]) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated: pubmed,openalex,crossref,journals,news")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()} or None
    return run(backfill=args.backfill, only=only)


if __name__ == "__main__":
    sys.exit(main())
