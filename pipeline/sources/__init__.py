"""Source adapters. Each returns a list of raw records in a common shape:

{
  "source": "pubmed" | "openalex" | "crossref" | "feed:<id>",
  "doi": str | None, "pmid": str | None, "pmcid": str | None, "openalex": str | None,
  "title": str, "journal": str | None, "issn": [str],
  "authors": [str], "affiliations": [str], "countries": [ISO2],
  "published": "YYYY-MM-DD" | None, "created": "YYYY-MM-DD" | None,
  "abstract": str, "url": str | None, "oa_url": str | None,
  "type": str | None, "language": str | None, "retracted": bool,
}
"""
