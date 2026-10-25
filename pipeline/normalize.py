"""Merge raw records into the canonical index, dedupe, score relevance, tag."""
from __future__ import annotations

import datetime as dt
import re

from . import countries
from .common import CONFIG_DIR, load_yaml, norm_title, stable_id, summarize

_SMALL_WORDS = {"of", "and", "the", "in", "for", "on", "a", "an", "to", "at", "by", "or", "de", "et", "la", "le", "les", "des", "du", "der", "die", "das", "und", "für", "von", "&"}
_PAREN = re.compile(r"\s*\([^)]*\)\s*$")


def _title_case(name: str) -> str:
    words = name.split()
    out = []
    for i, w in enumerate(words):
        if w.isupper() and len(w) > 1:  # JAMA, BMJ, PLOS
            out.append(w)
        elif i > 0 and w.lower() in _SMALL_WORDS:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def load_corrections() -> dict:
    path = CONFIG_DIR / "corrections.yml"
    if not path.exists():
        return {}
    return load_yaml("corrections.yml") or {}


class Corrections:
    """Hand corrections from config/corrections.yml, keyed by DOI or "pmid:NNN".
    They are applied after every automatic rule, so a fix made once survives
    every nightly run and every rebuild."""

    FIELDS = ("topics", "designs", "settings", "relevance")

    def __init__(self, cfg: dict):
        self.by_key: dict[str, dict] = {}
        for key, entry in (cfg.get("studies") or {}).items():
            k = str(key).strip().lower()
            k = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", k)
            self.by_key[k] = entry or {}

    def find(self, rec: dict) -> dict | None:
        if rec.get("doi") and rec["doi"].lower() in self.by_key:
            return self.by_key[rec["doi"].lower()]
        if rec.get("pmid") and f"pmid:{rec['pmid']}" in self.by_key:
            return self.by_key[f"pmid:{rec['pmid']}"]
        if rec.get("id") and rec["id"].lower() in self.by_key:
            return self.by_key[rec["id"].lower()]
        return None

    def apply(self, rec: dict) -> dict | None:
        """Return the corrected record, or None when it is excluded."""
        c = self.find(rec)
        if not c:
            return rec
        if c.get("exclude"):
            return None
        for f in self.FIELDS:
            if f in c and c[f] is not None:
                rec[f] = list(c[f]) if isinstance(c[f], (list, tuple)) else c[f]
        for f in ("topics", "designs", "settings"):
            for x in c.get(f"add_{f}") or []:
                if x not in rec.get(f, []):
                    rec.setdefault(f, []).append(x)
            for x in c.get(f"remove_{f}") or []:
                if x in rec.get(f, []):
                    rec[f].remove(x)
        if c.get("settings") is not None or c.get("add_settings") or c.get("remove_settings"):
            rec["settings"] = [countries.normalise_code(x) for x in rec.get("settings", []) if countries.normalise_code(x)]
        for f in ("language", "title_en"):
            if c.get(f):
                rec[f] = c[f]
        rec["corrected"] = True
        return rec


class JournalNames:
    """PubMed reports journals in sentence case with subtitles ("Journal of
    gambling studies", "Addiction (Abingdon, England)"); feeds and Crossref use
    the proper name. Map everything to one display name."""

    def __init__(self, known: list[str]):
        self.known = {k.lower(): k for k in known}

    def canonical(self, name: str | None) -> str:
        if not name:
            return ""
        n = name.strip()
        n = n.split(" : ")[0].strip()  # "Psychology of addictive behaviors : journal of the Society..."
        n = _PAREN.sub("", n)  # "Addiction (Abingdon, England)"
        key = n.lower()
        if key in self.known:
            return self.known[key]
        # Sentence-case names from PubMed: first letter capital, the rest lower.
        if n == n[:1].upper() + n[1:].lower() and " " in n:
            return _title_case(n)
        return n


