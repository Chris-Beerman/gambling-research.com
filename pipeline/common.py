"""Shared helpers for the fetch and build steps."""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
CONTENT_DIR = ROOT / "content"
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
SITE_DIR = ROOT / "_site"

USER_AGENT = "gambling-research-index/1.0 (+https://gambling-research.com/methodology/)"


def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")
    os.replace(tmp, path)


def today_utc() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def session(mailto: str | None = None) -> requests.Session:
    s = requests.Session()
    ua = USER_AGENT
    if mailto:
        ua += f" mailto:{mailto}"
    s.headers.update({"User-Agent": ua, "Accept": "application/json, text/xml, application/xml, */*"})
    return s


def get(s: requests.Session, url: str, *, params=None, timeout=60, tries=3, backoff=2.0, **kw) -> requests.Response:
    """GET with simple retries on network errors and 5xx/429."""
    last = None
    for attempt in range(tries):
        try:
            r = s.get(url, params=params, timeout=timeout, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code} from {url}", response=r)
            r.raise_for_status()
            return r
        except (requests.RequestException, OSError) as e:  # noqa: PERF203
            last = e
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url}: {last}")


_WS = re.compile(r"\s+")
_NONALNUM = re.compile(r"[^a-z0-9]+")


def clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)  # strip tags (JATS inline markup, HTML in feeds)
    s = html.unescape(s)
    return _WS.sub(" ", s.replace("\xa0", " ")).strip()


def norm_title(title: str) -> str:
    return _NONALNUM.sub(" ", (title or "").lower()).strip()


def norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = doi.strip().lower()
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", d)
    d = d.strip().rstrip(".")
    return d if d.startswith("10.") else None


def stable_id(*parts: str) -> str:
    h = hashlib.sha1("|".join(p or "" for p in parts).encode("utf-8")).hexdigest()
    return h[:16]


def summarize(text: str, max_chars: int = 360) -> str:
    """First sentence or two of an abstract, capped. The site links to the full
    record; it does not republish abstracts."""
    text = clean_text(text)
    # Drop structured-abstract labels at the start ("Background:", "Objectives:").
    text = re.sub(r"^(background|objectives?|aims?|introduction|purpose|importance)\s*:\s*", "", text, flags=re.I)
    if len(text) <= max_chars:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = ""
    for sent in sentences:
        if len(out) + len(sent) + 1 > max_chars:
            break
        out = (out + " " + sent).strip()
    if not out:
        out = text[: max_chars - 1].rsplit(" ", 1)[0]
    if len(out) < len(text):
        out = out.rstrip(".,;:") + " …"
    return out


def parse_date(value) -> dt.date | None:
    """Best-effort date parsing for the many shapes the sources return."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, (list, tuple)):  # Crossref date-parts: [[2026, 10, 3]]
        parts = value[0] if value and isinstance(value[0], (list, tuple)) else value
        try:
            y = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 and parts[1] else 1
            d = int(parts[2]) if len(parts) > 2 and parts[2] else 1
            return dt.date(y, m, d)
        except (ValueError, TypeError, IndexError):
            return None
    if isinstance(value, time.struct_time):
        try:
            return dt.date(value.tm_year, value.tm_mon, value.tm_mday)
        except ValueError:
            return None
    s = str(value).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"^(\d{4})-(\d{2})$", s)
    if m:
        return dt.date(int(m.group(1)), int(m.group(2)), 1)
    m = re.match(r"^(\d{4})$", s)
    if m:
        return dt.date(int(m.group(1)), 1, 1)
    try:
        from dateutil import parser as dparser

        return dparser.parse(s, fuzzy=True).date()
    except Exception:  # noqa: BLE001
        return None


def iso(d: dt.date | None) -> str | None:
    return d.isoformat() if d else None
