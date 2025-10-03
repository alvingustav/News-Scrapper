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

from zoneinfo import ZoneInfo
from typing import List, Dict, Optional

# ===================== Streamlit Config =====================
st.set_page_config(page_title="Sentimen Berita Lokal 🇮🇩", page_icon="📰", layout="wide")
st.title("📰 Analisis Sentimen Berita Lokal Indonesia")
st.caption("Ketik kata kunci → ambil dari RSS media Indonesia → ekstrak isi → klasifikasi sentimen")

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# ===================== Kumpulan RSS Media Lokal =====================
# (kategori berita umum/nasional/ekonomi/tekno bila tersedia)
INDONESIA_FEEDS: Dict[str, List[str]] = {
    # ======== Media Arus Utama ========
    "Kompas": [
        "https://rss.kompas.com/news",
        "https://rss.kompas.com/kompascom/ekonomi",
        "https://rss.kompas.com/kompascom/tekno",
        "https://rss.kompas.com/kompascom/megapolitan",
        "https://rss.kompas.com/nasional",
    ],
    "Detik": [
        "https://rss.detik.com/index.php/detiknews",
        "https://rss.detik.com/index.php/finance",
        "https://rss.detik.com/index.php/detikinet",
        "https://rss.detik.com/index.php/sepakbola",
        "https://rss.detik.com/index.php/health",
    ],
    "Tempo": [
        "https://rss.tempo.co/nasional",
        "https://rss.tempo.co/bisnis",
        "https://rss.tempo.co/teknologi",
        "https://rss.tempo.co/metro",
    ],
    "Liputan6": [
        "https://feed.liputan6.com/rss",
        "https://feed.liputan6.com/rss/bisnis",
        "https://feed.liputan6.com/rss/tekno",
        "https://feed.liputan6.com/rss/news",
    ],
    "Tribunnews": [
        "https://www.tribunnews.com/rss",
        "https://www.tribunnews.com/bisnis/rss",
        "https://www.tribunnews.com/techno/rss",
        "https://m.tribunnews.com/metro/rss",
    ],
    "ANTARA": [
        "https://www.antaranews.com/rss/top-news",
        "https://www.antaranews.com/rss/nasional",
        "https://www.antaranews.com/rss/ekonomi",
        "https://www.antaranews.com/rss/tekno",
    ],
    "CNN Indonesia": [
        "https://www.cnnindonesia.com/nasional/rss",
        "https://www.cnnindonesia.com/ekonomi/rss",
        "https://www.cnnindonesia.com/teknologi/rss",
    ],
    "CNBC Indonesia": [
        "https://www.cnbcindonesia.com/news/rss",
        "https://www.cnbcindonesia.com/market/rss",
        "https://www.cnbcindonesia.com/tech/rss",
        "https://www.cnbcindonesia.com/syariah/rss",
    ],
    "Merdeka": [
        "https://www.merdeka.com/feed/",
        "https://www.merdeka.com/uang/feed/",
        "https://www.merdeka.com/teknologi/feed/",
    ],
    "Republika": [
        "https://www.republika.co.id/rss",
        "https://www.republika.co.id/rss/nasional",
        "https://www.republika.co.id/rss/ekonomi",
        "https://www.republika.co.id/rss/islam",
    ],
    "BeritaSatu": [
        "https://www.beritasatu.com/rss/nasional",
        "https://www.beritasatu.com/rss/ekonomi",
        "https://www.beritasatu.com/rss/teknologi",
        "https://www.beritasatu.com/rss/politik",
    ],
    "Kumparan": [
        "https://lapi.kumparan.com/v2.0/rss/",
    ],
    "Viva": [
        "https://www.viva.co.id/rss/berita",
        "https://www.viva.co.id/rss/teknologi",
        "https://www.viva.co.id/rss/bisnis",
    ],
    "Okezone": [
        "https://sindikasi.okezone.com/index.php/okezone/RSS2.0",
        "https://economy.okezone.com/rss",
        "https://techno.okezone.com/rss",
    ],
    "IDN Times": [
        "https://www.idntimes.com/rss",
        "https://www.idntimes.com/business/rss",
        "https://www.idntimes.com/tech/rss",
    ],
    # --- Tambahan Media Utama ---
    "Sindonews": [
        "https://www.sindonews.com/rss",
        "https://ekbis.sindonews.com/rss",
        "https://tekno.sindonews.com/rss",
        "https://metro.sindonews.com/rss",
    ],
    "Medcom": [
        "https://www.medcom.id/rss",
        "https://www.medcom.id/ekonomi/rss",
        "https://www.medcom.id/teknologi/rss",
    ],
    "JPNN": [
        "https://www.jpnn.com/rss",
        "https://www.jpnn.com/ekonomi/rss",
        "https://www.jpnn.com/teknologi/rss",
    ],

    # ======== Bisnis/Ekonomi/Keuangan ========
    "Bisnis.com": [
        "https://www.bisnis.com/rss",
        "https://www.bisnis.com/rss/ekonomi",
        "https://finansial.bisnis.com/rss",
        "https://market.bisnis.com/rss",
    ],
    "Kontan": [
        "https://www.kontan.co.id/rss",
        "https://investasi.kontan.co.id/rss",
        "https://insight.kontan.co.id/rss",
    ],
    "Katadata": [
        "https://katadata.co.id/rss",
        "https://katadata.co.id/ekonomi/rss",
        "https://katadata.co.id/teknologi/rss",
    ],
    "Investor Daily": [
        "https://investor.id/rss",
        "https://investor.id/marketandnews/rss",
    ],
    "Fajar.co.id (Bisnis)": [
        "https://fajar.co.id/feed/",
    ],
    # --- Tambahan Media Bisnis ---
    "Warta Ekonomi": [
        "https://www.wartaekonomi.co.id/rss",
        "https://www.wartaekonomi.co.id/tag/ekonomi/feed",
        "https://www.wartaekonomi.co.id/tag/keuangan/feed",
    ],

    # ======== Media Digital/Analitis ========
    "Tirto": [
        "https://tirto.id/rss/sekarang",
        "https://tirto.id/rss/ekonomi",
        "https://tirto.id/rss/teknologi",
    ],
    "The Conversation Indonesia": [
        "https://theconversation.com/id/articles.atom",
        "https://theconversation.com/id/columns/ekonomi.atom",
        "https://theconversation.com/id/columns/teknologi.atom",
    ],
    "Media Indonesia": [
        "https://mediaindonesia.com/rss",
        "https://mediaindonesia.com/ekonomi/rss",
        "https://mediaindonesia.com/teknologi/rss",
    ],
    "Gatra": [
        "https://www.gatra.com/rss",
        "https://www.gatra.com/ekonomi/rss",
        "https://www.gatra.com/tekno/rss",
    ],
    "Tempo English (local, EN)": [
        "https://en.tempo.co/rss/national",
        "https://en.tempo.co/rss/business",
        "https://en.tempo.co/rss/tech",
    ],
    "Jakarta Post (local, EN)": [
        "https://www.thejakartapost.com/rss",
        "https://www.thejakartapost.com/business/rss",
        "https://www.thejakartapost.com/tech/rss",
    ],
    "Beritagar": [
        "https://beritagar.id/rss",
        "https://beritagar.id/tag/ekonomi/rss",
    ],

    # ======== Suara Network / TV/Radio ========
    "Suara": [
        "https://www.suara.com/rss",
        "https://www.suara.com/bisnis/rss",
        "https://www.suara.com/tekno/rss",
        "https://www.suara.com/news/rss",
    ],
    "KompasTV": [
        "https://www.kompas.tv/rss",
    ],
    "RRI": [
        "https://rri.co.id/feed",
    ],
    "Inilah.com": [
        "https://inilah.com/rss",
    ],

    # ======== Regional/Bermarkas di Daerah ========
    "Pikiran Rakyat (Jabar)": [
        "https://www.pikiran-rakyat.com/feed",
        "https://www.pikiran-rakyat.com/jawa-barat/rss",
        "https://www.pikiran-rakyat.com/ekonomi/rss",
        "https://www.pikiran-rakyat.com/teknologi/rss",
        "https://www.pikiran-rakyat.com/bandung-raya/rss",
    ],
    "Jawa Pos": [
        "https://www.jawapos.com/feed/",
        "https://www.jawapos.com/ekonomi-bisnis/feed/",
        "https://www.jawapos.com/teknologi/feed/",
    ],
    "Tribun Jabar": [
        "https://jabar.tribunnews.com/rss",
    ],
    "Tribun Medan": [
        "https://medan.tribunnews.com/rss",
    ],
    "Tribun Surabaya": [
        "https://surabaya.tribunnews.com/rss",
    ],
    "Antara Jabar": [
        "https://jabar.antaranews.com/rss",
        "https://jabar.antaranews.com/rss/berita",
    ],
    "Bandung Bisnis": [
        "https://bandung.bisnis.com/rss",
    ],
    "PRFM News (Bandung)": [
        "https://www.prfmnews.id/rss",
    ],
    "Jabar Ekspres (Radar Bandung)": [
        "https://jabarekspres.com/rss",
    ],
    "Galamedia (PR Network)": [
        "https://galamedia.pikiran-rakyat.com/feed",
    ],
    "Bali Post": [
        "https://www.balipost.com/feed",
    ],
    "Solopos": [
        "https://www.solopos.com/feed",
    ],
    "IDNTimes Regional": [
        "https://www.idntimes.com/jabar/rss",
        "https://www.idntimes.com/sulsel/rss",
        "https://www.idntimes.com/jatim/rss",
    ],
    # --- Tambahan Media Regional ---
    "Suara Surabaya": [
        "https://rss.suarasurabaya.net/rss",
    ],
    "Kaltim Post": [
        "https://kaltim.prokal.co/feed",
    ],
    "Tribun Jogja": [
        "https://jogja.tribunnews.com/rss",
    ],

    # ======== Teknologi & Startup Lokal ========
    "Tekno Kompas": [
        "https://rss.kompas.com/kompascom/tekno",
    ],
    "DetikInet": [
        "https://rss.detik.com/index.php/detikinet",
    ],
    "Dailysocial": [
        "https://dailysocial.id/rss",
        "https://dailysocial.id/post/category/news/rss",
    ],
    "Tech in Asia Indonesia": [
        "https://id.techinasia.com/feed",
    ],
    # --- Tambahan Media Tekno ---
    "Teknologi ID": [
        "https://teknologi.id/rss",
    ],
    "Gadgetren": [
        "https://gadgetren.com/feed",
    ],
    "InfoKomputer": [
        "https://infokomputer.grid.id/rss",
    ],

    # ======== Pemerintah/Resmi (untuk konfirmasi narasi) ========
    "Setkab": [
        "https://setkab.go.id/feed/",
    ],
    "Kemenkeu": [
        "https://www.kemenkeu.go.id/feed/",
        "https://www.kemenkeu.go.id/publikasi/siaran-pers/feed/",
    ],
    "BI (Bank Indonesia) News": [
        "https://www.bi.go.id/id/publikasi/ruang-media/news/Default.aspx?rss=1",
    ],
}

