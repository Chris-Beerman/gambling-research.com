---
kind: reference
title: Using this data
slug: data-use
description: The data and charts on this site are free to reuse with credit. The licences, the files, how the index stays independent of the gambling industry, and how to reach the editor on deadline.
deck: Every page of this index publishes its rows as a CSV at a fixed address, and every chart carries its source inside the image. Take any of it. Credit and a link are all that is asked.
updated: 2026-11-01
cite: false
---

## Free to reuse

**The data is CC0.** The index's own records — what each study, trial, bill or case is, when it entered the index, and the topic, design, setting and stage tags applied to it — are released into the public domain under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). Copy it, republish it, chart it, merge it with your own, build something commercial on it. No permission, no registration, no email required.

**The charts are CC BY 4.0.** Use them as they are, in print or online, with the credit that is already printed inside the image. Each chart is a plain SVG at its own address, so it can be linked, embedded or downloaded without going through this page.

**What is not mine to license.** Study titles, abstract excerpts and news headlines belong to their publishers. They appear here as short excerpts with a link to the source, and the CSVs carry the DOI or registry number so you can go to the record itself. Cite the underlying study, not this index, whenever the claim is the study's.

The credit line that is wanted, when a link is possible:

> Gambling Research Index (gambling-research.com)

and when it is not, the site's name alone is enough.

Every data page also prints a full suggested citation, with a button that copies it. That is the one to use in anything that will be checked later, because it carries the as-of date:

> Beerman, C. (2026). New gambling research [data set]. Gambling Research Index. Data as of November 1, 2026. https://gambling-research.com/research/

The index is rebuilt every night. A figure quoted from it without a date cannot be checked against it, and within a week it will not match.

<!-- catalogue -->

## No industry money

This site takes no funding, advertising, data or affiliate income from gambling operators, suppliers, affiliates, lotteries, prediction-market exchanges or any body they fund. It carries no advertising and no tracking beyond what the hosting provider logs. Nothing enters the index because someone asked, and nothing is kept out because someone objected. The full declaration of interests, including the editor's clinical practice, is on the [about page](/about/).

That matters for how you can use this. There is no sponsor whose name has to appear beside the data, no embargo, and no condition that a finding be described a particular way.

## For reporters, on deadline

Questions about anything on this site, or about what the research actually says, are welcome, and so are questions that end with "is this figure right?".

- **Email:** <editor@gambling-research.com>
- **Reply time:** email is answered within one working day. If you are filing today, put *deadline* in the subject line and it goes to the front of the queue. Office hours are US Central.
- **Attribution:** Chris Beerman, LCSW, CADC, editor of the Gambling Research Index and a clinical social worker in Chicago who treats gambling disorder.

What there is to say, on the record: what the published literature does and does not show on a given question; where a widely repeated number came from and whether it holds up; what sports-betting and prediction-market cases look like from a treatment room; how self-exclusion and blocking actually work in practice; and what is moving through the legislatures and the courts this month.

What there is not: legal advice, comment on any individual person or company's conduct, anything about a client, a position on behalf of any organisation, or a prevalence estimate invented on the spot. If a question is outside what the evidence supports, the answer will say so, which is usually more useful on deadline than a confident guess.

A standing offer: if you are checking a gambling statistic against the literature and cannot find the source, send it. Tracing a number to its origin is most of what this index is for.

## What is in the files

Every CSV follows the same conventions.

- **UTF-8, comma-separated, with a header row and no preamble.** `pandas.read_csv(url)` works directly on the address.
- **Dates are ISO 8601** (`2026-11-01`), and all timestamps are UTC.
- **Lists are separated by a vertical bar** (`sports-betting|youth`), because topics, authors and sponsors are often several. A value that contained a bar has it replaced with a slash.
- **Booleans are `true` and `false`;** missing values are empty, never `NA` or `0`.
- **Countries are ISO 3166-1 alpha-2 codes.** One trap worth knowing: Namibia's code is `NA`, which pandas reads as a missing value unless you pass `keep_default_na=False` or `na_values=[]`. The same applies to anything else that treats `NA` as null.
- **One row per record,** with the index's own stable `id` in the first column and the publisher's identifier — DOI, PubMed ID, registry number, bill number, docket number — in a column of its own.
- **Tags are assigned by rule, not by hand,** apart from the corrections listed on the [methodology page](/methodology/). A record can carry several topic tags, so topic counts sum to more than the number of records. The rules, and the score against a hand-checked set, are published.

