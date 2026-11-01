"""Unit tests for the CSV mirrors, Dataset markup and citation lines.
Run: python -m pytest -q"""
import csv
import io

import pytest

from pipeline.build import CSV_COLUMNS, DATASETS, Builder, csv_cell

TRACKERS = sorted(CSV_COLUMNS)


@pytest.fixture(scope="module")
def b():
    return Builder()


# ---- CSV cells ----
def test_csv_cell_scalars():
    assert csv_cell(None) == ""
    assert csv_cell("x") == "x"
    assert csv_cell(7) == "7"


def test_csv_cell_booleans_are_words_not_python_repr():
    # "True"/"False" would break a naive boolean parse in R or pandas.
    assert csv_cell(True) == "true"
    assert csv_cell(False) == "false"


def test_csv_cell_lists_are_semicolon_joined_and_drop_blanks():
    assert csv_cell(["a", "b"]) == "a; b"
    assert csv_cell(["a", None, "", "b"]) == "a; b"
    assert csv_cell([]) == ""


def test_csv_cell_dict_is_json_not_python_repr():
    assert csv_cell({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'


# ---- the exported files ----
@pytest.mark.parametrize("key", TRACKERS)
def test_every_tracker_has_columns_and_a_dataset_spec(key):
    assert CSV_COLUMNS[key], key
    assert key in DATASETS, key
    assert len(set(CSV_COLUMNS[key])) == len(CSV_COLUMNS[key]), f"{key}: duplicate column"


@pytest.mark.parametrize("key", TRACKERS)
def test_csv_columns_cover_the_data_or_are_deliberate(key, b):
    """Every CSV column is either a field in the data or a derived column the
    writer knows how to build. Catches a column renamed upstream."""
    records = b.tracker_records(key)
    if not records:
        pytest.skip(f"no {key} records locally")
    present = {k for r in records for k in r}
    derived = {"documents_count"}
    unknown = [c for c in CSV_COLUMNS[key] if c not in present and c not in derived]
    assert not unknown, f"{key}: columns not in the data and not derived: {unknown}"


@pytest.mark.parametrize("key", TRACKERS)
def test_csv_roundtrips_one_row_per_record_with_a_fixed_width(key, b, tmp_path):
    records = b.tracker_records(key)
    if not records:
        pytest.skip(f"no {key} records locally")
    cols = CSV_COLUMNS[key]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for rec in records[:200]:
        w.writerow(["" if c == "documents_count" else csv_cell(rec.get(c)) for c in cols])
    rows = list(csv.reader(io.StringIO(buf.getvalue())))
    assert rows[0] == cols
    assert len(rows) == len(records[:200]) + 1
    assert {len(r) for r in rows} == {len(cols)}, "ragged CSV"


# ---- Dataset markup ----
@pytest.mark.parametrize("key", TRACKERS)
def test_dataset_schema_has_what_google_requires(key, b):
    s = b.dataset_schema(key, b.tracker_records(key))
    assert s["@type"] == "Dataset"
    assert s["name"] and s["description"], "name and description are required"
    assert len(s["description"]) >= 50, "description too thin to be useful"
    assert s["url"].startswith("https://")
    assert s["isAccessibleForFree"] is True


@pytest.mark.parametrize("key", TRACKERS)
def test_dataset_licence_is_cc0_and_matches_the_repo_licence(key, b):
    s = b.dataset_schema(key, b.tracker_records(key))
    assert s["license"] == "https://creativecommons.org/publicdomain/zero/1.0/"


@pytest.mark.parametrize("key", TRACKERS)
def test_dataset_offers_both_json_and_csv_at_stable_urls(key, b):
    s = b.dataset_schema(key, b.tracker_records(key))
    formats = {d["encodingFormat"]: d["contentUrl"] for d in s["distribution"]}
    assert formats["application/json"].endswith(f"/data/{key}.json")
    assert formats["text/csv"].endswith(f"/data/{key}.csv")


@pytest.mark.parametrize("key", TRACKERS)
def test_dataset_credits_the_editor_with_an_orcid(key, b):
    s = b.dataset_schema(key, b.tracker_records(key))
    assert s["creator"]["name"]
    assert "orcid.org" in s["creator"].get("identifier", "")


@pytest.mark.parametrize("key", TRACKERS)
def test_temporal_coverage_is_an_open_ended_iso_interval(key, b):
    records = b.tracker_records(key)
    if not records:
        pytest.skip(f"no {key} records locally")
    span = b.dataset_schema(key, records).get("temporalCoverage", "")
    assert span.endswith("/.."), f"{key}: {span!r} should be open-ended"
    start = span[:-3]
    assert len(start) == 10 and start[4] == "-", f"{key}: {start!r} not an ISO date"


# ---- citation lines ----
@pytest.mark.parametrize("key", TRACKERS)
def test_data_citation_names_author_year_title_and_url(key, b):
    c = b.cite_data(key)
    assert c["kind"] == "data"
    assert c["text"].startswith("Beerman, C. (")
    assert "[Data set]" in c["text"]
    assert DATASETS[key]["title"] in c["text"]
    assert c["text"].rstrip().endswith(DATASETS[key]["page"])
    assert "CC0" in c["licence"]


@pytest.mark.parametrize("key", TRACKERS)
def test_data_citation_says_what_to_cite_instead(key, b):
    """The index's own norm is to cite the underlying work; the block must say so."""
    assert "Cite" in b.cite_data(key)["note"]


def test_data_citation_has_no_placeholder_for_the_reader_to_fill(b):
    for key in TRACKERS:
        text = b.cite_data(key)["text"]
        assert "[date]" not in text and "[" not in text.replace("[Data set]", "")


def test_text_citation_of_a_dated_page_uses_that_date(b):
    c = b.cite_text("Where to publish", "/journals/", date="2026-09-27", date_label="Last updated")
    assert c["kind"] == "text"
    assert "Last updated September 27, 2026." in c["text"]
    assert c["text"].endswith("https://gambling-research.com/journals/")
    assert c["licence"] == "CC BY 4.0"


def test_text_citation_without_a_date_falls_back_to_retrieval(b):
    c = b.cite_text("How the index works", "/methodology/")
    assert "Retrieved " in c["text"]


def test_digest_citation_carries_the_issue_number(b):
    c = b.cite_text("A headline", "/digest/2026-10-26/", date="2026-10-26", extra=" (Weekly Digest No. 2)")
    assert "A headline (Weekly Digest No. 2)." in c["text"]
    assert "October 26, 2026." in c["text"]
