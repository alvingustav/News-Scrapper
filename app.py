import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict

import pandas as pd
import streamlit as st
from gnews import GNews
import trafilatura

# ======== Streamlit Page Config ========
st.set_page_config(page_title="Sentimen Berita", page_icon="📰", layout="wide")

st.title("📰 Analisis Sentimen Berita")
st.caption("Masukkan kata kunci → ambil berita dari Google News → ekstrak isi → klasifikasi sentimen")

# ======== Model ========
@st.cache_resource
def load_model():
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
    model_name = "w11wo/indonesian-roberta-base-sentiment-classifier"
    tok = AutoTokenizer.from_pretrained(model_name)
    mdl = AutoModelForSequenceClassification.from_pretrained(model_name)
    clf = pipeline("sentiment-analysis", model=mdl, tokenizer=tok, truncation=True)
    return clf

# ======== Scraper ========
@st.cache_data
def search_news(keyword: str, language: str, country: str, period: str, max_results: int):
    gn = GNews(language=language, country=country, period=period, max_results=max_results)
    results = gn.get_news(keyword)
    return results

def fetch_article(url: str) -> Dict:
    data = {"url": url, "title": None, "text": None, "publish_date": None}
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            extracted = trafilatura.extract(downloaded, include_comments=False, include_tables=False, with_metadata=True)
            if extracted:
                meta = trafilatura.metadata.extract_metadata(downloaded)
                data["text"] = extracted
                if meta:
                    data["title"] = meta.title
                    data["publish_date"] = meta.date
    except Exception:
        pass
    return data

def fetch_articles(urls: List[str], max_workers: int = 8):
    out = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetch_article, u): u for u in urls}
        for fut in as_completed(futures):
            out.append(fut.result())
    return out

# ======== Sentiment ========
def map_label(pred):
    lab = pred["label"].lower()
    if "pos" in lab:
        return "positif"
    if "neu" in lab:
        return "netral"
    return "negatif"

def batch_sentiment(texts: List[str], clf, batch_size: int = 16):
    labels, scores = [], []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i+batch_size]
        results = clf(chunk, truncation=True)
        for r in results:
            labels.append(map_label(r))
            scores.append(r["score"])
    return labels, scores

# ======== Sidebar Input ========
with st.sidebar:
    keyword = st.text_input("Kata kunci", "inflasi Indonesia")
    period = st.selectbox("Rentang waktu", ["1d", "7d", "14d", "30d"], index=1)
    max_results = st.slider("Jumlah berita", 10, 100, 20, step=10)
    language = st.selectbox("Bahasa", ["id", "en"], index=0)
    country = st.selectbox("Negara", ["ID", "US", "SG"], index=0)
    run_btn = st.button("🚀 Jalankan")

# ======== Main Flow ========
if run_btn:
    with st.spinner("🔎 Mencari berita..."):
        news = search_news(keyword, language, country, period, max_results)

    urls = [n["url"] for n in news if n.get("url")]
    with st.spinner("📥 Mengunduh artikel..."):
        articles = fetch_articles(urls)

    df = pd.DataFrame(articles)
    df = df[df["text"].notna()]
    if df.empty:
        st.warning("Tidak ada artikel yang berhasil diambil.")
        st.stop()

    with st.spinner("🧠 Analisis sentimen..."):
        clf = load_model()
        labels, scores = batch_sentiment(df["text"].tolist(), clf)
        df["sentiment"] = labels
        df["confidence"] = scores

    st.subheader("Ringkasan Sentimen")
    st.bar_chart(df["sentiment"].value_counts())

    st.subheader("Detail")
    st.dataframe(df[["title", "publish_date", "sentiment", "confidence", "url"]])

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("💾 Unduh CSV", data=csv, file_name="sentimen.csv", mime="text/csv")