Each file holds exactly the rows its page shows, so the page, its chart, its CSV and its citation always describe the same set. The complete index, with no window applied, is in the JSON files: [papers.json](/data/papers.json), [news.json](/data/news.json), [trials.json](/data/trials.json), [bills.json](/data/bills.json) and [cases.json](/data/cases.json).

## Studies: field by field

One record per study. Every record carries every field; a field with nothing in it is an empty string, an empty array or `null` rather than absent.

| Field | What it holds |
|---|---|
| `id` | The index's own identifier, stable across rebuilds: `doi:<doi>` where a DOI exists, otherwise `pmid:<id>` or a URL-derived key. Use this to join, not the title. |
| `doi` | DOI, lowercase, no `https://doi.org/` prefix. Empty for the few records that have none. |
| `pmid` | PubMed identifier, where the record came from or matched PubMed. |
| `pmcid` | PubMed Central identifier, where a free copy sits in PMC. |
| `openalex` | OpenAlex work identifier (`W…`). |
| `title` | Article title as the source gives it, in its original language. |
| `journal` | Journal name. PubMed's abbreviated forms are expanded for the journals listed in `config/site.yml`; others appear as the source wrote them, so the same journal can appear under two spellings. |
| `authors` | Author names in order, as the source gives them. An array in JSON; semicolon-joined in CSV. Not disambiguated, so the same person may appear under more than one form. |
| `published` | Earliest publication date any source reports, `YYYY-MM-DD`. Day precision is often nominal — a journal that reports only a month or an issue year lands on the first of the month or the year. Can sit in the future for an article in an issue not yet dated. |
| `year` | Year of `published`. |
| `created` | When the source database first registered the record. |
| `first_seen` | **The date this index first saw the study.** This is the field the site sorts and filters on, and the one to use for "what is new"; `published` is for the citation. |
| `summary` | First sentence or two of the abstract, about 360 characters, ending in an ellipsis. Not the full abstract, and not written by the index. |
| `url` | Link to the publisher's record, normally `https://doi.org/…`. |
| `oa_url` | Link to a free full text (PubMed Central, or whatever location OpenAlex reports) when one is known. Empty does not prove the study is paywalled. |
| `sources` | Which sources supplied or confirmed the record: `pubmed`, `openalex`, `crossref`, or `feed:<id>` for a journal feed. A record found by one source only is weaker evidence than one found by three. |
| `type` | `article`, `review`, `letter`, `editorial`, `case-report` or `preprint`, from the source's own type. |
| `topics` | Topic slugs, from the rules documented on the [methodology page](/methodology/): `advertising`, `casino`, `cognition`, `comorbidity`, `equity`, `families`, `financial-harm`, `industry`, `lived-experience`, `loot-boxes`, `lottery`, `measurement`, `older-adults`, `online-gambling`, `policy`, `prediction-markets`, `prevalence`, `prevention`, `self-exclusion`, `sports-betting`, `trading`, `treatment`, `veterans`, `youth`. Empty means no topic reached its threshold, not that the study has no subject. |
| `designs` | Study designs: `trial`, `protocol`, `review`, `survey`, `longitudinal`, `qualitative`, `experiment`, `behavioral-data`, `case-report`, `commentary`. **Empty means not recorded, never "no design"** — this is the least reliable field in the file, and the section below says how unreliable. |
| `design_basis` | `pubmed` where the designs came from NLM's own publication types, `rules` where they came from keyword rules. `pubmed` is the more trustworthy of the two. |
| `settings` | **Where the study was done,** as ISO 3166-1 alpha-2 country codes. From MeSH geographic headings, the countries named in the title, or failing those the countries named in the abstract when few enough to be a setting rather than a comparison. |
| `setting_regions` | Those settings grouped into regions: `us`, `canada`, `uk-ireland`, `europe`, `asia`, `middle-east`, `africa`, `australia-nz`, `latin-america`. |
| `countries` | **Where the authors work,** from their affiliations. Not the same as `settings`: an Iranian survey with an Australian co-author has `settings: ["IR"]` and `countries: ["IR", "AU"]`. Confusing these two is the most common way to misread this file. |
| `regions` | `countries` grouped into the same regions as `setting_regions`. |
| `language` | ISO 639-1 code of the article's own language. Empty where no source reported one, which is not the same as English. |
| `relevance` | `high` for the main index, `low` for records that matched only a weak term and are shown on the [possibly related](/research/borderline/) page. The site's counts and every page except that one use `high` only. |
| `retracted` | `true` where a source flags the record as retracted. Only a handful are flagged, and absence is not evidence that a paper stands. |

