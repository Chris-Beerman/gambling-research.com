"""PubMed via NCBI E-utilities (no key needed; NCBI_API_KEY raises the rate limit)."""
from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET

from ..common import clean_text, get, iso, norm_doi, parse_date

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def fetch(s, cfg: dict, days: int) -> list[dict]:
    api_key = os.environ.get("NCBI_API_KEY", "")
    delay = 0.12 if api_key else 0.4
    base_params = {"db": "pubmed", "retmode": "json"}
    if api_key:
        base_params["api_key"] = api_key

    ids: list[str] = []
    retmax = 500
    retstart = 0
    while True:
        params = dict(base_params, term=cfg["query"], datetype="edat", reldate=str(days), retmax=str(retmax), retstart=str(retstart))
        r = get(s, f"{EUTILS}/esearch.fcgi", params=params)
        res = r.json().get("esearchresult", {})
        batch = res.get("idlist", [])
        ids.extend(batch)
        total = int(res.get("count", 0))
        retstart += retmax
        time.sleep(delay)
        if not batch or retstart >= total:
            break

    records: list[dict] = []
    for i in range(0, len(ids), 100):
        chunk = ids[i : i + 100]
        params = {"db": "pubmed", "id": ",".join(chunk), "retmode": "xml"}
        if api_key:
            params["api_key"] = api_key
        r = get(s, f"{EUTILS}/efetch.fcgi", params=params)
        records.extend(parse_efetch(r.content))
        time.sleep(delay)
    return records


def _text(el) -> str:
    return clean_text("".join(el.itertext())) if el is not None else ""


def parse_efetch(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out: list[dict] = []
    for art in root.iter("PubmedArticle"):
        med = art.find("MedlineCitation")
        if med is None:
            continue
        article = med.find("Article")
        if article is None:
            continue
        pmid = _text(med.find("PMID"))
        title = _text(article.find("ArticleTitle")).rstrip(".")
        journal_el = article.find("Journal")
        journal = _text(journal_el.find("Title")) if journal_el is not None else ""
        issns = [_text(e) for e in journal_el.findall("ISSN")] if journal_el is not None else []
        # Abstract: join labelled sections.
        abstract_parts = []
        for ab in article.findall("./Abstract/AbstractText"):
            label = ab.get("Label")
            txt = _text(ab)
            abstract_parts.append(f"{label.title()}: {txt}" if label else txt)
        abstract = " ".join(abstract_parts)
        authors, affiliations = [], []
        for au in article.findall("./AuthorList/Author"):
            last = _text(au.find("LastName"))
            fore = _text(au.find("ForeName")) or _text(au.find("Initials"))
            coll = _text(au.find("CollectiveName"))
            name = f"{fore} {last}".strip() if last else coll
            if name:
                authors.append(name)
            for aff in au.findall("./AffiliationInfo/Affiliation"):
                affiliations.append(_text(aff))
        doi = pmcid = None
        for aid in art.findall("./PubmedData/ArticleIdList/ArticleId"):
            t = aid.get("IdType")
            if t == "doi":
                doi = norm_doi(_text(aid))
            elif t == "pmc":
                pmcid = _text(aid)
        # Dates: ArticleDate (electronic) > JournalIssue/PubDate > PubMedPubDate pubmed
        published = None
        ad = article.find("ArticleDate")
        if ad is not None:
            published = parse_date(f"{_text(ad.find('Year'))}-{_text(ad.find('Month')).zfill(2)}-{_text(ad.find('Day')).zfill(2)}")
        if not published and journal_el is not None:
            pd = journal_el.find("./JournalIssue/PubDate")
            if pd is not None:
                y, m, d = _text(pd.find("Year")), _text(pd.find("Month")), _text(pd.find("Day"))
                md = _text(pd.find("MedlineDate"))
                published = parse_date(f"{y} {m} {d}".strip()) if y else parse_date(md)
        entrez = None
        for pdate in art.findall("./PubmedData/History/PubMedPubDate"):
            if pdate.get("PubStatus") in ("entrez", "pubmed"):
                entrez = parse_date(f"{_text(pdate.find('Year'))}-{_text(pdate.find('Month')).zfill(2)}-{_text(pdate.find('Day')).zfill(2)}")
                if pdate.get("PubStatus") == "entrez":
                    break
        pubtypes = [_text(pt).lower() for pt in article.findall("./PublicationTypeList/PublicationType")]
        rtype = "article"
        if any("review" in p for p in pubtypes) and not any("systematic" in p for p in pubtypes):
            rtype = "review"
        if any(p in ("letter", "comment", "editorial") for p in pubtypes):
            rtype = "letter"
        if any("case reports" in p for p in pubtypes):
            rtype = "case-report"
        if any("preprint" in p for p in pubtypes):
            rtype = "preprint"
        retracted = any("retract" in p for p in pubtypes)
        language = _text(article.find("Language")).lower()[:3] or None
        if language == "eng":
            language = "en"
        out.append(
            {
                "source": "pubmed",
                "doi": doi,
                "pmid": pmid,
                "pmcid": pmcid,
                "openalex": None,
                "title": title,
                "journal": journal,
                "issn": [i for i in issns if i],
                "authors": authors,
                "affiliations": affiliations,
                "countries": [],
                "published": iso(published),
                "created": iso(entrez),
                "abstract": abstract,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "oa_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else None,
                "type": rtype,
                "language": language,
                "retracted": retracted,
            }
        )
    return out