LANG_639_2 = {
    "eng": "en", "fre": "fr", "fra": "fr", "dut": "nl", "nld": "nl", "spa": "es", "chi": "zh", "zho": "zh", "ger": "de", "deu": "de",
    "ita": "it", "por": "pt", "swe": "sv", "nor": "no", "nob": "no", "dan": "da", "fin": "fi", "pol": "pl", "tur": "tr", "jpn": "ja",
    "kor": "ko", "rus": "ru", "ukr": "uk", "ara": "ar", "per": "fa", "fas": "fa", "ind": "id", "may": "ms", "msa": "ms", "tha": "th",
    "heb": "he", "hun": "hu", "cze": "cs", "ces": "cs", "gre": "el", "ell": "el", "ice": "is", "isl": "is", "slv": "sl", "hrv": "hr",
    "srp": "sr", "rum": "ro", "ron": "ro", "bul": "bg", "lit": "lt", "lav": "lv", "est": "et", "vie": "vi", "cat": "ca",
}
# When no source reports a language, a gambling word in the title often names it.
_LANG_HINTS = [
    ("fi", r"rahapel|peliriippuv|pelaami|ongelmapel"), ("sv", r"spelberoende|spelproblem|spel om pengar|spelande"), ("no", r"pengespill"),
    ("da", r"pengespil|ludomani"), ("de", r"gl[üu]cksspiel|sportwett|spielsucht"), ("fr", r"jeux? d.argent|paris sportifs|jeu pathologique"),
    ("es", r"apuestas|juego patol|juegos? de azar|ludopat[ií]a"), ("pt", r"apostas|jogos? de azar|jogo patol"), ("it", r"azzardo|scommess"),
    ("tr", r"kumar(baz| ba| oy| dav)|\\bbahis"), ("id", r"\bjudi\b|perjudian|\b(yang|dan|terhadap|pada|dalam|melalui|pengaruh|analisis|remaja|mahasiswa)\b"),
    ("ru", r"азартн"), ("zh", r"賭博|赌博|博彩|彩票"), ("ko", r"도박"), ("ja", r"ギャンブル"), ("ar", r"قمار|مراهن|ميسر"),
]
_LANG_HINT_RE = [(code, re.compile(p, re.I)) for code, p in _LANG_HINTS]


def norm_language(code, title: str = "") -> str | None:
    c = (code or "").strip().lower() if isinstance(code, str) else ""
    c = LANG_639_2.get(c, c)
    if c in ("ang", "und", "mul", "zxx"):
        c = ""
    if len(c) == 2:
        return c
    hints = [lang for lang, pat in _LANG_HINT_RE if pat.search(title or "")]
    if len(hints) == 1:
        return hints[0]
    if hints and "id" in hints and len(set(hints) - {"id"}) == 0:
        return "id"
    return None


class Assessment:
    """What the relevance rules found in a title and abstract."""

    __slots__ = ("relevance", "title_hit", "abstract_hits", "first_abstract_hit")

    def __init__(self, relevance, title_hit=False, abstract_hits=0, first_abstract_hit=None):
        self.relevance = relevance
        self.title_hit = title_hit
        self.abstract_hits = abstract_hits
        self.first_abstract_hit = first_abstract_hit