ALL_FEEDS = [(src, url) for src, urls in INDONESIA_FEEDS.items() for url in urls]

# ===================== Sentiment Model (with fallback) =====================
@st.cache_resource(show_spinner=False)
def load_models():
    """
    Coba model Indo 3-kelas, fallback ke multilingual.
    Pipeline dipaksa: padding, truncation, max_length=512 (uniform batch).
    """
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline

    tried = []
    for model_name, tag in [
        ("w11wo/indonesian-roberta-base-sentiment-classifier", "id-3c"),
        ("nlptown/bert-base-multilingual-uncased-sentiment", "mstars"),
    ]:
        try:
            tok = AutoTokenizer.from_pretrained(model_name, use_fast=True)
            # guard agar tidak "infinite" length
            try:
                tok.model_max_length = min(int(tok.model_max_length or 512), 512)
            except Exception:
                tok.model_max_length = 512

            mdl = AutoModelForSequenceClassification.from_pretrained(model_name)
            clf = pipeline(
                "text-classification",           # alias 'sentiment-analysis'
                model=mdl,
                tokenizer=tok,
                framework="pt",
                truncation=True,
                padding="max_length",            # uniform length
                max_length=512,
                return_all_scores=False,
            )
            return {"pipe": clf, "tag": tag, "model_name": model_name}
        except Exception as e:
            tried.append((model_name, str(e)))
            continue
    raise RuntimeError(f"Gagal memuat model. Tried: {tried}")

