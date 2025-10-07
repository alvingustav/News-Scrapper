# app.py
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from backend.feeds import ALL_FEEDS
from backend.search import search_multi_source
from backend.filters import is_west_java_hit
from backend.extract import fetch_articles
from backend.sentiment import load_models, batch_sentiment

st.set_page_config(page_title="Sentimen Berita Indonesia", page_icon="📰", layout="wide")
st.title("📰 Analisis Sentimen Berita Indonesia")
st.caption("Ketik kata kunci → ambil dari RSS media lokal → ekstrak isi → klasifikasi sentimen")

# ---------- INPUT UTAMA (BUKAN SIDEBAR) ----------
with st.form("search_form", clear_on_submit=False):
    st.subheader("🔎 Pencarian")
    col1, col2 = st.columns([2, 1])
    with col1:
        raw_kw = st.text_input("Kata kunci (pisahkan dengan koma)", "inflasi, suku bunga, BI rate")
    with col2:
        max_results = st.slider("Jumlah berita (maks)", 10, 200, 60, 10)

    col3, col4, col5 = st.columns([1.5, 1.5, 1])
    today_wib = datetime.now(ZoneInfo("Asia/Jakarta")).date()
    default_start = today_wib - timedelta(days=14)
    with col3:
        start_date = st.date_input("Tanggal mulai (WIB)", value=default_start)
    with col4:
        end_date = st.date_input("Tanggal selesai (WIB)", value=today_wib)
    with col5:
        lock_jabar = st.checkbox("🔒 Khusus Jabar", value=False)
    # app.py – di dalam st.form("search_form")
    col6, col7 = st.columns([1, 1])
    with col6:
        use_gnews = st.checkbox("➕ Tambahkan Google News", value=True,
                                help="Ambil juga hasil dari Google News RSS (disaring ke media Indonesia).")
    with col7:
        use_bm25 = st.checkbox("🎯 Rerank BM25", value=True,
                               help="Urutkan hasil paling relevan sebelum ekstraksi.")


    user_agent = st.text_input("Custom User-Agent (opsional)", value="")
    submitted = st.form_submit_button("🚀 Cari & Analisis", use_container_width=True)

if not submitted:
    st.info("Isi parameter lalu tekan **Cari & Analisis**.")
    st.stop()

# ---------- VALIDASI ----------
keywords = [k.strip() for k in re.split(r"[;,]", raw_kw) if k.strip()]
if not keywords:
    st.warning("Mohon isi kata kunci.")
    st.stop()

if end_date and start_date and end_date < start_date:
    st.warning("Tanggal selesai tidak boleh lebih awal dari tanggal mulai.")
    st.stop()

# ---------- CRAWL / SEARCH ----------
with st.status("🔎 Mengumpulkan RSS media lokal...", expanded=False) as status:
    rows = search_multi_source(
        keywords=keywords,
        max_results=max_results,
        date_start=start_date,
        date_end=end_date,
        use_google_news=use_gnews,
        use_bm25_rerank=use_bm25,
    )
    st.caption(f"Filter tanggal aktif (WIB): {start_date} s/d {end_date}")
    status.update(label=f"Ditemukan {len(rows)} kandidat URL.", state="complete")

if not rows:
    st.warning("Tidak ada URL cocok. Coba perluas kata kunci atau tanggal.")
    st.stop()

df_seed = pd.DataFrame(rows)
for c in ["title", "desc", "url"]:
    if c not in df_seed.columns: df_seed[c] = ""

if lock_jabar:
    before = len(df_seed)
    df_seed = df_seed[df_seed.apply(
        lambda r: is_west_java_hit(r.get("title",""), r.get("desc",""), r.get("url","")), axis=1)]
    after = len(df_seed)
    st.caption(f"Filter wilayah Jawa Barat aktif: {before} → {after} kandidat")
    if after == 0:
        st.warning("Tidak ada kandidat yang cocok wilayah Jabar. Matikan filter atau ganti keyword.")
        st.stop()

st.subheader("Kandidat URL")
st.dataframe(df_seed, use_container_width=True, hide_index=True)

# ---------- EKSTRAKSI ----------
urls = df_seed["url"].dropna().tolist()
with st.status("📥 Mengunduh & mengekstrak isi artikel...", expanded=False) as status:
    arts = fetch_articles(urls, user_agent or None, max_workers=8)
    status.update(label="Ekstraksi selesai.", state="complete")

# Gabungkan hasil ekstraksi dengan seed awal
df_art = pd.DataFrame(arts)
for c in ["url", "title_article", "text", "publish_date", "meta_desc", "final_url"]:
    if c not in df_art.columns:
        df_art[c] = None

df = df_seed.merge(df_art, on="url", how="left")
df["title_final"] = df["title_article"].fillna(df["title"])
df["publish_final"] = df["publish_date"].fillna(df["published"])

# ✅ (POINT 4) Normalisasi teks — taruh DI SINI
# Pastikan kolom text tidak kosong dan rapih
df["text"] = df.get("text", "").fillna("").astype(str)
df["text"] = df["text"].str.replace(r"\s+", " ", regex=True).str.strip()

# Hitung panjang teks untuk analisis kelayakan
df["len_text"] = df["text"].str.len()

st.caption("🔎 Debug ekstraksi (panjang teks)")
st.dataframe(df["len_text"].describe().to_frame("len_text_stats").T, width="stretch")

# Filter minimum panjang
MIN_LEN = 80
if int((df["len_text"] > MIN_LEN).sum()) == 0:
    st.warning("Semua ekstraksi gagal/terlalu pendek. Coba tambahkan feed, ganti keyword, atau isi User-Agent.")
    with st.expander("Lihat URL kandidat (debug)"):
        st.write(df[["title_final", "url"]])
    st.stop()

df = df[df["len_text"] > MIN_LEN].copy()

# Debug hasil akhir
with st.expander("🔧 Debug ekstraksi (contoh 10)"):
    cols_debug = [c for c in ["source", "title_final", "url", "final_url", "len_text"] if c in df.columns]
    st.dataframe(df[cols_debug].head(10), width="stretch")


# ---------- SENTIMEN ----------
with st.status("🧠 Memuat model & menganalisis sentimen...", expanded=False) as status:
    bundle = load_models()
    labels, scores = batch_sentiment(df["text"].tolist(), bundle, batch_size=8)
    status.update(label=f"Klasifikasi selesai (model: {bundle['model_name']}).", state="complete")

df["sentiment"] = labels
df["confidence"] = scores

# ---------- RINGKASAN ----------
st.subheader("Ringkasan Sentimen")
c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("Total artikel", len(df))
with c4: st.metric("Negatif", int((df["sentiment"] == "negatif").sum()))
with c3: st.metric("Netral", int((df["sentiment"] == "netral").sum()))
with c2: st.metric("Positif", int((df["sentiment"] == "positif").sum()))
st.bar_chart(df["sentiment"].value_counts(), use_container_width=True)

# ---------- TABEL & UNDUH ----------
show_cols = ["title_final", "source", "publish_final", "sentiment", "confidence", "url", "desc"]
st.subheader("Detail Hasil")
st.dataframe(df[show_cols].rename(columns={"title_final":"title","publish_final":"published"}),
             use_container_width=True, hide_index=True)

csv_bytes = (df[show_cols].rename(columns={"title_final":"title","publish_final":"published"})
             .to_csv(index=False).encode("utf-8"))
safe_kw = re.sub(r"[^\w\-]", "", "_".join(keywords))
st.download_button("💾 Unduh CSV", data=csv_bytes,
                   file_name=f"sentimen_berita_{safe_kw}.csv", mime="text/csv")