class Taxonomy:
    def __init__(self, cfg: dict, corrections: dict | None = None):
        self.cfg = cfg
        self.version = int(cfg.get("version", 1))
        site = load_yaml("site.yml")
        self.journals = JournalNames(list(site.get("core_journals", [])) + list(site.get("journal_names", [])))
        rel = cfg.get("relevance", {})
        self.strong = [re.compile(p, re.I) for p in rel.get("strong", [])]
        self.ambiguous = [re.compile(p, re.I) for p in rel.get("ambiguous", [])]
        self.weak = [re.compile(p, re.I) for p in rel.get("weak", [])]
        self.exclude = [re.compile(p, re.I) for p in rel.get("exclude_contexts", [])]
        self.drop = [re.compile(p, re.I) for p in rel.get("drop_titles", [])]
        self.exclude_journals = [re.compile(p, re.I) for p in rel.get("exclude_journals", [])]
        self.oa_only_hits = int(rel.get("openalex_only_abstract_hits", rel.get("single_source_min_abstract_hits", 3)))
        self.oa_only_early = int(rel.get("openalex_only_early_chars", 400))
        self.topics = [(t["slug"], t["label"], [re.compile(p, re.I) for p in t["patterns"]]) for t in cfg.get("topics", [])]
        self.topic_min = {t["slug"]: int(t.get("min_hits", 1)) for t in cfg.get("topics", [])}
        # Designs: (slug, label, title patterns, abstract patterns). The label table on
        # the methodology page shows both pattern sets.
        self.designs = []
        self.design_rules: dict[str, tuple[list, list, list]] = {}
        for dsg in cfg.get("designs", []):
            tp = [re.compile(p, re.I) for p in dsg.get("title", dsg.get("patterns", []))]
            ap = [re.compile(p, re.I) for p in dsg.get("abstract", dsg.get("patterns", []))]
            self.designs.append((dsg["slug"], dsg["label"], tp + ap))
            self.design_rules[dsg["slug"]] = (tp, ap, list(dsg.get("suppresses", [])))
        self.design_order = [d[0] for d in self.designs]
        self.pubtypes = {k.lower(): v for k, v in (cfg.get("pubtypes") or {}).items()}
        self.type_designs = {v for v in self.pubtypes.values() if v}
        self.regions = cfg.get("regions", {})
        self.code_to_region = dict(countries.CODE_TO_REGION)
        self.news_include = [re.compile(p, re.I) for p in cfg.get("news_include", [])]
        self.news_exclude = [re.compile(p, re.I) for p in cfg.get("news_exclude", [])]
        self.news_categories = [(c["slug"], c["label"], [re.compile(p, re.I) for p in c["patterns"]]) for c in cfg.get("news_categories", [])]
        self.bills_include = [re.compile(p, re.I) for p in cfg.get("bills_include", [])] or self.news_include
        self.bills_exclude = [re.compile(p, re.I) for p in cfg.get("bills_exclude", [])]
        self.cases_name = [re.compile(p, re.I) for p in cfg.get("cases_name", cfg.get("cases_include", []))] or self.news_include
        self.cases_text = [re.compile(p, re.I) for p in cfg.get("cases_text", cfg.get("cases_include", []))] or self.news_include
        self.cases_exclude = [re.compile(p, re.I) for p in cfg.get("cases_exclude", [])]
        self.corrections = Corrections(corrections if corrections is not None else load_corrections())

    # ---- papers -------------------------------------------------------
    def _clean(self, text: str) -> str:
        for ex in self.exclude:
            text = ex.sub(" ", text)
        return text

    def assess_full(self, title: str, abstract: str) -> Assessment:
        if any(p.search(title or "") for p in self.drop):
            return Assessment(None)
        ct, ca = self._clean(title or ""), self._clean(abstract or "")
        strong_t = any(p.search(ct) for p in self.strong)
        strong_a = [m.start() for p in self.strong for m in p.finditer(ca)]
        amb_t = any(p.search(ct) for p in self.ambiguous)
        amb_a = [m.start() for p in self.ambiguous for m in p.finditer(ca)]
        if strong_t or strong_a:
            # With a gambling context established, the ambiguous terms count too.
            hits = strong_a + amb_a
            return Assessment("high", strong_t or amb_t, len(hits), min(hits) if hits else None)
        if amb_t or amb_a:
            return Assessment("low")
        # Weak terms are checked on the original text so that excluded contexts
        # (a lottery used as a survey incentive) still land on the borderline list.
        if any(p.search(f"{title} {abstract}") for p in self.weak):
            return Assessment("low")
        return Assessment(None)

    def assess(self, title: str, abstract: str) -> tuple[str | None, bool, int]:
        """Returns (relevance, strong term in title, number of strong matches in abstract).
        relevance is 'high', 'low' or None (drop)."""
        a = self.assess_full(title, abstract)
        return a.relevance, a.title_hit, a.abstract_hits

    def relevance(self, text: str) -> str | None:
        """'high', 'low' or None (drop). Title-only convenience wrapper."""
        return self.assess(text, "")[0]

    def journal_excluded(self, journal: str | None) -> bool:
        return bool(journal) and any(p.search(journal) for p in self.exclude_journals)

    def topics_for(self, title: str, abstract: str) -> list[str]:
        out = []
        for slug, _, pats in self.topics:
            hits = sum(2 * len(p.findall(title or "")) + len(p.findall(abstract or "")) for p in pats)
            if hits >= self.topic_min.get(slug, 1):
                out.append(slug)
        return out

    def designs_for(self, title: str, abstract: str, pubtypes: list[str] | None = None, rtype: str | None = None) -> list[str]:
        found: set[str] = set()
        for slug, (tp, ap, _) in self.design_rules.items():
            if any(p.search(title or "") for p in tp) or any(p.search(abstract or "") for p in ap):
                found.add(slug)
        # NLM publication types settle the designs they cover (trial, review,
        # protocol, commentary, case report); the rules keep the rest.
        typed = {self.pubtypes[p] for p in (pubtypes or []) if self.pubtypes.get(p)}
        if typed:
            found = (found - self.type_designs) | typed
        if rtype in ("letter", "editorial"):
            found.add("commentary")
        if rtype == "review":
            found.add("review")
        for slug in self.design_order:
            if slug in found:
                for x in self.design_rules[slug][2]:
                    found.discard(x)
        return [d for d in self.design_order if d in found]

    def tag(self, text: str, title: str = "") -> tuple[list[str], list[str]]:
        """Topics and designs for a block of text (trials, bills and court records)."""
        return self.topics_for(title, text), self.designs_for(title, text)

    def countries_from_affiliations(self, affiliations: list[str]) -> list[str]:
        return countries.from_affiliations(affiliations)

    def settings_for(self, title: str, abstract: str, mesh: list[str] | None = None) -> list[str]:
        """Where the study was done, as far as the record says: MeSH geographic
        headings first, then countries named in the title, then countries named
        in the abstract when there are few enough to be the setting rather than
        a comparison."""
        found = countries.from_mesh(mesh or [])
        if found:
            return found
        found = countries.mentioned(title or "")
        if found:
            return found
        found = countries.mentioned(abstract or "")
        return found if len(found) <= 3 else []

    def regions_for(self, codes: list[str]) -> list[str]:
        out: list[str] = []
        for c in codes:
            r = self.code_to_region.get(countries.normalise_code(c) or "")
            if r and r not in out:
                out.append(r)
        return out

    def topic_label(self, slug: str) -> str:
        for s, label, _ in self.topics:
            if s == slug:
                return label
        return slug

    def design_label(self, slug: str) -> str:
        for s, label, _ in self.designs:
            if s == slug:
                return label
        return slug

    # ---- news ---------------------------------------------------------
    def news_keep(self, text: str) -> bool:
        if any(p.search(text) for p in self.news_exclude):
            return False
        return any(p.search(text) for p in self.news_include)

    def news_categorize(self, text: str, kind: str) -> tuple[list[str], str]:
        cats = [slug for slug, _, pats in self.news_categories if any(p.search(text) for p in pats)]
        if not cats:
            cats = ["industry" if kind in ("trade", "industry") else "regulation" if kind in ("regulator", "court") else "public-health" if kind == "public-health" else "industry"]
        return cats, cats[0]

    def news_label(self, slug: str) -> str:
        for s, label, _ in self.news_categories:
            if s == slug:
                return label
        return slug

    # ---- bills and court records ---------------------------------------
    def bills_keep(self, text: str) -> bool:
        if any(p.search(text) for p in self.bills_exclude):
            return False
        return any(p.search(text) for p in self.bills_include)

    def cases_keep(self, name: str, text: str = "") -> bool:
        """Keep when the case name names a gambling party, or the matched text is
        about gambling (after removing excluded contexts such as visa lotteries)."""
        if any(p.search(name) for p in self.cases_name):
            return True
        for ex in self.cases_exclude:
            text = ex.sub(" ", text)
        return any(p.search(text) for p in self.cases_text)


