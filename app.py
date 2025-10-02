import os
import re
import time
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict

import pandas as pd
import numpy as np
import requests
import streamlit as st
from gnews import GNews

# ======== Streamlit Page Config ========
st.set_page_config(page_title="Sentimen Berita", page_icon="📰", layout="wide")

st.title("📰 Analisis Sentimen Berita")
st.caption("Masukkan kata kunci → ambil berita dari Google News → ekstrak isi → klasifikasi sentimen")

# ======== Helpers & Caches ========

@st.cache_resource(show_spinner=False)
def load_models():
    """
    Primary: Indonesian RoBERTa sentiment classifier (3-class).
    Fallback: Multilingual star-rating (1–5) mapped ke {negatif, netral, positif}.
    """
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline

    model_infos = [
        # 3-label Indonesian model (umumnya output: negative/neutral/positive or LABEL_0..)
        ("w11wo/indonesian-roberta-base-sentiment-classifier", "indonesian-3c"),
        # 1–5 stars multilingual fallback
        ("nlptown/bert-base-multilingual-uncased-sentiment", "multilingual-stars"),
    ]

    errors = []
    for model_name, tag in model_infos:
        try:
            tok = AutoTokenizer.from_pretrained(model_name)
            mdl = AutoModelForSequenceClassification.from_pretrained(model_name)
            clf = pipeline("sentiment-analysis", model=mdl, tokenizer=tok, truncation=True)
            return {"pipeline": clf, "tag": tag, "model_name": model_name}
        except Exception as e:
            errors.append((model_name, str(e)))

    raise RuntimeError(f"Gagal memuat model. Detail: {errors}")


@st.cache_data(show_spinner=False)
def search_news(keyword: str, language: str, country: str, period: str, max_results: int):
    """
    Cari berita dari Google News (gnews). Hasil: list dict dengan URL, judul, sumber, tanggal.
    """
    gn = GNews(language=language, country=country, period=period, max_results=max_results)
    results = gn.get_news(keyword)
    # Normalisasi struktur
    cleaned = []
    for r in results:
        cleaned.append({
            "title": r.get("title"),
            "desc": r.get("description"),
            "published": r.get("published date") or r.get("published_date") or "",
            "source": (r.get("publisher") or {}).get("title") if isinstance(r.get("publisher"), dict) else r.get("publisher"),
            "url": r.get("url"),
        })
    return cleaned


def _download_parse_article(url: str, cfg: Config, timeout: int = 20) -> Dict:
    """
    Download + parse isi artikel dari URL menggunakan newspaper3k.
    """
    data = {
        "url": url, "title_article": None, "top_image": None, "text": None,
        "authors": None, "publish_date": None, "meta_desc": None
    }
    try:
        art = Article(url, language="id", config=cfg)
        art.download()
        art.parse()
        data["title_article"] = art.title
        data["top_image"] = getattr(art, "top_image", None)
        data["text"] = art.text
        data["authors"] = ", ".join(art.authors) if art.authors else None
        # publish_date could be datetime or None
        if isinstance(art.publish_date, datetime):
            data["publish_date"] = art.publish_date.isoformat()
        data["meta_desc"] = getattr(art, "meta_description", None)
        return data
    except Exception:
        return data


@st.cache_data(show_spinner=False)
import trafilatura

