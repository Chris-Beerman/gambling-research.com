"""Render the static site from data/ and content/ into _site/.

    python -m pipeline.build
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .common import CONTENT_DIR, DATA_DIR, ROOT, SITE_DIR, STATIC_DIR, TEMPLATE_DIR, load_json, load_yaml, today_utc
from . import countries
from .normalize import Taxonomy, apply_corrections
from .sources.trials import STATUSES
from .trackers import COURT_LEVELS, STAGES, STAGE_RANK

MD_EXT = ["tables", "attr_list", "footnotes", "sane_lists", "md_in_html", "toc"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


# ---------------------------------------------------------------- helpers
def d(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def fmt_date(s, style="medium"):
    x = d(s) if isinstance(s, str) else s
    if not x:
        return ""
    if style == "short":
        return f"{MONTHS[x.month - 1][:3]} {x.day}"
    if style == "long":
        return f"{MONTHS[x.month - 1]} {x.day}, {x.year}"
    if style == "month":
        return f"{MONTHS[x.month - 1]} {x.year}"
    return f"{MONTHS[x.month - 1][:3]} {x.day}, {x.year}"


def rfc822(s, hour: int = 12) -> str:
    x = d(s) if isinstance(s, str) else s
    if not x:
        return ""
    t = dt.datetime(x.year, x.month, x.day, hour, 0, 0, tzinfo=dt.timezone.utc)
    return t.strftime("%a, %d %b %Y %H:%M:%S +0000")


def fmt_time_utc(iso_ts: str | None) -> str:
    if not iso_ts:
        return ""
    try:
        t = dt.datetime.fromisoformat(iso_ts)
    except ValueError:
        return ""
    return f"{fmt_date(t.date())}, {t:%H:%M} UTC"


def family(name: str) -> str:
    name = name.strip()
    if "," in name:
        return name.split(",")[0].strip()
    parts = name.split()
    if not parts:
        return name
    # keep particles: "van der Berg", "de Souza"
    i = len(parts) - 1
    while i > 0 and parts[i - 1].lower() in ("van", "der", "de", "da", "di", "del", "della", "von", "la", "le", "du", "dos", "das", "bin", "al"):
        i -= 1
    return " ".join(parts[i:])


def authors_line(authors: list[str], limit: int = 3) -> str:
    fams = [family(a) for a in authors if a]
    if not fams:
        return ""
    if len(fams) <= limit:
        return ", ".join(fams[:-1]) + (" and " + fams[-1] if len(fams) > 1 else fams[0])
    return ", ".join(fams[:limit]) + f" and {len(fams) - limit} more"


def monday_of(x: dt.date) -> dt.date:
    return x - dt.timedelta(days=x.weekday())


def read_markdown(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        meta = yaml.safe_load(m.group(1)) or {}
        text = text[m.end():]
    html = markdown.markdown(text, extensions=MD_EXT, output_format="html5")
    return meta, html


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


LANGUAGE_NAMES = {
    "en": "English", "fi": "Finnish", "sv": "Swedish", "no": "Norwegian", "da": "Danish", "is": "Icelandic", "de": "German", "fr": "French",
    "es": "Spanish", "pt": "Portuguese", "it": "Italian", "nl": "Dutch", "pl": "Polish", "cs": "Czech", "sk": "Slovak", "hu": "Hungarian",
    "ro": "Romanian", "bg": "Bulgarian", "hr": "Croatian", "sr": "Serbian", "sl": "Slovenian", "el": "Greek", "tr": "Turkish", "ru": "Russian",
    "uk": "Ukrainian", "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian", "ar": "Arabic", "fa": "Persian", "he": "Hebrew", "zh": "Chinese",
    "ja": "Japanese", "ko": "Korean", "th": "Thai", "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "ca": "Catalan",
}


def language_name(code: str | None) -> str:
    return LANGUAGE_NAMES.get(code or "", (code or "").upper())


_FOLD = str.maketrans({"ı": "i", "İ": "I", "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "þ": "th", "œ": "oe"})


def fold(text: str) -> str:
    """Accents off ("Kaymakçı" -> "Kaymakci", "Castrén" -> "Castren") so a search
    typed without them still matches."""
    t = unicodedata.normalize("NFKD", (text or "").translate(_FOLD))
    return "".join(ch for ch in t if not unicodedata.combining(ch))


def setting_names(codes: list[str]) -> list[str]:
    return [countries.COUNTRY_NAMES.get(c, c) for c in codes or []]


# ---------------------------------------------------------------- data exports
# Explicit, stable column order per tracker: analysts build scripts against
# these, so a column must not move or vanish because a field was empty in one
# night's data. List fields are joined with "; "; nested structures are counted
# rather than flattened (the JSON carries their detail).
CSV_COLUMNS: dict[str, list[str]] = {
    "papers": [
        "id", "doi", "pmid", "pmcid", "openalex", "title", "journal", "authors", "published", "year",
        "first_seen", "url", "oa_url", "type", "topics", "designs", "settings", "setting_regions",
        "countries", "regions", "language", "relevance", "retracted", "sources", "summary",
    ],
    "trials": [
        "id", "registry", "kind", "title", "status", "study_type", "phases", "enrollment", "conditions",
        "interventions", "sponsor", "sponsor_class", "collaborators", "countries", "regions",
        "start_date", "completion_date", "first_posted", "last_updated", "results_posted", "results_date",
        "registration_type", "topics", "designs", "first_seen", "url", "summary",
    ],
    "bills": [
        "id", "level", "jurisdiction", "jurisdiction_code", "session", "identifier", "congress",
        "bill_type", "number", "title", "classification", "subjects", "sponsors", "introduced",
        "latest_action_date", "latest_action", "latest_passage_date", "stage", "previous_stage",
        "stage_changed", "topics", "first_seen", "url", "source_url", "abstract",
    ],
    "cases": [
        "id", "kind", "case_name", "court", "court_id", "court_citation", "court_level", "date_filed",
        "date_terminated", "latest_activity", "docket_number", "citation", "status", "suit_nature",
        "cite_count", "documents_count", "topics", "first_seen", "url", "snippet",
    ],
}

# What each tracker is, for the Dataset markup and the citation line.
DATASETS: dict[str, dict] = {
    "papers": {
        "page": "/research/",
        "name": "Gambling research index: studies and preprints",
        "title": "Gambling studies and preprints",
        "description": (
            "Peer-reviewed studies and preprints on gambling, betting, lotteries, loot boxes and prediction "
            "markets, collected nightly from PubMed, OpenAlex, Crossref and journal feeds, and tagged by topic, "
            "study design and study setting. One row per study."
        ),
        "keywords": ["gambling", "problem gambling", "sports betting", "bibliometrics", "research index"],
        "cite_note": "Citing a finding? Cite the study itself, not this index. Cite the dataset when the index is what you used — its coverage, counts, tags or trends over time.",
        "sources": ["https://pubmed.ncbi.nlm.nih.gov/", "https://openalex.org/", "https://www.crossref.org/"],
        "spatial": "Worldwide",
    },
    "trials": {
        "page": "/trials/",
        "name": "Gambling clinical trials and preregistrations",
        "title": "Gambling trials and preregistrations",
        "description": (
            "Registered clinical trials and public preregistrations of studies on gambling and betting, from "
            "ClinicalTrials.gov, ISRCTN and OSF Registries, with recruitment status, sponsor, country and whether "
            "results have been posted. One row per registration."
        ),
        "keywords": ["gambling", "clinical trials", "preregistration", "problem gambling", "treatment"],
        "cite_note": "Referring to one trial? Cite its registry record. Cite the dataset when you use the compilation — how many trials are recruiting, what is being tested, how often results are posted.",
        "sources": ["https://clinicaltrials.gov/", "https://www.isrctn.com/", "https://osf.io/registries"],
        "spatial": "Worldwide",
    },
    "bills": {
        "page": "/bills/",
        "name": "US gambling legislation tracker",
        "title": "Gambling bills in state legislatures and Congress",
        "description": (
            "Bills on gambling, sports betting, lotteries, casinos, prediction markets and self-exclusion in the "
            "US state legislatures and Congress, with sponsor, subject, latest recorded action and derived "
            "legislative stage. One row per bill."
        ),
        "keywords": ["gambling legislation", "sports betting law", "state legislatures", "prediction markets", "self-exclusion"],
        "cite_note": "Referring to one bill? Cite the bill and its legislature. Cite the dataset when you use the compilation — counts by state, what passed, how a session moved.",
        "sources": ["https://openstates.org/", "https://www.govinfo.gov/", "https://www.congress.gov/"],
        "spatial": "United States",
    },
    "cases": {
        "page": "/courts/",
        "name": "Gambling court opinions and federal dockets",
        "title": "Gambling court rulings and dockets",
        "description": (
            "Court opinions and federal dockets involving gambling, sports betting, lotteries, tribal gaming, "
            "sweepstakes and event contracts, from CourtListener, with court, level, filing date and citation "
            "count. One row per opinion or docket."
        ),
        "keywords": ["gambling law", "court opinions", "tribal gaming", "event contracts", "sweepstakes"],
        "cite_note": "Referring to one ruling? Cite the opinion. Cite the dataset when you use the compilation — what is being litigated, where, and how often.",
        "sources": ["https://www.courtlistener.com/"],
        "spatial": "United States",
    },
}


def csv_cell(value) -> str:
    """One JSON value as one CSV cell."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "; ".join(csv_cell(v) for v in value if v not in (None, ""))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