@st.cache_resource(show_spinner=False)
def load_fallback_pipeline():
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
    model_name = "nlptown/bert-base-multilingual-uncased-sentiment"
    tok = AutoTokenizer.from_pretrained(model_name, use_fast=True)
    tok.model_max_length = 512
    mdl = AutoModelForSequenceClassification.from_pretrained(model_name)
    return pipeline(
        "text-classification",
        model=mdl,
        tokenizer=tok,
        framework="pt",
        truncation=True,
        padding="max_length",
        max_length=512,
        return_all_scores=False,
    )

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

def _safe_text(s) -> str:
    if not isinstance(s, str):
        s = "" if s is None else str(s)
    s = s.strip()
    # potong panjang ekstrem (tokenizer tetap batasi ke 512 token)
    if len(s) > 6000:
        s = s[:6000]
    return s

def batch_sentiment(texts: List[str], clf_bundle: Dict, batch_size: int = 8):
    """
    Inferensi aman:
    - sanitasi teks
    - padding='max_length', max_length=512 (uniform)
    - retry per-item
    - fallback multilingual jika tetap gagal
    """
    pipe = clf_bundle["pipe"]; tag = clf_bundle["tag"]
    labels, scores = [], []
    i = 0
    N = len(texts)
    while i < N:
        chunk = [_safe_text(t) for t in texts[i:i+batch_size]]
        try:
            results = pipe(chunk, truncation=True, padding="max_length", max_length=512)
            for r in results:
                l, s = _map_label(r, tag)
                labels.append(l); scores.append(float(s))
            i += batch_size
        except Exception:
            # retry satu per satu
            for t in chunk:
                try:
                    r = pipe(t, truncation=True, padding="max_length", max_length=512)[0]
                    l, s = _map_label(r, tag)
                    labels.append(l); scores.append(float(s))
                except Exception:
                    try:
                        fb = load_fallback_pipeline()
                        r2 = fb(t, truncation=True, padding="max_length", max_length=512)[0]
                        lab = r2["label"].lower(); sc = float(r2.get("score", 0.0))
                        # map 1-5 stars → sentimen
                        m = re.search(r"(\d)", lab); stars = int(m.group(1)) if m else 3
                        if stars <= 2: labels.append("negatif"); scores.append(sc)
                        elif stars == 3: labels.append("netral"); scores.append(sc)
                        else: labels.append("positif"); scores.append(sc)
                    except Exception:
                        labels.append("netral"); scores.append(0.0)
            i += batch_size
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
            # normalisasi ke Asia/Jakarta (WIB) lalu jadikan naive
            if dt.tzinfo:
                dt = dt.astimezone(ZoneInfo("Asia/Jakarta")).replace(tzinfo=None)
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