# ----------------------------------------------------------------------
def key_for(rec: dict) -> str:
    if rec.get("doi"):
        return "doi:" + rec["doi"]
    if rec.get("pmid"):
        return "pmid:" + str(rec["pmid"])
    t = norm_title(rec.get("title", ""))
    return "title:" + stable_id(t[:200])


SOURCE_PRIORITY = {"pubmed": 3, "crossref": 2, "openalex": 1, "stored": 0}


def _prio(source: str) -> int:
    return SOURCE_PRIORITY.get(source.split(":")[0], 0)


def _prefix_match(nt: str, titles: dict[str, str]) -> str | None:
    """A feed that drops subtitles ("Solidarity and Chance") should still merge
    with the full record ("Solidarity and Chance: Bingo in Italy")."""
    if len(nt) < 15:
        return None
    for full, key in titles.items():
        if full.startswith(nt + " ") or nt.startswith(full + " "):
            return key
    return None


def merge_raw(raw: list[dict]) -> dict[str, dict]:
    """Group raw records by DOI/PMID/title, merging fields by source priority."""
    groups: dict[str, dict] = {}
    pmid_to_key: dict[str, str] = {}
    title_to_key: dict[str, str] = {}
    # DOI-bearing records first so that DOI-less feed items attach to them.
    ordered = sorted(raw, key=lambda r: 0 if r.get("doi") else 1)
    for rec in ordered:
        if not rec.get("title"):
            continue
        key = key_for(rec)
        # Link records that lack a DOI to an existing DOI group via PMID or title.
        if not key.startswith("doi:"):
            nt = norm_title(rec["title"])[:200]
            if rec.get("pmid") and rec["pmid"] in pmid_to_key:
                key = pmid_to_key[rec["pmid"]]
            elif nt in title_to_key:
                key = title_to_key[nt]
            else:
                pm = _prefix_match(nt, title_to_key)
                if pm:
                    key = pm
        g = groups.get(key)
        if g is None:
            g = {"sources": [], "_recs": []}
            groups[key] = g
        g["_recs"].append(rec)
        if rec["source"] not in g["sources"]:
            g["sources"].append(rec["source"])
        if rec.get("pmid"):
            pmid_to_key[rec["pmid"]] = key
        title_to_key[norm_title(rec["title"])[:200]] = key
    return groups


