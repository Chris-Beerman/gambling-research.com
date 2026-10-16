---
title: How the index works
slug: methodology
description: Where the Gambling Research index gets its studies and news, how it decides what belongs, how it tags, and how to report a mistake.
deck: Sources, search rules, tagging and known gaps, so the index can be checked and improved by anyone.
---

## Coverage

The index aims to list every new peer-reviewed article, review, commentary and preprint about gambling and closely related activities: sports betting, online gambling, casino and machine gambling, lotteries, loot boxes and simulated gambling in video games, prediction markets and event contracts, gambling-like trading, and the policy, treatment, prevention and measurement research around them. It is not limited by country or language, though English-language journals dominate the sources.

It does not try to cover gaming disorder in the video-game sense, gambling as a metaphor, decision science that uses lotteries or gambling tasks only as a method, or industry market reports.

## Sources

Each night a job queries:

- **PubMed** (NCBI E-utilities): a saved query over titles, abstracts and MeSH headings, by entry date. PubMed brings the strongest metadata (abstracts, affiliations, publication types, PubMed Central links).
- **OpenAlex**: a boolean search over titles and abstracts, by publication date, limited to journal sources (its repository records, from Zenodo and the like, are mostly promotional spam). OpenAlex brings journals outside MEDLINE, including law, economics and non-English titles, plus author country codes and free-full-text links. Because its search is loose, a study that only OpenAlex supplies must name the subject in its title or mention it more than once in the abstract.
- **Crossref**: everything registered by the journals devoted to gambling (Journal of Gambling Studies, International Gambling Studies, Journal of Gambling Issues, Journal of Behavioral Addictions, Critical Gambling Studies, Gaming Law Review), by DOI registration date.
- **Journal feeds**: the tables of contents of the gambling journals and of the addiction journals that publish gambling work most often, plus medRxiv's addiction-medicine preprints.

The exact queries and feed addresses are in [`config/sources.yml`](https://github.com/Chris-Beerman/gambling-research.com/blob/main/config/sources.yml). The table at the bottom of this page shows what each source returned on the last run and which ones failed.

## What gets kept

A record is kept when its title or abstract contains at least one strong gambling term (gambling, bettors, sports betting, wagering, casino, slot machine, lottery tickets, loot box, prediction market, self-exclusion, and so on). Records that mention only a weak term (a bare "lottery" or "bet") are kept but marked as [possibly related](/research/borderline/) and left out of the main lists; this catches economics papers that use lotteries as a method. Mentions of the Iowa Gambling Task and similar laboratory tasks are ignored when deciding relevance, so neuroscience papers that only use such a task are dropped unless they also study gambling.

Duplicates are merged by DOI, then by PubMed ID, then by normalised title. When sources disagree, PubMed's fields win, then Crossref's, then OpenAlex's; the free-full-text link comes from whichever source has one.

## Dates

Two dates appear on every entry. The date in the margin is when the study entered this index, which is the useful "new" date: journals publish online first, then in an issue, and databases index weeks later. The publication date after the journal name is the earliest date the sources report. The first build of the index used the sources' own dates to backfill, so early entries carry an approximate "added" date.

## Summaries

Each entry shows the first sentence or two of the abstract, capped at about 360 characters, as a pointer. Full abstracts are not republished; the title links to the publisher's record and the "free full text" tag links to an open copy (PubMed Central or the location OpenAlex reports) when one exists.

## Tagging

Topics, study designs and regions are assigned by keyword rules, listed in full at the bottom of this page. Rules are deliberately simple so that anyone can read them and propose a fix. They make mistakes: a paper about lottery *funding* will be tagged "lottery", and a review that mentions a trial in passing may be tagged as a trial. Country tags come from author affiliations (OpenAlex country codes, or country names in PubMed affiliation strings) and record where the authors work, not where the data were collected.

## News

News comes from the feeds of regulators, courts, the press and trade outlets, and from Google News searches for a few phrases. A headline is kept when it matches gambling terms, categorised by keyword (public health and treatment, research in the news, prediction markets, regulation and law, industry), and capped at ten items per source per day. The home page shows everything except pure industry news; the [news page](/news/) shows everything. Headlines link to their sources; nothing is rewritten.

## The digest

The weekly digest is written by the editor from a ranked shortlist the index produces each Monday (`data/weekly/latest.json`). The shortlist scores studies by journal, design, free availability and topic, which is a convenience, not a quality judgment. Choosing what to write about and what to say is editorial.

## What this index is not

It is not a systematic review, and its coverage has not been formally validated against a gold standard. Sources fail, queries miss synonyms, and some journals have no feed. Use it to see what is new, then search properly before claiming that something has not been studied.

## Corrections {#corrections}

Write to <editor@gambling-research.com> or open an issue in the [repository](https://github.com/Chris-Beerman/gambling-research.com/issues). For a misfiled study, include the DOI and what is wrong. For a missing journal or feed, include the feed address.

## Data and code

The whole index is published at [/data/papers.json](/data/papers.json) and [/data/news.json](/data/news.json) under CC0. The code is MIT-licensed. Anyone can run it for another field by changing the configuration files.
