"""Render the static site from data/ and content/ into _site/.

    python -m pipeline.build
"""
from __future__ import annotations

import datetime as dt
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .common import CONTENT_DIR, DATA_DIR, ROOT, SITE_DIR, STATIC_DIR, TEMPLATE_DIR, load_json, load_yaml, today_utc
from .normalize import Taxonomy

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
            }
        )
        self.urls: list[str] = []

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

    # ---- rendering ----
    def render(self, template: str, out_path: str, **ctx):
        tpl = self.env.get_template(template)
        base = {
            "site": self.site,
            "today": self.today,
            "nav": [("/research/", "Research", "research"), ("/news/", "News", "news"), ("/digest/", "Digest", "digest"), ("/journals/", "Reference", "reference")],
            "fixture": self.fixture,
            "updated": fmt_time_utc(self.fetch_log.get("finished")),
            "path": "/" + out_path.replace("index.html", "").strip("/") + ("/" if not out_path.endswith(".xml") and not out_path.endswith(".txt") else ""),
        }
        if base["path"] == "//":
            base["path"] = "/"
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
        for name in ("papers.json", "news.json", "fetch_log.json", "weekly/latest.json"):
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
        design_counts = Counter(x for p in recent for x in p.get("designs", []))
        topics_sorted = [(slug, self.tax.topic_label(slug), n) for slug, n in topic_counts.most_common()]

        # Home
        home_news = [n for n in self.news(self.site.get("home_news_days", 7)) if n.get("primary") != "industry"][: self.site.get("home_news_count", 12)]
        self.render(
            "home.html", "index.html",
            papers=recent[: self.site.get("home_paper_count", 24)], this_week_count=len(this_week), total_count=len(self.papers(None)),
            news=home_news, digest=digests[0] if digests else None, topics=topics_sorted[:14],
            journal_feed_count=sum(1 for f in self.sources.get("journal_feeds", []) if f.get("enabled", True)),
        )
        # Research index
        self.render(
            "research.html", "research/index.html",
            weeks=self.by_week(recent), count=len(recent), window=window, topics=topics_sorted,
            regions=[(s, self.tax.regions[s]["label"], n) for s, n in region_counts.most_common() if s in self.tax.regions],
            designs=[(s, self.tax.design_label(s), n) for s, n in design_counts.most_common()], this_week_count=len(this_week),
        )
        # Borderline (low relevance) for transparency
        low = self.papers(window, relevance="low")
        self.render("research.html", "research/borderline/index.html", weeks=self.by_week(low), count=len(low), window=window, topics=[], regions=[], designs=[], borderline=True, this_week_count=0)
        # Topic pages
        topic_window = self.site.get("topic_window_days", 365)
        year_papers = self.papers(topic_window)
        for slug, label, _ in self.tax.topics:
            tp = [p for p in year_papers if slug in p.get("topics", [])]
            self.render("topic.html", f"research/topics/{slug}/index.html", papers=tp, label=label, slug=slug, count=len(tp), window=topic_window)
        self.render("topics.html", "research/topics/index.html", topics=[(s, l, sum(1 for p in year_papers if s in p.get("topics", []))) for s, l, _ in self.tax.topics], window=topic_window)
        # Monthly archive
        months: dict[str, list] = defaultdict(list)
        for p in self.papers(None):
            months[(p.get("first_seen") or "0000-00")[:7]].append(p)
        month_list = sorted(months, reverse=True)
        for ym in month_list:
            y, m = ym.split("-")
            self.render("archive.html", f"research/archive/{y}/{m}/index.html", papers=months[ym], ym=ym, label=fmt_date(f"{ym}-01", "month"), months=[(x, fmt_date(f"{x}-01", "month"), len(months[x])) for x in month_list])
        self.render("archive_index.html", "research/archive/index.html", months=[(x, fmt_date(f"{x}-01", "month"), len(months[x])) for x in month_list])
        # News
        news_window = self.site.get("news_window_days", 30)
        nitems = self.news(news_window)
        cat_counts = Counter(n.get("primary") for n in nitems)
        self.render("news.html", "news/index.html", days=self.by_day(nitems), count=len(nitems), window=news_window, categories=[(s, l, cat_counts.get(s, 0)) for s, l, _ in self.tax.news_categories])
        # Digests
        self.render("digest_index.html", "digest/index.html", digests=digests)
        for dg in digests:
            self.render("digest.html", f"digest/{dg['slug']}/index.html", digest=dg)
        # Reference and other pages
        for path in sorted((CONTENT_DIR / "pages").glob("*.md")):
            meta, html = read_markdown(path)
            slug = meta.get("slug", path.stem)
            if slug == "methodology":
                self.render("methodology.html", f"{slug}/index.html", page=meta, body=html, log=self.fetch_log, sources=self.sources, topics=self.tax.topics, designs=self.tax.designs)
            else:
                self.render("page.html", f"{slug}/index.html", page=meta, body=html)
        # Feeds
        self.render("feed_digest.xml", "feed.xml", digests=digests[:20])
        self.render("feed_research.xml", "research/feed.xml", papers=recent[:50])
        # Sitemap
        self.render("sitemap.xml", "sitemap.xml", urls=sorted(set(self.urls)))
        print(f"built {len(self.urls)} pages; {len(recent)} studies in the {window}-day window; {len(nitems)} news items; fixture={self.fixture}", file=sys.stderr)


def main() -> int:
    Builder().build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
