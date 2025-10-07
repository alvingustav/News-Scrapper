# backend/feeds.py
from typing import Dict, List

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
