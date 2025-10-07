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
