# backend/extract.py
from __future__ import annotations

import html as htmllib
import re
import time
import random
import urllib.parse
from typing import List, Dict, Optional, Tuple

import requests
import streamlit as st
import trafilatura
from concurrent.futures import ThreadPoolExecutor, as_completed

import base64
from urllib.parse import urlparse, parse_qs

import json
from urllib.parse import quote, urlparse
from bs4 import BeautifulSoup


# =========================
# Utilities (resolvers/meta)
# =========================

def _first_external_href(html_text: str) -> Optional[str]:
    """Ambil href eksternal pertama (bukan *.google.com/news.google.com)."""
    try:
        hrefs = re.findall(r'href=["\'](https?://[^"\']+)["\']', html_text, re.I)
        for u in hrefs:
            if "google.com" not in u and "news.google.com" not in u:
                return htmllib.unescape(u)
    except Exception:
        pass
    return None


def get_decoding_params(gn_art_id: str, session: requests.Session) -> Dict:
    """
    Ambil parameter decoding (signature, timestamp) dari Google News article.
    Fallback: coba /articles dulu, kalau gagal coba /rss/articles
    """
    urls_to_try = [
        f"https://news.google.com/articles/{gn_art_id}",
        f"https://news.google.com/rss/articles/{gn_art_id}"
    ]
    
    for url in urls_to_try:
        try:
            response = session.get(url, timeout=10)
            if not response.ok:
                continue
                
            soup = BeautifulSoup(response.text, "html.parser")
            div = soup.select_one("c-wiz > div")
            
            if div:
                signature = div.get("data-n-a-sg")
                timestamp = div.get("data-n-a-ts")
                
                if signature and timestamp:
                    return {
                        "signature": signature,
                        "timestamp": timestamp,
                        "gn_art_id": gn_art_id,
                    }
        except Exception:
            continue
    
    raise ValueError(f"Cannot get decoding params for {gn_art_id}")


def decode_google_news_batch(articles: List[Dict], session: requests.Session) -> List[str]:
    """
    Decode multiple Google News URLs menggunakan batchexecute API.
    Articles format: [{"signature": "...", "timestamp": "...", "gn_art_id": "..."}]
    Returns: List of decoded URLs
    """
    articles_reqs = [
        [
            "Fbv4je",
            f'["garturlreq",[[\"X\",\"X\",[\"X\",\"X\"],null,null,1,1,\"US:en\",null,1,null,null,null,null,null,0,1],\"X\",\"X\",1,[1,1,1],1,1,null,0,0,null,0],"{art["gn_art_id"]}",{art["timestamp"]},"{art["signature"]}"]',
        ]
        for art in articles
    ]
    
    payload = f"f.req={quote(json.dumps([articles_reqs]))}"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Referer": "https://news.google.com/"
    }
    
    try:
        response = session.post(
            url="https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers=headers,
            data=payload,
            timeout=20
        )
        response.raise_for_status()
        
        # Parse response
        parts = response.text.split("\n\n")
        if len(parts) < 2:
            raise ValueError("Invalid batchexecute response")
        
        decoded = json.loads(parts[1])
        return [json.loads(res[2])[1] for res in decoded[:-2]]
        
    except Exception as e:
        raise ValueError(f"Batch decode failed: {e}")


def resolve_gnews_new(url: str, session: requests.Session) -> str:
    """
    Resolve Google News URL menggunakan metode batchexecute (2024-2025).
    Metode ini diperlukan untuk URL format /articles/ atau /rss/articles/
    """
    try:
        parsed = urlparse(url)
        path_parts = parsed.path.split("/")
        
        # Extract article ID dari URL
        gn_art_id = None
        if "articles" in path_parts:
            idx = path_parts.index("articles")
            if idx + 1 < len(path_parts):
                gn_art_id = path_parts[idx + 1]
        
        if not gn_art_id:
            return url
        
        # Get decoding params
        params = get_decoding_params(gn_art_id, session)
        
        # Decode URL
        decoded_urls = decode_google_news_batch([params], session)
        
        if decoded_urls and len(decoded_urls) > 0:
            return decoded_urls[0]
        
        return url
        
    except Exception as e:
        st.warning(f"⚠️ Google News decode error: {str(e)[:100]}")
        return url