# Nama provinsi + seluruh kab/kota Jabar (varian ejaan umum)
JABAR_KEYWORDS = {
    "jawa barat", "jabar", "bandung", "kota bandung", "kabupaten bandung", "bandung barat",
    "cimahi", "sumedang", "garut", "tasikmalaya", "kota tasikmalaya",
    "cianjur", "sukabumi", "kota sukabumi", "bogor", "kota bogor", "kabupaten bogor",
    "depok", "bekasi", "kota bekasi", "kabupaten bekasi",
    "karawang", "purwakarta", "subang", "indramayu", "majalengka", "kuningan", "cirebon", "kota cirebon",
    "pangandaran", "banjar", "kota banjar",
    # Area/landmark yang sering dipakai
    "gedung sate", "bandung raya", "ciwidey", "lembang", "cibiru", "cibinong", "parahyangan"
}

def is_west_java_hit(title: str, summary: str, url: str) -> bool:
    t = (title or "").lower()
    s = (summary or "").lower()
    u = (url or "").lower()
    # 1) cek di judul/deskripsi
    for k in JABAR_KEYWORDS:
        if k in t or k in s:
            return True
    # 2) sedikit heuristic domain/slug
    heuristics = ["jabar", "jawabarat", "bandung", "cirebon", "bogor", "bekasi", "tasik", "garut", "cianjur", "sukabumi", "depok"]
    return any(h in u for h in heuristics)


