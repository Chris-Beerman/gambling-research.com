---
title: Data use and reuse
slug: data-use
description: The gambling data on this site is free to reuse. What is released under CC0, what belongs to publishers, how to attribute it, and how to reach the editor on deadline.
deck: The trackers on this site are public domain. Take them, chart them, build on them; a citation is requested, not required.
cite: false
---

Four datasets on this site are compiled here and published nowhere else: new gambling **studies**, registered **trials and preregistrations**, **bills** in the state legislatures and Congress, and **court** opinions and dockets. They update nightly. This page says what you may do with them.

## What you may do

The four trackers are released under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) — placed in the public domain. You may copy, republish, chart, redistribute, text-mine, feed them to a model and sell work built on them, with no permission and no obligation. CC0 asks nothing of you.

A citation is **requested, not required**. It is requested because it helps people find the source and check the numbers, and because it is how this site stays worth maintaining. Each tracker page carries a citation line ready to copy.

## What is not ours to license

Two things on this site are not covered by that release, and this is worth being exact about.

**Publishers' material.** Study titles, the short abstract excerpts and the news headlines in the data belong to the publishers and outlets that produced them. This site reproduces only enough to identify a record and links to the original. CC0 covers the compilation around them — the identifiers, dates, tags, topic and design classifications, settings, and the structure that makes the set queryable — not the publishers' text.

**Facts versus compilation.** The bills, rulings, trial registrations and publication records underneath these trackers are public records and matters of fact. Nobody owns them, this site included. What is released here is the compiled, cleaned and classified set: the work of collecting, deduplicating and tagging. Where a figure originates with an agency — a legislature, a court, a registry — cite that agency as the source of the figure and this site as where you got the compiled version.

**Editorial text.** The weekly digest, the reference pages and the written analysis are licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): reuse them, commercially included, with attribution to the author and a link to the page.

**Code.** The software that builds the site is MIT-licensed and [on GitHub](https://github.com/Chris-Beerman/gambling-research.com).

## The downloads

Every tracker is published as JSON and as CSV at a stable URL. The CSVs carry one row per record and a fixed column order, so a script written against them keeps working.

| Dataset | Page | JSON | CSV |
|---|---|---|---|
| Studies and preprints | [/research/](/research/) | [papers.json](/data/papers.json) | [papers.csv](/data/papers.csv) |
| Trials and preregistrations | [/trials/](/trials/) | [trials.json](/data/trials.json) | [trials.csv](/data/trials.csv) |
| Bills | [/bills/](/bills/) | [bills.json](/data/bills.json) | [bills.csv](/data/bills.csv) |
| Courts | [/courts/](/courts/) | [cases.json](/data/cases.json) | [cases.csv](/data/cases.csv) |

Also published, same terms: [index_meta.json](/data/index_meta.json) (what period the index covers and when it was last rebuilt), [fetch_log.json](/data/fetch_log.json) (what each nightly run read and whether a source failed), [gold_report.json](/data/gold_report.json) (how the tagging rules score against a hand-checked set) and [weekly/latest.json](/data/weekly/latest.json) (the ranked shortlist the digest is drafted from).

The policy news feed is published as [news.json](/data/news.json) but has no CSV and no dataset record. It is a feed of other outlets' headlines rather than a compilation of this site's own, and it is not offered as a dataset.

## Updates and stability

The trackers are rebuilt every night and the files are replaced in place, so a URL always returns the current set rather than a snapshot. Links do not go stale and nothing is moved to a dated archive. Each dataset's own page states when it was last updated.

If a classification rule changes, the whole index since January 2022 is re-read and re-tagged, then scored against a hand-checked set before anything is published; a run that scores below the threshold is discarded and nothing changes that night. [How the index works](/methodology/) describes this in full.

If you need a stable snapshot for a publication — the exact set as it stood on the day you ran your analysis — ask and one will be sent.

## Funding

This site takes no funding, advertising, data or affiliate income from gambling operators, suppliers, affiliates, lotteries, prediction-market exchanges or bodies they fund. It carries no advertising and no tracking beyond what the hosting provider logs.

It is edited by Chris Beerman, LCSW, CADC, a clinical social worker in Chicago who treats gambling disorder and runs a private practice, [Chicago Addiction Therapy](https://www.chicagoaddictiontherapy.com/). That relationship, and every other interest worth declaring, is set out on the [About page](/about/) rather than buried here.

## For reporters and researchers

Write to <editor@gambling-research.com>.

**On deadline.** Say so in the subject line and you will get an answer the same day, evenings and weekends included. If the answer is that the data does not support what you are asking, you will get that instead.

**Figures broken out differently.** If you need a cut the site does not publish — by state, by product, by court, by year, a series rather than a snapshot — ask. These are the editor's own datasets and reshaping one is usually a few minutes' work.

**Background.** The editor is also available to explain what these numbers look like clinically: who actually turns up for treatment, what self-exclusion does and does not reach, and where a published figure is weaker than it appears. Attributed or on background, whichever suits.

**What will not happen.** No embargoed access, no exclusives and no copy approval. Everything here is public to everyone at the same time.

## Corrections

A misfiled study, a wrong date, a bill at the wrong stage: write to <editor@gambling-research.com> or [open an issue](https://github.com/Chris-Beerman/gambling-research.com/issues). Corrections are made in the data rather than quietly on the page, so they carry forward into every later copy and into anything built on it. Rules and hand corrections are version-controlled and public.