def _earliest(*dates: str | None) -> str | None:
    ds = sorted(x[:10] for x in dates if x)
    return ds[0] if ds else None


def canonical(key: str, group: dict, tax: Taxonomy, today: dt.date, existing: dict | None) -> dict | None:
    recs = sorted(group["_recs"], key=lambda r: -_prio(r["source"]))

    def first(field, pred=lambda v: bool(v)):
        for r in recs:
            v = r.get(field)
            if pred(v):
                return v
        return None

    title = first("title")
    abstract = max((r.get("abstract") or "" for r in recs), key=len)
    # Sources seen for this study over its life in the index, not just tonight:
    # a study first found in a journal feed and re-read from OpenAlex is not an
    # OpenAlex-only record.
    sources = sorted(set(group["sources"]) | set((existing or {}).get("sources") or []))
    doi = first("doi")
    pmid = first("pmid")
    journal = tax.journals.canonical(first("journal"))
    correction = tax.corrections.find({"doi": doi, "pmid": pmid, "id": key})
    a = tax.assess_full(title, abstract)
    rel = a.relevance
    if correction and correction.get("relevance"):
        rel = correction["relevance"]
    elif rel is not None and tax.journal_excluded(journal):
        rel = None
    if rel is None:
        return None
    # OpenAlex's search is loose and its corpus includes repository spam. A record
    # that only OpenAlex supplies must name the subject in its title, or keep
    # returning to it in the abstract from the opening sentences on, and never
    # earns a borderline listing.
    if sources == ["openalex"] and not (correction and correction.get("relevance")):
        early = a.first_abstract_hit is not None and a.first_abstract_hit < tax.oa_only_early
        if rel == "low" or not (a.title_hit or (a.abstract_hits >= tax.oa_only_hits and early)):
            return None
    countries_found: list[str] = []
    for r in recs:
        for c in r.get("countries") or []:
            c = countries.normalise_code(c)
            if c and c not in countries_found:
                countries_found.append(c)
    if not countries_found:
        affs = [x for r in recs for x in (r.get("affiliations") or [])]
        countries_found = tax.countries_from_affiliations(affs)
    rtype = first("type") or "article"
    pubtypes = first("pubtypes") or []
    mesh = first("mesh") or []
    topics = tax.topics_for(title, abstract)
    designs = tax.designs_for(title, abstract, pubtypes, rtype)
    settings = tax.settings_for(title, abstract, mesh)
    published = first("published")
    created = first("created")
    pmcid = first("pmcid")
    oa_url = first("oa_url")
    if not oa_url and pmcid:
        oa_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
    url = f"https://doi.org/{doi}" if doi else first("url")
    if existing and existing.get("first_seen"):
        first_seen = existing["first_seen"]
    else:
        # Nightly runs: today. Backfill and rebuild set it from the sources' dates later.
        first_seen = today.isoformat()
    language = None
    for r in recs:
        language = norm_language(r.get("language"))
        if language:
            break
    language = language or norm_language(None, title)
    rec = {
        "id": key,
        "doi": doi,
        "pmid": pmid,
        "pmcid": pmcid,
        "openalex": first("openalex"),
        "title": title,
        "journal": journal,
        "authors": (first("authors") or [])[:50],
        "published": published,
        "year": int(published[:4]) if published else None,
        "created": created,
        "first_seen": first_seen,
        "summary": summarize(abstract) if abstract else ((existing or {}).get("summary") or ""),
        "url": url,
        "oa_url": oa_url,
        "sources": sources,
        "type": rtype,
        "topics": topics,
        "designs": designs,
        "design_basis": "pubmed" if any(tax.pubtypes.get(p) for p in pubtypes) else "rules",
        "settings": settings,
        "setting_regions": tax.regions_for(settings),
        "countries": countries_found,
        "regions": tax.regions_for(countries_found),
        "language": language,
        "relevance": rel,
        "retracted": any(r.get("retracted") for r in recs),
    }
    rec = tax.corrections.apply(rec)
    if rec is not None:
        rec["setting_regions"] = tax.regions_for(rec.get("settings") or [])
    return rec


