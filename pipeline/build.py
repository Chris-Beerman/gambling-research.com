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
            }
        )
        self.urls: list[str] = []
        # Main navigation: href, label, kind (colour cue), and the path prefixes it covers.
        self.nav = [
            {"href": "/research/", "label": "Research", "kind": "research", "paths": ["/research/", "/trials/"]},
            {"href": "/news/", "label": "Policy", "kind": "news", "paths": ["/news/", "/bills/", "/courts/"]},
            {"href": "/digest/", "label": "Digest", "kind": "digest", "paths": ["/digest/"]},
            {"href": "/journals/", "label": "Reference", "kind": "reference", "paths": ["/journals/", "/conferences/", "/datasets/", "/measures/", "/guide/"]},
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
        for slug, label, statuses in self.STATUS_GROUPS:
            items = [t for t in self.trials_all if t.get("status") in statuses]
            if slug == "completed":
                items.sort(key=lambda t: (t.get("completion_date") or t.get("last_updated") or "", t["title"]), reverse=True)
            elif slug == "registered":
                items.sort(key=lambda t: (t.get("first_posted") or "", t["title"]), reverse=True)
            else:
                items.sort(key=lambda t: (t.get("start_date") or t.get("first_posted") or "", t["title"]), reverse=True)
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

    # ---- rendering ----
    def render(self, template: str, out_path: str, **ctx):
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
        for name in ("papers.json", "news.json", "trials.json", "bills.json", "cases.json", "fetch_log.json", "weekly/latest.json"):
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
        )
        # Research index
        self.render(
            "research.html", "research/index.html", section="research",
            weeks=self.by_week(recent), count=len(recent), window=window, topics=topics_sorted,
            regions=[(s, self.tax.regions[s]["label"], n) for s, n in region_counts.most_common() if s in self.tax.regions],
            designs=[(s, self.tax.design_label(s), n) for s, n in design_counts.most_common()], this_week_count=len(this_week),
        )
        # Borderline (low relevance) for transparency
        low = self.papers(window, relevance="low")
        self.render("research.html", "research/borderline/index.html", section="research", weeks=self.by_week(low), count=len(low), window=window, topics=[], regions=[], designs=[], borderline=True, this_week_count=0)
        # Topic pages
        topic_window = self.site.get("topic_window_days", 365)
        year_papers = self.papers(topic_window)
        for slug, label, _ in self.tax.topics:
            tp = [p for p in year_papers if slug in p.get("topics", [])]
            self.render("topic.html", f"research/topics/{slug}/index.html", section="research", papers=tp, label=label, slug=slug, count=len(tp), window=topic_window)
        self.render("topics.html", "research/topics/index.html", section="research", topics=[(s, l, sum(1 for p in year_papers if s in p.get("topics", []))) for s, l, _ in self.tax.topics], window=topic_window)
        # Monthly archive
        months: dict[str, list] = defaultdict(list)
        for p in self.papers(None):
            months[(p.get("first_seen") or "0000-00")[:7]].append(p)
        month_list = sorted(months, reverse=True)
        for ym in month_list:
            y, m = ym.split("-")
            self.render("archive.html", f"research/archive/{y}/{m}/index.html", section="research", papers=months[ym], ym=ym, label=fmt_date(f"{ym}-01", "month"), months=[(x, fmt_date(f"{x}-01", "month"), len(months[x])) for x in month_list])
        self.render("archive_index.html", "research/archive/index.html", section="research", months=[(x, fmt_date(f"{x}-01", "month"), len(months[x])) for x in month_list])
        # News
        news_window = self.site.get("news_window_days", 30)
        nitems = self.news(news_window)
        cat_counts = Counter(n.get("primary") for n in nitems)
        self.render("news.html", "news/index.html", section="policy", days=self.by_day(nitems), count=len(nitems), window=news_window, categories=[(s, l, cat_counts.get(s, 0)) for s, l, _ in self.tax.news_categories])
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
        self.render(
            "trials.html", "trials/index.html", section="research",
            groups=trial_groups, n_trials=n_trials, n_regs=n_regs, n_recruiting=n_recruiting, n_results=n_results, n_new_year=n_new_year,
            topics=[(x, self.tax.topic_label(x), n) for x, n in trial_topics.most_common(16)],
            regions=[(x, self.tax.regions[x]["label"], n) for x, n in trial_regions.most_common() if x in self.tax.regions],
            registries=[(k, v) for k, v in (("clinicaltrials", "ClinicalTrials.gov"), ("isrctn", "ISRCTN"), ("osf", "OSF Registries")) if any(t.get("registry") == k for t in self.trials_all)],
        )
        bills_window = self.site.get("bills_window_days", 365)
        bitems = self.bills(bills_window)
        stage_counts = Counter(b.get("stage") for b in bitems)
        juris = Counter((b.get("jurisdiction_code"), b.get("jurisdiction")) for b in bitems)
        bill_topics = Counter(x for b in bitems for x in b.get("topics", []))
        month_ago = (self.today - dt.timedelta(days=30)).isoformat()
        self.render(
            "bills.html", "bills/index.html", section="policy",
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
        self.render(
            "courts.html", "courts/index.html", section="policy",
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
