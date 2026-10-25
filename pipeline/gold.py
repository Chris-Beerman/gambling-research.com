"""The hand-checked set: studies whose correct tags were decided by a person,
in tests/gold/labels.yml. It is the yardstick for every change to the rules.

    python -m pipeline.gold check            # score data/papers.json against the labels; exit 1 below the thresholds
    python -m pipeline.gold review OUT.json  # re-read the candidates and write what the rules see (needs network)

The check runs in the nightly workflow after the fetch: if a rule change makes
the index worse on the hand-checked set, nothing is committed or published.
No abstracts are stored in the repository; the labels hold only the answers.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import yaml

from .common import DATA_DIR, ROOT, load_json, load_yaml, session, today_utc
from .normalize import Taxonomy, canonical, merge_raw

GOLD_DIR = ROOT / "tests" / "gold"


def load_labels() -> dict:
    path = GOLD_DIR / "labels.yml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def score(papers: list[dict], labels: dict) -> dict:
    by_doi = {p["doi"]: p for p in papers if p.get("doi")}
    studies = labels.get("studies") or {}
    res = {k: {"n": 0, "ok": 0, "misses": []} for k in ("keep", "designs", "settings", "topics")}
    rules_only = {k: {"n": 0, "ok": 0} for k in ("designs", "settings", "topics")}

    def tally(kind: str, ok: bool, doi: str, detail: str, corrected: bool):
        res[kind]["n"] += 1
        res[kind]["ok"] += int(ok)
        if not ok:
            res[kind]["misses"].append(f"{doi}: {detail}")
        if kind in rules_only and not corrected:
            rules_only[kind]["n"] += 1
            rules_only[kind]["ok"] += int(ok)

    for doi, lab in studies.items():
        doi = str(doi).lower()
        p = by_doi.get(doi)
        in_main = p is not None and p.get("relevance") == "high"
        keep = lab.get("keep", True)
        tally("keep", in_main == keep, doi, f"expected {'in' if keep else 'out of'} the main index, found {'in' if in_main else 'out'}", False)
        if not (keep and in_main):
            continue
        corrected = bool(p.get("corrected"))
        if "designs" in lab:
            want, got = set(lab["designs"] or []), set(p.get("designs") or [])
            tally("designs", want == got, doi, f"designs {sorted(got)} != {sorted(want)}", corrected)
        if "settings" in lab:
            want, got = set(lab["settings"] or []), set(p.get("settings") or [])
            tally("settings", want == got, doi, f"settings {sorted(got)} != {sorted(want)}", corrected)
        if "topics" in lab or "not_topics" in lab:
            got = set(p.get("topics") or [])
            missing = set(lab.get("topics") or []) - got
            wrong = set(lab.get("not_topics") or []) & got
            tally("topics", not missing and not wrong, doi, f"topics missing {sorted(missing)}, wrongly present {sorted(wrong)}", corrected)
    out = {}
    for k, v in res.items():
        out[k] = {"n": v["n"], "accuracy": round(v["ok"] / v["n"], 3) if v["n"] else None, "misses": v["misses"]}
    out["rules_only"] = {k: {"n": v["n"], "accuracy": round(v["ok"] / v["n"], 3) if v["n"] else None} for k, v in rules_only.items()}
    return out


def check() -> int:
    labels = load_labels()
    if not labels.get("studies"):
        print("gold: no labels yet", file=sys.stderr)
        return 0
    papers = load_json(DATA_DIR / "papers.json", [])
    result = score(papers, labels)
    thresholds = labels.get("thresholds") or {}
    failed = []
    for k in ("keep", "designs", "settings", "topics"):
        r = result[k]
        line = f"{k:9s} {r['accuracy'] if r['accuracy'] is not None else '-':>6} on {r['n']} studies"
        ro = result["rules_only"].get(k)
        if ro and ro["n"]:
            line += f"   (rules alone, without hand corrections: {ro['accuracy']} on {ro['n']})"
        print(line)
        for m in r["misses"]:
            print(f"    miss  {m}")
        t = thresholds.get(k)
        if t is not None and r["accuracy"] is not None and r["accuracy"] < float(t):
            failed.append(f"{k} {r['accuracy']} < {t}")
    report = dict(result, checked=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), thresholds=thresholds, passed=not failed)
    with open(DATA_DIR / "gold_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
        f.write("\n")
    if failed:
        print("gold check FAILED: " + "; ".join(failed), file=sys.stderr)
        return 1
    print("gold check passed", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- review
_SENT = re.compile(r"(?<=[.!?])\s+")
_METHOD_CUES = re.compile(r"\b(method|we |participants|sample|data|interview|survey|trial|randomi|register|regist|cohort|review|search|databases|recruited|analys|design|protocol|cross.sectional|longitudinal|experiment|qualitative|records|conducted)", re.I)


def excerpts(abstract: str, n: int = 3, width: int = 220) -> list[str]:
    out = []
    for sent in _SENT.split(abstract or "")[1:]:
        if _METHOD_CUES.search(sent):
            out.append(sent[:width] + ("…" if len(sent) > width else ""))
        if len(out) >= n:
            break
    return out


def review(out_path: str) -> int:
    from .sources import crossref, openalex, pubmed

    sources_cfg = load_yaml("sources.yml")
    tax = Taxonomy(load_yaml("taxonomy.yml"))
    s = session()
    dois = [ln.strip().lower() for ln in (GOLD_DIR / "candidates.txt").read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    papers = load_json(DATA_DIR / "papers.json", [])
    by_doi = {p["doi"]: p for p in papers if p.get("doi")}
    raw = openalex.fetch_dois(s, sources_cfg["openalex"], dois)
    pmids = [by_doi[d]["pmid"] for d in dois if d in by_doi and by_doi[d].get("pmid")]
    raw += pubmed.fetch_ids(s, pmids)
    got = {r["doi"] for r in raw if r.get("doi")}
    raw += crossref.fetch_dois(s, sources_cfg["crossref"], [d for d in dois if d not in got])
    groups = merge_raw(raw)
    rows = []
    for key, g in groups.items():
        doi = next((r["doi"] for r in g["_recs"] if r.get("doi")), None)
        if doi not in dois:
            continue
        prev = by_doi.get(doi)
        rec = canonical(key, g, tax, today_utc(), prev)
        abstract = max((r.get("abstract") or "" for r in g["_recs"]), key=len)
        a = tax.assess_full(g["_recs"][0]["title"], abstract)
        rows.append({
            "doi": doi,
            "title": g["_recs"][0]["title"],
            "journal": next((r.get("journal") for r in g["_recs"] if r.get("journal")), ""),
            "sources_now": g["sources"],
            "sources_ever": sorted(set(g["sources"]) | set((prev or {}).get("sources") or [])),
            "pubtypes": next((r.get("pubtypes") for r in g["_recs"] if r.get("pubtypes")), []),
            "mesh": next((r.get("mesh") for r in g["_recs"] if r.get("mesh")), []),
            "author_countries": rec["countries"] if rec else None,
            "relevance": a.relevance, "title_hit": a.title_hit, "abstract_hits": a.abstract_hits, "first_hit": a.first_abstract_hit,
            "kept": rec is not None and rec.get("relevance") == "high",
            "topics": rec["topics"] if rec else None,
            "designs": rec["designs"] if rec else None,
            "settings": rec["settings"] if rec else None,
            "language": rec["language"] if rec else None,
            "summary": (rec or prev or {}).get("summary", ""),
            "method_sentences": excerpts(abstract),
        })
    missing = [d for d in dois if d not in {r["doi"] for r in rows}]
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "not_found": missing}, f, ensure_ascii=False, indent=1)
    print(f"review: {len(rows)} studies, {len(missing)} not found", file=sys.stderr)
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "check":
        return check()
    if len(sys.argv) >= 3 and sys.argv[1] == "review":
        return review(sys.argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