@st.cache_data(show_spinner=False)
def search_indonesia_rss(
    keyword: str,
    max_results: int,
    date_start: Optional[datetime.date] = None,
    date_end: Optional[datetime.date] = None,
) -> List[Dict]:
    """
    Agregasi semua RSS lokal → filter by keyword & rentang tanggal (Asia/Jakarta) → dedup & limit.
    - date_start/date_end berupa tipe datetime.date (bukan datetime).
    """
    out = []

    for source, url in ALL_FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries:
                # keyword check
                if not matches_keyword(e, keyword):
                    continue

                link = getattr(e, "link", None) or ""
                if not link:
                    continue

                dt = parse_entry_date(e)  # datetime naive WIB atau None
                # jika user set filter tanggal, hanya ambil yang punya tanggal & berada dalam range (inklusif)
                if (date_start or date_end):
                    if dt is None:
                        continue  # tak bisa dibandingkan, skip
                    d = dt.date()
                    if date_start and d < date_start:
                        continue
                    if date_end and d > date_end:
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

    # Sort by published desc (kalau ada), else min
    def _key(r):
        try:
            return dtparser.parse(r["published"])
        except Exception:
            return datetime.min
    rows.sort(key=_key, reverse=True)

    return rows[:max_results]

# ====== Konstanta ======
NEWSAPI_KEY = "60448de50608492983ffdf1a9f4379cf"

