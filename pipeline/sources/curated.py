"""Hand-curated records: content/curated.yml.

The nightly sources miss some things the index should carry, chiefly preprints
on servers the automatic queries do not cover (PsyArXiv, OSF Preprints, SSRN)
and, by policy, the editor's own studies, which are listed under the same rules
as every other paper and labelled as the editor's. Each entry here becomes a
raw record with source "curated"; it merges with records from the automatic
sources by DOI or title, and its hand-checked fields take priority.

content/curated.yml:

    records:
      - doi: 10.31234/osf.io/xxxxx        # or url: when there is no DOI
        title: Do losses stop mattering as betting escalates? ...
        authors: [Chris Beerman]
        journal: PsyArXiv                 # venue or server as it should display
        published: 2026-11-06
        type: preprint                    # preprint | article | letter | ...
        abstract: >
          Two or three sentences; the summary shown is cut from this.
        oa_url: https://osf.io/preprints/psyarxiv/xxxxx_v1   # free full text
        editor_authored: true             # shows the "by the editor" label
        note: Submitted to the Journal of Gambling Studies.  # optional, shown after the authors
        topics: [prediction-markets]      # optional: added to the rule-based topic tags
        designs: [behavioral-data]        # optional: replaces the rule-based design tags
        draft: true                       # optional: keep out of the index until removed

An entry with `draft: true`, or without both a title and a DOI or URL, is
skipped and reported as a warning.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..common import CONTENT_DIR, clean_text, norm_doi

CURATED_PATH = CONTENT_DIR / "curated.yml"


def load(path: Path = CURATED_PATH, warnings: list[str] | None = None) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    out: list[dict] = []
    for i, e in enumerate(cfg.get("records") or []):
        if not isinstance(e, dict):
            continue
        if e.get("draft"):
            continue
        title = clean_text(e.get("title") or "").rstrip(".")
        doi = norm_doi(e.get("doi"))
        url = (e.get("url") or "").strip() or (f"https://doi.org/{doi}" if doi else None)
        if not title or not url:
            if warnings is not None:
                warnings.append(f"curated record {i + 1} skipped: needs a title and a doi or url")
            continue
        authors = e.get("authors") or []
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(";") if a.strip()]
        out.append(
            {
                "source": "curated",
                "doi": doi,
                "pmid": str(e["pmid"]) if e.get("pmid") else None,
                "pmcid": e.get("pmcid"),
                "openalex": e.get("openalex"),
                "title": title,
                "journal": clean_text(e.get("journal") or e.get("venue") or ""),
                "issn": [],
                "authors": [clean_text(a) for a in authors],
                "affiliations": [],
                "countries": list(e.get("countries") or []),
                "published": str(e["published"])[:10] if e.get("published") else None,
                "created": str(e.get("created") or e.get("published") or "")[:10] or None,
                "abstract": clean_text(e.get("abstract") or ""),
                "url": url,
                "oa_url": e.get("oa_url"),
                "type": e.get("type") or "article",
                "language": e.get("language") or "en",
                "retracted": bool(e.get("retracted")),
                "editor_authored": bool(e.get("editor_authored")),
                "note": clean_text(e.get("note") or "") or None,
                "topics": list(e.get("topics") or []),
                "designs": list(e.get("designs") or []),
            }
        )
    return out