def retag_stored(prev: dict, tax: Taxonomy) -> dict | None:
    """Re-apply the rules to a record no source returned in a rebuild (a feed item
    without a DOI, say), using what the index kept: its title and summary."""
    group = {"sources": list(prev.get("sources") or []), "_recs": [dict(prev, source=(prev.get("sources") or ["feed"])[0], abstract=prev.get("summary") or "", affiliations=[])]}
    rec = canonical(prev["id"], group, tax, dt.date.fromisoformat(prev.get("first_seen") or "2000-01-01"), prev)
    if rec is not None:
        rec["summary"] = prev.get("summary") or ""
    return rec


def update_index(existing: list[dict], raw: list[dict], tax: Taxonomy, today: dt.date, backfill: bool, rebuild: bool = False) -> tuple[list[dict], dict]:
    """Return the updated index and a small stats dict.

    rebuild=True re-derives every study already in the index: those the sources
    returned again are re-tagged from the fresh records, the rest from their
    stored title and summary, and studies the current rules no longer keep are
    removed."""
    by_id = {p["id"]: p for p in existing}
    by_doi = {p["doi"]: p for p in existing if p.get("doi")}
    by_pmid = {p["pmid"]: p for p in existing if p.get("pmid")}
    by_title = {norm_title(p["title"])[:200]: p for p in existing}
    groups = merge_raw(raw)
    added = updated = dropped = removed = 0
    touched: set[str] = set()
    for key, group in groups.items():
        sample = group["_recs"][0]
        prev = by_id.get(key)
        if prev is None:
            for r in group["_recs"]:
                if r.get("doi") and r["doi"] in by_doi:
                    prev = by_doi[r["doi"]]
                    break
                if r.get("pmid") and r["pmid"] in by_pmid:
                    prev = by_pmid[r["pmid"]]
                    break
            if prev is None:
                nt = norm_title(sample["title"])[:200]
                prev = by_title.get(nt)
                if prev is None and not any(r.get("doi") for r in group["_recs"]):
                    pm = _prefix_match(nt, {t: p["id"] for t, p in by_title.items()})
                    if pm:
                        prev = by_id.get(pm)
        rec = canonical(key, group, tax, today, prev)
        if rec is None:
            dropped += 1
            # The current rules no longer keep a study that was in the index.
            if prev is not None and prev["id"] in by_id and prev["id"] not in touched:
                del by_id[prev["id"]]
                removed += 1
            continue
        if prev is not None:
            # Keep the original id and first_seen; refresh everything else.
            rec["id"] = prev["id"]
            rec["first_seen"] = prev.get("first_seen") or rec["first_seen"]
            for f in ("summary", "oa_url", "pmid", "pmcid", "openalex", "doi", "published"):
                if not rec.get(f) and prev.get(f):
                    rec[f] = prev[f]
            if rec.get("published"):
                rec["year"] = int(rec["published"][:4])
            if prev["id"] in touched:
                # Two groups resolved to the same study (a DOI-less feed copy and the
                # DOI record): keep the richer one's tags, union the sources.
                old = by_id[prev["id"]]
                rec["sources"] = sorted(set(old.get("sources", [])) | set(rec["sources"]))
            by_id[prev["id"]] = rec
            touched.add(prev["id"])
            updated += 1
        else:
            if backfill or rebuild:
                # A study found by a backfill or rebuild entered the literature
                # before tonight; date it by the sources rather than today.
                basis = _earliest(rec.get("published"), rec.get("created"))
                if basis:
                    try:
                        rec["first_seen"] = min(dt.date.fromisoformat(basis), today).isoformat()
                    except ValueError:
                        pass
            by_id[rec["id"]] = rec
            touched.add(rec["id"])
            added += 1
        if rec.get("doi"):
            by_doi[rec["doi"]] = rec
        if rec.get("pmid"):
            by_pmid[rec["pmid"]] = rec
        by_title[norm_title(rec["title"])[:200]] = rec
    if rebuild:
        for pid in [k for k in by_id if k not in touched]:
            rec = retag_stored(by_id[pid], tax)
            if rec is None:
                del by_id[pid]
                removed += 1
            else:
                by_id[pid] = rec
    # Hand exclusions also remove studies that no source returned tonight.
    for pid in [k for k, p in by_id.items() if tax.corrections.find(p) and tax.corrections.find(p).get("exclude")]:
        del by_id[pid]
        removed += 1
    papers = list(by_id.values())
    papers.sort(key=lambda p: (p.get("first_seen") or "", p.get("published") or "", p["title"]), reverse=True)
    return papers, {"raw": len(raw), "groups": len(groups), "added": added, "updated": updated, "dropped_irrelevant": dropped, "removed": removed, "total": len(papers)}