# ====== Fallback Search ======
def search_google_news_rss(keywords: List[str], limit: int = 50) -> List[Dict]:
    """Ganti dengan RSS Indonesia tambahan yang lebih relevan"""
    extra_feeds = [
        ("BBC Indonesia", "https://feeds.bbci.co.uk/indonesia/rss.xml"),
        ("VOA Indonesia", "https://www.voaindonesia.com/api/z$qmgqpyvm"),
        ("DW Indonesia", "https://rss.dw.com/xml/rss-id-all"),
        ("RFI Indonesia", "https://www.rfi.fr/id/rss"),
    ]
    
    out = []
    for name, feed_url in extra_feeds:
        try:
            st.caption(f"🔍 Mencoba {name}...")
            feed = feedparser.parse(feed_url)
            st.caption(f"📡 {name}: {len(feed.entries)} entries")
            
            for entry in feed.entries[:limit//len(extra_feeds)]:
                hits = matches_keyword_multi(entry, keywords)
                if hits:
                    out.append({
                        "title": entry.title,
                        "url": entry.link,
                        "source": name,
                        "published": getattr(entry, "published", None),
                        "desc": getattr(entry, "summary", ""),
                        "hit_keywords": ", ".join(hits),
                    })
        except Exception as e:
            st.caption(f"❌ {name}: {str(e)}")
    
    return out


def search_newsapi(keywords: List[str], limit: int = 50) -> List[Dict]:
    """Implementasi NewsAPI dengan debugging yang terlihat di UI"""
    out = []
    if not NEWSAPI_KEY:
        st.caption("❌ NewsAPI: API key tidak tersedia")
        return out
        
    try:
        query = " OR ".join(keywords)
        st.caption(f"🔍 NewsAPI query: {query}")
        
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "q": query,
            "language": "id",
            "country": "id", 
            "pageSize": min(limit, 100),
            "apiKey": NEWSAPI_KEY
        }
        
        response = requests.get(url, params=params, timeout=15)
        st.caption(f"📡 NewsAPI status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            articles = data.get("articles", [])
            st.caption(f"📰 NewsAPI raw articles: {len(articles)}")
            
            for article in articles:
                title = (article.get("title") or "").lower()
                desc = (article.get("description") or "").lower()
                
                matched = [k for k in keywords if k.lower() in title or k.lower() in desc]
                if matched:
                    out.append({
                        "title": article.get("title"),
                        "url": article.get("url", ""),
                        "source": f"NewsAPI ({article.get('source', {}).get('name', 'Unknown')})",
                        "published": article.get("publishedAt"),
                        "desc": article.get("description"),
                        "hit_keywords": ", ".join(matched),
                    })
        elif response.status_code == 429:
            st.caption("⚠️ NewsAPI: Rate limit exceeded")
        elif response.status_code == 401:
            st.caption("❌ NewsAPI: API key invalid")
        else:
            st.caption(f"❌ NewsAPI error {response.status_code}: {response.text[:100]}")
            
    except Exception as e:
        st.caption(f"❌ NewsAPI exception: {str(e)}")
        
    st.caption(f"✅ NewsAPI hasil: {len(out)} artikel")
    return out

def search_berita_indo_api(keywords: List[str], limit: int = 50) -> List[Dict]:
    endpoints = [
        "https://berita-indo-api-next.vercel.app/api/cnn-news",
        "https://berita-indo-api-next.vercel.app/api/cnbc-news",
        "https://berita-indo-api-next.vercel.app/api/republika-news",
    ]
    out = []
    for ep in endpoints:
        try:
            for art in requests.get(ep, timeout=10).json().get("data", []):
                if len(out) >= limit:
                    break
                title = (art["title"] or "").lower()
                desc = (art["description"] or "").lower()
                hits = [kw for kw in keywords if kw.lower() in title or kw.lower() in desc]
                if hits:
                    out.append(
                        {
                            "title": art["title"],
                            "url": art["url"],
                            "source": f"BeritaIndo ({ep.split('/')[-1]})",
                            "published": art["isoDate"],
                            "desc": art["description"],
                            "hit_keywords": ", ".join(hits),
                        }
                    )
        except Exception:
            continue
    return out[:limit]

def matches_keyword_multi(entry, keywords: List[str]) -> List[str]:
    """
    Mengembalikan list keyword yang match dengan entry RSS
    """
    kw_matches = []
    title = (getattr(entry, "title", "") or "").lower()
    summary = (getattr(entry, "summary", "") or "").lower()
    
    for keyword in keywords:
        kw = keyword.strip().lower()
        if not kw:
            continue
        if kw in title or kw in summary:
            kw_matches.append(keyword)
    
    return kw_matches


# ====== Master search ======
@st.cache_data(show_spinner=False)
def search_multi_source(
    keywords: List[str],
    max_results: int,
    date_start: Optional[datetime.date] = None,
    date_end: Optional[datetime.date] = None,
    max_workers: int = 32,
) -> List[Dict]:
    def _fetch(src, url):
        try:
            return src, feedparser.parse(url)
        except Exception:
            return src, None

    def safe_parse_date(date_str):
        """Parse tanggal dengan aman, hilangkan timezone untuk sorting"""
        try:
            if not date_str:
                return datetime.min
            dt = dtparser.parse(date_str)
            # Hilangkan timezone info untuk menghindari mixing offset-aware/naive
            return dt.replace(tzinfo=None)
        except Exception:
            return datetime.min

    rows: List[Dict] = []
    
    # --- 1) RSS lokal paralel ---
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_fetch, s, u) for s, u in ALL_FEEDS]
        for fut in as_completed(futures):
            src, feed = fut.result()
            if not feed:
                continue
            for e in feed.entries:
                hits = matches_keyword_multi(e, keywords)
                if not hits:
                    continue
                link = getattr(e, "link", "")
                if not link:
                    continue
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

    st.caption(f"🔍 RSS lokal: {len(rows)} artikel")

    # --- 2) Fallback Google News RSS jika <10 ---
    if len(rows) < 10:
        try:
            google_results = search_google_news_rss(keywords, max_results // 2)
            rows.extend(google_results)
            st.caption(f"📰 + Google News RSS: {len(google_results)} artikel")
        except Exception as e:
            st.caption(f"📰 + Google News RSS: Error - {str(e)}")
    
    # --- 3) NewsAPI ---
    if len(rows) < max_results:
        try:
            newsapi_results = search_newsapi(keywords, max_results // 3)
            rows.extend(newsapi_results)
            st.caption(f"🌐 + NewsAPI: {len(newsapi_results)} artikel")
        except Exception as e:
            st.caption(f"🌐 + NewsAPI: Error - {str(e)}")
    
    # --- 4) Berita Indo API ---
    if len(rows) < max_results:
        try:
            berita_indo_results = search_berita_indo_api(keywords, max_results // 4)
            rows.extend(berita_indo_results)
            st.caption(f"📡 + Berita Indo API: {len(berita_indo_results)} artikel")
        except Exception as e:
            st.caption(f"📡 + Berita Indo API: Error - {str(e)}")


    # --- deduplikasi & sort dengan handling timezone yang aman ---
    seen_urls = set()
    unique_rows = []
    for row in rows:
        if row["url"] not in seen_urls:
            seen_urls.add(row["url"])
            unique_rows.append(row)

    # Sort dengan safe date parsing
    unique_rows.sort(key=lambda r: safe_parse_date(r["published"]), reverse=True)
    
    st.caption(f"✅ Total unik setelah deduplikasi: {len(unique_rows)}")
    
    return unique_rows[:max_results]



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
        "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    )
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://www.google.com/",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate", 
        "Sec-Fetch-Site": "cross-site",
        "Upgrade-Insecure-Requests": "1"
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
def fetch_articles(urls: List[str], user_agent: Optional[str] = None, max_workers: int = 6):
    import time
    import random
    
    def fetch_with_delay(url):
        time.sleep(random.uniform(0.5, 2.0))  # Random delay 0.5-2s
        return fetch_article(url, user_agent)
    
    out = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:  # Reduced from 12 to 6
        futures = [ex.submit(fetch_with_delay, u) for u in urls]
        for fut in as_completed(futures):
            out.append(fut.result())
    return out


# ===================== Sidebar =====================
with st.sidebar:
    st.header("⚙️ Pengaturan")
    # BARU:
    raw_kw = st.text_input("Kata kunci (pisahkan dengan koma)", "inflasi, suku bunga")
    keywords = [k.strip() for k in re.split(r"[;,]", raw_kw) if k.strip()]
    max_results = st.slider("Jumlah berita (maks)", 10, 200, 60, 10)

    # rentang tanggal (WIB). default: 14 hari ke belakang s/d hari ini
    today_wib = datetime.now(ZoneInfo("Asia/Jakarta")).date()
    default_start = today_wib - timedelta(days=14)
    date_range = st.date_input(
        "Rentang tanggal (WIB)",
        (default_start, today_wib),
        help="Pilih tanggal mulai & selesai. Kosongkan salah satu jika ingin bebas di ujung."
    )

    # normalisasi output date_input → (start_date, end_date)
    start_date = end_date = None
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    elif date_range:  # single date
        start_date = date_range

    user_agent = st.text_input("Custom User-Agent (opsional)", value="")
    lock_jabar = st.checkbox("🔒 Kunci ke Jawa Barat", value=False)
    run_btn = st.button("🚀 Cari & Analisis", use_container_width=True)


# ===================== Main Flow =====================
if run_btn:
    if not keywords:
        st.warning("Mohon isi kata kunci.")
        st.stop()

    # 1) Search lokal RSS
    with st.status("🔎 Mengumpulkan RSS media lokal...", expanded=False) as status:
        # BARU:
        rows = search_multi_source(
            keywords,  # list instead of string
            max_results=max_results,
            date_start=start_date,
            date_end=end_date,
        )
        # tampilkan ringkasan filter aktif
        if start_date or end_date:
            st.caption(
                f"Filter tanggal aktif (WIB): "
                f"{start_date.isoformat() if start_date else '—'} s/d "
                f"{end_date.isoformat() if end_date else '—'}"
            )
        status.update(label=f"Ditemukan {len(rows)} kandidat URL dari media lokal.", state="complete")


    if not rows:
        st.warning("Tidak ada URL dari RSS lokal yang cocok. Coba perluas kata kunci atau naikkan jumlah/longgarkan filter hari.")
        st.stop()

    df_seed = pd.DataFrame(rows)

    # Pastikan kolom yang dipakai filter ada (hindari KeyError / None)
    for c in ["title", "desc", "url"]:
        if c not in df_seed.columns:
            df_seed[c] = ""
    
    if lock_jabar:
        before = len(df_seed)
        df_seed = df_seed[
            df_seed.apply(
                lambda r: is_west_java_hit(
                    r.get("title", ""), r.get("desc", ""), r.get("url", "")
                ),
                axis=1,
            )
        ]
        after = len(df_seed)
        st.caption(f"Filter wilayah Jawa Barat aktif: {before} → {after} kandidat")
        if after == 0:
            st.warning(
                "Tidak ada kandidat yang cocok dengan wilayah Jawa Barat. "
                "Coba ganti kata kunci atau matikan filter."
            )
            st.stop()
    else:
        st.caption("Filter wilayah Jawa Barat nonaktif.")
    
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
        labels, scores = batch_sentiment(df["text"].tolist(), bundle, batch_size=8)
        status.update(label=f"Klasifikasi selesai (model: {bundle['model_name']}).", state="complete")

    df["sentiment"] = labels
    df["confidence"] = scores

    # 4) Ringkasan
    st.subheader("Ringkasan Sentimen")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Total artikel", len(df))
    with c2: st.metric("Positif", int((df["sentiment"] == "positif").sum()))
    with c3: st.metric("Netral", int((df["sentiment"] == "netral").sum()))
    with c4: st.metric("Negatif", int((df["sentiment"] == "negatif").sum()))
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
    safe_kw = re.sub(r"[^\w\-]", "", "_".join(keywords))
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
