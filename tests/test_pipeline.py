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
    raw.append({"source": "openalex", "doi": "10.1000/lottery", "pmid": None, "pmcid": None, "openalex": "W8", "title": "Lottery incentives for survey response", "journal": "Survey Methods", "issn": [], "authors": [], "affiliations": [], "countries": [], "published": "2026-10-01", "created": None, "abstract": "A lottery incentive raised response rates.", "url": "x", "oa_url": None, "type": "article", "language": "en", "retracted": False})
    papers, stats = update_index([], raw, TAX, TODAY, backfill=True)
    assert stats["dropped_irrelevant"] == 1  # Iowa Gambling Task dropped
    assert len(papers) == 2
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