def update_news(existing: list[dict], raw: list[dict], tax: Taxonomy, today: dt.date, max_per_source_day: int, keep_days: int = 400) -> tuple[list[dict], dict]:
    by_id = {n["id"]: n for n in existing}
    seen_titles = {norm_title(n["title"])[:120] for n in existing}
    added = dropped = 0
    cutoff = (today - dt.timedelta(days=keep_days)).isoformat()
    for item in raw:
        if item["id"] in by_id:
            continue
        nt = norm_title(item["title"])[:120]
        if nt in seen_titles:
            continue
        text = f"{item['title']} {item.get('summary', '')}"
        if not tax.news_keep(text):
            dropped += 1
            continue
        cats, primary = tax.news_categorize(text, item.get("kind", "press"))
        item = dict(item, categories=cats, primary=primary, first_seen=today.isoformat())
        if not item.get("published"):
            item["published"] = today.isoformat()
        by_id[item["id"]] = item
        seen_titles.add(nt)
        added += 1
    news = [n for n in by_id.values() if (n.get("published") or "") >= cutoff]
    news.sort(key=lambda n: (n.get("published") or "", n.get("first_seen") or ""), reverse=True)
    # Per-source-per-day cap (keeps the first N seen).
    counts: dict[tuple[str, str], int] = {}
    capped = []
    for n in news:
        k = (n.get("feed_id", ""), (n.get("published") or "")[:10])
        counts[k] = counts.get(k, 0) + 1
        if counts[k] <= max_per_source_day:
            capped.append(n)
    return capped, {"raw": len(raw), "added": added, "dropped_irrelevant": dropped, "total": len(capped)}