def resolve_gnews_advanced(url: str, session: requests.Session, timeout: int = 20) -> Tuple[str, Optional[str]]:
    """
    Resolve Google News URL dengan berbagai metode:
    1. Decode CBMi base64 URLs
    2. Follow redirects dengan session cookies
    3. Extract dari JavaScript redirect
    """
    final_url = url
    first_html = None
    
    try:
        # Method 1: Decode base64 articles URL
        if "/articles/CBMi" in url or "/articles/CAIi" in url:
            # Extract base64 portion
            match = re.search(r'/articles/(CBMi[A-Za-z0-9_-]+|CAIi[A-Za-z0-9_-]+)', url)
            if match:
                try:
                    encoded = match.group(1)
                    # Tambahkan padding jika perlu
                    padding = len(encoded) % 4
                    if padding:
                        encoded += '=' * (4 - padding)
                    
                    decoded = base64.urlsafe_b64decode(encoded).decode('utf-8', errors='ignore')
                    # Cari URL dalam decoded content
                    url_match = re.search(r'https?://[^\s\x00-\x1f\"\'<>]+', decoded)
                    if url_match:
                        final_url = url_match.group(0)
                        # Validate it's not Google domain
                        if "google.com" not in final_url:
                            return final_url, None
                except Exception:
                    pass
        
        # Method 2: Standard redirect following dengan cookies
        session.cookies.clear()
        r = session.get(url, timeout=timeout, allow_redirects=True)
        
        if r.ok and r.url:
            final_url = r.url
            
            # Jika masih di Google News, extract dari HTML
            if "news.google.com" in final_url:
                r.encoding = r.apparent_encoding or 'utf-8'
                first_html = r.text
                
                # Method 3a: Meta refresh
                meta_match = re.search(
                    r'<meta[^>]*http-equiv=["\']refresh["\'][^>]*content=["\'][^;]*;\s*url=([^"\']+)',
                    first_html, re.I
                )
                if meta_match:
                    redirect_url = htmllib.unescape(meta_match.group(1))
                    if redirect_url and "google.com" not in redirect_url:
                        final_url = redirect_url
                        return final_url, first_html
                
                # Method 3b: JavaScript window.location
                js_match = re.search(
                    r'window\.location\s*=\s*["\']([^"\']+)["\']',
                    first_html, re.I
                )
                if js_match:
                    redirect_url = htmllib.unescape(js_match.group(1))
                    if redirect_url and "google.com" not in redirect_url:
                        final_url = redirect_url
                        return final_url, first_html
                
                # Method 3c: First external link
                ext = _first_external_href(first_html)
                if ext:
                    final_url = ext
                    
    except Exception as e:
        pass
    
    return final_url, first_html



def _apply_meta_from_html(dest: Dict, html_text: str) -> None:
    """Isi title/date/desc dari metadata trafilatura bila tersedia."""
    try:
        meta = trafilatura.metadata.extract_metadata(html_text)
        if meta:
            dest["title_article"] = dest.get("title_article") or meta.title
            dest["publish_date"] = dest.get("publish_date") or meta.date
            dest["meta_desc"] = dest.get("meta_desc") or meta.description
    except Exception:
        pass


def _find_amp_and_canonical(html_text: str) -> Tuple[Optional[str], Optional[str]]:
    """Cari <link rel='amphtml'> dan <link rel='canonical'> sederhana via regex."""
    amp_url = None
    canonical_url = None
    try:
        m_amp = re.search(
            r'<link[^>]+rel=["\']amphtml["\'][^>]+href=["\']([^"\']+)["\']',
            html_text, re.I
        )
        if m_amp:
            amp_url = m_amp.group(1)

        m_canon = re.search(
            r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
            html_text, re.I
        )
        if m_canon:
            canonical_url = m_canon.group(1)
    except Exception:
        pass
    return amp_url, canonical_url


