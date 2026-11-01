---
kind: reference
title: Using this data
slug: data-use
description: The data and charts on this site are free to reuse with credit. The licences, the files, how the index stays independent of the gambling industry, and how to reach the editor on deadline.
deck: Every page of this index publishes its rows as a CSV at a fixed address, and every chart carries its source inside the image. Take any of it. Credit and a link are all that is asked.
updated: 2026-11-01
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

## Stable addresses

The addresses on this page are meant to be linked to and scripted against, and they do not move. If one ever has to change, the old address will redirect. The files are rebuilt every night, so a script that fetches one weekly will see the window roll forward; `dateModified` in the page's structured data and the as-of date in the citation both tell you which night you have.

Each page also publishes `schema.org/Dataset` metadata, so the datasets can be found through [Google Dataset Search](https://datasetsearch.research.google.com/) and read by anything else that understands the vocabulary. The whole set is catalogued as a `DataCatalog` on this page.

## Corrections

A misfiled study, a wrong date, a bill at the wrong stage: write to <editor@gambling-research.com> or [open an issue](https://github.com/Chris-Beerman/gambling-research.com/issues). Corrections are made in the data, not quietly on the page, so they carry forward into every file and every rebuild — and if you have already published a figure that a correction changes, say so and you will be told what moved.
