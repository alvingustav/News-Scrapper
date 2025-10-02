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

# ===================== Streamlit Config =====================
st.set_page_config(page_title="Sentimen Berita Lokal 🇮🇩", page_icon="📰", layout="wide")
st.title("📰 Analisis Sentimen Berita Lokal Indonesia")
st.caption("Ketik kata kunci → ambil dari RSS media Indonesia → ekstrak isi → klasifikasi sentimen")

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# ===================== Kumpulan RSS Media Lokal =====================
# (kategori berita umum/nasional/ekonomi/tekno bila tersedia)
INDONESIA_FEEDS: Dict[str, List[str]] = {
    "Kompas": [
        "https://rss.kompas.com/news",
        "https://rss.kompas.com/kompascom/ekonomi",
        "https://rss.kompas.com/kompascom/tekno",
        "https://rss.kompas.com/kompascom/megapolitan",
        "https://rss.kompas.com/nasional"
    ],
    "Detik": [
        "https://rss.detik.com/index.php/detiknews",
        "https://rss.detik.com/index.php/finance",
        "https://rss.detik.com/index.php/detikinet"
    ],
    "Tempo": [
        "https://rss.tempo.co/nasional",
        "https://rss.tempo.co/bisnis",
        "https://rss.tempo.co/teknologi"
    ],
    "Liputan6": [
        "https://feed.liputan6.com/rss",
        "https://feed.liputan6.com/rss/tekno",
        "https://feed.liputan6.com/rss/bisnis"
    ],
    "Tribunnews": [
        "https://www.tribunnews.com/rss",
        "https://www.tribunnews.com/bisnis/rss",
        "https://www.tribunnews.com/techno/rss"
    ],
    "ANTARA": [
        "https://www.antaranews.com/rss/top-news",
        "https://www.antaranews.com/rss/ekonomi",
        "https://www.antaranews.com/rss/tekno"
    ],
    "CNN Indonesia": [
        "https://www.cnnindonesia.com/nasional/rss",
        "https://www.cnnindonesia.com/ekonomi/rss",
        "https://www.cnnindonesia.com/teknologi/rss"
    ],
    "CNBC Indonesia": [
        "https://www.cnbcindonesia.com/news/rss",
        "https://www.cnbcindonesia.com/market/rss",
        "https://www.cnbcindonesia.com/tech/rss"
    ],
    "Merdeka": [
        "https://www.merdeka.com/feed/",
        "https://www.merdeka.com/uang/feed/",
        "https://www.merdeka.com/teknologi/feed/"
    ],
    "Republika": [
        "https://www.republika.co.id/rss",
        "https://www.republika.co.id/rss/nasional",
        "https://www.republika.co.id/rss/ekonomi"
    ],
    "BeritaSatu": [
        "https://www.beritasatu.com/rss/nasional",
        "https://www.beritasatu.com/rss/ekonomi",
        "https://www.beritasatu.com/rss/teknologi"
    ],
    "Kumparan": [
        "https://lapi.kumparan.com/v2.0/rss/",
    ],
    "Viva": [
        "https://www.viva.co.id/rss/berita",
        "https://www.viva.co.id/rss/teknologi",
        "https://www.viva.co.id/rss/bisnis"
    ],
    "Okezone": [
        "https://sindikasi.okezone.com/index.php/okezone/RSS2.0",
        "https://economy.okezone.com/rss",
        "https://techno.okezone.com/rss"
    ],
    "IDN Times": [
        "https://www.idntimes.com/rss",
        "https://www.idntimes.com/business/rss",
        "https://www.idntimes.com/tech/rss"
    ],
}

ALL_FEEDS = [(src, url) for src, urls in INDONESIA_FEEDS.items() for url in urls]