def _extract_with_trafilatura(html: Optional[str], src_url: str) -> Optional[str]:
    """Pembungkus trafilatura.extract dengan opsi yang cenderung lebih 'recall'."""
    try:
        return trafilatura.extract(
            html=html, url=src_url,
            include_comments=False,
            include_tables=False,
            with_metadata=True,
            favor_recall=True
        )
    except Exception:
        return None


# =========================
# Main extractors
# =========================

def fetch_article(url: str, user_agent: Optional[str] = None) -> Dict:
    """
    Ekstraksi berlapis dari suatu URL.
    - Handle khusus Google News (resolve ke publisher)
    - Trafilatura → AMP fallback → Readability → Boilerpy3 → JusText
    Mengembalikan dict minimal: {url, final_url, title_article, text, publish_date, meta_desc}
    """
    data: Dict = {
        "url": url,
        "final_url": None,
        "title_article": None,
        "text": None,
        "publish_date": None,
        "meta_desc": None,
        # tambahan debug opsional:
        "extractor_used": None,
        "error": None,
    }

    UA = user_agent or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
        "Referer": "https://news.google.com/",
    }

    session = requests.Session()
    session.headers.update(headers)

    # STEP 0 — resolve Google News → publisher (METODE BARU)
    final_url = url
    first_html: Optional[str] = None
    
    try:
        if "news.google.com" in url:
            # Gunakan metode baru batchexecute
            final_url = resolve_gnews_new(url, session)
            
            # Cek apakah berhasil
            if "news.google.com" in final_url:
                data["error"] = "gnews_unresolved"
                st.warning(f"⚠️ Gagal resolve Google News: {url[:80]}...")
            else:
                st.success(f"✅ Resolved: {final_url[:80]}...")
                
    except Exception as e:
        data["error"] = f"resolve_gnews: {e}"
        st.error(f"❌ Error resolving: {str(e)[:100]}")
    
    data["final_url"] = final_url

    # Helper: simple backoff for 429/503
    def get_with_backoff(u: str, tries: int = 3, tout: int = 20) -> Optional[requests.Response]:
        for i in range(tries):
            try:
                r = session.get(u, timeout=tout, allow_redirects=True)
                if r.status_code in (429, 503):
                    time.sleep((2 ** i) + random.random())
                    continue
                return r
            except Exception:
                time.sleep((2 ** i) * 0.5 + random.random())
        return None

    # STEP 1 — trafilatura.fetch_url langsung di final_url
    try:
        downloaded = trafilatura.fetch_url(final_url, no_ssl=True, user_agent=UA)
        if downloaded:
            extracted = _extract_with_trafilatura(downloaded, final_url)
            if extracted and len(extracted) > 120:
                data["text"] = extracted
                _apply_meta_from_html(data, downloaded)
                if not data["title_article"]:
                    try:
                        bex = trafilatura.bare_extraction(downloaded, with_metadata=True)
                        if bex and "title" in bex:
                            data["title_article"] = bex["title"]
                    except Exception:
                        pass
                data["extractor_used"] = "trafilatura.fetch_url"
                return data
    except Exception:
        pass

    # STEP 2 — requests ke final_url (pakai first_html kalau sudah ada dari resolver)
    html = first_html
    if html is None:
        r = get_with_backoff(final_url)
        if r and r.ok and "text/html" in (r.headers.get("Content-Type", "") or ""):
            r.encoding = r.apparent_encoding or r.encoding
            html = r.text
            data["final_url"] = r.url or final_url

    # STEP 3 — trafilatura.extract dari HTML mentah
    if html:
        extracted = _extract_with_trafilatura(html, data["final_url"] or final_url)
        if extracted and len(extracted) > 120:
            data["text"] = extracted
            _apply_meta_from_html(data, html)
            if not data["title_article"]:
                try:
                    bex = trafilatura.bare_extraction(html, with_metadata=True)
                    if bex and "title" in bex:
                        data["title_article"] = bex["title"]
                except Exception:
                    pass
            # canonical/AMP
            amp_u, canon_u = _find_amp_and_canonical(html)
            if canon_u:
                data["final_url"] = canon_u
            data["extractor_used"] = "trafilatura.extract(html)"
            return data

        # STEP 3b — AMP fallback (sering lebih bersih)
        amp_u, canon_u = _find_amp_and_canonical(html)
        if amp_u:
            r_amp = get_with_backoff(amp_u)
            if r_amp and r_amp.ok:
                r_amp.encoding = r_amp.apparent_encoding or r_amp.encoding
                amp_html = r_amp.text
                extracted = _extract_with_trafilatura(amp_html, amp_u)
                if extracted and len(extracted) > 100:
                    data["text"] = extracted
                    data["final_url"] = canon_u or amp_u
                    _apply_meta_from_html(data, amp_html)
                    data["extractor_used"] = "AMP(trafilatura)"
                    return data

    # STEP 4 — readability-lxml
    try:
        from readability import Document
        if not html:
            r = get_with_backoff(final_url)
            if r and r.ok:
                r.encoding = r.apparent_encoding or r.encoding
                html = r.text
                data["final_url"] = r.url or final_url
        if html:
            doc = Document(html)
            content_html = doc.summary()
            text = re.sub(r"<[^>]+>", " ", content_html or "")
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 100:
                data["text"] = text
                data["title_article"] = data.get("title_article") or (doc.short_title() or None)
                data["extractor_used"] = "readability"
                return data
    except Exception:
        pass

    # STEP 5 — boilerpy3
    try:
        from boilerpy3 import extractors
        if not html:
            r = get_with_backoff(final_url)
            if r and r.ok:
                r.encoding = r.apparent_encoding or r.encoding
                html = r.text
                data["final_url"] = r.url or final_url
        if html:
            extractor = extractors.ArticleExtractor()
            text = extractor.get_content(html)
            text = re.sub(r"\s+", " ", text or "").strip()
            if len(text) > 100:
                data["text"] = text
                data["extractor_used"] = "boilerpy3"
                return data
    except Exception:
        pass

    # STEP 6 — jusText
    try:
        import justext
        if not html:
            r = get_with_backoff(final_url)
            if r and r.ok:
                r.encoding = r.apparent_encoding or r.encoding
                html = r.text
                data["final_url"] = r.url or final_url
        if html:
            # encoding guard
            enc = "utf-8"
            try:
                enc = r.encoding or "utf-8"  # type: ignore[name-defined]
            except Exception:
                pass
            paragraphs = justext.justext(
                html.encode(enc, errors="ignore"),
                justext.get_stoplist("Indonesian")
            )
            text = " ".join(p.text for p in paragraphs if not p.is_boilerplate)
            text = re.sub(r"\s+", " ", text or "").strip()
            if len(text) > 100:
                data["text"] = text
                data["extractor_used"] = "jusText"
                return data
    except Exception:
        pass

    # Jika semua gagal
    if not data.get("text"):
        data["error"] = data.get("error") or "no_content_extracted"
    return data


@st.cache_data(show_spinner=False)
def fetch_articles(urls: List[str], user_agent: Optional[str] = None, max_workers: int = 8) -> List[Dict]:
    """Parallel fetch dengan sedikit delay agar tidak agresif."""
    def fetch_with_delay(u: str) -> Dict:
        time.sleep(random.uniform(0.35, 1.1))  # sopan
        return fetch_article(u, user_agent)

    out: List[Dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(fetch_with_delay, u) for u in urls]
        for fut in as_completed(futures):
            try:
                out.append(fut.result())
            except Exception as e:
                out.append({
                    "url": u,  # type: ignore[name-defined]
                    "final_url": None,
                    "title_article": None,
                    "text": None,
                    "publish_date": None,
                    "meta_desc": None,
                    "extractor_used": None,
                    "error": f"executor: {e}",
                })
    return out
