"""Unit tests for parsing, merging, relevance and tagging. Run: python -m pytest -q"""
import datetime as dt

from pipeline.common import load_yaml, norm_doi, summarize
from pipeline.normalize import Taxonomy, update_index, update_news
from pipeline.sources import crossref, feeds, openalex, pubmed

TAX = Taxonomy(load_yaml("taxonomy.yml"))
TODAY = dt.date(2026, 10, 15)

PUBMED_XML = b"""<?xml version="1.0"?>
<PubmedArticleSet>
<PubmedArticle>
 <MedlineCitation Status="In-Process" Owner="NLM">
  <PMID Version="1">41111111</PMID>
  <Article PubModel="Print-Electronic">
   <Journal><ISSN IssnType="Electronic">1573-3602</ISSN><JournalIssue CitedMedium="Internet"><PubDate><Year>2026</Year><Month>Oct</Month></PubDate></JournalIssue><Title>Journal of gambling studies</Title></Journal>
   <ArticleTitle>Direct marketing and sports betting: a randomised field experiment.</ArticleTitle>
   <Abstract><AbstractText Label="BACKGROUND">Sports bettors receive frequent inducements.</AbstractText><AbstractText Label="METHODS">We randomised 1,000 account holders.</AbstractText></Abstract>
   <AuthorList><Author><LastName>Rockloff</LastName><ForeName>Matthew</ForeName><AffiliationInfo><Affiliation>CQUniversity, Melbourne, Australia.</Affiliation></AffiliationInfo></Author><Author><LastName>Smith</LastName><ForeName>Ann</ForeName></Author></AuthorList>
   <Language>eng</Language>
   <PublicationTypeList><PublicationType>Journal Article</PublicationType><PublicationType>Randomized Controlled Trial</PublicationType></PublicationTypeList>
   <ArticleDate DateType="Electronic"><Year>2026</Year><Month>10</Month><Day>03</Day></ArticleDate>
  </Article>
 </MedlineCitation>
 <PubmedData>
  <History><PubMedPubDate PubStatus="entrez"><Year>2026</Year><Month>10</Month><Day>05</Day></PubMedPubDate></History>
  <ArticleIdList><ArticleId IdType="doi">10.1007/S10899-026-99999-1</ArticleId><ArticleId IdType="pmc">PMC12345678</ArticleId></ArticleIdList>
 </PubmedData>
</PubmedArticle>
</PubmedArticleSet>"""


def test_pubmed_parse():
    recs = pubmed.parse_efetch(PUBMED_XML)
    assert len(recs) == 1
    r = recs[0]
    assert r["doi"] == "10.1007/s10899-026-99999-1"
    assert r["pmid"] == "41111111"
    assert r["published"] == "2026-10-03"
    assert r["created"] == "2026-10-05"
    assert r["oa_url"].endswith("PMC12345678/")
    assert r["authors"] == ["Matthew Rockloff", "Ann Smith"]
    assert "Background: Sports bettors" in r["abstract"]
    assert r["language"] == "en"


def test_openalex_convert():
    w = {
        "id": "https://openalex.org/W123", "doi": "https://doi.org/10.1007/s10899-026-99999-1", "title": "Direct marketing and sports betting: a randomised field experiment",
        "publication_date": "2026-10-03", "type": "article", "language": "en", "is_retracted": False, "created_date": "2026-10-04",
        "primary_location": {"source": {"display_name": "Journal of Gambling Studies", "issn": ["1050-5350", "1573-3602"]}, "landing_page_url": "x"},
        "open_access": {"oa_url": "https://example.org/oa.pdf"},
        "authorships": [{"author": {"display_name": "Matthew Rockloff"}, "countries": ["AU"], "institutions": [{"display_name": "CQUniversity", "country_code": "AU"}]}],
        "abstract_inverted_index": {"Sports": [0], "bettors": [1], "receive": [2], "inducements.": [3]},
        "ids": {"pmid": "https://pubmed.ncbi.nlm.nih.gov/41111111"},
    }
    r = openalex.convert(w)
    assert r["doi"] == "10.1007/s10899-026-99999-1"
    assert r["abstract"] == "Sports bettors receive inducements."
    assert r["countries"] == ["AU"]
    assert r["pmid"] == "41111111"
    assert r["oa_url"].endswith(".pdf")


def test_crossref_convert():
    it = {"DOI": "10.1007/s10899-026-99999-1", "title": ["Direct marketing and sports betting: a randomised field experiment"], "container-title": ["Journal of Gambling Studies"],
          "author": [{"given": "Matthew", "family": "Rockloff", "affiliation": [{"name": "CQUniversity, Australia"}]}], "published-online": {"date-parts": [[2026, 10, 3]]},
          "created": {"date-parts": [[2026, 10, 2]]}, "type": "journal-article", "ISSN": ["1573-3602"]}
    r = crossref.convert(it, "Journal of Gambling Studies")
    assert r["published"] == "2026-10-03" and r["created"] == "2026-10-02"
    assert r["authors"] == ["Matthew Rockloff"]


