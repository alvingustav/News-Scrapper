import os
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import pandas as pd
import streamlit as st
import requests
import trafilatura
import feedparser
from dateutil import parser as dtparser

# ============ Streamlit Config ============
st.set_page_config(page_title="Sentimen Berita", page_icon="📰", layout="wide")
st.title("📰 Analisis Sentimen Berita")
st.caption("Masukkan kata kunci → ambil berita → ekstrak isi → klasifikasi sentimen")

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# ============ Sentiment Model (with fallback) ============
@st.cache_resource(show_spinner=False)
def load_models():
    """
    Try Indonesian 3-class first, then fallback to multilingual 1–5 stars.
    """
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline

    tried = []
    for model_name, tag in [
        ("w11wo/indonesian-roberta-base-sentiment-classifier", "id-3c"),
        ("nlptown/bert-base-multilingual-uncased-sentiment", "mstars"),
    ]:
        try:
            tok = AutoTokenizer.from_pretrained(model_name)
            mdl = AutoModelForSequenceClassification.from_pretrained(model_name)
            clf = pipeline("sentiment-analysis", model=mdl, tokenizer=tok, truncation=True)
            return {"pipe": clf, "tag": tag, "model_name": model_name}
        except Exception as e:
            tried.append((model_name, str(e)))
            continue
    raise RuntimeError(f"Gagal memuat model. Tried: {tried}")

def _map_label(pred: Dict, tag: str):
    lab = pred["label"].lower()
    sc = float(pred.get("score", 0.0))
    if tag == "id-3c":
        if "pos" in lab or lab.endswith("2"):
            return "positif", sc
        if "neu" in lab or lab.endswith("1"):
            return "netral", sc
        return "negatif", sc
    # mstars -> '1 star'..'5 stars'
    m = re.search(r"(\d)", lab)
    stars = int(m.group(1)) if m else 3
    if stars <= 2:
        return "negatif", sc
    if stars == 3:
        return "netral", sc
    return "positif", sc

def batch_sentiment(texts: List[str], clf_bundle: Dict, batch_size: int = 16):
    pipe = clf_bundle["pipe"]
    tag = clf_bundle["tag"]
    labels, scores = [], []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i+batch_size]
        results = pipe(chunk, truncation=True)
        for r in results:
            l, s = _map_label(r, tag)
            labels.append(l); scores.append(s)
    return labels, scores

# ============ Search Backends ============
def normalize_rows(rows: List[Dict], max_results: int) -> List[Dict]:
    """Ensure std keys: title, url, source, published, desc"""
    out = []
    for r in rows[:max_results]:
        out.append({
            "title": r.get("title"),
            "url": r.get("url"),
            "source": r.get("source"),
            "published": r.get("published"),
            "desc": r.get("desc"),
        })
    # drop rows without url
    out = [x for x in out if x.get("url")]
    # de-duplicate by url
    uniq = {}
    for x in out:
        uniq.setdefault(x["url"], x)
    return list(uniq.values())

def search_google_news_rss(keyword: str, language: str = "id", country: str = "ID",
                           max_results: int = 50) -> List[Dict]:
    q = urllib.parse.quote(keyword)
    rss_url = f"https://news.google.com/rss/search?q={q}&hl={language}&gl={country}&ceid={country}:{language}"
    feed = feedparser.parse(rss_url)
    rows = []
    for e in feed.entries:
        rows.append({
            "title": e.get("title"),
            "url": e.get("link"),
            "source": getattr(e, "source", {}).get("title") if hasattr(e, "source") else None,
            "published": e.get("published") or e.get("updated"),
            "desc": e.get("summary"),
        })
    return normalize_rows(rows, max_results)

def search_gdelt_doc(keyword: str, timespan: str = "7d", max_results: int = 50) -> List[Dict]:
    """
    GDELT DOC 2.0 (no key). timespan: '1d','7d','30d','90d'.
    """
    query = {
        "query": keyword,
        "mode": "artlist",
        "maxrecords": str(max_results),
        "format": "json",
        "timespan": timespan
    }
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    try:
        r = requests.get(url, params=query, timeout=20)
        r.raise_for_status()
        data = r.json()
        rows = []
        for art in data.get("articles", []):
            rows.append({
                "title": art.get("title"),
                "url": art.get("url"),
                "source": art.get("sourceCountry") or art.get("domain"),
                "published": art.get("seendate"),
                "desc": art.get("sourceCommonName"),
            })
        return normalize_rows(rows, max_results)
    except Exception:
        return []

