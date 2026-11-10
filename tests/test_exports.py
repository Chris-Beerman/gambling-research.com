"""Unit tests for the per-page exports: CSVs, citations, Dataset metadata, charts.

Run: python -m pytest -q
"""
import xml.etree.ElementTree as ET

import pytest

from pipeline import charts, exports
from pipeline.exports import Col, DataPage

SITE = {
    "title": "Gambling Research Index",
    "url": "https://gambling-research.com",
    "canonical_domain": "gambling-research.com",
    "editor": {"name": "Chris Beerman", "credentials": "LCSW, CADC", "orcid": "0009-0004-8277-2086"},
}

ROWS = [
    {"id": "doi:10.1/a", "first_seen": "2026-10-02", "title": "A study, with a comma", "authors": ["Ann Smith", "Bo Lee"],
     "topics": ["sports-betting", "youth"], "retracted": False, "oa_url": None, "cite_count": 0},
    {"id": "doi:10.1/b", "first_seen": "2026-09-01", "title": 'He said "maybe"', "authors": [],
     "topics": [], "retracted": True, "oa_url": "https://example.org/x", "cite_count": 4},
]
COLS = [
    Col("id", "Stable identifier"),
    Col("first_seen", "Date it entered the index"),
    Col("title", "Title"),
    Col("authors", "Author names"),
    Col("topics", "Topic tags"),
    Col("retracted", "Retraction flag"),
    Col("oa_url", "Free full text"),
    Col("cite_count", "Citations"),
]


def page(rows=ROWS, **kw) -> DataPage:
    kw.setdefault("slug", "research")
    kw.setdefault("path", "/research/")
    kw.setdefault("name", "New gambling research")
    kw.setdefault("description", "What the rows are.")
    kw.setdefault("columns", COLS)
    kw.setdefault("date_field", "first_seen")
    return DataPage(rows=rows, **kw)


# ---------------------------------------------------------------- CSV
def test_csv_has_a_header_and_no_preamble():
    text = exports.to_csv(ROWS, COLS)
    first = text.splitlines()[0]
    assert first == "id,first_seen,title,authors,topics,retracted,oa_url,cite_count"
    assert not text.startswith("#")


def test_csv_round_trips_through_a_reader():
    import csv as _csv
    import io

    rows = list(_csv.DictReader(io.StringIO(exports.to_csv(ROWS, COLS))))
    assert len(rows) == 2
    assert rows[0]["title"] == "A study, with a comma"          # the comma survives quoting
    assert rows[1]["title"] == 'He said "maybe"'                # so do the quotes
    assert rows[0]["authors"] == "Ann Smith|Bo Lee"             # lists on a vertical bar
    assert rows[1]["authors"] == ""                             # an empty list is empty, not "[]"
    assert rows[0]["retracted"] == "false" and rows[1]["retracted"] == "true"
    assert rows[0]["oa_url"] == ""                              # None is empty, never "None"
    assert rows[1]["cite_count"] == "4"                         # a zero is not swallowed
    assert rows[0]["cite_count"] == "0"


def test_a_value_containing_the_separator_cannot_fake_a_second_item():
    out = exports.render(["a|b", "c"])
    assert out == "a/b|c"


# ---------------------------------------------------------------- citation
def test_author_reference():
    assert exports.author_ref("Chris Beerman") == "Beerman, C."
    assert exports.author_ref("Ann Mary Lee") == "Lee, A. M."
    assert exports.author_ref("Plato") == "Plato"


def test_citation_is_one_line_and_carries_the_four_parts():
    line = exports.citation(SITE, page(), as_of_long="November 1, 2026", year=2026)
    assert "\n" not in line
    assert line.startswith("Beerman, C. (2026).")                 # author
    assert "New gambling research [data set]" in line             # title
    assert "Data as of November 1, 2026." in line                 # as-of date
    assert line.endswith("https://gambling-research.com/research/")  # URL


