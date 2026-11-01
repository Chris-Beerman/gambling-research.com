"""The published CSV copies of the index."""
import csv

from pipeline.build import CSV_COLUMNS, csv_cell, write_csv


def test_cell_formats_each_type():
    assert csv_cell(None) == ""
    assert csv_cell(True) == "true"
    assert csv_cell(False) == "false"
    assert csv_cell(2026) == "2026"
    assert csv_cell(["a", "b"]) == "a; b"
    # Empty members are dropped rather than leaving stray separators.
    assert csv_cell(["a", "", None, "b"]) == "a; b"
    assert csv_cell([]) == ""
    # A newline inside a summary must not break the row.
    assert csv_cell("one\ntwo\r\nthree") == "one two  three"


def test_write_csv_round_trips(tmp_path):
    rows = [
        {
            "id": "doi:10.1/x",
            "title": 'A study, with a comma and "quotes"',
            "authors": ["Ferris", "Wynne"],
            "topics": [],
            "retracted": False,
            "year": 2026,
            "summary": "Line one\nline two",
        },
        {"id": "pmid:42", "title": "Second"},
    ]
    cols = ["id", "title", "authors", "topics", "retracted", "year", "summary"]
    out = tmp_path / "sub" / "papers.csv"
    assert write_csv(out, rows, cols) == 2

    with out.open(newline="", encoding="utf-8") as fh:
        got = list(csv.reader(fh))

    assert got[0] == cols
    assert len(got) == 3
    assert all(len(r) == len(cols) for r in got)
    assert got[1][1] == 'A study, with a comma and "quotes"'
    assert got[2] == ["pmid:42", "Second", "", "", "", "", ""]
    assert "\n" not in got[1][6]


def test_paper_columns_cover_the_record_fields():
    """Every field a paper record carries is published, so the dictionary is complete."""
    fields = {
        "id", "doi", "pmid", "pmcid", "openalex", "title", "journal", "authors",
        "published", "year", "created", "first_seen", "summary", "url", "oa_url",
        "sources", "type", "topics", "designs", "design_basis", "settings",
        "setting_regions", "countries", "regions", "language", "relevance",
        "retracted",
    }
    published = set(CSV_COLUMNS["papers"])
    # 'created' is the source database's own registration date, deliberately
    # left out: 'published' and 'first_seen' are the two dates that matter.
    assert fields - published == {"created"}
    assert published - fields == set()


def test_every_dataset_has_an_id_first():
    for name, cols in CSV_COLUMNS.items():
        assert cols[0] == "id", name
        assert len(cols) == len(set(cols)), name