# ---------------------------------------------------------------- build
class Builder:
    def __init__(self):
        self.site = load_yaml("site.yml")
        self.sources = load_yaml("sources.yml")
        self.tax = Taxonomy(load_yaml("taxonomy.yml"))
        self.today = today_utc()
        self.papers_all = load_json(DATA_DIR / "papers.json", [])
        self.news_all = load_json(DATA_DIR / "news.json", [])
        self.fetch_log = load_json(DATA_DIR / "fetch_log.json", {})
        self.trials_all = load_json(DATA_DIR / "trials.json", [])
        self.bills_all = load_json(DATA_DIR / "bills.json", [])
        self.cases_all = load_json(DATA_DIR / "cases.json", [])
        # Hand corrections take effect on the next build, not only on the next fetch.
        by_id = {p["id"]: p for p in self.papers_all}
        apply_corrections(by_id, self.tax)
        self.papers_all = list(by_id.values())
        self.fixture = False
        if not self.papers_all:
            fx = load_json(ROOT / "pipeline" / "fixtures" / "papers.json", [])
            if fx:
                self.papers_all, self.fixture = fx, True
        if not self.news_all and self.fixture:
            self.news_all = load_json(ROOT / "pipeline" / "fixtures" / "news.json", [])
        self.env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html", "xml"]), trim_blocks=True, lstrip_blocks=True)
        self.env.filters.update(
            {
                "fmt_date": fmt_date,
                "rfc822": rfc822,
                "authors_line": authors_line,
                "topic_label": self.tax.topic_label,
                "design_label": self.tax.design_label,
                "news_label": self.tax.news_label,
                "region_label": lambda s: self.tax.regions.get(s, {}).get("label", s),
                "slugify": slugify,
                "status_label": lambda s: STATUSES.get(s, s),
                "stage_label": lambda s: dict(STAGES).get(s, s),
                "level_label": lambda s: dict(COURT_LEVELS).get(s, s),
                "language_name": language_name,
                "setting_names": setting_names,
            }
        )
        self.urls: list[str] = []
        # Main navigation: href, label, kind (colour cue), and the path prefixes it covers.
        self.nav = [
            {"href": "/research/", "label": "Research", "kind": "research", "paths": ["/research/", "/trials/"]},
            {"href": "/news/", "label": "Policy", "kind": "news", "paths": ["/news/", "/bills/", "/courts/"]},
            {"href": "/digest/", "label": "Digest", "kind": "digest", "paths": ["/digest/"]},
            {"href": "/journals/", "label": "Reference", "kind": "reference", "paths": ["/journals/", "/conferences/", "/datasets/", "/measures/", "/guide/"]},
            {"href": "/search/", "label": "Search", "kind": "search", "paths": ["/search/"]},
        ]
        self.subnavs = {
            "research": [("/research/", "New studies"), ("/trials/", "Trials and preregistrations"), ("/research/topics/", "Topics"), ("/research/archive/", "Archive")],
            "policy": [("/news/", "News"), ("/bills/", "Bills"), ("/courts/", "Courts")],
        }

    # ---- exports, Dataset markup and citations ----
    def tracker_records(self, key: str) -> list[dict]:
        return {"papers": self.papers_all, "trials": self.trials_all, "bills": self.bills_all, "cases": self.cases_all}[key]

    def write_csv(self, key: str, records: list[dict]) -> None:
        """A CSV mirror of the tracker's JSON, at a stable URL beside it."""
        cols = CSV_COLUMNS[key]
        dest = SITE_DIR / "data" / f"{key}.csv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(cols)
            for rec in records:
                row = []
                for c in cols:
                    if c == "documents_count":
                        row.append(str(len(rec.get("documents") or [])))
                    else:
                        row.append(csv_cell(rec.get(c)))
                w.writerow(row)

    def coverage_span(self, key: str, records: list[dict]) -> str:
        """ISO 8601 open-ended interval covering the records actually present."""
        field = {"papers": "published", "trials": "first_posted", "bills": "introduced", "cases": "date_filed"}[key]
        if key == "papers" and self.coverage_from():
            start = self.coverage_from()
        else:
            dates = sorted(x for x in (r.get(field) or "" for r in records) if x)
            start = dates[0][:10] if dates else None
        return f"{start}/.." if start else ""

    def dataset_schema(self, key: str, records: list[dict]) -> dict:
        spec = DATASETS[key]
        base = self.site["url"]
        page = base + spec["page"]
        ed = self.site.get("editor", {})
        creator = {"@type": "Person", "@id": f"{base}/about/#editor", "name": ed.get("name"), "url": f"{base}/about/"}
        if ed.get("credentials"):
            creator["honorificSuffix"] = ed["credentials"]
        if ed.get("orcid"):
            creator["identifier"] = f"https://orcid.org/{ed['orcid']}"
            creator["sameAs"] = f"https://orcid.org/{ed['orcid']}"
        schema = {
            "@context": "https://schema.org",
            "@type": "Dataset",
            "@id": page + "#dataset",
            "name": spec["name"],
            "description": spec["description"],
            "url": page,
            "keywords": spec["keywords"],
            "license": "https://creativecommons.org/publicdomain/zero/1.0/",
            "isAccessibleForFree": True,
            "creator": creator,
            "publisher": {"@type": "Person", "@id": f"{base}/about/#editor", "name": ed.get("name")},
            "inLanguage": "en",
            "isBasedOn": spec["sources"],
            "variableMeasured": [c for c in CSV_COLUMNS[key]],
            "distribution": [
                {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{base}/data/{key}.json"},
                {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{base}/data/{key}.csv"},
            ],
            "includedInDataCatalog": {"@type": "DataCatalog", "name": self.site["title"], "url": base + "/"},
            "creativeWorkStatus": "Updated nightly",
        }
        span = self.coverage_span(key, records)
        if span:
            schema["temporalCoverage"] = span
        if spec.get("spatial"):
            schema["spatialCoverage"] = {"@type": "Place", "name": spec["spatial"]}
        modified = (self.fetch_log.get("finished") or "")[:10]
        if modified:
            schema["dateModified"] = modified
        return schema

    def as_of(self) -> str:
        """The date the data last changed, for the citation line."""
        stamp = (self.fetch_log.get("finished") or "")[:10]
        return stamp or self.today.isoformat()

    def cite_data(self, key: str) -> dict:
        """The suggested citation for a tracker page."""
        spec = DATASETS[key]
        base = self.site["url"]
        page = base + spec["page"]
        ed = self.site.get("editor", {})
        author = f"{family(ed.get('name', ''))}, {ed.get('name', ' ')[0]}." if ed.get("name") else ""
        as_of = self.as_of()
        text = (
            f"{author} ({as_of[:4]}). {spec['title']} [Data set]. {self.site['title']}. "
            f"Data as of {fmt_date(as_of, 'long')}. {page}"
        )
        return {
            "text": text,
            "licence": "CC0 1.0",
            "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "kind": "data",
            "json_url": f"/data/{key}.json",
            "csv_url": f"/data/{key}.csv",
            "as_of": as_of,
            "note": spec.get("cite_note", ""),
        }

    def cite_text(self, title: str, path: str, *, date: str | None = None, extra: str = "", date_label: str = "") -> dict:
        """The suggested citation for an editorial page or a digest issue."""
        base = self.site["url"]
        ed = self.site.get("editor", {})
        author = f"{family(ed.get('name', ''))}, {ed.get('name', ' ')[0]}." if ed.get("name") else ""
        stamp = (date or self.today.isoformat())[:10]
        bits = [f"{author} ({stamp[:4]}).", f"{title}{extra}.", f"{self.site['title']}."]
        if date:
            bits.append(f"{date_label} {fmt_date(stamp, 'long')}.".strip())
        else:
            bits.append(f"Retrieved {fmt_date(self.today.isoformat(), 'long')}.")
        bits.append(f"{base}{path}")
        return {
            "text": " ".join(bits),
            "licence": "CC BY 4.0",
            "licence_url": "https://creativecommons.org/licenses/by/4.0/",
            "kind": "text",
        }

    # ---- data views ----
    def papers(self, days: int | None, relevance="high"):
        out = [p for p in self.papers_all if p.get("relevance") == relevance]
        if days:
            since = (self.today - dt.timedelta(days=days)).isoformat()
            out = [p for p in out if (p.get("first_seen") or "") >= since]
        out.sort(key=lambda p: (p.get("first_seen") or "", p.get("published") or "", p["title"]), reverse=True)
        return out

    def by_week(self, papers):
        groups: dict[dt.date, list] = defaultdict(list)
        for p in papers:
            x = d(p.get("first_seen")) or self.today
            groups[monday_of(x)].append(p)
        return [(k, groups[k]) for k in sorted(groups, reverse=True)]

    def news(self, days: int):
        since = (self.today - dt.timedelta(days=days)).isoformat()
        out = [n for n in self.news_all if (n.get("published") or "") >= since]
        out.sort(key=lambda n: (n.get("published") or "", n.get("first_seen") or ""), reverse=True)
        return out

    def by_day(self, items):
        groups: dict[str, list] = defaultdict(list)
        for n in items:
            groups[(n.get("published") or "")[:10]].append(n)
        return [(k, groups[k]) for k in sorted(groups, reverse=True)]

    def digests(self):
        out = []
        for path in sorted((CONTENT_DIR / "digests").glob("*.md"), reverse=True):
            meta, html = read_markdown(path)
            if meta.get("draft"):
                continue
            slug = path.stem
            out.append({"slug": slug, "url": f"/digest/{slug}/", "title": meta.get("title", slug), "date": meta.get("date", slug[:10]), "summary": meta.get("summary", ""), "html": html, "meta": meta})
        out.sort(key=lambda x: str(x["date"]), reverse=True)
        # Issue numbers count up from the oldest published digest.
        for i, dg in enumerate(out):
            dg["number"] = len(out) - i
        return out


    # ---- trackers ----
    STATUS_GROUPS = [
        ("recruiting", "recruiting", ["recruiting", "not-yet-recruiting", "enrolling-by-invitation"]),
        ("active", "active, not recruiting", ["active"]),
        ("completed", "completed", ["completed"]),
        ("stopped", "stopped early", ["terminated", "suspended", "withdrawn"]),
        ("registered", "preregistrations", ["registered"]),
        ("unknown", "status unknown", ["unknown"]),
    ]

    def trials_view(self):
        groups: list[tuple[str, str, list]] = []
        two_years = (self.today - dt.timedelta(days=730)).isoformat()
        for slug, label, statuses in self.STATUS_GROUPS:
            items = [t for t in self.trials_all if t.get("status") in statuses]
            if slug == "registered":  # OSF goes back to 2013; the page shows recent registrations, the JSON has all
                items = [t for t in items if (t.get("first_posted") or t.get("first_seen") or "") >= two_years]
            if slug == "completed":
                items.sort(key=lambda t: (t.get("completion_date") or t.get("last_updated") or "", t["title"]), reverse=True)
            else:
                items.sort(key=lambda t: (t.get("first_posted") or t.get("first_seen") or "", t["title"]), reverse=True)
            for t in items:
                t["status_group"] = slug
            if items:
                groups.append((slug, label, items))
        return groups

    def bills(self, days: int):
        since = (self.today - dt.timedelta(days=days)).isoformat()
        out = [b for b in self.bills_all if (b.get("latest_action_date") or "") >= since]
        out.sort(key=lambda b: (b.get("latest_action_date") or "", b.get("jurisdiction") or "", b.get("identifier") or ""), reverse=True)
        return out

    def cases(self, days: int):
        since = (self.today - dt.timedelta(days=days)).isoformat()
        out = [c for c in self.cases_all if (c.get("latest_activity") or "") >= since]
        out.sort(key=lambda c: (c.get("latest_activity") or "", c.get("case_name") or ""), reverse=True)
        return out

    def by_month(self, items, field: str):
        groups: dict[str, list] = defaultdict(list)
        for it in items:
            groups[(it.get(field) or "")[:7]].append(it)
        return [(k, groups[k]) for k in sorted(groups, reverse=True)]

    # ---- search ----
    def coverage_from(self) -> str | None:
        meta = load_json(DATA_DIR / "index_meta.json", {})
        return meta.get("coverage_from")

    def search_records(self, papers: list[dict]) -> list[dict]:
        out = []
        for p in papers:
            topics = [self.tax.topic_label(t) for t in p.get("topics", [])]
            designs = [self.tax.design_label(x) for x in p.get("designs", [])]
            settings = setting_names(p.get("settings") or [])
            authors = p.get("authors") or []
            text = " ".join([p["title"], " ".join(authors), p.get("journal") or "", p.get("summary") or "", " ".join(topics), " ".join(designs), " ".join(settings), p.get("doi") or ""])
            folded = fold(f"{p['title']} {' '.join(authors)}")
            if folded != f"{p['title']} {' '.join(authors)}":
                text += " " + folded
            filters = {
                "topic": topics,
                "design": designs,
                "setting": [self.tax.regions.get(r, {}).get("label", r) for r in p.get("setting_regions") or []],
                "authors": [self.tax.regions.get(r, {}).get("label", r) for r in p.get("regions") or []],
                "year": [str(p["year"])] if p.get("year") else [],
                "access": ["Free full text"] if p.get("oa_url") else [],
                "language": [language_name(p.get("language"))] if p.get("language") and p.get("language") != "en" else [],
            }
            meta = {
                "title": p["title"],
                "journal": p.get("journal") or (p.get("type") or "article").replace("-", " ").capitalize(),
                "published": fmt_date(p.get("published")) if p.get("published") else "",
                "authors": authors_line(authors),
                "summary": p.get("summary") or "",
                "oa": p.get("oa_url") or "",
                "topics": "|".join(f"{t}~{self.tax.topic_label(t)}" for t in p.get("topics", [])[:4]),
                "designs": "|".join(designs[:2]),
                "setting": ", ".join(settings),
                "language": language_name(p.get("language")) if p.get("language") and p.get("language") != "en" else "",
                "retracted": "1" if p.get("retracted") else "",
            }
            out.append({
                "url": p.get("url") or f"/research/#{p['id']}",
                "content": text,
                "meta": meta,
                "filters": {k: v for k, v in filters.items() if v},
                "sort": {"published": (p.get("published") or p.get("first_seen") or "0000-00-00").replace("-", "")},
            })
        return out

    def build_search(self, papers: list[dict]) -> bool:
        records = self.search_records(papers)
        tmp = SITE_DIR / ".search-records.json"
        tmp.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        script = ROOT / "pipeline" / "search_index.mjs"
        if not (ROOT / "node_modules" / "pagefind").exists():
            print("search: node_modules/pagefind is missing (run npm ci); the search page will say search is unavailable", file=sys.stderr)
            tmp.unlink()
            return False
        try:
            subprocess.run(["node", str(script), str(tmp), str(SITE_DIR / "pagefind")], check=True, cwd=ROOT, timeout=900)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"search: index not built: {e}", file=sys.stderr)
            return False
        finally:
            tmp.unlink(missing_ok=True)
        return True

    # ---- rendering ----
    def render(self, template: str, out_path: str, **ctx):
        tpl = self.env.get_template(template)
        base = {
            "site": self.site,
            "today": self.today,
            "nav": self.nav,
            "fixture": self.fixture,
            "updated": fmt_time_utc(self.fetch_log.get("finished")),
            "path": "/" + out_path.replace("index.html", "").strip("/") + ("/" if not out_path.endswith(".xml") and not out_path.endswith(".txt") else ""),
        }
        if base["path"] == "//":
            base["path"] = "/"
        base["nav_current"] = next((item["href"] for item in self.nav if any(base["path"].startswith(pre) for pre in item["paths"])), None)
        section = ctx.get("section")
        if section in self.subnavs:
            base["subnav"] = self.subnavs[section]
            matches = [href for href, _ in self.subnavs[section] if base["path"].startswith(href)]
            base["subnav_current"] = max(matches, key=len) if matches else None
        base.update(ctx)
        html = tpl.render(**base)
        dest = SITE_DIR / out_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        if out_path.endswith("index.html"):
            self.urls.append(base["path"])

    def build(self):
        if SITE_DIR.exists():
            shutil.rmtree(SITE_DIR)
        SITE_DIR.mkdir(parents=True)
        shutil.copytree(STATIC_DIR, SITE_DIR / "static")
        (SITE_DIR / ".nojekyll").write_text("")
        (SITE_DIR / "CNAME").write_text(self.site["canonical_domain"] + "\n")
        (SITE_DIR / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {self.site['url']}/sitemap.xml\n")
        # Public copies of the index.
        (SITE_DIR / "data").mkdir()
        for name in ("papers.json", "news.json", "trials.json", "bills.json", "cases.json", "fetch_log.json", "index_meta.json", "gold_report.json", "weekly/latest.json"):
            src = DATA_DIR / name
            if src.exists():
                (SITE_DIR / "data" / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, SITE_DIR / "data" / name)
        # CSV mirrors of the four CC0 trackers, at stable URLs beside the JSON.
        for key in CSV_COLUMNS:
            self.write_csv(key, self.tracker_records(key))

        window = self.site.get("index_window_days", 90)
        recent = self.papers(window)
        week_ago = (self.today - dt.timedelta(days=7)).isoformat()
        this_week = [p for p in recent if (p.get("first_seen") or "") >= week_ago]
        digests = self.digests()
        topic_counts = Counter(t for p in recent for t in p.get("topics", []))
        region_counts = Counter(r for p in recent for r in p.get("regions", []))
        setting_counts = Counter(r for p in recent for r in p.get("setting_regions", []))
        design_counts = Counter(x for p in recent for x in p.get("designs", []))
        topics_sorted = [(slug, self.tax.topic_label(slug), n) for slug, n in topic_counts.most_common()]

        # Home
        home_news = [n for n in self.news(self.site.get("home_news_days", 7)) if n.get("primary") != "industry"][: self.site.get("home_news_count", 12)]
        self.render(
            "home.html", "index.html",
            papers=recent[: self.site.get("home_paper_count", 24)], this_week_count=len(this_week), total_count=len(self.papers(None)),
            news=home_news, digest=digests[0] if digests else None, topics=topics_sorted[:14],
            trackers={
                "recruiting": sum(1 for t in self.trials_all if t.get("status") in ("recruiting", "not-yet-recruiting", "enrolling-by-invitation")),
                "trials_year": sum(1 for t in self.trials_all if (t.get("first_posted") or "")[:4] == self.today.isoformat()[:4]),
                "regs_year": sum(1 for t in self.trials_all if t.get("kind") == "registration" and (t.get("first_posted") or "")[:4] == self.today.isoformat()[:4]),
                "bills_month": sum(1 for b in self.bills_all if (b.get("latest_action_date") or "") >= (self.today - dt.timedelta(days=30)).isoformat()),
                "bills_enacted_year": sum(1 for b in self.bills_all if b.get("stage") == "enacted" and (b.get("latest_action_date") or "")[:4] == self.today.isoformat()[:4]),
                "opinions_month": sum(1 for c in self.cases_all if c.get("kind") == "opinion" and (c.get("date_filed") or "") >= (self.today - dt.timedelta(days=30)).isoformat()),
                "dockets_month": sum(1 for c in self.cases_all if c.get("kind") == "docket" and (c.get("latest_activity") or "") >= (self.today - dt.timedelta(days=30)).isoformat()),
            },
            journal_feed_count=sum(1 for f in self.sources.get("journal_feeds", []) if f.get("enabled", True)),
            coverage_from=self.coverage_from(),
        )
        # Research index
        self.render(
            "research.html", "research/index.html", section="research",
            weeks=self.by_week(recent), count=len(recent), window=window, topics=topics_sorted,
            regions=[(s, self.tax.regions[s]["label"], n) for s, n in region_counts.most_common() if s in self.tax.regions],
            settings=[(s, self.tax.regions[s]["label"], n) for s, n in setting_counts.most_common() if s in self.tax.regions],
            designs=[(s, self.tax.design_label(s), n) for s, n in sorted(design_counts.items(), key=lambda x: self.tax.design_order.index(x[0]) if x[0] in self.tax.design_order else 99)], this_week_count=len(this_week),
            total_count=len(self.papers(None)), coverage_from=self.coverage_from(),
            dataset=self.dataset_schema("papers", self.papers_all), cite=self.cite_data("papers"),
        )
        # Borderline (low relevance) for transparency
        low = self.papers(window, relevance="low")
        self.render("research.html", "research/borderline/index.html", section="research", weeks=self.by_week(low), count=len(low), window=window, topics=[], regions=[], settings=[], designs=[], borderline=True, this_week_count=0)
        # Topic pages
        topic_window = self.site.get("topic_window_days", 365)
        year_papers = self.papers(topic_window)
        for slug, label, _ in self.tax.topics:
            tp = [p for p in year_papers if slug in p.get("topics", [])]
            self.render("topic.html", f"research/topics/{slug}/index.html", section="research", papers=tp, label=label, slug=slug, count=len(tp), window=topic_window)
        self.render("topics.html", "research/topics/index.html", section="research", topics=[(s, l, sum(1 for p in year_papers if s in p.get("topics", []))) for s, l, _ in self.tax.topics], window=topic_window)
        # Monthly archive
        months: dict[str, list] = defaultdict(list)
        for p in self.papers(None):
            months[(p.get("first_seen") or "0000-00")[:7]].append(p)
        month_list = sorted(months, reverse=True)
        for ym in month_list:
            y, m = ym.split("-")
            self.render("archive.html", f"research/archive/{y}/{m}/index.html", section="research", papers=months[ym], ym=ym, label=fmt_date(f"{ym}-01", "month"), months=[(x, fmt_date(f"{x}-01", "month"), len(months[x])) for x in month_list])
        self.render("archive_index.html", "research/archive/index.html", section="research", months=[(x, fmt_date(f"{x}-01", "month"), len(months[x])) for x in month_list])
        # News
        news_window = self.site.get("news_window_days", 30)
        nitems = self.news(news_window)
        cat_counts = Counter(n.get("primary") for n in nitems)
        self.render("news.html", "news/index.html", section="policy", days=self.by_day(nitems), count=len(nitems), window=news_window, categories=[(s, l, cat_counts.get(s, 0)) for s, l, _ in self.tax.news_categories])
        # Trackers: trials, bills, courts
        trial_groups = self.trials_view()
        n_trials = sum(1 for t in self.trials_all if t.get("kind") == "trial")
        n_regs = sum(1 for t in self.trials_all if t.get("kind") == "registration")
        n_recruiting = sum(1 for t in self.trials_all if t.get("status") in ("recruiting", "not-yet-recruiting", "enrolling-by-invitation"))
        n_results = sum(1 for t in self.trials_all if t.get("results_posted"))
        year = self.today.isoformat()[:4]
        n_new_year = sum(1 for t in self.trials_all if (t.get("first_posted") or "")[:4] == year)
        trial_topics = Counter(x for t in self.trials_all for x in t.get("topics", []))
        trial_regions = Counter(r for t in self.trials_all for r in t.get("regions", []))
        self.render(
            "trials.html", "trials/index.html", section="research",
            groups=trial_groups, n_trials=n_trials, n_regs=n_regs, n_recruiting=n_recruiting, n_results=n_results, n_new_year=n_new_year,
            topics=[(x, self.tax.topic_label(x), n) for x, n in trial_topics.most_common(10)],
            regions=[(x, self.tax.regions[x]["label"], n) for x, n in trial_regions.most_common() if x in self.tax.regions],
            registries=[(k, v) for k, v in (("clinicaltrials", "ClinicalTrials.gov"), ("isrctn", "ISRCTN"), ("osf", "OSF Registries")) if any(t.get("registry") == k for t in self.trials_all)],
            dataset=self.dataset_schema("trials", self.trials_all), cite=self.cite_data("trials"),
        )
        bills_window = self.site.get("bills_window_days", 365)
        bitems = self.bills(bills_window)
        stage_counts = Counter(b.get("stage") for b in bitems)
        juris = Counter((b.get("jurisdiction_code"), b.get("jurisdiction")) for b in bitems)
        bill_topics = Counter(x for b in bitems for x in b.get("topics", []))
        month_ago = (self.today - dt.timedelta(days=30)).isoformat()
        self.render(
            "bills.html", "bills/index.html", section="policy",
            months=self.by_month(bitems, "latest_action_date"), count=len(bitems), window=bills_window,
            stages=[(slug, label, stage_counts.get(slug, 0)) for slug, label in STAGES if stage_counts.get(slug)],
            jurisdictions=sorted(((code, name, n) for (code, name), n in juris.items() if code), key=lambda x: x[1]),
            n_jurisdictions=len([1 for (code, _), _ in juris.items() if code and code != "us"]),
            has_federal=any(b.get("level") == "federal" for b in bitems),
            topics=[(x, self.tax.topic_label(x), n) for x, n in bill_topics.most_common(14)],
            enacted_year=[b for b in bitems if b.get("stage") == "enacted" and (b.get("latest_action_date") or "")[:4] == year],
            recent_count=sum(1 for b in bitems if (b.get("latest_action_date") or "") >= month_ago),
            dataset=self.dataset_schema("bills", self.bills_all), cite=self.cite_data("bills"),
        )
        cases_window = self.site.get("cases_window_days", 180)
        citems = self.cases(cases_window)
        level_counts = Counter(c.get("court_level") for c in citems)
        case_topics = Counter(x for c in citems for x in c.get("topics", []))
        self.render(
            "courts.html", "courts/index.html", section="policy",
            months=self.by_month(citems, "latest_activity"), count=len(citems), window=cases_window,
            n_opinions=sum(1 for c in citems if c.get("kind") == "opinion"), n_dockets=sum(1 for c in citems if c.get("kind") == "docket"),
            levels=[(slug, label, level_counts.get(slug, 0)) for slug, label in COURT_LEVELS if level_counts.get(slug)],
            topics=[(x, self.tax.topic_label(x), n) for x, n in case_topics.most_common(14)],
            recent_opinions=sum(1 for c in citems if c.get("kind") == "opinion" and (c.get("date_filed") or "") >= month_ago),
            dataset=self.dataset_schema("cases", self.cases_all), cite=self.cite_data("cases"),
        )
        self.render("feed_trials.xml", "trials/feed.xml", trials=sorted(self.trials_all, key=lambda t: (t.get("first_seen") or "", t["title"]), reverse=True)[:50])
        self.render("feed_bills.xml", "bills/feed.xml", bills=bitems[:50])
        self.render("feed_courts.xml", "courts/feed.xml", cases=citems[:50])
        # Digests
        self.render("digest_index.html", "digest/index.html", digests=digests)
        for dg in digests:
            self.render(
                "digest.html", f"digest/{dg['slug']}/index.html", digest=dg,
                cite=self.cite_text(dg["title"], dg["url"], date=str(dg["date"]), extra=f" (Weekly Digest No. {dg['number']})"),
            )
        # Reference and other pages
        for path in sorted((CONTENT_DIR / "pages").glob("*.md")):
            meta, html = read_markdown(path)
            slug = meta.get("slug", path.stem)
            if slug == "methodology":
                self.render(
                "methodology.html", f"{slug}/index.html", page=meta, body=html, log=self.fetch_log, sources=self.sources, topics=self.tax.topics,
                cite=self.cite_text(meta.get("title", slug), f"/{slug}/"),
                topic_min=self.tax.topic_min, designs=self.tax.designs, design_rules=self.tax.design_rules, pubtypes=self.tax.pubtypes,
                gold=load_json(DATA_DIR / "gold_report.json", {}), index_meta=load_json(DATA_DIR / "index_meta.json", {}),
                n_corrections=len(self.tax.corrections.by_key),
            )
            else:
                cite = None
                if meta.get("cite", True):
                    cite = self.cite_text(
                        meta.get("title", slug), f"/{slug}/",
                        date=str(meta["updated"]) if meta.get("updated") else None,
                        date_label="Last updated",
                    )
                self.render("page.html", f"{slug}/index.html", page=meta, body=html, cite=cite)
        # Search across the whole index
        main_index = self.papers(None)
        search_ok = self.build_search(main_index)
        years = sorted({p["year"] for p in main_index if p.get("year")})
        self.render(
            "search.html", "search/index.html", search_ok=search_ok, total=len(main_index),
            coverage_from=self.coverage_from(), first_year=years[0] if years else None,
        )
        # Feeds
        self.render("feed_digest.xml", "feed.xml", digests=digests[:20])
        self.render("feed_research.xml", "research/feed.xml", papers=recent[:50])
        # Sitemap
        self.render("sitemap.xml", "sitemap.xml", urls=sorted(set(self.urls)))
        print(f"built {len(self.urls)} pages; {len(recent)} studies in the {window}-day window; {len(nitems)} news items; fixture={self.fixture}", file=sys.stderr)


def main() -> int:
    Builder().build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
