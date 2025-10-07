# backend/search.py
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
import feedparser
from dateutil import parser as dtparser
from datetime import datetime

import streamlit as st
from backend.feeds import ALL_FEEDS
from backend.utils import parse_entry_date, matches_keyword_multi, is_in_date_range_str
import urllib.parse
import feedparser
import pandas as pd
from backend.utils import is_in_date_range_str, matches_keyword_multi
import re

from rank_bm25 import BM25Okapi

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")  # set di Streamlit Secrets / env

def _safe_sort_key(date_str):
    try:
        if not date_str: return datetime.min
        return dtparser.parse(date_str).replace(tzinfo=None)
    except Exception:
        return datetime.min

@st.cache_data(show_spinner=False)
def search_multi_source(
    keywords: List[str],
    max_results: int,
    date_start=None,
    date_end=None,
    max_workers: int = 24,
) -> List[Dict]:
    rows: List[Dict] = []

    # 1) RSS lokal (paralel)
    def _fetch(src, url):
        try: return src, feedparser.parse(url)
        except Exception: return src, None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_fetch, s, u) for s, u in ALL_FEEDS]
        for fut in as_completed(futures):
            src, feed = fut.result()
            if not feed: continue
            for e in feed.entries:
                hits = matches_keyword_multi(e, keywords)
                if not hits: continue
                link = getattr(e, "link", "")
                if not link: continue
                dt = parse_entry_date(e)
                if (date_start or date_end) and (
                    dt is None
                    or (date_start and dt.date() < date_start)
                    or (date_end and dt.date() > date_end)
                ):
                    continue
                rows.append({
                    "title": getattr(e, "title", ""),
                    "url": link,
                    "source": src,
                    "published": dt.isoformat() if dt else getattr(e, "published", None),
                    "desc": getattr(e, "summary", ""),
                    "hit_keywords": ", ".join(hits),
                })

    # (Opsional) tambah fallback lain di sini, tapi tetap filtrasi tanggal sebelum append

    # dedup & sort
    seen = set(); uniq = []
    for r in rows:
        if r["url"] in seen: continue
        seen.add(r["url"]); uniq.append(r)

    uniq.sort(key=lambda r: _safe_sort_key(r["published"]), reverse=True)
    return uniq[:max_results]

# domain Indonesia yang umum (untuk menyaring hasil GNews ke media lokal)
INDO_DOMAINS_RE = re.compile(
    r"(kompas|detik|tempo|liputan6|tribun|antaranews|cnnindonesia|cnbcindonesia|"
    r"merdeka|republika|beritasatu|kumparan|jpnn|sindonews|medcom|gatra|"
    r"katadata|kontan|bisnis\.com|idntimes|mediaindonesia|jawapos|"
    r"thejakartapost|tempo\.co|pikiran-rakyat|prfmnews|jabarekspres|bandung\.bisnis)",
    re.I
)

def _gnews_rss_url(query: str, lang="id", country="ID"):
    # hl=id, gl=ID, ceid=ID:id → konteks Indonesia
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl={lang}&gl={country}&ceid={country}:{lang}"

def _unwrap_gnews_link(link: str) -> str:
    # sebagian sudah direct ke publisher. tapi kalau berupa redirect news.google.com/url?url=...
    try:
        if "news.google.com" not in link:
            return link
        parsed = urllib.parse.urlparse(link)
        qs = dict(urllib.parse.parse_qsl(parsed.query))
        return qs.get("url", link)
    except Exception:
        return link

def bm25_rerank(rows: list[dict], keywords: list[str], topk: int | None = None) -> list[dict]:
    if not rows:
        return rows
    df = pd.DataFrame(rows)
    df["__txt"] = (df.get("title","") + " " + df.get("desc","")).str.lower()
    corpus = [t.split() for t in df["__txt"].tolist()]
    bm25 = BM25Okapi(corpus)
    query_tokens = " ".join(keywords).lower().split()
    scores = bm25.get_scores(query_tokens)
    df["__bm25"] = scores
    df = df.sort_values("__bm25", ascending=False)
    if topk:
        df = df.head(topk)
    return df.drop(columns=["__txt","__bm25"], errors="ignore").to_dict(orient="records")

def search_google_news_rss(
    keywords: list[str],
    limit: int = 100,
    date_start=None,
    date_end=None,
    filter_to_indonesia: bool = True,
) -> list[dict]:
    """Cari via Google News RSS untuk setiap keyword, lalu gabung & saring tanggal/brand lokal."""
    out = []
    per_kw = max(5, limit // max(1, len(keywords)))  # alokasi kasar per keyword

    for kw in keywords:
        rss_url = _gnews_rss_url(kw, lang="id", country="ID")
        feed = feedparser.parse(rss_url)
        for e in feed.entries[:per_kw]:
            title = getattr(e, "title", "")
            desc = getattr(e, "summary", "")
            link = _unwrap_gnews_link(getattr(e, "link", ""))
            pub = getattr(e, "published", None)

            # saring tanggal (inklusif) → skip jika filter aktif & tanggal tak ada/di luar range
            if not is_in_date_range_str(pub, date_start, date_end):
                continue

            # saring domain ke media Indonesia (opsional)
            if filter_to_indonesia and not INDO_DOMAINS_RE.search(link):
                continue

            # pastikan match setidaknya salah satu keyword (kadang GNews “longgar”)
            hits = [k for k in keywords if k.lower() in (title + " " + desc).lower()]
            if not hits:
                continue

            out.append({
                "title": title,
                "url": link,
                "source": "Google News",
                "published": pub,
                "desc": desc,
                "hit_keywords": ", ".join(hits),
            })

    # dedup by URL
    seen = set(); uniq = []
    for r in out:
        if r["url"] in seen: continue
        seen.add(r["url"]); uniq.append(r)
    return uniq[:limit]
