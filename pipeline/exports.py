"""Per-page data exports: the CSV, the one-line citation and the Dataset metadata.

Every page of the index that publishes counts is described here once, as a
``DataPage``, and that single description drives four things that have to agree with
each other: the CSV at a stable URL, the ``schema.org/Dataset`` block that makes the
page eligible for Google Dataset Search, the suggested citation printed on the page,
and the row in the catalogue on /data-use/. Changing a column changes all four.

The CSVs carry no comment or preamble rows: a file an analyst can read with
``pd.read_csv(url)`` and nothing else. Provenance travels in the rows instead, as the
DOI, registry number or docket number of each record, and on the page as the
citation.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Callable

LIST_SEP = "|"
CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"


@dataclass(frozen=True)
class Col:
    """One CSV column: its header, what it means, and where to read it."""
    name: str
    desc: str
    src: str | Callable[[dict], Any] | None = None


def render(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        parts = []
        for x in v:
            if isinstance(x, dict):
                x = x.get("name") or x.get("title") or x.get("description") or ""
            s = str(x).replace(LIST_SEP, "/").strip()
            if s:
                parts.append(s)
        return LIST_SEP.join(parts)
    if isinstance(v, dict):
        return str(v.get("name") or v.get("title") or "")
    return str(v)


def cell(row: dict, col: Col) -> str:
    src = col.src if col.src is not None else col.name
    return render(src(row) if callable(src) else row.get(src))


def to_csv(rows: list[dict], columns: list[Col]) -> str:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([c.name for c in columns])
    for row in rows:
        w.writerow([cell(row, c) for c in columns])
    return buf.getvalue()


# ---------------------------------------------------------------- column sets
PAPER_COLS = [
    Col("id", "Stable identifier for the record within this index"),
    Col("first_seen", "Date the study entered this index (ISO 8601)"),
    Col("published", "Publication date as the source reports it"),
    Col("year", "Publication year"),
    Col("title", "Title as the source reports it"),
    Col("authors", "Author names, in order, separated by a vertical bar"),
    Col("journal", "Journal or preprint server"),
    Col("type", "Record type: journal article, preprint, review and so on"),
    Col("doi", "Digital Object Identifier, lower-cased"),
    Col("pmid", "PubMed identifier where the record has one"),
    Col("url", "Link to the publisher's record"),
    Col("oa_url", "Link to a free full text where one was found"),
    Col("topics", "Topic tags assigned by this index, separated by a vertical bar"),
    Col("designs", "Study-design tags assigned by this index"),
    Col("settings", "ISO country codes of where the study was done"),
    Col("author_countries", "ISO country codes of where the authors work", "countries"),
    Col("language", "Language of the record, as an ISO 639-1 code"),
    Col("retracted", "true where the record is marked retracted"),
    Col("relevance", "Whether this index treats the study as squarely about gambling (high) or only loosely related (low)"),
    Col("sources", "Which databases supplied the record"),
]

NEWS_COLS = [
    Col("id", "Stable identifier for the item within this index"),
    Col("published", "Publication date and time as the feed reports it"),
    Col("first_seen", "Date the item entered this index (ISO 8601)"),
    Col("title", "Headline as published"),
    Col("source", "Outlet or regulator that published it"),
    Col("category", "Primary category assigned by this index", "primary"),
    Col("categories", "All categories matched, separated by a vertical bar"),
    Col("url", "Link to the original item"),
]

TRIAL_COLS = [
    Col("id", "Registry identifier (NCT number, ISRCTN number or OSF registration id)"),
    Col("registry", "Registry the record came from: clinicaltrials, isrctn or osf"),
    Col("kind", "trial for a registered trial, registration for a preregistration"),
    Col("title", "Study title as registered"),
    Col("status", "Recruitment status as the registry reports it"),
    Col("study_type", "Interventional, observational or other, as registered"),
    Col("phases", "Trial phase where one is registered"),
    Col("conditions", "Conditions studied, separated by a vertical bar"),
    Col("interventions", "Interventions studied, separated by a vertical bar"),
    Col("sponsor", "Lead sponsor"),
    Col("sponsor_class", "Sponsor type: industry, academic, government or other"),
    Col("countries", "ISO country codes of the study locations"),
    Col("start_date", "Study start date as registered"),
    Col("completion_date", "Completion date, actual or anticipated, as registered"),
    Col("first_posted", "Date the record first appeared on the registry"),
    Col("last_updated", "Date the registry record was last changed"),
    Col("results_posted", "true where results have been posted to the registry"),
    Col("topics", "Topic tags assigned by this index"),
    Col("url", "Link to the registry record"),
]

BILL_COLS = [
    Col("id", "Stable identifier for the bill within this index"),
    Col("level", "state or federal"),
    Col("jurisdiction", "Legislature the bill was introduced in"),
    Col("jurisdiction_code", "Two-letter state code, or us for Congress"),
    Col("session", "Legislative session"),
    Col("identifier", "Bill number as the legislature writes it"),
    Col("title", "Bill title or short description"),
    Col("classification", "Measure type: bill, resolution and so on"),
    Col("sponsors", "Sponsor names, separated by a vertical bar"),
    Col("introduced", "Date of introduction"),
    Col("latest_action_date", "Date of the most recent recorded action"),
    Col("latest_action", "The most recent recorded action, as the legislature wrote it"),
    Col("stage", "Stage read from the recorded actions: introduced, committee, passed_one, passed_both, enacted, failed"),
    Col("topics", "Topic tags assigned by this index"),
    Col("url", "Link to the bill on the legislature's site or on Open States"),
]

CASE_COLS = [
    Col("id", "Stable identifier for the record within this index"),
    Col("kind", "opinion for a filed opinion, docket for an active federal docket"),
    Col("case_name", "Case name as the court writes it"),
    Col("court", "Court"),
    Col("court_level", "Court level: scotus, federal_appellate, federal_district, state_high, state_appellate or other"),
    Col("docket_number", "Docket number"),
    Col("citation", "Reporter citation where one has been assigned"),
    Col("date_filed", "Date the opinion was filed, or the date the case was opened"),
    Col("date_terminated", "Date the case closed, where it has"),
    Col("latest_activity", "Date of the most recent docket activity"),
    Col("suit_nature", "Nature of suit as recorded on the docket"),
    Col("cite_count", "How many later opinions cite this one, per CourtListener"),
    Col("topics", "Topic tags assigned by this index"),
    Col("url", "Link to the record on CourtListener"),
]


# ---------------------------------------------------------------- data pages
ARCHIVE_GROUP = "Research archive"


@dataclass
class DataPage:
    """One page of the index that publishes counts, and everything derived from it."""
    slug: str                       # "research", "bills", "topics/sports-betting"
    path: str                       # the page it belongs to: "/research/"
    name: str                       # dataset and citation title
    description: str                # one sentence: what the rows are and what bounds them
    rows: list[dict]
    columns: list[Col]
    date_field: str                 # the column that bounds the temporal coverage
    unit: str = "records"           # plural noun for prose and chart descriptions
    group: str = "Research"         # heading it sits under in the catalogue
    json_url: str | None = None     # the full-file JSON companion, where there is one
    keywords: list[str] = field(default_factory=list)
    charts: list[dict] = field(default_factory=list)
    measurement: str = ""           # how the rows were collected
    csv_bytes: int = 0              # filled in when the CSV is written
    short: str = ""                 # compact label for the catalogue lists

    @property
    def label(self) -> str:
        return self.short or self.name

    @property
    def is_dataset(self) -> bool:
        """Whether this page claims a schema.org/Dataset record of its own.

        Google Dataset Search rewards a few substantial datasets and filters thin,
        near-duplicate ones. The monthly archive pages are time-slices of records
        already published in full on /research/ -- several hold a single study --
        so a Dataset record for each would be 78 near-duplicates competing with
        the tracker they came from. They keep their CSV, citation and charts; they
        just do not claim to be datasets in their own right. Topic pages do claim
        one: a topic is a distinct subject set, not a cut of the same rows, and
        that holds however few studies it currently has.
        """
        return self.group != ARCHIVE_GROUP

    @property
    def csv_url(self) -> str:
        return f"/data/{self.slug}.csv"

    @property
    def count(self) -> int:
        return len(self.rows)

    def coverage(self) -> tuple[str, str]:
        dates = sorted(d for d in ((r.get(self.date_field) or "")[:10] for r in self.rows) if len(d) == 10)
        return (dates[0], dates[-1]) if dates else ("", "")


def citation(site: dict, page: DataPage, *, as_of_long: str, year: int) -> str:
    """The suggested citation: author, title, as-of date, URL, on one line."""
    return (
        f"{author_ref(site['editor']['name'])} ({year}). "
        f"{page.name} [data set]. {site['title']}. "
        f"Data as of {as_of_long}. {site['url']}{page.path}"
    )


def author_ref(full_name: str) -> str:
    """"Chris Beerman" -> "Beerman, C."."""
    parts = [p for p in (full_name or "").split() if p]
    if len(parts) < 2:
        return full_name or ""
    return f"{parts[-1]}, " + " ".join(f"{p[0]}." for p in parts[:-1])


def human_size(n: int) -> str:
    """A size schema.org and a reader can both use: "205 KB", "1.4 MB"."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{round(n / 1024)} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def dataset_jsonld(site: dict, page: DataPage, *, as_of_iso: str, citation_text: str, csv_bytes: int) -> dict:
    """schema.org/Dataset for one data page, in the shape Google Dataset Search reads."""
    base = site["url"]
    start, end = page.coverage()
    editor = site["editor"]
    creator: dict[str, Any] = {
        "@type": "Person",
        "@id": f"{base}/about/#editor",
        "name": editor["name"],
        "url": f"{base}/about/",
    }
    if editor.get("orcid"):
        creator["sameAs"] = f"https://orcid.org/{editor['orcid']}"
    distribution = [{
        "@type": "DataDownload",
        "name": f"{page.name}: CSV",
        "encodingFormat": "text/csv",
        "contentUrl": f"{base}{page.csv_url}",
        "contentSize": human_size(csv_bytes),
    }]
    if page.json_url:
        distribution.append({
            "@type": "DataDownload",
            "name": f"{page.name}: JSON",
            "encodingFormat": "application/json",
            "contentUrl": f"{base}{page.json_url}",
        })
    out: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "@id": f"{base}{page.path}#dataset",
        "name": f"{page.name} — {site['title']}",
        "description": page.description,
        "url": f"{base}{page.path}",
        "identifier": f"{base}{page.path}#dataset",
        "license": CC0,
        "isAccessibleForFree": True,
        "creator": creator,
        "maintainer": {"@id": f"{base}/about/#editor"},
        "publisher": {"@type": "Organization", "@id": f"{base}/#publisher", "name": site["title"], "url": f"{base}/"},
        "includedInDataCatalog": {"@type": "DataCatalog", "@id": f"{base}/data-use/#catalog", "name": f"{site['title']} data", "url": f"{base}/data-use/"},
        "dateModified": as_of_iso,
        "creditText": citation_text,
        "distribution": distribution,
        "variableMeasured": [{"@type": "PropertyValue", "name": c.name, "description": c.desc} for c in page.columns],
        "inLanguage": "en",
    }
    if page.keywords:
        out["keywords"] = page.keywords
    if start and end:
        out["temporalCoverage"] = f"{start}/{end}"
    if page.measurement:
        out["measurementTechnique"] = page.measurement
    return out


def catalog_jsonld(site: dict, pages: list[DataPage], as_of_iso: str) -> dict:
    """The DataCatalog on /data-use/ that every Dataset on the site belongs to."""
    base = site["url"]
    return {
        "@context": "https://schema.org",
        "@type": "DataCatalog",
        "@id": f"{base}/data-use/#catalog",
        "name": f"{site['title']} data",
        "description": (
            f"Free, openly licensed data on gambling research, trials, legislation, court activity and policy news, rebuilt nightly by the "
            f"{site['title']}. Every page of the index publishes its rows as a CSV at a stable URL. No funding, advertising or data from "
            f"gambling operators, suppliers or affiliates."
        ),
        "url": f"{base}/data-use/",
        "license": CC0,
        "isAccessibleForFree": True,
        "dateModified": as_of_iso,
        "inLanguage": "en",
        "publisher": {"@type": "Organization", "@id": f"{base}/#publisher", "name": site["title"], "url": f"{base}/"},
        "creator": {"@id": f"{base}/about/#editor"},
        "dataset": [{"@type": "Dataset", "@id": f"{base}{p.path}#dataset", "name": f"{p.name} — {site['title']}", "url": f"{base}{p.path}"} for p in pages if p.is_dataset],
    }
