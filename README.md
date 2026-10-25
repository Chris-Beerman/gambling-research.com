# gambling-research.com

An independent index of new gambling studies and policy news. Static site, rebuilt nightly by GitHub Actions and served by GitHub Pages.

## How it works

```
config/      site.yml (names, windows), sources.yml (queries, feeds, backfill_from), taxonomy.yml (tags, relevance rules,
             rules version), corrections.yml (hand fixes that override every rule)
pipeline/    fetch.py (nightly collection) -> data/papers.json, data/news.json, data/trials.json, data/bills.json,
             data/cases.json, data/fetch_log.json, data/weekly/latest.json
             build.py (renders _site/ from data/ and content/ with templates/; search_index.mjs writes _site/pagefind/)
             gold.py (scores the index against the hand-checked studies in tests/gold/labels.yml)
content/     pages/*.md (reference pages, About, methodology), digests/YYYY-MM-DD.md (weekly digest posts)
templates/   Jinja2 templates; static/ holds the stylesheet, the filter script and the favicon
.github/     workflows/site.yml: nightly fetch + commit + build + deploy; also runs on every push to main
```

Nightly at 06:17 UTC the workflow queries PubMed, OpenAlex, Crossref and the configured journal and news feeds, plus the trackers (ClinicalTrials.gov, ISRCTN and OSF for trials; Open States, GovInfo and Congress.gov for bills; CourtListener for courts), merges and tags the results, commits the updated `data/` files, builds the site and deploys it. A push to `main` rebuilds and deploys without fetching. Run it by hand from the Actions tab ("Build and deploy", "Run workflow"); tick *backfill* for a wider window.

## Tagging, corrections and rebuilds

Tags come in three layers, first answer wins: `config/corrections.yml` (hand fixes, keyed by DOI), then PubMed's own indexing (publication types for designs, MeSH geographic headings for the study setting), then the keyword rules in `config/taxonomy.yml`. Each study records both its **setting** (`settings`: where it was done) and its **author countries** (`countries`: where the authors work); the entry shows the setting.

Fix one study: add it to `config/corrections.yml` and push. Change a rule: edit `config/taxonomy.yml`, **bump `version`**, run `python -m pytest -q`, and push. The next nightly run sees the new version, re-reads every study since `backfill_from` (in `config/sources.yml`) month by month, re-reads anything older by DOI or PubMed ID, and re-applies the rules to all of it. It then scores the result against `tests/gold/labels.yml`; if the scores fall below the thresholds in that file, the run stops and nothing is committed or published. `data/index_meta.json` records the last complete rebuild. A rebuild that could not read a source re-tags what it got and removes nothing; the next night tries again.

## Local use

```
pip install -r requirements.txt
npm ci                              # Pagefind, for the search index (optional locally)
python -m pytest -q                 # unit tests
python -m pipeline.fetch --backfill # first collection (needs network)
python -m pipeline.fetch --only trials,bills,courts   # just the trackers
python -m pipeline.fetch --rebuild  # re-read everything since backfill_from and re-tag (needs network)
python -m pipeline.gold check       # score data/papers.json against the hand-checked set
python -m pipeline.build            # renders _site/ (and _site/pagefind/ when Pagefind is installed)
python -m http.server -d _site 8000
```

When `data/papers.json` is empty the build falls back to `pipeline/fixtures/` so the templates can be checked without data.

## Writing a digest

Create `content/digests/YYYY-MM-DD.md`:

```
---
title: Losses as a brake, the Sixth Circuit, and who gets the push notification
date: 2026-10-19
summary: One-sentence deck shown on the home page and in the feed.
---
Body in Markdown. Link each study to its publisher record.
```

`data/weekly/latest.json` holds a ranked shortlist of the past seven days (studies and policy news) to draft from. A draft with `draft: true` in its front matter is not published.

## Settings worth knowing

- `config/site.yml`: title, descriptor, editor, contact address, how many days each page shows.
- `config/sources.yml`: add or disable a source with `enabled: false`; news feeds take a `kind` that sets the fallback category.
- `config/taxonomy.yml`: topic, design and news-category rules (regular expressions), region mapping, and the relevance rules that decide what is kept.
- Repository secrets: `OPENALEX_API_KEY` (required for the OpenAlex source; free at openalex.org/settings/api) and `OPENSTATES_API_KEY` (required for state bills; free at openstates.org/accounts/profile). Recommended: `CONGRESS_API_KEY` (an api.data.gov key from api.congress.gov/sign-up, used for both GovInfo and Congress.gov; without it the shared DEMO_KEY is used and capped at 25 requests a run) and `COURTLISTENER_API_TOKEN` (free account at courtlistener.com; anonymous access is limited to about 100 requests a day per address, shared with every other GitHub Actions runner on the same address). Optional: `OSF_TOKEN` (raises OSF's rate limit), `OPENALEX_MAILTO` and `CROSSREF_MAILTO` (an email for the APIs' polite pools), `NCBI_API_KEY` (raises PubMed's rate limit).

## Handoff: domains and mail

1. GitHub Pages: Settings → Pages → Source "GitHub Actions"; custom domain `gambling-research.com`; tick "Enforce HTTPS" once the certificate is issued.
2. DNS at Squarespace for `gambling-research.com`: A records for `@` to 185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153; CNAME for `www` to `chris-beerman.github.io`.
3. `gamblingresearch.net`: forward (301) to `https://gambling-research.com` in Squarespace's domain settings.
4. Mail: `editor@gambling-research.com` is the contact address on the site; set up forwarding for it (Squarespace domain email forwarding, or any mailbox provider) and change `contact_email` in `config/site.yml` if a different address is used.

## Licences

Code MIT; index data CC0; editorial content CC BY 4.0. See `LICENSE`.
