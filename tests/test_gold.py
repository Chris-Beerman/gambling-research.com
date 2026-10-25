"""The hand-checked labels must use the taxonomy's own slugs and valid country codes,
and the scorer must count what it says it counts."""
from pipeline import countries
from pipeline.common import load_yaml
from pipeline.gold import load_labels, score


def test_labels_use_known_slugs_and_codes():
    tax = load_yaml("taxonomy.yml")
    topics = {t["slug"] for t in tax["topics"]}
    designs = {d["slug"] for d in tax["designs"]}
    labels = load_labels()
    assert labels.get("studies"), "tests/gold/labels.yml is empty"
    for doi, lab in labels["studies"].items():
        assert str(doi).startswith("10."), doi
        assert set(lab) <= {"keep", "designs", "settings", "topics", "not_topics"}, doi
        assert set(lab.get("designs") or []) <= designs, doi
        assert set(lab.get("topics") or []) | set(lab.get("not_topics") or []) <= topics, doi
        for c in lab.get("settings") or []:
            assert countries.normalise_code(c) in countries.COUNTRY_NAMES, (doi, c)
    assert len(labels["studies"]) >= 50


def test_score_counts_hits_and_misses():
    labels = {"studies": {
        "10.1/a": {"designs": ["survey"], "settings": [False], "topics": ["youth"]},  # [False] is how YAML reads [NO]
        "10.1/b": {"keep": False},
        "10.1/c": {"keep": False},
    }}
    papers = [
        {"doi": "10.1/a", "relevance": "high", "designs": ["survey"], "settings": ["NO"], "topics": ["youth", "policy"]},
        {"doi": "10.1/c", "relevance": "high", "designs": [], "settings": [], "topics": []},
    ]
    r = score(papers, labels)
    assert r["keep"]["accuracy"] == round(2 / 3, 3) and r["keep"]["n"] == 3
    assert r["designs"]["accuracy"] == 1.0 and r["settings"]["accuracy"] == 1.0 and r["topics"]["accuracy"] == 1.0