# ---------------------------------------------------------------- Dataset
def test_dataset_jsonld_carries_what_dataset_search_needs():
    dp = page(json_url="/data/papers.json", keywords=["gambling"], measurement="Nightly queries.")
    dp.csv_bytes = 2048
    cite = exports.citation(SITE, dp, as_of_long="November 1, 2026", year=2026)
    ds = exports.dataset_jsonld(SITE, dp, as_of_iso="2026-11-01", citation_text=cite, csv_bytes=dp.csv_bytes)
    assert ds["@type"] == "Dataset"
    for required in ("name", "description", "url", "license", "creator", "distribution", "isAccessibleForFree"):
        assert ds[required], required
    assert ds["temporalCoverage"] == "2026-09-01/2026-10-02"      # oldest/newest row, not today
    assert ds["creditText"] == cite
    assert [d["encodingFormat"] for d in ds["distribution"]] == ["text/csv", "application/json"]
    assert ds["distribution"][0]["contentUrl"].startswith("https://")
    assert ds["distribution"][0]["contentSize"] == "2 KB"
    assert {v["name"] for v in ds["variableMeasured"]} == {c.name for c in COLS}
    assert all(v["description"] for v in ds["variableMeasured"])  # every column is documented


def test_dataset_without_rows_omits_the_coverage_rather_than_inventing_one():
    dp = page(rows=[])
    ds = exports.dataset_jsonld(SITE, dp, as_of_iso="2026-11-01", citation_text="x", csv_bytes=0)
    assert "temporalCoverage" not in ds


def test_catalog_lists_every_dataset():
    pages = [page(), page(slug="bills", path="/bills/", name="Bills")]
    cat = exports.catalog_jsonld(SITE, pages, "2026-11-01")
    assert cat["@type"] == "DataCatalog"
    assert [d["@id"] for d in cat["dataset"]] == [
        "https://gambling-research.com/research/#dataset",
        "https://gambling-research.com/bills/#dataset",
    ]


@pytest.mark.parametrize("n,expect", [(0, "0 B"), (900, "900 B"), (2048, "2 KB"), (3_000_000, "2.9 MB")])
def test_human_size(n, expect):
    assert exports.human_size(n) == expect


# ---------------------------------------------------------------- charts
CREDIT_SITE = "gambling-research.com"
CREDIT_RIGHT = "Data as of November 1, 2026 · CC BY 4.0"


def svg(kind="columns", labels=None, values=None):
    labels = labels if labels is not None else ["Aug 3", "Aug 10", "Aug 17"]
    values = values if values is not None else [12, 40, 7]
    draw = charts.columns if kind == "columns" else charts.bars
    return draw(labels, values, title="New studies by week", subtitle="Past 90 days.",
                credit_site=CREDIT_SITE, credit_right=CREDIT_RIGHT, y_unit="studies").svg


@pytest.mark.parametrize("kind", ["columns", "bars"])
def test_chart_is_well_formed_xml(kind):
    root = ET.fromstring(svg(kind))
    assert root.tag.endswith("svg")
    assert root.get("role") == "img"


@pytest.mark.parametrize("kind", ["columns", "bars"])
def test_the_credit_travels_inside_the_image(kind):
    """The whole point: a screenshot of the chart still says where it came from."""
    out = svg(kind)
    assert CREDIT_SITE in out
    assert "Data as of November 1, 2026" in out
    assert "CC BY 4.0" in out


@pytest.mark.parametrize("kind", ["columns", "bars"])
def test_chart_has_a_title_and_a_description_for_screen_readers(kind):
    root = ET.fromstring(svg(kind))
    ns = "{http://www.w3.org/2000/svg}"
    assert root.find(f"{ns}title").text == "New studies by week"
    assert root.find(f"{ns}desc").text


def test_chart_carries_its_own_dark_mode_steps():
    out = svg()
    assert "prefers-color-scheme: dark" in out
    assert charts.DARK["series"] in out and charts.LIGHT["series"] in out


def test_columns_label_only_the_peak():
    out = svg(values=[12, 40, 7])
    assert ">40<" in out
    assert ">12<" not in out


def test_bars_label_every_tip():
    out = svg("bars", labels=["a", "b"], values=[3, 9])
    assert ">3<" in out and ">9<" in out