## What the other files hold

**News** (`news.csv`): `source` is the outlet, `feed_id` the feed it arrived on, `kind` the type of publisher (`regulator`, `trade`, `press`), `categories` and `primary` the subject (`regulation`, `prediction-markets`, `research`, `public-health`, `industry`). Headlines are the outlet's own words and `url` often points at a Google News redirect rather than the outlet directly.

**Trials** (`trials.csv`): `registry` is `clinicaltrials`, `isrctn` or `osf`, and `kind` separates a `trial` from a `registration`. `status` is the registry's own word, not the index's assessment — ClinicalTrials.gov's `unknown` means the sponsor has not updated the record in two years. `results_posted` means results appear in the registry, not that a paper exists. `first_posted` is when the record appeared in the registry; the index's own first sighting is not kept for trials.

**Bills** (`bills.csv`): `level` is `state` or `federal`, `jurisdiction` the state or `United States`. `stage` is derived from the legislature's recorded actions (`introduced`, `committee`, `reported`, `passed-one`, `passed-both`, `enacted`, `vetoed`, `failed`) and can lag the legislature's own site by a day or two. `identifier` is the bill number as the legislature writes it, so joining across sessions needs `session` too.

**Cases** (`cases.csv`): `kind` separates an `opinion` from a `docket`. `court_level` is `scotus`, `federal-appellate`, `federal-district`, `state-supreme`, `state-appellate` or `state-trial`. `snippet` is CourtListener's extract, not a summary. This file is the thinnest of the five: state trial courts and most state dockets are not in CourtListener at all, so treat it as a watch list.

## Before you analyse this

The index is a current-awareness tool that happens to be published as data. It was not built as a research corpus, and four things will bite an analysis that assumes otherwise.

**It is not a systematic review and has not been validated against a gold standard.** Coverage has been checked against 138 studies tagged by hand, and the current scores are in [`gold_report.json`](/data/gold_report.json) and on the [methodology page](/methodology/). On a separate random sample of 59 studies checked before any further rule changes, the rules placed 95% correctly in or out of the index, gave the right setting for 91% and the right key topics for 86%, but gave the complete, correct set of designs for only 59%. Most design errors were blanks rather than wrong labels. **Do not treat `designs` as a reliable variable**, and do not report "no studies have examined X" on the strength of a query against this file.

**Coverage starts in January 2022.** Earlier work is absent, not rare. The 2022 to late 2026 records were collected in one backfill pass and carry approximate `first_seen` dates, so a time series of `first_seen` shows when the index was built, not when the field published.

**English-language journals dominate the sources,** and `language` is empty for several hundred records. A count by language understates non-English work.

**Tags change.** When a rule changes, the next nightly run re-reads and re-tags the whole index, so the same `id` can carry different `topics` from one month to the next. Keep the copy you analysed, and record `rules_version`.

Deliberately out of scope, so you will not find them here: gaming disorder in the video-game sense, gambling used as a metaphor, decision science that uses gambling tasks only as a method, and industry market reports.

## Stable addresses

The addresses on this page are meant to be linked to and scripted against, and they do not move. If one ever has to change, the old address will redirect. The files are rebuilt every night, so a script that fetches one weekly will see the window roll forward; `dateModified` in the page's structured data and the as-of date in the citation both tell you which night you have.

Each page also publishes `schema.org/Dataset` metadata, so the datasets can be found through [Google Dataset Search](https://datasetsearch.research.google.com/) and read by anything else that understands the vocabulary. The whole set is catalogued as a `DataCatalog` on this page.

## Corrections

A misfiled study, a wrong date, a bill at the wrong stage: write to <editor@gambling-research.com> or [open an issue](https://github.com/Chris-Beerman/gambling-research.com/issues). Corrections are made in the data, not quietly on the page, so they carry forward into every file and every rebuild — and if you have already published a figure that a correction changes, say so and you will be told what moved.