# ===================== Sentiment Model (with fallback) =====================
@st.cache_resource(show_spinner=False)
def load_models():
    """
    Pertama coba Indonesian 3-class, kalau gagal fallback ke multilingual 1–5 stars.
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
    pipe = clf_bundle["pipe"]; tag = clf_bundle["tag"]
    labels, scores = [], []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i+batch_size]
        results = pipe(chunk, truncation=True)
        for r in results:
            l, s = _map_label(r, tag)
            labels.append(l); scores.append(s)
    return labels, scores

# ===================== Pencarian RSS: Media Lokal =====================
def parse_entry_date(entry) -> Optional[datetime]:
    candidates = [
        getattr(entry, "published", None),
        getattr(entry, "updated", None),
        entry.get("published") if isinstance(entry, dict) else None,
        entry.get("updated") if isinstance(entry, dict) else None,
    ]
    for c in candidates:
        if not c:
            continue
        try:
            dt = dtparser.parse(c)
            # normalisasi ke naive
            if dt.tzinfo:
                dt = dt.astimezone(tz=None).replace(tzinfo=None)
            return dt
        except Exception:
            continue
    return None

def matches_keyword(entry, keyword: str) -> bool:
    kw = keyword.strip().lower()
    if not kw:
        return True
    title = (getattr(entry, "title", "") or "").lower()
    summary = (getattr(entry, "summary", "") or "").lower()
    return (kw in title) or (kw in summary)

@st.cache_data(show_spinner=False)
def search_indonesia_rss(keyword: str, max_results: int, days_filter: int) -> List[Dict]:
    """
    Agregasi semua RSS lokal → filter by keyword & umur berita → dedup & limit.
    """
    out = []
    cutoff = None
    if days_filter > 0:
        cutoff = datetime.utcnow() - timedelta(days=days_filter)

    for source, url in ALL_FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries:
                if not matches_keyword(e, keyword):
                    continue
                link = getattr(e, "link", None) or ""
                if not link:
                    continue
                dt = parse_entry_date(e)
                if cutoff and dt and dt < cutoff:
                    continue
                out.append({
                    "title": getattr(e, "title", None),
                    "url": link,
                    "source": source,
                    "published": dt.isoformat() if dt else getattr(e, "published", None),
                    "desc": getattr(e, "summary", None),
                })
        except Exception:
            continue

    # De-duplicate by url
    uniq = {}
    for r in out:
        uniq.setdefault(r["url"], r)
    rows = list(uniq.values())
    # Sort by published desc (if available), else keep order
    def _key(r):
        try:
            return dtparser.parse(r["published"])
        except Exception:
            return datetime.min
    rows.sort(key=_key, reverse=True)
    return rows[:max_results]

# ===================== Ekstraksi Artikel: Trafilatura + Fallback =====================
def fetch_article(url: str, user_agent: Optional[str] = None) -> Dict:
    """
    Strategi:
    1) trafilatura.fetch_url + extract
    2) requests.get + trafilatura.extract(html=...)
    3) readability-lxml
    4) boilerpy3
    5) jusText
    """
    data = {"url": url, "title_article": None, "text": None, "publish_date": None, "meta_desc": None}

    UA = user_agent or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache", "Pragma": "no-cache", "Connection": "keep-alive",
    }

    def _fill_meta_from_traf(downloaded: str):
        try:
            meta = trafilatura.metadata.extract_metadata(downloaded)
            if meta:
                data["title_article"] = data["title_article"] or meta.title
                data["publish_date"] = data["publish_date"] or meta.date
                data["meta_desc"] = data["meta_desc"] or meta.description
        except Exception:
            pass

    # 1) trafilatura.fetch_url
    try:
        downloaded = trafilatura.fetch_url(url, no_ssl=True, user_agent=UA)
        if downloaded:
            extracted = trafilatura.extract(
                downloaded, include_comments=False, include_tables=False, with_metadata=True
            )
            if extracted and len(extracted) > 60:
                data["text"] = extracted
                _fill_meta_from_traf(downloaded)
                if not data["title_article"]:
                    bex = trafilatura.bare_extraction(downloaded, with_metadata=True)
                    if bex and "title" in bex:
                        data["title_article"] = bex["title"]
                return data
    except Exception:
        pass

    # 2) requests.get + trafilatura.extract(html=...)
    html = None
    try:
        resp = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        if resp.ok and "text/html" in resp.headers.get("Content-Type", ""):
            resp.encoding = resp.apparent_encoding or resp.encoding
            html = resp.text
            extracted = trafilatura.extract(
                html, include_comments=False, include_tables=False, with_metadata=True, url=url
            )
            if extracted and len(extracted) > 60:
                data["text"] = extracted
                try:
                    meta = trafilatura.metadata.extract_metadata(html)
                    if meta:
                        data["title_article"] = data["title_article"] or meta.title
                        data["publish_date"] = data["publish_date"] or meta.date
                        data["meta_desc"] = data["meta_desc"] or meta.description
                except Exception:
                    pass
                if not data["title_article"]:
                    try:
                        bex = trafilatura.bare_extraction(html, with_metadata=True)
                        if bex and "title" in bex:
                            data["title_article"] = bex["title"]
                    except Exception:
                        pass
                return data
    except Exception:
        pass

    # 3) readability-lxml
    try:
        from readability import Document
        if html is None:
            resp = requests.get(url, headers=headers, timeout=20)
            if not resp.ok:
                raise RuntimeError("HTTP not OK")
            resp.encoding = resp.apparent_encoding or resp.encoding
            html = resp.text
        doc = Document(html)
        content_html = doc.summary()
        text = re.sub(r"<[^>]+>", " ", content_html or "")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 60:
            data["text"] = text
            data["title_article"] = data["title_article"] or (doc.short_title() or None)
            return data
    except Exception:
        pass

    # 4) boilerpy3
    try:
        from boilerpy3 import extractors
        if html is None:
            resp = requests.get(url, headers=headers, timeout=20)
            if not resp.ok:
                raise RuntimeError("HTTP not OK")
            resp.encoding = resp.apparent_encoding or resp.encoding
            html = resp.text
        extractor = extractors.ArticleExtractor()
        text = extractor.get_content(html)
        text = re.sub(r"\s+", " ", text or "").strip()
        if len(text) > 60:
            data["text"] = text
            return data
    except Exception:
        pass

    # 5) jusText
    try:
        import justext
        if html is None:
            resp = requests.get(url, headers=headers, timeout=20)
            if not resp.ok:
                raise RuntimeError("HTTP not OK")
            resp.encoding = resp.apparent_encoding or resp.encoding
            html = resp.text
        paragraphs = justext.justext(
            html.encode(resp.encoding or "utf-8", errors="ignore"),
            justext.get_stoplist("Indonesian")
        )
        text = " ".join(p.text for p in paragraphs if not p.is_boilerplate)
        text = re.sub(r"\s+", " ", text or "").strip()
        if len(text) > 60:
            data["text"] = text
            return data
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

# ===================== Sidebar =====================
with st.sidebar:
    st.header("⚙️ Pengaturan")
    keyword = st.text_input("Kata kunci", "inflasi Indonesia")
    max_results = st.slider("Jumlah berita (maks)", 10, 200, 60, 10)
    days_filter = st.slider("Filter umur berita (hari, 0=tanpa filter)", 0, 90, 14)
    user_agent = st.text_input("Custom User-Agent (opsional)", value="")
    run_btn = st.button("🚀 Cari & Analisis", use_container_width=True)

st.markdown("---")

# ===================== Main Flow =====================
if run_btn:
    if not keyword.strip():
        st.warning("Mohon isi kata kunci.")
        st.stop()

    # 1) Search lokal RSS
    with st.status("🔎 Mengumpulkan RSS media lokal...", expanded=False) as status:
        rows = search_indonesia_rss(keyword.strip(), max_results=max_results, days_filter=days_filter)
        status.update(label=f"Ditemukan {len(rows)} kandidat URL dari media lokal.", state="complete")

    if not rows:
        st.warning("Tidak ada URL dari RSS lokal yang cocok. Coba perluas kata kunci atau naikkan jumlah/longgarkan filter hari.")
        st.stop()

    df_seed = pd.DataFrame(rows)
    st.subheader("Kandidat URL (Lokal)")
    st.dataframe(df_seed, use_container_width=True, hide_index=True)

    # 2) Extract
    urls = df_seed["url"].dropna().tolist()
    with st.status("📥 Mengunduh & mengekstrak isi artikel...", expanded=False) as status:
        arts = fetch_articles(urls, user_agent or None, max_workers=12)
        status.update(label="Ekstraksi selesai.", state="complete")

    df_art = pd.DataFrame(arts)
    for c in ["url", "title_article", "text", "publish_date", "meta_desc"]:
        if c not in df_art.columns:
            df_art[c] = None

    df = df_seed.merge(df_art, on="url", how="left")
    df["title_final"] = df["title_article"].fillna(df["title"])
    df["publish_final"] = df["publish_date"].fillna(df["published"])

    # Pastikan kolom text string
    if "text" not in df.columns:
        df["text"] = ""
    else:
        df["text"] = df["text"].fillna("").astype(str)
    df["text"] = df["text"].str.replace(r"\s+", " ", regex=True).str.strip()

    # Debug panjang teks
    df["len_text"] = df["text"].str.len()
    st.caption("🔎 Debug ekstraksi (panjang teks)")
    dbg = df["len_text"].describe(percentiles=[0.25, 0.5, 0.75]).to_frame("len_text_stats")
    st.dataframe(dbg.T, use_container_width=True)

    MIN_LEN = 80
    success_cnt = int((df["len_text"] > MIN_LEN).sum())
    if success_cnt == 0:
        st.warning("Semua ekstraksi gagal/terlalu pendek. Coba tambah jumlah feed, ganti keyword, atau isi User-Agent.")
        with st.expander("Lihat URL kandidat (debug)"):
            st.write(df[["title_final", "url"]])
        st.stop()

    df = df[df["len_text"] > MIN_LEN].copy()

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

    # 4) Ringkasan
    st.subheader("Ringkasan Sentimen")
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Total artikel", len(df))
    with c2: st.metric("Positif", int((df["sentiment"] == "positif").sum()))
    with c3: st.metric("Negatif", int((df["sentiment"] == "negatif").sum()))
    st.bar_chart(df["sentiment"].value_counts(), use_container_width=True)

    # 5) Tabel hasil
    show_cols = ["title_final", "source", "publish_final", "sentiment", "confidence", "url", "desc"]
    st.subheader("Detail Hasil (Media Lokal)")
    st.dataframe(
        df[show_cols].rename(columns={"title_final": "title", "publish_final": "published"}),
        use_container_width=True, hide_index=True
    )

    # 6) CSV
    csv_bytes = (
        df[show_cols]
        .rename(columns={"title_final": "title", "publish_final": "published"})
        .to_csv(index=False).encode("utf-8")
    )
    safe_kw = re.sub(r"\W+", "_", keyword.strip())
    st.download_button("💾 Unduh CSV", data=csv_bytes, file_name=f"sentimen_berita_lokal_{safe_kw}.csv", mime="text/csv")

    with st.expander("ℹ️ Catatan"):
        st.markdown("""
- Sumber berasal dari **RSS resmi** portal berita Indonesia yang umum.
- Tidak semua feed konsisten memberi tanggal → urutan mungkin tidak sempurna.
- Sebagian domain bisa paywalled/anti-bot; sudah ada 4 fallback extraction.
- Hasil sentimen sifatnya prediksi; untuk keputusan penting, lakukan verifikasi manual.
        """)

else:
    st.info("Masukkan kata kunci, atur jumlah & filter hari, lalu klik **Cari & Analisis**.")