def search_gnews_lib(keyword: str, language: str = "id", country: str = "ID",
                     period: str = "7d", max_results: int = 50) -> List[Dict]:
    try:
        from gnews import GNews
    except Exception:
        return []
    gn = GNews(language=language, country=country, period=period, max_results=max_results)
    res = gn.get_news(keyword) or []
    rows = []
    for r in res:
        rows.append({
            "title": r.get("title"),
            "url": r.get("url"),
            "source": (r.get("publisher") or {}).get("title") if isinstance(r.get("publisher"), dict) else r.get("publisher"),
            "published": r.get("published date") or r.get("published_date"),
            "desc": r.get("description"),
        })
    return normalize_rows(rows, max_results)

def search_newsapi(keyword: str, language: str = "id", page_size: int = 50) -> List[Dict]:
    """
    Needs NEWSAPI_KEY env var. language: 'id' or 'en'.
    """
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        return []
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": keyword,
        "language": language,
        "sortBy": "publishedAt",
        "pageSize": min(page_size, 100),
        "apiKey": api_key
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        rows = []
        for a in data.get("articles", []):
            rows.append({
                "title": a.get("title"),
                "url": a.get("url"),
                "source": (a.get("source") or {}).get("name"),
                "published": a.get("publishedAt"),
                "desc": a.get("description"),
            })
        return normalize_rows(rows, page_size)
    except Exception:
        return []

def search_news(backend: str, keyword: str, language: str, country: str,
                period: str, timespan: str, max_results: int) -> List[Dict]:
    if backend == "Google News RSS (no key)":
        return search_google_news_rss(keyword, language, country, max_results)
    if backend == "GDELT 2.0 (no key)":
        return search_gdelt_doc(keyword, timespan=timespan, max_results=max_results)
    if backend == "GNews (library, no key)":
        return search_gnews_lib(keyword, language, country, period, max_results)
    if backend == "NewsAPI (needs NEWSAPI_KEY)":
        return search_newsapi(keyword, language, max_results)
    return []

# ============ Extraction via Trafilatura ============
def fetch_article(url: str, user_agent: Optional[str] = None) -> Dict:
    data = {"url": url, "title_article": None, "text": None, "publish_date": None, "meta_desc": None}
    try:
        downloaded = trafilatura.fetch_url(
            url,
            no_ssl=True,
            user_agent=user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
        if not downloaded:
            return data

        extracted = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            with_metadata=True
        )
        if extracted:
            data["text"] = extracted

        meta = trafilatura.metadata.extract_metadata(downloaded)
        if meta:
            data["title_article"] = meta.title or None
            data["publish_date"] = meta.date or None
            data["meta_desc"] = meta.description or None

        if not data["title_article"]:
            bex = trafilatura.bare_extraction(downloaded, with_metadata=True)
            if bex and "title" in bex:
                data["title_article"] = bex["title"]
    except Exception:
        pass
    return data

@st.cache_data(show_spinner=False)
def fetch_articles(urls: List[str], user_agent: Optional[str] = None, max_workers: int = 12):
    out = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetch_article, u, user_agent): u for u in urls}
        for fut in as_completed(futures):
            out.append(fut.result())
    return out

# ============ Sidebar ============
with st.sidebar:
    st.header("⚙️ Pengaturan")
    backend = st.selectbox(
        "Sumber pencarian",
        ["Google News RSS (no key)", "GDELT 2.0 (no key)", "GNews (library, no key)", "NewsAPI (needs NEWSAPI_KEY)"],
        index=0
    )
    keyword = st.text_input("Kata kunci", "inflasi Indonesia")
    language = st.selectbox("Bahasa", ["id", "en"], index=0)
    country = st.selectbox("Negara", ["ID", "US", "SG", "MY", "AU"], index=0)
    max_results = st.slider("Jumlah berita (maks)", 10, 200, 40, 10)
    period = st.selectbox("Period (GNews lib)", ["1d", "7d", "14d", "30d", "3m", "6m", "12m"], index=1)
    timespan = st.selectbox("Timespan (GDELT)", ["1d", "7d", "30d", "90d"], index=1)
    days_filter = st.slider("Filter umur berita (hari, post-filter)", 0, 90, 0,
                            help="0 = tanpa filter tanggal; berlaku ke semua backend")
    user_agent = st.text_input("Custom User-Agent (opsional)", value="")
    run_btn = st.button("🚀 Cari & Analisis", use_container_width=True)

st.markdown("---")

