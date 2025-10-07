# backend/utils.py
import re
from datetime import datetime
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from dateutil import parser as dtparser
from zoneinfo import ZoneInfo

def parse_entry_date(entry):
    candidates = [
        getattr(entry, "published", None),
        getattr(entry, "updated", None),
        entry.get("published") if isinstance(entry, dict) else None,
        entry.get("updated") if isinstance(entry, dict) else None,
    ]
    for c in candidates:
        if not c: continue
        try:
            dt = dtparser.parse(c)
            if dt.tzinfo:
                dt = dt.astimezone(ZoneInfo("Asia/Jakarta")).replace(tzinfo=None)
            return dt
        except Exception:
            pass
    return None

def is_in_date_range_str(date_str, start_date, end_date) -> bool:
    if not (start_date or end_date):
        return True
    if not date_str:
        return False
    try:
        dt = dtparser.parse(date_str)
        if dt.tzinfo:
            dt = dt.astimezone(ZoneInfo("Asia/Jakarta")).replace(tzinfo=None)
        d = dt.date()
        if start_date and d < start_date: return False
        if end_date and d > end_date: return False
        return True
    except Exception:
        return False

def matches_keyword_multi(entry, keywords):
    title = (getattr(entry, "title", "") or "").lower()
    summary = (getattr(entry, "summary", "") or "").lower()
    hits = []
    for kw in keywords:
        k = kw.strip().lower()
        if k and (k in title or k in summary):
            hits.append(kw)
    return hits

def canonicalize(u: str) -> str:
    try:
        p = urlparse(u)
        q = [(k,v) for (k,v) in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith(("utm_","gclid","fbclid"))]
        path = p.path.replace("/amp", "").replace("/amp/", "/")
        return urlunparse((p.scheme, p.netloc, path, "", urlencode(q), ""))
    except Exception:
        return u
