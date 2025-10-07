# backend/extract.py
import re
import time, random
from typing import List, Dict, Optional
import requests
import streamlit as st
import trafilatura
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_article(url: str, user_agent: Optional[str] = None) -> Dict:
    data = {"url": url, "title_article": None, "text": None,
            "publish_date": None, "meta_desc": None, "final_url": None}
    UA = user_agent or ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
        "Referer": "https://news.google.com/"
    }

    def _extract_with_trafilatura(html: Optional[str], src_url: str):
        try:
            extracted = trafilatura.extract(
                html=html, url=src_url,
                include_comments=False, include_tables=False,
                with_metadata=True, favor_recall=True
            )
            return extracted
        except Exception:
            return None

    def _apply_meta(html_text: str):
        try:
            meta = trafilatura.metadata.extract_metadata(html_text)
            if meta:
                data["title_article"]  = data["title_article"]  or meta.title
                data["publish_date"]   = data["publish_date"]   or meta.date
                data["meta_desc"]      = data["meta_desc"]      or meta.description
        except Exception:
            pass

    def _find_amp_and_canonical(html_text: str):
        amp_url = None; canonical_url = None
        try:
            # cari via regex ringan
            m_amp = re.search(r'<link[^>]+rel=["\']amphtml["\'][^>]+href=["\']([^"\']+)["\']', html_text, re.I)
            if m_amp: amp_url = m_amp.group(1)
            m_canon = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', html_text, re.I)
            if m_canon: canonical_url = m_canon.group(1)
        except Exception:
            pass
        return amp_url, canonical_url

    session = requests.Session()
    session.headers.update(headers)

    # STEP 0: Jika ini link Google News, follow redirect untuk dapat final URL
    final_url = url
    first_html = None
    if "news.google.com" in url:
        try:
            r0 = session.get(url, timeout=20, allow_redirects=True)
            if r0.ok:
                final_url = r0.url or url
                r0.encoding = r0.apparent_encoding or r0.encoding
                first_html = r0.text
        except Exception:
            pass

    data["final_url"] = final_url

    # STEP 1: coba trafilatura.fetch_url pada final_url
    try:
        downloaded = trafilatura.fetch_url(final_url, no_ssl=True, user_agent=UA)
        if downloaded:
            extracted = _extract_with_trafilatura(downloaded, final_url)
            if extracted and len(extracted) > 120:
                data["text"] = extracted
                _apply_meta(downloaded)
                if not data["title_article"]:
                    bex = trafilatura.bare_extraction(downloaded, with_metadata=True)
                    if bex and "title" in bex: data["title_article"] = bex["title"]
                return data
    except Exception:
        pass

    # STEP 2: requests.get (kalau belum punya html)
    html = first_html
    if html is None:
        try:
            r = session.get(final_url, timeout=20, allow_redirects=True)
            if r.ok and "text/html" in r.headers.get("Content-Type",""):
                r.encoding = r.apparent_encoding or r.encoding
                html = r.text
                data["final_url"] = r.url or final_url
        except Exception:
            html = None

    # STEP 3: ekstrak dari HTML yang ada
    if html:
        extracted = _extract_with_trafilatura(html, data["final_url"])
        if extracted and len(extracted) > 120:
            data["text"] = extracted
            _apply_meta(html)
            if not data["title_article"]:
                try:
                    bex = trafilatura.bare_extraction(html, with_metadata=True)
                    if bex and "title" in bex: data["title_article"] = bex["title"]
                except Exception:
                    pass
            # cek canonical & gunakan sebagai final_url untuk konsistensi
            amp_u, canon_u = _find_amp_and_canonical(html)
            if canon_u: data["final_url"] = canon_u
            return data

        # STEP 3b: coba AMP (sering lebih bersih)
        amp_u, canon_u = _find_amp_and_canonical(html)
        if amp_u:
            try:
                r_amp = session.get(amp_u, timeout=20)
                if r_amp.ok:
                    r_amp.encoding = r_amp.apparent_encoding or r_amp.encoding
                    amp_html = r_amp.text
                    extracted = _extract_with_trafilatura(amp_html, amp_u)
                    if extracted and len(extracted) > 100:
                        data["text"] = extracted
                        data["final_url"] = canon_u or amp_u
                        _apply_meta(amp_html)
                        return data
            except Exception:
                pass

    # STEP 4: readability-lxml
    try:
        from readability import Document
        if not html:
            r = session.get(final_url, timeout=20)
            if not r.ok: raise RuntimeError("HTTP not OK")
            r.encoding = r.apparent_encoding or r.encoding
            html = r.text
        doc = Document(html)
        content_html = doc.summary()
        text = re.sub(r"<[^>]+>", " ", content_html or "")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 100:
            data["text"] = text
            data["title_article"] = data["title_article"] or (doc.short_title() or None)
            return data
    except Exception:
        pass

    # STEP 5: boilerpy3
    try:
        from boilerpy3 import extractors
        if not html:
            r = session.get(final_url, timeout=20)
            if not r.ok: raise RuntimeError("HTTP not OK")
            r.encoding = r.apparent_encoding or r.encoding
            html = r.text
        extractor = extractors.ArticleExtractor()
        text = extractor.get_content(html)
        text = re.sub(r"\s+", " ", text or "").strip()
        if len(text) > 100:
            data["text"] = text
            return data
    except Exception:
        pass

    # STEP 6: jusText
    try:
        import justext
        if not html:
            r = session.get(final_url, timeout=20)
            if not r.ok: raise RuntimeError("HTTP not OK")
            r.encoding = r.apparent_encoding or r.encoding
            html = r.text
        paragraphs = justext.justext(
            html.encode(r.encoding or "utf-8", errors="ignore"),
            justext.get_stoplist("Indonesian")
        )
        text = " ".join(p.text for p in paragraphs if not p.is_boilerplate)
        text = re.sub(r"\s+", " ", text or "").strip()
        if len(text) > 100:
            data["text"] = text
            return data
    except Exception:
        pass

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
