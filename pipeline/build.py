"""Render the static site from data/ and content/ into _site/.

    python -m pipeline.build
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .common import CONTENT_DIR, DATA_DIR, ROOT, SITE_DIR, STATIC_DIR, TEMPLATE_DIR, load_json, load_yaml, today_utc
from . import countries
from . import charts as chartkit
from . import exports
from .exports import BILL_COLS, CASE_COLS, Col, DataPage, NEWS_COLS, PAPER_COLS, TRIAL_COLS
from .normalize import Taxonomy, apply_corrections
from .sources.trials import STATUSES
from .trackers import COURT_LEVELS, STAGES, STAGE_RANK

MD_EXT = ["tables", "attr_list", "footnotes", "sane_lists", "md_in_html", "toc"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


# ---------------------------------------------------------------- helpers
def d(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def fmt_date(s, style="medium"):
    x = d(s) if isinstance(s, str) else s
    if not x:
        return ""
    if style == "short":
        return f"{MONTHS[x.month - 1][:3]} {x.day}"
    if style == "long":
        return f"{MONTHS[x.month - 1]} {x.day}, {x.year}"
    if style == "month":
        return f"{MONTHS[x.month - 1]} {x.year}"
    return f"{MONTHS[x.month - 1][:3]} {x.day}, {x.year}"


def rfc822(s, hour: int = 12) -> str:
    x = d(s) if isinstance(s, str) else s
    if not x:
        return ""
    t = dt.datetime(x.year, x.month, x.day, hour, 0, 0, tzinfo=dt.timezone.utc)
    return t.strftime("%a, %d %b %Y %H:%M:%S +0000")


def fmt_time_utc(iso_ts: str | None) -> str:
    if not iso_ts:
        return ""
    try:
        t = dt.datetime.fromisoformat(iso_ts)
    except ValueError:
        return ""
    return f"{fmt_date(t.date())}, {t:%H:%M} UTC"


def family(name: str) -> str:
    name = name.strip()
    if "," in name:
        return name.split(",")[0].strip()
    parts = name.split()
    if not parts:
        return name
    # keep particles: "van der Berg", "de Souza"
    i = len(parts) - 1
    while i > 0 and parts[i - 1].lower() in ("van", "der", "de", "da", "di", "del", "della", "von", "la", "le", "du", "dos", "das", "bin", "al"):
        i -= 1
    return " ".join(parts[i:])


def authors_line(authors: list[str], limit: int = 3) -> str:
    fams = [family(a) for a in authors if a]
    if not fams:
        return ""
    if len(fams) <= limit:
        return ", ".join(fams[:-1]) + (" and " + fams[-1] if len(fams) > 1 else fams[0])
    return ", ".join(fams[:limit]) + f" and {len(fams) - limit} more"


def monday_of(x: dt.date) -> dt.date:
    return x - dt.timedelta(days=x.weekday())


def read_markdown(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        meta = yaml.safe_load(m.group(1)) or {}
        text = text[m.end():]
    html = markdown.markdown(text, extensions=MD_EXT, output_format="html5")
    return meta, html


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


LANGUAGE_NAMES = {
    "en": "English", "fi": "Finnish", "sv": "Swedish", "no": "Norwegian", "da": "Danish", "is": "Icelandic", "de": "German", "fr": "French",
    "es": "Spanish", "pt": "Portuguese", "it": "Italian", "nl": "Dutch", "pl": "Polish", "cs": "Czech", "sk": "Slovak", "hu": "Hungarian",
    "ro": "Romanian", "bg": "Bulgarian", "hr": "Croatian", "sr": "Serbian", "sl": "Slovenian", "el": "Greek", "tr": "Turkish", "ru": "Russian",
    "uk": "Ukrainian", "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian", "ar": "Arabic", "fa": "Persian", "he": "Hebrew", "zh": "Chinese",
    "ja": "Japanese", "ko": "Korean", "th": "Thai", "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "ca": "Catalan",
}


def language_name(code: str | None) -> str:
    return LANGUAGE_NAMES.get(code or "", (code or "").upper())


_FOLD = str.maketrans({"ı": "i", "İ": "I", "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "þ": "th", "œ": "oe"})


def fold(text: str) -> str:
    """Accents off ("Kaymakçı" -> "Kaymakci", "Castrén" -> "Castren") so a search
    typed without them still matches."""
    t = unicodedata.normalize("NFKD", (text or "").translate(_FOLD))
    return "".join(ch for ch in t if not unicodedata.combining(ch))


def setting_names(codes: list[str]) -> list[str]:
    return [countries.COUNTRY_NAMES.get(c, c) for c in codes or []]


# ---------------------------------------------------------------- build
class Builder:
    def __init__(self):
        self.site = load_yaml("site.yml")
        self.sources = load_yaml("sources.yml")
        self.tax = Taxonomy(load_yaml("taxonomy.yml"))
        self.today = today_utc()
        self.papers_all = load_json(DATA_DIR / "papers.json", [])
        self.news_all = load_json(DATA_DIR / "news.json", [])
        self.fetch_log = load_json(DATA_DIR / "fetch_log.json", {})
        self.trials_all = load_json(DATA_DIR / "trials.json", [])
        self.bills_all = load_json(DATA_DIR / "bills.json", [])
        self.cases_all = load_json(DATA_DIR / "cases.json", [])
        # Hand corrections take effect on the next build, not only on the next fetch.
        by_id = {p["id"]: p for p in self.papers_all}
        apply_corrections(by_id, self.tax)
        self.papers_all = list(by_id.values())
        self.fixture = False
        if not self.papers_all:
            fx = load_json(ROOT / "pipeline" / "fixtures" / "papers.json", [])
            if fx:
                self.papers_all, self.fixture = fx, True
        if not self.news_all and self.fixture:
            self.news_all = load_json(ROOT / "pipeline" / "fixtures" / "news.json", [])
        self.env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html", "xml"]), trim_blocks=True, lstrip_blocks=True)
        self.env.filters.update(
            {
                "fmt_date": fmt_date,
                "rfc822": rfc822,
                "authors_line": authors_line,
                "topic_label": self.tax.topic_label,
                "design_label": self.tax.design_label,
                "news_label": self.tax.news_label,
                "region_label": lambda s: self.tax.regions.get(s, {}).get("label", s),
                "slugify": slugify,
                "status_label": lambda s: STATUSES.get(s, s),
                "stage_label": lambda s: dict(STAGES).get(s, s),
                "level_label": lambda s: dict(COURT_LEVELS).get(s, s),
                "language_name": language_name,
                "setting_names": setting_names,
            }
        )
        self.urls: list[str] = []
        # The index's own as-of date: when the last nightly run finished, not when this
        # build ran. Every citation, CSV and chart on the site states this one date.
        self.as_of = d((self.fetch_log.get("finished") or "")[:10]) or self.today
        self.data_pages: list[DataPage] = []
        # Main navigation: href, label, kind (colour cue), and the path prefixes it covers.
        self.nav = [
            {"href": "/research/", "label": "Research", "kind": "research", "paths": ["/research/", "/trials/"]},
            {"href": "/news/", "label": "Policy", "kind": "news", "paths": ["/news/", "/bills/", "/courts/"]},
            {"href": "/digest/", "label": "Digest", "kind": "digest", "paths": ["/digest/"]},
            {"href": "/journals/", "label": "Reference", "kind": "reference", "paths": ["/journals/", "/conferences/", "/datasets/", "/measures/", "/guide/", "/data-use/"]},
            {"href": "/search/", "label": "Search", "kind": "search", "paths": ["/search/"]},
        ]
        self.subnavs = {
            "research": [("/research/", "New studies"), ("/trials/", "Trials and preregistrations"), ("/research/topics/", "Topics"), ("/research/archive/", "Archive")],
            "policy": [("/news/", "News"), ("/bills/", "Bills"), ("/courts/", "Courts")],
        }

    # ---- data views ----
    def papers(self, days: int | None, relevance="high"):
        out = [p for p in self.papers_all if p.get("relevance") == relevance]
        if days:
            since = (self.today - dt.timedelta(days=days)).isoformat()
            out = [p for p in out if (p.get("first_seen") or "") >= since]
        out.sort(key=lambda p: (p.get("first_seen") or "", p.get("published") or "", p["title"]), reverse=True)
        return out

    def by_week(self, papers):
        groups: dict[dt.date, list] = defaultdict(list)
        for p in papers:
            x = d(p.get("first_seen")) or self.today
            groups[monday_of(x)].append(p)
        return [(k, groups[k]) for k in sorted(groups, reverse=True)]

    def news(self, days: int):
        since = (self.today - dt.timedelta(days=days)).isoformat()
        out = [n for n in self.news_all if (n.get("published") or "") >= since]
        out.sort(key=lambda n: (n.get("published") or "", n.get("first_seen") or ""), reverse=True)
        return out

    def by_day(self, items):
        groups: dict[str, list] = defaultdict(list)
        for n in items:
            groups[(n.get("published") or "")[:10]].append(n)
        return [(k, groups[k]) for k in sorted(groups, reverse=True)]

    def digests(self):
        out = []
        for path in sorted((CONTENT_DIR / "digests").glob("*.md"), reverse=True):
            meta, html = read_markdown(path)
            if meta.get("draft"):
                continue
            slug = path.stem
            out.append({"slug": slug, "url": f"/digest/{slug}/", "title": meta.get("title", slug), "date": meta.get("date", slug[:10]), "summary": meta.get("summary", ""), "html": html, "meta": meta})
        out.sort(key=lambda x: str(x["date"]), reverse=True)
        # Issue numbers count up from the oldest published digest.
        for i, dg in enumerate(out):
            dg["number"] = len(out) - i
        return out


    # ---- trackers ----
    STATUS_GROUPS = [
        ("recruiting", "recruiting", ["recruiting", "not-yet-recruiting", "enrolling-by-invitation"]),
        ("active", "active, not recruiting", ["active"]),
        ("completed", "completed", ["completed"]),
        ("stopped", "stopped early", ["terminated", "suspended", "withdrawn"]),
        ("registered", "preregistrations", ["registered"]),
        ("unknown", "status unknown", ["unknown"]),
    ]

    def trials_view(self):
        groups: list[tuple[str, str, list]] = []
        two_years = (self.today - dt.timedelta(days=730)).isoformat()
        for slug, label, statuses in self.STATUS_GROUPS:
            items = [t for t in self.trials_all if t.get("status") in statuses]
            if slug == "registered":  # OSF goes back to 2013; the page shows recent registrations, the JSON has all
                items = [t for t in items if (t.get("first_posted") or t.get("first_seen") or "") >= two_years]
            if slug == "completed":
                items.sort(key=lambda t: (t.get("completion_date") or t.get("last_updated") or "", t["title"]), reverse=True)
            else:
                items.sort(key=lambda t: (t.get("first_posted") or t.get("first_seen") or "", t["title"]), reverse=True)
            for t in items:
                t["status_group"] = slug
            if items:
                groups.append((slug, label, items))
        return groups

    def bills(self, days: int):
        since = (self.today - dt.timedelta(days=days)).isoformat()
        out = [b for b in self.bills_all if (b.get("latest_action_date") or "") >= since]
        out.sort(key=lambda b: (b.get("latest_action_date") or "", b.get("jurisdiction") or "", b.get("identifier") or ""), reverse=True)
        return out

    def cases(self, days: int):
        since = (self.today - dt.timedelta(days=days)).isoformat()
        out = [c for c in self.cases_all if (c.get("latest_activity") or "") >= since]
        out.sort(key=lambda c: (c.get("latest_activity") or "", c.get("case_name") or ""), reverse=True)
        return out

    def by_month(self, items, field: str):
        groups: dict[str, list] = defaultdict(list)
        for it in items:
            groups[(it.get(field) or "")[:7]].append(it)
        return [(k, groups[k]) for k in sorted(groups, reverse=True)]

    # ---- search ----
    def coverage_from(self) -> str | None:
        meta = load_json(DATA_DIR / "index_meta.json", {})
        return meta.get("coverage_from")

    def search_records(self, papers: list[dict]) -> list[dict]:
        out = []
        for p in papers:
            topics = [self.tax.topic_label(t) for t in p.get("topics", [])]
            designs = [self.tax.design_label(x) for x in p.get("designs", [])]
            settings = setting_names(p.get("settings") or [])
            authors = p.get("authors") or []
            text = " ".join([p["title"], " ".join(authors), p.get("journal") or "", p.get("summary") or "", " ".join(topics), " ".join(designs), " ".join(settings), p.get("doi") or ""])
            folded = fold(f"{p['title']} {' '.join(authors)}")
            if folded != f"{p['title']} {' '.join(authors)}":
                text += " " + folded
            filters = {
                "topic": topics,
                "design": designs,
                "setting": [self.tax.regions.get(r, {}).get("label", r) for r in p.get("setting_regions") or []],
                "authors": [self.tax.regions.get(r, {}).get("label", r) for r in p.get("regions") or []],
                "year": [str(p["year"])] if p.get("year") else [],
                "access": ["Free full text"] if p.get("oa_url") else [],
                "language": [language_name(p.get("language"))] if p.get("language") and p.get("language") != "en" else [],
            }
            meta = {
                "title": p["title"],
                "journal": p.get("journal") or (p.get("type") or "article").replace("-", " ").capitalize(),
                "published": fmt_date(p.get("published")) if p.get("published") else "",
                "authors": authors_line(authors),
                "summary": p.get("summary") or "",
                "oa": p.get("oa_url") or "",
                "topics": "|".join(f"{t}~{self.tax.topic_label(t)}" for t in p.get("topics", [])[:4]),
                "designs": "|".join(designs[:2]),
                "setting": ", ".join(settings),
                "language": language_name(p.get("language")) if p.get("language") and p.get("language") != "en" else "",
                "retracted": "1" if p.get("retracted") else "",
            }
            out.append({
                "url": p.get("url") or f"/research/#{p['id']}",
                "content": text,
                "meta": meta,
                "filters": {k: v for k, v in filters.items() if v},
                "sort": {"published": (p.get("published") or p.get("first_seen") or "0000-00-00").replace("-", "")},
            })
        return out

    def build_search(self, papers: list[dict]) -> bool:
        records = self.search_records(papers)
        tmp = SITE_DIR / ".search-records.json"
        tmp.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        script = ROOT / "pipeline" / "search_index.mjs"
        if not (ROOT / "node_modules" / "pagefind").exists():
            print("search: node_modules/pagefind is missing (run npm ci); the search page will say search is unavailable", file=sys.stderr)
            tmp.unlink()
            return False
        try:
            subprocess.run(["node", str(script), str(tmp), str(SITE_DIR / "pagefind")], check=True, cwd=ROOT, timeout=900)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"search: index not built: {e}", file=sys.stderr)
            return False
        finally:
            tmp.unlink(missing_ok=True)
        return True

    # ---- counts over time, with the empty periods kept ----
    def partial_note(self, period: str) -> str:
        """A caption warning when the last column covers an unfinished period."""
        if period == "week" and self.as_of.weekday() != 6:
            return " The last column is a part-week."
        if period == "month":
            first_next = (self.as_of.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
            if self.as_of != first_next - dt.timedelta(days=1):
                return " The last column is the month so far."
        if period == "year" and (self.as_of.month, self.as_of.day) != (12, 31):
            return " The last column is the year so far."
        return ""

    def weekly_series(self, items, days: int, field: str = "first_seen"):
        end, start = monday_of(self.as_of), monday_of(self.as_of - dt.timedelta(days=days - 1))
        weeks, x = [], start
        while x <= end:
            weeks.append(x)
            x += dt.timedelta(days=7)
        counts = Counter(monday_of(d(it.get(field)) or self.as_of) for it in items)
        return [fmt_date(w, "short") for w in weeks], [counts.get(w, 0) for w in weeks]

    def monthly_series(self, items, months: int, field: str):
        ym, y, m = [], self.as_of.year, self.as_of.month
        for _ in range(months):
            ym.append(f"{y:04d}-{m:02d}")
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        ym.reverse()
        counts = Counter((it.get(field) or "")[:7] for it in items)
        labels = [f"{MONTHS[int(x[5:7]) - 1][:3]} {x[:4]}" if i == 0 or x[5:7] == "01" else MONTHS[int(x[5:7]) - 1][:3] for i, x in enumerate(ym)]
        return labels, [counts.get(x, 0) for x in ym]

    def yearly_series(self, items, years: int, field: str):
        last = self.as_of.year
        span = list(range(last - years + 1, last + 1))
        counts = Counter(int((it.get(field) or "")[:4]) for it in items if (it.get(field) or "")[:4].isdigit())
        return [str(y) for y in span], [counts.get(y, 0) for y in span]

    # ---- data pages: CSV, charts, citation, Dataset metadata ----
    def chart(self, slug: str, kind: str, labels: list[str], values: list, *, title: str, subtitle: str, unit: str, caption: str) -> dict:
        """One chart, as a standalone SVG string with the credit inside the image."""
        draw = chartkit.columns if kind == "columns" else chartkit.bars
        made = draw(
            labels, values, title=title, subtitle=subtitle, y_unit=unit,
            credit_site=self.site["canonical_domain"],
            credit_right=f"Data as of {fmt_date(self.as_of, 'long')} \u00b7 CC BY 4.0",
        )
        return {
            "slug": slug, "svg": made.svg, "width": made.width, "height": made.height,
            "title": title, "caption": caption,
            "alt": f"{title}. {subtitle} The figures are in the list below and in the CSV.",
        }

    def catalogue(self) -> list[tuple[str, list]]:
        """The data pages, grouped for the catalogue on /data-use/."""
        groups: dict[str, list] = defaultdict(list)
        for dp in self.data_pages:
            groups[dp.group].append(dp)
        order = ["Research", "Policy", "Research by topic", "Research archive"]
        return [(g, groups[g]) for g in order if g in groups] + [(g, v) for g, v in groups.items() if g not in order]

    def publish(self, dp: DataPage) -> DataPage:
        """Write a data page's CSV and charts, then hand it back for rendering."""
        text = exports.to_csv(dp.rows, dp.columns)
        dp.csv_bytes = len(text.encode("utf-8"))
        dest = SITE_DIR / "data" / f"{dp.slug}.csv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8", newline="")
        for ch in dp.charts:
            out = SITE_DIR / "charts" / f"{ch['slug']}.svg"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(ch["svg"], encoding="utf-8")
            ch["url"] = f"/charts/{ch['slug']}.svg"
        self.data_pages.append(dp)
        return dp

    # ---- rendering ----
    def render(self, template: str, out_path: str, dp: DataPage | None = None, **ctx):
        tpl = self.env.get_template(template)
        base = {
            "site": self.site,
            "today": self.today,
            "nav": self.nav,
            "fixture": self.fixture,
            "updated": fmt_time_utc(self.fetch_log.get("finished")),
            "path": "/" + out_path.replace("index.html", "").strip("/") + ("/" if not out_path.endswith(".xml") and not out_path.endswith(".txt") else ""),
        }
        if base["path"] == "//":
            base["path"] = "/"
        base["nav_current"] = next((item["href"] for item in self.nav if any(base["path"].startswith(pre) for pre in item["paths"])), None)
        section = ctx.get("section")
        if section in self.subnavs:
            base["subnav"] = self.subnavs[section]
            matches = [href for href, _ in self.subnavs[section] if base["path"].startswith(href)]
            base["subnav_current"] = max(matches, key=len) if matches else None
        if dp is not None:
            cite = exports.citation(self.site, dp, as_of_long=fmt_date(self.as_of, "long"), year=self.as_of.year)
            base["citation"] = cite
            if dp.is_dataset:
                base["dataset"] = exports.dataset_jsonld(self.site, dp, as_of_iso=self.as_of.isoformat(), citation_text=cite, csv_bytes=dp.csv_bytes)
            base["data_page"] = dp
            base["charts"] = dp.charts
        base.update(ctx)
        html = tpl.render(**base)
        dest = SITE_DIR / out_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        if out_path.endswith("index.html"):
            self.urls.append(base["path"])

    def build(self):
        if SITE_DIR.exists():
            shutil.rmtree(SITE_DIR)
        SITE_DIR.mkdir(parents=True)
        shutil.copytree(STATIC_DIR, SITE_DIR / "static")
        (SITE_DIR / ".nojekyll").write_text("")
        (SITE_DIR / "CNAME").write_text(self.site["canonical_domain"] + "\n")
        (SITE_DIR / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {self.site['url']}/sitemap.xml\n")
        # Public copies of the index.
        (SITE_DIR / "data").mkdir()
        for name in ("papers.json", "news.json", "trials.json", "bills.json", "cases.json", "fetch_log.json", "index_meta.json", "gold_report.json", "weekly/latest.json"):
            src = DATA_DIR / name
            if src.exists():
                (SITE_DIR / "data" / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, SITE_DIR / "data" / name)

        window = self.site.get("index_window_days", 90)
        recent = self.papers(window)
        week_ago = (self.today - dt.timedelta(days=7)).isoformat()
        this_week = [p for p in recent if (p.get("first_seen") or "") >= week_ago]
        digests = self.digests()
        topic_counts = Counter(t for p in recent for t in p.get("topics", []))
        region_counts = Counter(r for p in recent for r in p.get("regions", []))
        setting_counts = Counter(r for p in recent for r in p.get("setting_regions", []))
        design_counts = Counter(x for p in recent for x in p.get("designs", []))
        topics_sorted = [(slug, self.tax.topic_label(slug), n) for slug, n in topic_counts.most_common()]

        # Home
        home_news = [n for n in self.news(self.site.get("home_news_days", 7)) if n.get("primary") != "industry"][: self.site.get("home_news_count", 12)]
        self.render(
            "home.html", "index.html",
            papers=recent[: self.site.get("home_paper_count", 24)], this_week_count=len(this_week), total_count=len(self.papers(None)),
            news=home_news, digest=digests[0] if digests else None, topics=topics_sorted[:14],
            trackers={
                "recruiting": sum(1 for t in self.trials_all if t.get("status") in ("recruiting", "not-yet-recruiting", "enrolling-by-invitation")),
                "trials_year": sum(1 for t in self.trials_all if (t.get("first_posted") or "")[:4] == self.today.isoformat()[:4]),
                "regs_year": sum(1 for t in self.trials_all if t.get("kind") == "registration" and (t.get("first_posted") or "")[:4] == self.today.isoformat()[:4]),
                "bills_month": sum(1 for b in self.bills_all if (b.get("latest_action_date") or "") >= (self.today - dt.timedelta(days=30)).isoformat()),
                "bills_enacted_year": sum(1 for b in self.bills_all if b.get("stage") == "enacted" and (b.get("latest_action_date") or "")[:4] == self.today.isoformat()[:4]),
                "opinions_month": sum(1 for c in self.cases_all if c.get("kind") == "opinion" and (c.get("date_filed") or "") >= (self.today - dt.timedelta(days=30)).isoformat()),
                "dockets_month": sum(1 for c in self.cases_all if c.get("kind") == "docket" and (c.get("latest_activity") or "") >= (self.today - dt.timedelta(days=30)).isoformat()),
            },
            journal_feed_count=sum(1 for f in self.sources.get("journal_feeds", []) if f.get("enabled", True)),
            coverage_from=self.coverage_from(),
        )
        # Research index
        n_feeds = sum(1 for f in self.sources.get("journal_feeds", []) if f.get("enabled", True))
        wk_labels, wk_values = self.weekly_series(recent, window)
        research_dp = self.publish(DataPage(
            slug="research", path="/research/", name="New gambling research",
            description=(
                f"Every peer-reviewed study, preprint and review on gambling, betting, lotteries, loot boxes and prediction markets that "
                f"entered the {self.site['title']} in the {window} days to {fmt_date(self.as_of, 'long')} ({len(recent)} records), tagged by "
                f"topic, study design, the country the study was done in and the countries its authors work in. Collected nightly from "
                f"PubMed, OpenAlex, Crossref and {n_feeds} journal feeds. One row per study."
            ),
            rows=recent, columns=PAPER_COLS, date_field="first_seen", unit="studies", group="Research",
            json_url="/data/papers.json",
            keywords=["gambling", "problem gambling", "gambling disorder", "sports betting", "lotteries", "loot boxes", "prediction markets", "gambling research", "bibliometrics", "public health"],
            measurement="Nightly automated queries to PubMed, OpenAlex, Crossref and journal RSS feeds, de-duplicated by DOI and title and tagged by the published keyword rules.",
            charts=[
                self.chart(
                    "research-by-week", "columns", wk_labels, wk_values,
                    title="New gambling studies entering the index, by week",
                    subtitle=f"Past {window} days. From PubMed, OpenAlex, Crossref and {n_feeds} journal feeds.",
                    unit="studies", caption=f"Studies first seen each week over the past {window} days." + self.partial_note("week"),
                ),
            ],
        ))
        self.render(
            "research.html", "research/index.html", dp=research_dp, section="research",
            weeks=self.by_week(recent), count=len(recent), window=window, topics=topics_sorted,
            regions=[(s, self.tax.regions[s]["label"], n) for s, n in region_counts.most_common() if s in self.tax.regions],
            settings=[(s, self.tax.regions[s]["label"], n) for s, n in setting_counts.most_common() if s in self.tax.regions],
            designs=[(s, self.tax.design_label(s), n) for s, n in sorted(design_counts.items(), key=lambda x: self.tax.design_order.index(x[0]) if x[0] in self.tax.design_order else 99)], this_week_count=len(this_week),
            total_count=len(self.papers(None)), coverage_from=self.coverage_from(),
        )
        # Borderline (low relevance) for transparency
        low = self.papers(window, relevance="low")
        low_dp = self.publish(DataPage(
            slug="research-borderline", path="/research/borderline/", name="Possibly related studies",
            description=(
                f"Studies from the past {window} days that mention gambling, betting or lotteries only in passing ({len(low)} records), kept out "
                f"of the main {self.site['title']} and published here so that misfiled work can be found. Same columns as the main research export."
            ),
            rows=low, columns=PAPER_COLS, date_field="first_seen", unit="studies", group="Research",
            json_url="/data/papers.json", keywords=["gambling", "gambling research", "borderline relevance", "screening"],
            measurement="The same nightly collection as the main index; these are the records the relevance rules scored as only loosely related.",
        ))
        self.render("research.html", "research/borderline/index.html", dp=low_dp, section="research", weeks=self.by_week(low), count=len(low), window=window, topics=[], regions=[], settings=[], designs=[], borderline=True, this_week_count=0)
        # Topic pages
        topic_window = self.site.get("topic_window_days", 365)
        year_papers = self.papers(topic_window)
        for slug, label, _ in self.tax.topics:
            tp = [p for p in year_papers if slug in p.get("topics", [])]
            mo_labels, mo_values = self.monthly_series(tp, 12, "first_seen")
            topic_dp = self.publish(DataPage(
                slug=f"topics/{slug}", path=f"/research/topics/{slug}/", name=f"Gambling research on {label}",
                description=(
                    f"Studies tagged \u201c{label}\u201d that entered the {self.site['title']} in the {topic_window} days to "
                    f"{fmt_date(self.as_of, 'long')} ({len(tp)} records), with the same columns as the main research export. "
                    f"Tags are assigned automatically from titles and abstracts, so a study can carry several."
                ),
                rows=tp, columns=PAPER_COLS, date_field="first_seen", unit="studies", group="Research by topic", short=label,
                json_url="/data/papers.json", keywords=["gambling", label, "gambling research"],
                measurement="Nightly automated queries to PubMed, OpenAlex, Crossref and journal RSS feeds, tagged by the published keyword rules.",
                charts=[self.chart(
                    f"topics/{slug}-by-month", "columns", mo_labels, mo_values,
                    title=f"Gambling studies on {label}, by month",
                    subtitle=f"Studies entering the index each month over the past {topic_window} days.",
                    unit="studies", caption="Counted by the month a study entered the index, not its publication date." + self.partial_note("month"),
                )],
            ))
            self.render("topic.html", f"research/topics/{slug}/index.html", dp=topic_dp, section="research", papers=tp, label=label, slug=slug, count=len(tp), window=topic_window)
        topic_year = [(s, l, sum(1 for p in year_papers if s in p.get("topics", []))) for s, l, _ in self.tax.topics]
        topics_dp = self.publish(DataPage(
            slug="research-topics", path="/research/topics/", name="Gambling research by topic",
            description=(
                f"How many studies in the {self.site['title']} carry each topic tag, over the {topic_window} days to "
                f"{fmt_date(self.as_of, 'long')}. One row per tag; a study can carry several, so the counts sum to more than the number of studies."
            ),
            rows=[{"topic": s, "label": l, "studies": n} for s, l, n in topic_year],
            columns=[
                Col("topic", "Topic tag as it appears in the data and in page URLs"),
                Col("label", "Readable label for the tag"),
                Col("studies", f"Studies carrying the tag in the {topic_window} days to {self.as_of.isoformat()}"),
            ],
            date_field="", unit="topics", group="Research",
            keywords=["gambling research", "topics", "research trends"],
            measurement="Counted from the tagged index; tags come from keyword rules applied to titles and abstracts.",
            charts=[self.chart(
                "research-topics", "bars",
                [l for _, l, _ in sorted(topic_year, key=lambda x: -x[2])[:14]],
                [n for _, _, n in sorted(topic_year, key=lambda x: -x[2])[:14]],
                title="Gambling research by topic",
                subtitle=f"Studies carrying each tag in the past {topic_window} days.",
                unit="studies", caption="A study can carry several tags, so the bars sum to more than the number of studies.",
            )],
        ))
        self.render("topics.html", "research/topics/index.html", dp=topics_dp, section="research", topics=topic_year, window=topic_window)
        # Monthly archive
        months: dict[str, list] = defaultdict(list)
        for p in self.papers(None):
            months[(p.get("first_seen") or "0000-00")[:7]].append(p)
        month_list = sorted(months, reverse=True)
        for ym in month_list:
            y, m = ym.split("-")
            month_dp = self.publish(DataPage(
                slug=f"research-archive/{ym}", path=f"/research/archive/{y}/{m}/", name=f"Gambling research added in {fmt_date(f'{ym}-01', 'month')}",
                description=(
                    f"Every study that entered the {self.site['title']} in {fmt_date(f'{ym}-01', 'month')} ({len(months[ym])} records), "
                    f"with the same columns as the main research export."
                ),
                rows=months[ym], columns=PAPER_COLS, date_field="first_seen", unit="studies", group="Research archive", short=fmt_date(f"{ym}-01", "month"),
                json_url="/data/papers.json", keywords=["gambling research", fmt_date(f"{ym}-01", "month")],
                measurement="Nightly automated queries to PubMed, OpenAlex, Crossref and journal RSS feeds.",
            ))
            self.render("archive.html", f"research/archive/{y}/{m}/index.html", dp=month_dp, section="research", papers=months[ym], ym=ym, label=fmt_date(f"{ym}-01", "month"), months=[(x, fmt_date(f"{x}-01", "month"), len(months[x])) for x in month_list])
        self.render("archive_index.html", "research/archive/index.html", section="research", months=[(x, fmt_date(f"{x}-01", "month"), len(months[x])) for x in month_list])
        # News
        news_window = self.site.get("news_window_days", 30)
        nitems = self.news(news_window)
        cat_counts = Counter(n.get("primary") for n in nitems)
        news_cats = sorted(((l, cat_counts.get(s, 0)) for s, l, _ in self.tax.news_categories if cat_counts.get(s)), key=lambda x: -x[1])
        news_dp = self.publish(DataPage(
            slug="news", path="/news/", name="Gambling policy and public-health news",
            description=(
                f"Policy, regulatory, legal and public-health news about gambling from the {news_window} days to {fmt_date(self.as_of, 'long')} "
                f"({len(nitems)} items), collected from regulators, the press and trade outlets and categorised by keyword. Headlines and links "
                f"only, one row per item; the text belongs to the publisher."
            ),
            rows=nitems, columns=NEWS_COLS, date_field="published", unit="items", group="Policy",
            json_url="/data/news.json",
            keywords=["gambling policy", "gambling regulation", "sports betting policy", "prediction markets", "public health", "news"],
            measurement="Nightly collection from regulator, press and trade-outlet RSS feeds and news search, de-duplicated by URL and title.",
            charts=[self.chart(
                "news-by-category", "bars", [l for l, _ in news_cats], [n for _, n in news_cats],
                title="Gambling news by category",
                subtitle=f"{len(nitems)} items from the past {news_window} days.",
                unit="items", caption="Categories are matched by keyword, so expect the occasional miss.",
            )] if news_cats else [],
        ))
        self.render("news.html", "news/index.html", dp=news_dp, section="policy", days=self.by_day(nitems), count=len(nitems), window=news_window, categories=[(s, l, cat_counts.get(s, 0)) for s, l, _ in self.tax.news_categories])
        # Trackers: trials, bills, courts
        trial_groups = self.trials_view()
        n_trials = sum(1 for t in self.trials_all if t.get("kind") == "trial")
        n_regs = sum(1 for t in self.trials_all if t.get("kind") == "registration")
        n_recruiting = sum(1 for t in self.trials_all if t.get("status") in ("recruiting", "not-yet-recruiting", "enrolling-by-invitation"))
        n_results = sum(1 for t in self.trials_all if t.get("results_posted"))
        year = self.today.isoformat()[:4]
        n_new_year = sum(1 for t in self.trials_all if (t.get("first_posted") or "")[:4] == year)
        trial_topics = Counter(x for t in self.trials_all for x in t.get("topics", []))
        trial_regions = Counter(r for t in self.trials_all for r in t.get("regions", []))
        tr_labels, tr_values = self.yearly_series(self.trials_all, 12, "first_posted")
        trials_dp = self.publish(DataPage(
            slug="trials", path="/trials/", name="Gambling trials and preregistrations",
            description=(
                f"Every registered clinical trial and public preregistration about gambling, betting or a related behaviour that the "
                f"{self.site['title']} tracks, as of {fmt_date(self.as_of, 'long')} ({len(self.trials_all)} records: {n_trials} trials and "
                f"{n_regs} preregistrations), from ClinicalTrials.gov, ISRCTN and OSF Registries, with status, sponsor, conditions, "
                f"interventions and whether results have been posted. One row per registration."
            ),
            rows=self.trials_all, columns=TRIAL_COLS, date_field="first_posted", unit="registrations", group="Research",
            json_url="/data/trials.json",
            keywords=["gambling", "clinical trials", "preregistration", "gambling treatment", "study registry", "open science"],
            measurement="Nightly automated queries to the ClinicalTrials.gov, ISRCTN and OSF Registries APIs.",
            charts=[self.chart(
                "trials-by-year", "columns", tr_labels, tr_values,
                title="Gambling trials and preregistrations, by year registered",
                subtitle="Registrations first posted each year, from ClinicalTrials.gov, ISRCTN and OSF Registries.",
                unit="registrations", caption="Counted by the year the registry record first appeared." + self.partial_note("year"),
            )],
        ))
        self.render(
            "trials.html", "trials/index.html", dp=trials_dp, section="research",
            groups=trial_groups, n_trials=n_trials, n_regs=n_regs, n_recruiting=n_recruiting, n_results=n_results, n_new_year=n_new_year,
            topics=[(x, self.tax.topic_label(x), n) for x, n in trial_topics.most_common(10)],
            regions=[(x, self.tax.regions[x]["label"], n) for x, n in trial_regions.most_common() if x in self.tax.regions],
            registries=[(k, v) for k, v in (("clinicaltrials", "ClinicalTrials.gov"), ("isrctn", "ISRCTN"), ("osf", "OSF Registries")) if any(t.get("registry") == k for t in self.trials_all)],
        )
        bills_window = self.site.get("bills_window_days", 365)
        bitems = self.bills(bills_window)
        stage_counts = Counter(b.get("stage") for b in bitems)
        juris = Counter((b.get("jurisdiction_code"), b.get("jurisdiction")) for b in bitems)
        bill_topics = Counter(x for b in bitems for x in b.get("topics", []))
        month_ago = (self.today - dt.timedelta(days=30)).isoformat()
        bill_months, bill_counts = self.monthly_series(bitems, 12, "latest_action_date")
        top_juris = sorted(((name, n) for (code, name), n in juris.items() if code), key=lambda x: -x[1])[:12]
        bills_dp = self.publish(DataPage(
            slug="bills", path="/bills/", name="Gambling bills in the state legislatures and Congress",
            description=(
                f"Every bill on gambling, sports betting, lotteries, casinos, prediction markets or self-exclusion with recorded action in the "
                f"{bills_window} days to {fmt_date(self.as_of, 'long')} ({len(bitems)} bills across {len(top_juris)} or more legislatures), with its "
                f"sponsors, its latest action and the stage it has reached. State bills from Open States, federal bills from GovInfo and "
                f"Congress.gov. One row per bill."
            ),
            rows=bitems, columns=BILL_COLS, date_field="latest_action_date", unit="bills", group="Policy",
            json_url="/data/bills.json",
            keywords=["gambling legislation", "sports betting bills", "state legislature", "prediction markets", "self-exclusion", "gambling policy", "lawmaking"],
            measurement="Nightly automated queries to Open States, GovInfo and Congress.gov; the stage is read from the recorded actions.",
            charts=[
                self.chart(
                    "bills-by-month", "columns", bill_months, bill_counts,
                    title="Gambling bills with legislative action, by month",
                    subtitle="Bills whose most recent recorded action fell in each month.",
                    unit="bills", caption="A bill is counted in the month of its latest recorded action, so it appears once." + self.partial_note("month"),
                ),
                self.chart(
                    "bills-by-legislature", "bars", [n for n, _ in top_juris], [c for _, c in top_juris],
                    title="Where gambling bills are moving",
                    subtitle=f"Legislatures with the most gambling bills active in the past {bills_window} days.",
                    unit="bills", caption="Counted from bills with recorded action in the window, not from bills introduced.",
                ),
            ] if top_juris else [],
        ))
        self.render(
            "bills.html", "bills/index.html", dp=bills_dp, section="policy",
            months=self.by_month(bitems, "latest_action_date"), count=len(bitems), window=bills_window,
            stages=[(slug, label, stage_counts.get(slug, 0)) for slug, label in STAGES if stage_counts.get(slug)],
            jurisdictions=sorted(((code, name, n) for (code, name), n in juris.items() if code), key=lambda x: x[1]),
            n_jurisdictions=len([1 for (code, _), _ in juris.items() if code and code != "us"]),
            has_federal=any(b.get("level") == "federal" for b in bitems),
            topics=[(x, self.tax.topic_label(x), n) for x, n in bill_topics.most_common(14)],
            enacted_year=[b for b in bitems if b.get("stage") == "enacted" and (b.get("latest_action_date") or "")[:4] == year],
            recent_count=sum(1 for b in bitems if (b.get("latest_action_date") or "") >= month_ago),
        )
        cases_window = self.site.get("cases_window_days", 180)
        citems = self.cases(cases_window)
        level_counts = Counter(c.get("court_level") for c in citems)
        case_topics = Counter(x for c in citems for x in c.get("topics", []))
        court_months, court_counts = self.monthly_series(citems, 6, "latest_activity")
        courts_dp = self.publish(DataPage(
            slug="courts", path="/courts/", name="Gambling court opinions and dockets",
            description=(
                f"Court opinions filed and federal dockets with activity in the {cases_window} days to {fmt_date(self.as_of, 'long')} "
                f"({len(citems)} records) that involve gambling, betting, lotteries, casinos, tribal gaming, sweepstakes or event contracts, "
                f"from CourtListener, with court, level, docket number and reporter citation. One row per opinion or docket."
            ),
            rows=citems, columns=CASE_COLS, date_field="latest_activity", unit="records", group="Policy",
            json_url="/data/cases.json",
            keywords=["gambling litigation", "sports betting law", "tribal gaming", "sweepstakes", "event contracts", "court opinions", "gambling policy"],
            measurement="Nightly automated queries to the CourtListener API for opinions and federal dockets matching the published search terms.",
            charts=[self.chart(
                "courts-by-month", "columns", court_months, court_counts,
                title="Gambling cases with court activity, by month",
                subtitle="Opinions filed and federal dockets with new filings each month.",
                unit="records", caption="Counted by the month of the most recent activity on the record." + self.partial_note("month"),
            )],
        ))
        self.render(
            "courts.html", "courts/index.html", dp=courts_dp, section="policy",
            months=self.by_month(citems, "latest_activity"), count=len(citems), window=cases_window,
            n_opinions=sum(1 for c in citems if c.get("kind") == "opinion"), n_dockets=sum(1 for c in citems if c.get("kind") == "docket"),
            levels=[(slug, label, level_counts.get(slug, 0)) for slug, label in COURT_LEVELS if level_counts.get(slug)],
            topics=[(x, self.tax.topic_label(x), n) for x, n in case_topics.most_common(14)],
            recent_opinions=sum(1 for c in citems if c.get("kind") == "opinion" and (c.get("date_filed") or "") >= month_ago),
        )
        self.render("feed_trials.xml", "trials/feed.xml", trials=sorted(self.trials_all, key=lambda t: (t.get("first_seen") or "", t["title"]), reverse=True)[:50])
        self.render("feed_bills.xml", "bills/feed.xml", bills=bitems[:50])
        self.render("feed_courts.xml", "courts/feed.xml", cases=citems[:50])
        # Digests
        self.render("digest_index.html", "digest/index.html", digests=digests)
        for dg in digests:
            self.render(
                "digest.html", f"digest/{dg['slug']}/index.html", digest=dg,
                citation=exports.text_citation(
                    self.site, f"{dg['title']} (Weekly Digest No. {dg['number']})", dg["url"],
                    as_of_long=fmt_date(self.as_of, "long"), year=int(str(dg["date"])[:4]),
                    date_long=fmt_date(str(dg["date"]), "long"),
                ),
            )
        # Reference and other pages
        for path in sorted((CONTENT_DIR / "pages").glob("*.md")):
            meta, html = read_markdown(path)
            slug = meta.get("slug", path.stem)
            if slug == "methodology":
                self.render(
                "methodology.html", f"{slug}/index.html", page=meta, body=html, log=self.fetch_log, sources=self.sources, topics=self.tax.topics,
                citation=exports.text_citation(
                    self.site, meta.get("title", slug), f"/{slug}/",
                    as_of_long=fmt_date(self.as_of, "long"), year=self.as_of.year,
                ),
                topic_min=self.tax.topic_min, designs=self.tax.designs, design_rules=self.tax.design_rules, pubtypes=self.tax.pubtypes,
                gold=load_json(DATA_DIR / "gold_report.json", {}), index_meta=load_json(DATA_DIR / "index_meta.json", {}),
                n_corrections=len(self.tax.corrections.by_key),
            )
            elif slug == "data-use":
                self.render(
                    "data_use.html", f"{slug}/index.html", page=meta, body=html,
                    catalogue=self.catalogue(), as_of=fmt_date(self.as_of, "long"),
                    catalog_schema=exports.catalog_jsonld(self.site, self.data_pages, self.as_of.isoformat()),
                    n_datasets=len(self.data_pages),
                )
            else:
                citation = None
                if meta.get("cite", True):
                    citation = exports.text_citation(
                        self.site, meta.get("title", slug), f"/{slug}/",
                        as_of_long=fmt_date(self.as_of, "long"), year=self.as_of.year,
                    )
                self.render("page.html", f"{slug}/index.html", page=meta, body=html, citation=citation)
        # Search across the whole index
        main_index = self.papers(None)
        search_ok = self.build_search(main_index)
        years = sorted({p["year"] for p in main_index if p.get("year")})
        self.render(
            "search.html", "search/index.html", search_ok=search_ok, total=len(main_index),
            coverage_from=self.coverage_from(), first_year=years[0] if years else None,
        )
        # Feeds
        self.render("feed_digest.xml", "feed.xml", digests=digests[:20])
        self.render("feed_research.xml", "research/feed.xml", papers=recent[:50])
        # Sitemap
        self.render("sitemap.xml", "sitemap.xml", urls=sorted(set(self.urls)))
        n_charts = sum(len(dp.charts) for dp in self.data_pages)
        print(
            f"built {len(self.urls)} pages; {len(recent)} studies in the {window}-day window; {len(nitems)} news items; "
            f"{len(self.data_pages)} data pages with CSVs and {n_charts} charts; fixture={self.fixture}",
            file=sys.stderr,
        )


def main() -> int:
    Builder().build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