def test_merge_and_relevance():
    raw = pubmed.parse_efetch(PUBMED_XML)
    raw.append(crossref.convert({"DOI": "10.1007/s10899-026-99999-1", "title": ["Direct marketing and sports betting: a randomised field experiment"], "container-title": ["Journal of Gambling Studies"], "created": {"date-parts": [[2026, 10, 2]]}, "type": "journal-article"}, None))
    raw.append({"source": "openalex", "doi": None, "pmid": None, "pmcid": None, "openalex": "W9", "title": "Neural correlates of risk in the Iowa Gambling Task", "journal": "NeuroImage", "issn": [], "authors": [], "affiliations": [], "countries": ["DE"], "published": "2026-10-01", "created": None, "abstract": "We used the Iowa Gambling Task to study reward.", "url": "x", "oa_url": None, "type": "article", "language": "en", "retracted": False})
    raw.append({"source": "pubmed", "doi": "10.1000/lottery", "pmid": "1", "pmcid": None, "openalex": None, "title": "Lottery incentives for survey response", "journal": "Survey Methods", "issn": [], "authors": [], "affiliations": [], "countries": [], "published": "2026-10-01", "created": None, "abstract": "A lottery incentive raised response rates.", "url": "x", "oa_url": None, "type": "article", "language": "en", "retracted": False})
    # OpenAlex-only records: a single passing mention is not enough, and spam titles are dropped.
    raw.append({"source": "openalex", "doi": "10.1000/oa-weak", "pmid": None, "pmcid": None, "openalex": "W7", "title": "Corporate debt maturity in China", "journal": "Applied Economics", "issn": [], "authors": [], "affiliations": [], "countries": [], "published": "2026-10-01", "created": None, "abstract": "We use local gambling preferences as a proxy for risk appetite.", "url": "x", "oa_url": None, "type": "article", "language": "en", "retracted": False})
    raw.append({"source": "openalex", "doi": "10.1000/oa-spam", "pmid": None, "pmcid": None, "openalex": "W6", "title": "Code promo 1xBet 2027: welcome bonus for sports betting", "journal": "Zenodo", "issn": [], "authors": [], "affiliations": [], "countries": [], "published": "2026-10-01", "created": None, "abstract": "Sports betting bonus code.", "url": "x", "oa_url": None, "type": "article", "language": "en", "retracted": False})
    raw.append({"source": "openalex", "doi": "10.1000/oa-good", "pmid": None, "pmcid": None, "openalex": "W5", "title": "Vulnerability and unfair profits in British gambling regulation", "journal": "European Law Open", "issn": [], "authors": [], "affiliations": [], "countries": ["GB"], "published": "2026-10-01", "created": None, "abstract": "Recent measures.", "url": "x", "oa_url": None, "type": "article", "language": "en", "retracted": False})
    papers, stats = update_index([], raw, TAX, TODAY, backfill=True)
    assert stats["dropped_irrelevant"] == 3  # Iowa Gambling Task, weak OpenAlex-only record, spam title
    assert len(papers) == 3
    assert any(p["doi"] == "10.1000/oa-good" for p in papers)
    main = [p for p in papers if p["doi"] == "10.1007/s10899-026-99999-1"][0]
    assert set(main["sources"]) == {"pubmed", "crossref"}
    assert "sports-betting" in main["topics"] and "advertising" in main["topics"]
    assert "trial" in main["designs"]
    assert main["countries"] == ["AU"] and main["regions"] == ["australia-nz"]
    assert main["first_seen"] == "2026-10-05"  # backfill uses the entrez/created date
    low = [p for p in papers if p["doi"] == "10.1000/lottery"][0]
    assert low["relevance"] == "low"
    # Second run: same record again, nightly mode; first_seen must not move.
    papers2, stats2 = update_index(papers, raw[:1], TAX, dt.date(2026, 10, 20), backfill=False)
    assert stats2["added"] == 0 and stats2["updated"] == 1
    assert [p for p in papers2 if p["doi"] == "10.1007/s10899-026-99999-1"][0]["first_seen"] == "2026-10-05"


def test_news():
    raw = [
        {"id": "a", "title": "Kalshi asks appeals court to block state enforcement", "url": "https://x/1", "source": "LSR", "feed_id": "lsr", "kind": "trade", "published": "2026-10-15", "summary": ""},
        {"id": "b", "title": "Study finds helpline calls peak in March", "url": "https://x/2", "source": "Paper", "feed_id": "gnews", "kind": "press", "published": "2026-10-15", "summary": "Problem gambling researchers report"},
        {"id": "c", "title": "Local bakery wins award", "url": "https://x/3", "source": "Paper", "feed_id": "gnews", "kind": "press", "published": "2026-10-15", "summary": ""},
    ]
    news, stats = update_news([], raw, TAX, TODAY, 10)
    assert stats["dropped_irrelevant"] == 1
    kalshi = [n for n in news if n["id"] == "a"][0]
    assert kalshi["primary"] == "prediction-markets"
    study = [n for n in news if n["id"] == "b"][0]
    assert study["primary"] == "public-health"  # public-health outranks research when both match


