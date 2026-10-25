"""Tagging rules, layer by layer: corrections, database metadata, keyword rules.
The examples are written for the tests (no publisher abstracts are stored here);
each mirrors a mistake the index has made or could make."""
import datetime as dt

from pipeline import countries
from pipeline.build import fold
from pipeline.common import load_yaml
from pipeline.normalize import Taxonomy, norm_language, update_index

TODAY = dt.date(2026, 10, 25)


def tax(corrections=None):
    return Taxonomy(load_yaml("taxonomy.yml"), corrections=corrections or {})


def rec(source="pubmed", doi="10.1000/x", title="", abstract="", **kw):
    r = {"source": source, "doi": doi, "pmid": kw.pop("pmid", None), "pmcid": None, "openalex": None, "title": title, "journal": kw.pop("journal", "Journal of Gambling Studies"),
         "issn": [], "authors": [], "affiliations": kw.pop("affiliations", []), "countries": kw.pop("countries", []), "published": "2026-10-01", "created": "2026-10-02",
         "abstract": abstract, "url": "x", "oa_url": None, "type": kw.pop("type", "article"), "language": "en", "retracted": False}
    r.update(kw)
    return r


def index(*records, t=None, existing=None, rebuild=False):
    papers, stats = update_index(existing or [], list(records), t or tax(), TODAY, backfill=False, rebuild=rebuild)
    return {p["doi"]: p for p in papers}, stats


# ---------------------------------------------------------------- relevance
def test_ambiguous_terms_need_a_gambling_context():
    t = tax()
    assert t.assess("Self-exclusion relational knowledge distillation for event recognition", "")[0] == "low"
    assert t.assess("Self-exclusion from online casinos", "")[0] == "high"
    assert t.assess("Choices between lotteries under ambiguity", "Participants chose between lotteries.")[0] == "low"
    assert t.assess("A political gamble: coalition politics", "")[0] == "low"


def test_metaphors_and_statistics_terms_are_ignored():
    t = tax()
    assert t.assess("Gambling for re-election", "Politicians gamble for re-election.")[0] in (None, "low")
    assert t.assess("Sequential tests with e-values", "Testing by betting gives anytime-valid inference.")[0] != "high"
    # The stray-mention journal list drops a record even with a strong term.
    papers, _ = index(rec(title="Event recognition and casino surveillance", journal="Applied Optics"))
    assert not papers


def test_openalex_only_needs_the_subject_in_the_title_or_early_and_often():
    title_hit = rec("openalex", "10.1000/a", "Online gambling among students", "We surveyed students.")
    passing = rec("openalex", "10.1000/b", "Digital risks of young people", "Gambling harms are rising. " + "Online gambling and sports betting were measured. " * 2)
    late = rec("openalex", "10.1000/c", "Halal tourism and satisfaction", "Tourists value prayer facilities. " * 20 + "Hotels avoid gambling and alcohol. Gambling is haram. Casinos are absent.")
    once = rec("openalex", "10.1000/d", "Financial literacy education for teenagers", "Risks include paylater misuse and online gambling.")
    papers, _ = index(title_hit, passing, late, once)
    assert set(papers) == {"10.1000/a", "10.1000/b"}


def test_non_english_titles_count():
    t = tax()
    assert t.assess("Rahapeliriippuvuus ja itsemurha", "")[0] == "high"
    assert t.assess("Dampak judi online pada remaja", "")[0] == "high"
    assert norm_language(None, "Rahapeliriippuvuus ja itsemurha") == "fi"
    assert norm_language("eng") == "en" and norm_language("ang") is None


# ---------------------------------------------------------------- designs
def test_pubmed_publication_types_decide_trial_and_protocol():
    t = tax()
    # A register-study protocol that mentions randomised trials in passing.
    assert t.designs_for("Study protocol: a 10-year register study of gambling disorder", "Prior randomized controlled trials were small. This protocol describes a register-based study.", ["clinical trial protocol"]) == ["protocol", "behavioral-data"]
    # Indexers say RCT even though the title does not.
    assert "trial" in t.designs_for("Brief intervention for sports bettors", "Participants received feedback.", ["randomized controlled trial"])
    # Without a trial publication type, a PubMed record that only cites trials is not a trial.
    assert "trial" not in t.designs_for("Sequential monitoring methods", "In randomized trials, repeated interim analyses inflate error.", ["comparative study"])


def test_design_rules_look_for_the_authors_own_study():
    t = tax()
    assert "trial" in t.designs_for("Personalised feedback for gamblers", "In this randomised controlled trial, 400 gamblers were allocated to feedback or control.")
    assert "trial" not in t.designs_for("Loot box identification", "Meta-analyses suggest links with problem gambling; early longitudinal evidence suggests migration to gambling.")
    assert "review" not in t.designs_for("Loot box identification", "Meta-analyses suggest links with problem gambling.")
    assert t.designs_for("Treatments for gambling disorder: a systematic review", "We conducted a systematic review; 12 randomized controlled trials were included.") == ["review"]
    assert "survey" not in t.designs_for("Losses among horse race bettors", "Previous research mainly relied on self-reported data. We analysed account data from 30,000 bettors.")
    assert "behavioral-data" in t.designs_for("Losses among horse race bettors", "We analysed account data from 30,000 bettors.")
    assert t.designs_for("Editorial: prediction markets and public health", "") == ["commentary"]


