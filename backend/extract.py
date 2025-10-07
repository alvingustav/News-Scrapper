# backend/extract.py
import re
import time, random
from typing import List, Dict, Optional
import requests
import streamlit as st
import trafilatura
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_article(url: str, user_agent: Optional[str] = None) -> Dict:
    data = {"url": url, "title_article": None, "text": None, "publish_date": None, "meta_desc": None}
    UA = user_agent or ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    headers = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
               "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7", "Cache-Control": "no-cache",
               "Pragma": "no-cache", "Connection": "keep-alive", "Referer": "https://www.google.com/"}

    def _meta_from(downloaded: str):
        try:
            meta = trafilatura.metadata.extract_metadata(downloaded)
            if meta:
                data["title_article"] = data["title_article"] or meta.title
                data["publish_date"] = data["publish_date"] or meta.date
                data["meta_desc"] = data["meta_desc"] or meta.description
        except Exception: pass

    # 1) trafilatura.fetch_url
    try:
        downloaded = trafilatura.fetch_url(url, no_ssl=True, user_agent=UA)
        if downloaded:
            extracted = trafilatura.extract(downloaded, include_comments=False, include_tables=False, with_metadata=True)
            if extracted and len(extracted) > 60:
                data["text"] = extracted; _meta_from(downloaded)
                if not data["title_article"]:
                    bex = trafilatura.bare_extraction(downloaded, with_metadata=True)
                    if bex and "title" in bex: data["title_article"] = bex["title"]
                return data
    except Exception: pass

    # 2) requests.get + extract html
    html = None
    try:
        r = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        if r.ok and "text/html" in r.headers.get("Content-Type",""):
            r.encoding = r.apparent_encoding or r.encoding
            html = r.text
            extracted = trafilatura.extract(html, include_comments=False, include_tables=False, with_metadata=True, url=url)
            if extracted and len(extracted) > 60:
                data["text"] = extracted
                try:
                    meta = trafilatura.metadata.extract_metadata(html)
                    if meta:
                        data["title_article"] = data["title_article"] or meta.title
                        data["publish_date"] = data["publish_date"] or meta.date
                        data["meta_desc"] = data["meta_desc"] or meta.description
                except Exception: pass
                if not data["title_article"]:
                    try:
                        bex = trafilatura.bare_extraction(html, with_metadata=True)
                        if bex and "title" in bex: data["title_article"] = bex["title"]
                    except Exception: pass
                return data
    except Exception: pass

    # 3) readability-lxml
    try:
        from readability import Document
        if html is None:
            r = requests.get(url, headers=headers, timeout=20)
            if not r.ok: raise RuntimeError("HTTP not OK")
            r.encoding = r.apparent_encoding or r.encoding
            html = r.text
        doc = Document(html)
        content_html = doc.summary()
        text = re.sub(r"<[^>]+>", " ", content_html or "")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 60:
            data["text"] = text; data["title_article"] = data["title_article"] or (doc.short_title() or None)
            return data
    except Exception: pass

    # 4) boilerpy3
    try:
        from boilerpy3 import extractors
        if html is None:
            r = requests.get(url, headers=headers, timeout=20)
            if not r.ok: raise RuntimeError("HTTP not OK")
            r.encoding = r.apparent_encoding or r.encoding
            html = r.text
        extractor = extractors.ArticleExtractor()
        text = extractor.get_content(html)
        text = re.sub(r"\s+", " ", text or "").strip()
        if len(text) > 60:
            data["text"] = text; return data
    except Exception: pass

    # 5) jusText
    try:
        import justext
        if html is None:
            r = requests.get(url, headers=headers, timeout=20)
            if not r.ok: raise RuntimeError("HTTP not OK")
            r.encoding = r.apparent_encoding or r.encoding
            html = r.text
        paragraphs = justext.justext(html.encode(r.encoding or "utf-8", errors="ignore"),
                                     justext.get_stoplist("Indonesian"))
        text = " ".join(p.text for p in paragraphs if not p.is_boilerplate)
        text = re.sub(r"\s+", " ", text or "").strip()
        if len(text) > 60:
            data["text"] = text; return data
    except Exception: pass

    return data

@st.cache_data(show_spinner=False)
def fetch_articles(urls: List[str], user_agent: Optional[str] = None, max_workers: int = 8):
    def fetch_with_delay(u):
        time.sleep(random.uniform(0.4, 1.2))  # sopan
        return fetch_article(u, user_agent)
    out = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(fetch_with_delay, u) for u in urls]
        for fut in as_completed(futures):
            out.append(fut.result())
    return out