def test_feed_parse(monkeypatch):
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>Self-exclusion coverage in Illinois - Legal Sports Report</title><link>https://news.google.com/x</link><pubDate>Wed, 15 Oct 2026 10:00:00 GMT</pubDate><source url="https://lsr">Legal Sports Report</source><description>Short.</description></item>
    </channel></rss>"""

    class R:
        content = rss

    monkeypatch.setattr(feeds, "get", lambda s, url, **kw: R())
    items = feeds.fetch_news_feed(None, {"id": "gnews-test", "name": "Google News", "url": "x", "kind": "press"})
    assert items[0]["source"] == "Legal Sports Report"
    assert items[0]["title"] == "Self-exclusion coverage in Illinois"
    assert items[0]["published"] == "2026-10-15"


def test_helpers():
    assert norm_doi("https://doi.org/10.1111/ADD.70369.") == "10.1111/add.70369"
    s = summarize("Background: First sentence here. Second sentence is longer and adds detail. Third sentence should be cut when the cap is small.", max_chars=80)
    assert s.startswith("First sentence here.") and s.endswith("…")


# ---- hand-curated records and the editor label --------------------------
def test_curated_load_and_editor_label(tmp_path):
    from pipeline.normalize import is_editor_author
    from pipeline.sources import curated

    assert is_editor_author(["Chris Beerman"], "Chris Beerman")
    assert is_editor_author(["Beerman C", "Smith A"], "Chris Beerman")
    assert is_editor_author(["Beerman, Chris P."], "Chris Beerman")
    assert not is_editor_author(["Jane Beerman"], "Chris Beerman")
    assert not is_editor_author(["Ann Smith"], "Chris Beerman")
    assert not is_editor_author(["Chris Beerman"], None)

    p = tmp_path / "curated.yml"
    p.write_text(
        "records:\n"
        "  - draft: true\n    title: Not yet\n    doi: 10.31234/osf.io/draft1\n"
        "  - title: Missing a link\n"
        "  - doi: 10.31234/osf.io/abcde\n    title: Do losses stop mattering as betting escalates?\n"
        "    authors: [Chris Beerman]\n    journal: PsyArXiv\n    type: preprint\n    published: 2026-11-06\n"
        "    editor_authored: true\n    note: Under review.\n    topics: [prediction-markets, nonsense-topic]\n"
        "    abstract: Losses on near-coin-flip sports contracts on a prediction market act as a brake on further betting.\n",
        encoding="utf-8",
    )
    w: list[str] = []
    recs = curated.load(p, warnings=w)
    assert len(recs) == 1 and len(w) == 1
    r = recs[0]
    assert r["source"] == "curated" and r["doi"] == "10.31234/osf.io/abcde" and r["url"] == "https://doi.org/10.31234/osf.io/abcde"
    assert r["editor_authored"] and r["type"] == "preprint"

    papers, stats = update_index([], recs, TAX, TODAY, backfill=False)
    assert stats["added"] == 1
    rec = papers[0]
    assert rec["editor_authored"] is True
    assert rec["relevance"] == "high"
    assert rec["journal"] == "PsyArXiv" and rec["note"] == "Under review."
    assert "prediction-markets" in rec["topics"] and "nonsense-topic" not in rec["topics"]
    assert rec["sources"] == ["curated"]

    # The same paper arriving later from PubMed (journal version, same DOI)
    # keeps the label and the hand-entered note.
    pub = dict(r, source="pubmed", pmid="42424242", journal="Journal of gambling studies", type="article", editor_authored=False, note=None, topics=[])
    papers2, stats2 = update_index(papers, [pub], TAX, TODAY, backfill=False)
    assert stats2["updated"] == 1 and len(papers2) == 1
    assert papers2[0]["editor_authored"] is True and papers2[0]["note"] == "Under review."
    assert papers2[0]["journal"] == "Journal of Gambling Studies"

    # Automatic labelling from the author list alone.
    auto = dict(pub, doi="10.1007/s10899-026-10000-0", pmid="4343434", title="The help-seeking clock", authors=["Chris Beerman"])
    papers3, _ = update_index([], [auto], TAX, TODAY, backfill=False)
    assert papers3[0]["editor_authored"] is True
    other = dict(auto, doi="10.1007/s10899-026-10000-1", pmid="4343435", authors=["Ann Smith"])
    papers4, _ = update_index([], [other], TAX, TODAY, backfill=False)
    assert papers4[0]["editor_authored"] is False