def fetch_articles(urls, max_workers: int = 12):
    """
    Ambil isi artikel untuk banyak URL memakai trafilatura (tanpa newspaper3k).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    out = []
    cfg = trafilatura.settings.use_config()
    cfg.set("DEFAULT", "EXTRACTION_TIMEOUT", "20")
    cfg.set("DEFAULT", "EXTRACTION_TECHNIQUE", "fast")  # cepat & cukup akurat

    def _one(u):
        data = {"url": u, "title_article": None, "top_image": None, "text": None,
                "authors": None, "publish_date": None, "meta_desc": None}
        try:
            downloaded = trafilatura.fetch_url(u, no_ssl=True)
            if not downloaded:
                return data
            result = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                with_metadata=True,
                config=cfg,
            )
            if not result:
                return data
            meta = trafilatura.metadata.extract_metadata(downloaded)
            data["text"] = result
            if meta:
                data["title_article"] = meta.title
                data["authors"] = ", ".join(meta.author) if meta.author else None
                data["publish_date"] = meta.date
                data["meta_desc"] = meta.description
            return data
        except Exception:
            return data

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_one, u): u for u in urls}
        for fut in as_completed(futures):
            out.append(fut.result())
    return out


def _map_logits_to_label(pred, tag: str):
    """
    Konsistensikan label ke {negatif, netral, positif}.
    """
    label = pred["label"]
    score = float(pred.get("score", 0.0))

    if tag == "indonesian-3c":
        # Umum: model sudah keluarkan 'positive','negative','neutral' atau 'LABEL_0..'
        lab = label.lower()
        if "pos" in lab or lab.endswith("2"):
            return "positif", score
        if "neu" in lab or lab.endswith("1"):
            return "netral", score
        # default ke negatif
        return "negatif", score

    # multilingual-stars: labels like '1 star', '2 stars', ..., '5 stars'
    m = re.search(r"(\d)", label)
    stars = int(m.group(1)) if m else 3
    if stars <= 2:
        return "negatif", score
    if stars == 3:
        return "netral", score
    return "positif", score


def batch_sentiment(texts: List[str], clf_bundle: Dict, batch_size: int = 16):
    """
    Analisis sentimen untuk list teks dalam batch.
    """
    pipe = clf_bundle["pipeline"]
    tag = clf_bundle["tag"]
    preds_lbl, preds_score = [], []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i+batch_size]
        results = pipe(chunk, truncation=True)
        for r in results:
            lab, sc = _map_logits_to_label(r, tag)
            preds_lbl.append(lab)
            preds_score.append(sc)
    return preds_lbl, preds_score


def clean_text(x: str) -> str:
    if not x:
        return ""
    x = re.sub(r"\s+", " ", x).strip()
    return x


# ======== Sidebar Inputs ========
with st.sidebar:
    st.header("⚙️ Pengaturan")
    keyword = st.text_input("Kata kunci pencarian", value="inflasi Indonesia")
    period = st.selectbox(
        "Rentang waktu (Google News)",
        options=["1d", "7d", "14d", "30d", "3m", "6m", "12m"],
        index=1,
        help="Format gnews period. Contoh: 1d, 7d, 30d, 3m"
    )
    max_results = st.slider("Jumlah berita (maks)", min_value=10, max_value=200, value=40, step=10)
    language = st.selectbox("Bahasa", options=["id", "en"], index=0)
    country = st.selectbox("Negara sumber", options=["ID", "US", "SG", "MY", "AU"], index=0)
    ua = st.text_input("Custom User-Agent (opsional)", value="")
    run_btn = st.button("🚀 Crawl & Analisis", use_container_width=True)

st.markdown("---")

# ======== Main Flow ========

if run_btn:
    if not keyword.strip():
        st.warning("Mohon isi kata kunci terlebih dahulu.")
        st.stop()

    # 1) Cari URL berita
    with st.status("🔎 Mencari berita dari Google News...", expanded=False) as status:
        news_rows = search_news(keyword.strip(), language, country, period, max_results)
        status.update(label=f"Ditemukan {len(news_rows)} kandidat artikel.", state="complete")

    if len(news_rows) == 0:
        st.info("Tidak ada hasil. Coba ganti kata kunci / rentang waktu.")
        st.stop()

    df_seed = pd.DataFrame(news_rows)
    df_seed["published"] = df_seed["published"].astype(str)
    st.subheader("Hasil Pencarian (Kandidat)")
    st.dataframe(df_seed, use_container_width=True, hide_index=True)

    # 2) Ambil isi artikel
    urls = [r["url"] for r in news_rows if r.get("url")]
    with st.status("🧩 Mengunduh & mengekstrak isi artikel...", expanded=False) as status:
        articles = fetch_articles(urls, ua or None, max_workers=12)
        status.update(label="Ekstraksi selesai.", state="complete")

    df_art = pd.DataFrame(articles)
    # Gabungkan metadata awal
    df = df_seed.merge(df_art, on="url", how="left")

    # Bersihkan dan filter
    df["text"] = df["text"].map(clean_text)
    df = df[df["text"].str.len() > 120].copy()  # buang artikel terlalu pendek
    df["title_final"] = df["title_article"].fillna(df["title"])
    df["source"] = df["source"].fillna("unknown")
    df["publish_date"] = df["publish_date"].fillna(df["published"])

    if df.empty:
        st.warning("Tidak ada artikel yang berhasil diekstrak kontennya. Cobalah dengan kata kunci lain/rentang waktu lain.")
        st.stop()

    # 3) Load model sentimen
    with st.status("🧠 Memuat model sentimen...", expanded=False) as status:
        try:
            model_bundle = load_models()
            status.update(label=f"Model siap: {model_bundle['model_name']}", state="complete")
        except Exception as e:
            st.error(f"Gagal memuat model: {e}")
            st.stop()

    # 4) Inferensi sentimen (batch)
    with st.status("📊 Menganalisis sentimen artikel...", expanded=False) as status:
        labels, scores = batch_sentiment(df["text"].tolist(), model_bundle, batch_size=16)
        status.update(label="Klasifikasi selesai.", state="complete")

    df["sentiment"] = labels
    df["confidence"] = scores

    # 5) Ringkasan & Visual
    st.subheader("Ringkasan Sentimen")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total artikel", len(df))
    with col2:
        st.metric("Positif", int((df["sentiment"] == "positif").sum()))
    with col3:
        st.metric("Negatif", int((df["sentiment"] == "negatif").sum()))

    st.bar_chart(df["sentiment"].value_counts(), use_container_width=True)

    # 6) Tabel Hasil (utama)
    show_cols = ["title_final", "source", "publish_date", "sentiment", "confidence", "url", "text"]
    st.subheader("Detail Hasil")
    st.dataframe(df[show_cols].rename(columns={
        "title_final": "title",
        "publish_date": "published"
    }), use_container_width=True, hide_index=True)

    # 7) Unduh CSV
    csv_bytes = df[show_cols].rename(columns={"title_final": "title", "publish_date": "published"}).to_csv(index=False).encode("utf-8")
    st.download_button("💾 Unduh CSV", data=csv_bytes, file_name=f"sentimen_berita_{re.sub(r'\\W+','_',keyword)}.csv", mime="text/csv")

    # 8) Catatan legal/teknis
    with st.expander("ℹ️ Catatan & Praktik Baik"):
        st.markdown("""
- Sumber artikel berasal dari tautan Google News. Mohon pahami **Terms of Service** tiap situs saat mengambil konten.
- Beberapa situs mungkin memblokir crawling otomatis; gunakan **User-Agent** kustom bila perlu.
- Model default: `w11wo/indonesian-roberta-base-sentiment-classifier` (fallback ke `nlptown/bert-base-multilingual-uncased-sentiment`).
- Hasil sentimen bersifat **prediksi**; pertimbangkan validasi manual untuk kasus sensitif.
        """)

else:
    st.info("Masukkan kata kunci di sisi kiri lalu klik **Crawl & Analisis** untuk mulai.")