# ---------------------------------------------------------------- topics
def test_topics_need_a_title_match_or_repeated_mentions():
    t = tax()
    abstract = "We surveyed 2,000 adults about sports betting. The findings have policy implications."
    assert "policy" not in t.topics_for("Sports betting frequency among adults", abstract)
    assert "policy" in t.topics_for("Sports betting policy in Ontario", abstract)
    assert "families" not in t.topics_for("Familiarity with odds formats", "Bettors' familiarity with odds formats varies.")
    assert "advertising" not in t.topics_for("Health promotion and gambling", "A health promotion approach to gambling harm.")


# ---------------------------------------------------------------- settings and author countries
def test_norway_is_europe_not_false():
    t = tax()
    assert countries.normalise_code(False) == "NO"
    assert t.regions_for(["NO", "TR"]) == ["europe"]
    assert t.regions_for([False]) == ["europe"]


def test_setting_is_kept_apart_from_author_location():
    r = rec("pubmed", "10.1000/iran", "Gambling among medical sciences students in central-southern Iran: a cross-sectional study",
            "A cross-sectional survey of 900 students.", affiliations=["Kerman University of Medical Sciences, Kerman, Iran", "School of Public Health, Monash University, Melbourne, Australia"])
    papers, _ = index(r)
    p = papers["10.1000/iran"]
    assert p["settings"] == ["IR"] and p["setting_regions"] == ["middle-east"]
    assert set(p["countries"]) == {"IR", "AU"}


def test_mesh_geographic_headings_win():
    r = rec("pubmed", "10.1000/fin", "Gambling disorder and suicide: last healthcare visit before death", "A register study.", mesh=["Gambling", "Suicide", "Finland", "Humans"])
    papers, _ = index(r)
    assert papers["10.1000/fin"]["settings"] == ["FI"]


def test_language_names_are_not_settings():
    t = tax()
    assert t.settings_for("Validation of the Spanish-language PGSI among US adults", "") == ["US"]
    assert t.settings_for("Chinese gamblers in Macao casinos", "") == ["MO"]
    assert "MX" not in t.settings_for("Sports betting in New Mexico", "")


# ---------------------------------------------------------------- corrections and rebuilds
def test_corrections_override_and_exclude():
    corr = {"studies": {"10.1000/fix": {"designs": ["protocol"], "add_topics": ["self-exclusion"], "settings": ["SE"]}, "10.1000/drop": {"exclude": True}}}
    t = tax(corr)
    papers, stats = index(
        rec(doi="10.1000/fix", title="Gambling treatment: a randomised trial", abstract="This randomised controlled trial will recruit 200 gamblers."),
        rec(doi="10.1000/drop", title="Gambling metaphors in finance", abstract="Gambling."),
        t=t,
    )
    assert papers["10.1000/fix"]["designs"] == ["protocol"] and "self-exclusion" in papers["10.1000/fix"]["topics"]
    assert papers["10.1000/fix"]["settings"] == ["SE"] and papers["10.1000/fix"]["setting_regions"] == ["europe"]
    assert "10.1000/drop" not in papers
    # An exclusion also removes a study already in the index that no source returned tonight.
    existing = [dict(papers["10.1000/fix"], doi="10.1000/drop", id="doi:10.1000/drop", title="Old entry")]
    papers2, _ = index(t=t, existing=existing)
    assert "10.1000/drop" not in papers2


def test_rebuild_removes_what_the_rules_no_longer_keep_and_keeps_first_seen():
    old = [
        {"id": "doi:10.1000/keep", "doi": "10.1000/keep", "pmid": None, "title": "Sports betting harms", "summary": "", "sources": ["pubmed"], "first_seen": "2026-07-01", "topics": [], "designs": [], "countries": [], "regions": [], "relevance": "high"},
        {"id": "doi:10.1000/stale", "doi": "10.1000/stale", "pmid": None, "title": "Emotional predictors of returning a favour", "summary": "Participants played a lottery game.", "sources": ["openalex"], "first_seen": "2026-07-01", "topics": [], "designs": [], "countries": [], "regions": [], "relevance": "high"},
    ]
    papers, stats = index(rec(doi="10.1000/keep", title="Sports betting harms", abstract="Sports bettors reported harms."), existing=old, rebuild=True)
    assert set(papers) == {"10.1000/keep"} and stats["removed"] == 1
    assert papers["10.1000/keep"]["first_seen"] == "2026-07-01"


def test_search_folding():
    assert fold("Kaymakçı Castrén Sørensen Łukasz") == "Kaymakci Castren Sorensen Lukasz"


def test_same_title_different_doi_are_different_studies():
    old = [{"id": "doi:10.1000/n1", "doi": "10.1000/n1", "pmid": None, "title": "In Case You Haven't Heard", "summary": "", "sources": ["openalex"], "first_seen": "2026-10-17",
            "topics": [], "designs": [], "countries": [], "regions": [], "relevance": "high"}]
    other = rec("openalex", "10.1000/n2", "In Case You Haven't Heard", "A note on hospital staffing.")
    papers, _ = index(other, existing=old)
    assert "10.1000/n1" in papers and "10.1000/n2" not in papers
