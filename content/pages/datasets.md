---
title: Datasets and public data
slug: datasets
description: Public datasets and data sources for gambling research, from transaction-level prediction-market trades to national prevalence surveys and regulator revenue reports.
deck: "Data that can be analysed without an operator's cooperation: transaction-level trading records, national surveys with gambling modules, search and helpline series, and the revenue reports regulators publish every month."
updated: 2026-10-10
---

Most gambling research is gated by data access. The sources below are open, or open to researchers on application, and several need no ethics review because they contain no identifiable people. Always read the licence and the documentation; a few notes here will be out of date.

## Transaction-level data

**Polymarket Users dataset** (Akey, Grégoire, Harvie and Martineau, 2026). Every reconciled end-user trade on Polymarket from November 2022 to March 2026, with market metadata, per-account features and profit-and-loss panels, in daily parquet files. Hosted on Hugging Face as `vgregoire/polymarket-users` under CC BY 4.0; cite the authors' working paper (SSRN 6443103). Large (hundreds of millions of trades); DuckDB reads it directly over HTTP. The one public dataset in which individual betting behaviour can be followed over time at scale.

**Polymarket and Kalshi public APIs.** Market lists, prices and resolution data are public; Polymarket's on-chain settlement makes trade histories reconstructible. Kalshi's API covers markets and prices, not other users' trades.

**Operator-provided data.** The large behavioural datasets of the 2000s and 2010s (bwin.party and others, archived by the Division on Addiction at Cambridge Health Alliance) remain available through that program's data-sharing page and are still used for secondary analyses.

## National surveys with gambling modules

| Survey | Country | Gambling content | Access |
|---|---|---|---|
| Gambling Survey for Great Britain | UK | Annual from 2023; PGSI, participation, harms; replaces the Health Survey modules | UK Data Service |
| Health Survey for England; Scottish Health Survey | UK | Gambling modules in 2012, 2015, 2016 and 2018 | UK Data Service |
| NESARC Wave 1 (2001 to 2002) and Wave 2 (2004 to 2005) | US | DSM-IV pathological gambling criteria in a representative sample of about 43,000 | NIAAA, on application |
| National Survey on Gambling Attitudes and Gambling Experiences (NGAGE) | US | NCPG's national survey, 2018 and 2021 waves; published reports with state-level estimates | NCPG reports |
| Massachusetts SEIGMA baseline and follow-up surveys; MAGIC cohort | US | The most detailed US state series, built around casino openings, with a longitudinal cohort | Massachusetts Gaming Commission and UMass Amherst |
| Canadian Community Health Survey, 2018 rapid-response gambling module | Canada | PGSI and participation, about 25,000 respondents | Statistics Canada (RDC or PUMF) |
| HILDA | Australia | Gambling module in several waves since 2015 (participation, spend, PGSI) | Melbourne Institute, on application |
| Swelogs | Sweden | Longitudinal gambling study, 2008 onward | Public Health Agency of Sweden |
| Greo Dataverse | Canada and international | Curated gambling datasets, including the Canadian Problem Gambling Index validation data and Manitoba surveys | borealisdata.ca/dataverse/GREO |

## Search, helpline and treatment series

**Google Trends** gives relative search interest for any term basket by week and by state back to 2004. Pulls are samples, so average several retrieval days; treat the result as help-seeking intent, not prevalence. The published template is Yeola and colleagues (*JAMA Internal Medicine*, 2025), who used it to estimate the effect of sports-betting legalization on searches for gambling-addiction help.

**Helpline volumes.** The National Problem Gambling Helpline (1-800-GAMBLER) publishes aggregate call statistics periodically; some state councils publish monthly intake counts (Pennsylvania's are the most consistent). Monthly series for most states have to be requested.

**Treatment episode data.** Public treatment-admissions datasets in the US (TEDS) do not record gambling as a primary problem, which is itself a finding. State-funded treatment programs (Illinois, Massachusetts, Minnesota, Oregon and others) publish annual counts in their reports.

## Regulator and revenue data

Every US state with legal sports betting publishes monthly handle, revenue and tax figures; Illinois, New Jersey, Pennsylvania and Nevada publish the most detail (by operator and by product). The Illinois Gaming Board also publishes monthly casino and video-gaming-terminal reports by venue, which make county-level density analyses possible. Legal Sports Report maintains a compiled revenue tracker across states. UNLV's Center for Gaming Research publishes historical Nevada and national revenue tables. The UK Gambling Commission publishes detailed industry statistics several times a year.

## Self-exclusion and consumer-protection data

Enrolment counts for state self-exclusion programs appear in regulator annual reports (Illinois publishes its statewide program's enrolment figure; several others do). The UK's GAMSTOP and Sweden's Spelpaus publish registration counts. Documents, not data: operators' terms, help centres and responsible-gambling pages can be audited systematically, and a few published audits show how.

## Advertising and marketing data

The Google Ads Transparency Center and Meta Ad Library expose currently running creatives by advertiser and are the cleanest sampling frame for served gambling advertising; neither back-fills, so collection has to start before the period of interest. Affiliate listings (Legal Sports Report and others) record welcome-offer terms and state availability daily.

## Literature data

[PubMed](https://pubmed.ncbi.nlm.nih.gov) (E-utilities), [OpenAlex](https://openalex.org) (API, no key), [Crossref](https://api.crossref.org) and [Semantic Scholar](https://www.semanticscholar.org) (API key for volume) are free and are what this site's own [index](/methodology/) runs on. Retraction Watch's database is free through Crossref.

*A dataset missing here? Write to <editor@gambling-research.com>.*
