---
kind: reference
title: Index data
slug: data
description: "Download the Gambling Research Index as JSON or CSV, with every field documented, the licence, the known limits of the data, and how to cite it."
deck: The whole index as a file, in JSON or CSV, with a field-by-field dictionary. Metadata under CC0, no registration, no API key, no rate limit.
updated: 2026-11-01
---

Everything the site shows is built from these files, and they are published at the same moment the pages are. Nothing is held back for a paid tier, because there is no paid tier. If you want the index as a table, take the CSV; if you are writing code against it, take the JSON.

## Download

Each file is rewritten by the nightly build, so a link always returns the current index. The row counts below were taken on 1 November 2026 and grow by roughly 40 to 60 studies a week; the live count is on the [home page](/) and in `index_meta.json`.

| What | CSV | JSON | Rows |
|---|---|---|---|
| Studies in the main index | [papers.csv](/data/papers.csv) | [papers.json](/data/papers.json) | 7,171 |
| Studies marked possibly related | [papers-borderline.csv](/data/papers-borderline.csv) | in `papers.json`, `relevance: low` | 1,203 |
| Policy and news items | [news.csv](/data/news.csv) | [news.json](/data/news.json) | 1,372 |
| Trials and preregistrations | [trials.csv](/data/trials.csv) | [trials.json](/data/trials.json) | 715 |
| Bills | [bills.csv](/data/bills.csv) | [bills.json](/data/bills.json) | 638 |
| Court opinions and dockets | [cases.csv](/data/cases.csv) | [cases.json](/data/cases.json) | 82 |

Three smaller files describe the run rather than the field: `index_meta.json` (the rules version, the first year covered, and when the index was last re-read end to end), `fetch_log.json` (what each source returned on the last run, and which failed) and `gold_report.json` (the current accuracy scores against the hand-checked set).

The JSON files are a single array of records, UTF-8, no wrapper object. The CSV files are UTF-8 with a header row, comma-separated, minimally quoted. Where a field holds several values, the CSV joins them with a semicolon and a space (`advertising; comorbidity; equity`); the JSON keeps them as an array. `papers.csv` holds the main index only, and the records the rules were unsure about are in `papers-borderline.csv`, so a count taken from `papers.csv` matches the count the site reports.

## Licence

The index metadata — the records in these files, the tags assigned to them and the arrangement of the whole — is released under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). Take it, redistribute it, build on it commercially, with no permission needed and no attribution required, though attribution is welcome and the citation below makes it easy.

Two things in the files are not the index's to licence. Study titles and the short summaries are the publishers' and the authors', quoted here under fair use as a pointer to the original; news headlines belong to the outlets that wrote them. Reproducing a title or a 360-character summary alongside a link is what this index does and is almost certainly fine for you to do too, but republishing full abstracts is not, and the licence above does not cover it. The editorial writing on this site — the digests and the reference pages, including this one — is [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The code that builds all of it is MIT, in the [repository](https://github.com/Chris-Beerman/gambling-research.com).

## Citing the index

Cite the study, not this site, when you are citing a finding — the index is how you found the paper, not evidence for anything. Cite the index itself when you have used it as a dataset, when you are reporting a count drawn from it, or when a library guide or resource page links to it.

**APA.** Beerman, C. (2026). *Gambling Research Index* [Data set]. https://gambling-research.com/data/papers.json

**With a retrieval date,** which is the form to use for any count or analysis, because the index changes nightly:

> Beerman, C. (2026). *Gambling Research Index* [Data set]. Retrieved 1 November 2026, from https://gambling-research.com/data/papers.json

**In a sentence.** "Gambling Research Index (gambling-research.com), retrieved 1 November 2026."

For reproducibility, record the `rules_version` and `rebuilt` values from `index_meta.json` beside the retrieval date. Those two say which tagging rules produced the tags you analysed; the rules change, and when they do the whole index is re-read and re-tagged, so a count from one rules version is not strictly comparable with a count from another.

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

## Corrections

A misfiled study, a wrong setting, a missing journal: write to <editor@gambling-research.com> with the DOI and what is wrong, or open an [issue](https://github.com/Chris-Beerman/gambling-research.com/issues). Fixes go into `config/corrections.yml`, which overrides every rule and survives every rebuild, so a correction stays corrected. If you are using the data at any scale and something looks wrong in aggregate, that is worth an email too — a systematic error is more useful to hear about than a single bad record.
