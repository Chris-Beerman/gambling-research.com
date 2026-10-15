# gambling-research.com

An independent index of new gambling studies and policy news. Static site, rebuilt nightly by GitHub Actions and served by GitHub Pages.

## How it works

```
config/      site.yml (names, windows), sources.yml (queries and feeds), taxonomy.yml (tags, relevance rules)
pipeline/    fetch.py (nightly collection) -> data/papers.json, data/news.json, data/fetch_log.json, data/weekly/latest.json
             build.py (renders _site/ from data/ and content/ with templates/)
content/     pages/*.md (reference pages, About, methodology), digests/YYYY-MM-DD.md (weekly digest posts)
templates/   Jinja2 templates; static/ holds the stylesheet, the filter script and the favicon
.github/     workflows/site.yml: nightly fetch + commit + build + deploy; also runs on every push to main
```

Nightly at 06:17 UTC the workflow queries PubMed, OpenAlex, Crossref and the configured journal and news feeds, merges and tags the results, commits the updated `data/` files, builds the site and deploys it. A push to `main` rebuilds and deploys without fetching. Run it by hand from the Actions tab ("Build and deploy", "Run workflow"); tick *backfill* for a wider window.

## Local use

```
pip install -r requirements.txt
python -m pytest -q                 # unit tests
python -m pipeline.fetch --backfill # first collection (needs network)
python -m pipeline.build            # renders _site/
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
- Repository secrets (optional): `OPENALEX_MAILTO` and `CROSSREF_MAILTO` (an email for the APIs' polite pools), `NCBI_API_KEY` (raises PubMed's rate limit).

## Handoff: domains and mail

1. GitHub Pages: Settings → Pages → Source "GitHub Actions"; custom domain `gambling-research.com`; tick "Enforce HTTPS" once the certificate is issued.
2. DNS at Squarespace for `gambling-research.com`: A records for `@` to 185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153; CNAME for `www` to `chris-beerman.github.io`.
3. `gamblingresearch.net`: forward (301) to `https://gambling-research.com` in Squarespace's domain settings.
4. Mail: `editor@gambling-research.com` is the contact address on the site; set up forwarding for it (Squarespace domain email forwarding, or any mailbox provider) and change `contact_email` in `config/site.yml` if a different address is used.

## Licences

Code MIT; index data CC0; editorial content CC BY 4.0. See `LICENSE`.