# ============ Main ============
if run_btn:
    if not keyword.strip():
        st.warning("Mohon isi kata kunci.")
        st.stop()

    # 1) Search
    with st.status("🔎 Mencari berita...", expanded=False) as status:
        rows = search_news(backend, keyword.strip(), language, country, period, timespan, max_results)
        status.update(label=f"Ditemukan {len(rows)} kandidat URL.", state="complete")

    if not rows:
        st.warning("Tidak ada URL ditemukan dari backend yang dipilih. Coba backend lain / tambah jumlah / ganti kata kunci.")
        st.stop()

    df_seed = pd.DataFrame(rows)
    # Post-filter tanggal jika diminta
    if days_filter > 0:
        cutoff = datetime.utcnow() - timedelta(days=days_filter)
        def _ok_date(x):
            try:
                dt = dtparser.parse(x) if isinstance(x, str) else None
                if not dt:
                    return True  # kalau tak ada tanggal, biarkan
                # normalisasi ke UTC naive
                if dt.tzinfo:
                    dt = dt.astimezone(tz=None).replace(tzinfo=None)
                return dt >= cutoff
            except Exception:
                return True
        df_seed = df_seed[df_seed["published"].apply(_ok_date)]
    st.subheader("Kandidat URL")
    st.dataframe(df_seed, use_container_width=True, hide_index=True)

    # 2) Extract articles
    urls = df_seed["url"].dropna().tolist()
    with st.status("📥 Mengunduh & mengekstrak isi artikel...", expanded=False) as status:
        arts = fetch_articles(urls, user_agent or None, max_workers=12)
        status.update(label="Ekstraksi selesai.", state="complete")

    STD_COLS = ["url", "title_article", "text", "publish_date", "meta_desc"]
    df_art = pd.DataFrame(arts)
    for c in STD_COLS:
        if c not in df_art.columns:
            df_art[c] = None

    df = df_seed.merge(df_art, on="url", how="left")
    # --- setelah merge df_seed & df_art ---
    df["title_final"] = df["title_article"].fillna(df["title"])
    df["publish_final"] = df["publish_date"].fillna(df["published"])
    
    # Pastikan kolom 'text' selalu ada & berupa string
    if "text" not in df.columns:
        df["text"] = ""
    else:
        df["text"] = df["text"].fillna("").astype(str)
    
    # (opsional) bersihkan whitespace berlebih
    df["text"] = df["text"].str.replace(r"\s+", " ", regex=True).str.strip()
    
    # Hitung artikel yang berhasil diekstrak (panjang > 120)
    success_cnt = int((df["text"].str.len() > 120).sum())
    if success_cnt == 0:
        st.warning("Semua ekstraksi gagal/terlalu pendek. Coba backend lain, tambah jumlah, atau ganti user-agent.")
        with st.expander("Lihat URL kandidat (debug)"):
            st.write(df[["title_final", "url"]])
        st.stop()
    
    # Hanya pertahankan artikel yang punya teks cukup panjang
    df = df[df["text"].str.len() > 120].copy()

    # 3) Sentiment
    with st.status("🧠 Memuat model & menganalisis sentimen...", expanded=False) as status:
        try:
            bundle = load_models()
        except Exception as e:
            st.error(f"Gagal memuat model: {e}")
            st.stop()
        labels, scores = batch_sentiment(df["text"].tolist(), bundle, batch_size=16)
        status.update(label=f"Klasifikasi selesai (model: {bundle['model_name']}).", state="complete")

    df["sentiment"] = labels
    df["confidence"] = scores

    # 4) Summary + Charts
    st.subheader("Ringkasan Sentimen")
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Total artikel", len(df))
    with col2: st.metric("Positif", int((df["sentiment"] == "positif").sum()))
    with col3: st.metric("Negatif", int((df["sentiment"] == "negatif").sum()))
    st.bar_chart(df["sentiment"].value_counts(), use_container_width=True)

    # 5) Tabel Hasil
    show_cols = ["title_final", "source", "publish_final", "sentiment", "confidence", "url", "desc"]
    st.subheader("Detail Hasil")
    st.dataframe(df[show_cols].rename(columns={
        "title_final": "title",
        "publish_final": "published"
    }), use_container_width=True, hide_index=True)

    # 6) CSV
    csv_bytes = (
        df[show_cols]
        .rename(columns={"title_final": "title", "publish_final": "published"})
        .to_csv(index=False).encode("utf-8")
    )
    safe_kw = re.sub(r"\W+", "_", keyword.strip())
    st.download_button("💾 Unduh CSV", data=csv_bytes, file_name=f"sentimen_berita_{safe_kw}.csv", mime="text/csv")

    # 7) Notes
    with st.expander("ℹ️ Catatan & Praktik"):
        st.markdown("""
- Backends: **Google News RSS**, **GDELT DOC 2.0**, **GNews library**, **NewsAPI** (butuh `NEWSAPI_KEY`).
- Ekstraksi: **trafilatura** (lebih stabil daripada newspaper3k).
- Beberapa domain anti-bot/paywalled → wajar jika gagal diekstrak.
- Hasil sentimen bersifat prediksi; untuk kasus kritikal, lakukan verifikasi manual.
        """)

else:
    st.info("Isi kata kunci di sidebar, pilih backend, lalu klik **Cari & Analisis**.")