def test_an_empty_chart_does_not_divide_by_zero():
    out = svg(values=[0, 0, 0])
    ET.fromstring(out)


def test_a_chart_reports_its_own_size_so_the_page_can_reserve_the_space():
    made = charts.bars(["a", "b", "c"], [1, 2, 3], title="t", subtitle="s", credit_site=CREDIT_SITE, credit_right=CREDIT_RIGHT)
    assert made.width == 960
    assert made.height > 100
    assert f'height="{made.height}"' in made.svg


@pytest.mark.parametrize("top,expect", [(50, 60), (7, 8), (119, 150), (1, 1), (0, 1)])
def test_axis_maximum_is_a_round_number_at_or_above_the_data(top, expect):
    nice, step = charts._nice(top)
    assert nice == expect and nice >= top and step >= 1


# ---- which pages claim a Dataset record ----
def test_archive_months_do_not_claim_a_dataset_record():
    """78 month-slices of the same records would be near-duplicates competing
    with the tracker they came from, so they publish a CSV without claiming one."""
    page = DataPage(
        slug="research-archive/2020-05", path="/research/archive/2020/05/",
        name="Gambling research added in May 2020", description="x", rows=[{"first_seen": "2020-05-02"}],
        columns=[], date_field="first_seen", group=exports.ARCHIVE_GROUP,
    )
    assert page.is_dataset is False


def test_a_small_topic_still_claims_a_dataset_record():
    """A topic is a distinct subject set, not a cut of the same rows, so it
    claims one however few studies it currently holds."""
    page = DataPage(
        slug="topics/older-adults", path="/research/topics/older-adults/",
        name="Gambling research on older adults", description="x",
        rows=[{"first_seen": "2026-01-01"}] * 7,
        columns=[], date_field="first_seen", group="Research by topic",
    )
    assert page.is_dataset is True


def test_trackers_claim_a_dataset_record(): 
    page = DataPage(
        slug="bills", path="/bills/", name="Gambling bills", description="x",
        rows=[{"introduced": "2026-01-01"}], columns=[], date_field="introduced", group="Policy",
    )
    assert page.is_dataset is True


def test_catalogue_lists_only_pages_that_claim_a_dataset():
    archive = DataPage(
        slug="research-archive/2020-05", path="/research/archive/2020/05/", name="May 2020",
        description="x", rows=[], columns=[], date_field="first_seen", group=exports.ARCHIVE_GROUP,
    )
    topic = DataPage(
        slug="topics/x", path="/research/topics/x/", name="Topic X",
        description="x", rows=[], columns=[], date_field="first_seen", group="Research by topic",
    )
    cat = exports.catalog_jsonld(SITE, [archive, topic], "2026-11-10")
    urls = [d["url"] for d in cat["dataset"]]
    assert any("/topics/x/" in u for u in urls)
    assert not any("/archive/" in u for u in urls)


# ---- citations for pages that are writing rather than data ----
def test_dated_page_cites_like_an_article():
    c = exports.text_citation(
        SITE, "A headline (Weekly Digest No. 2)", "/digest/2026-10-26/",
        as_of_long="November 10, 2026", year=2026, date_long="October 26, 2026",
    )
    assert c.startswith("Beerman, C. (2026).")
    assert "A headline (Weekly Digest No. 2)." in c
    assert "October 26, 2026." in c
    assert "Retrieved" not in c
    assert c.endswith("/digest/2026-10-26/")


def test_living_page_cites_with_a_retrieval_date():
    """A reference page changes, so the reader needs to know which version."""
    c = exports.text_citation(
        SITE, "Where to publish gambling research", "/journals/",
        as_of_long="November 10, 2026", year=2026,
    )
    assert "Retrieved November 10, 2026." in c
    assert c.endswith("/journals/")


def test_text_citation_leaves_no_placeholder_to_fill():
    c = exports.text_citation(SITE, "T", "/x/", as_of_long="November 10, 2026", year=2026)
    assert "[" not in c and "]" not in c
