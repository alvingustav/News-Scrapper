# backend/filters.py
def is_west_java_hit(title: str, summary: str, url: str) -> bool:
    JABAR_KEYWORDS = {
        "jawa barat","jabar","bandung","kota bandung","kabupaten bandung","bandung barat",
        "cimahi","sumedang","garut","tasikmalaya","kota tasikmalaya",
        "cianjur","sukabumi","kota sukabumi","bogor","kota bogor","kabupaten bogor",
        "depok","bekasi","kota bekasi","kabupaten bekasi",
        "karawang","purwakarta","subang","indramayu","majalengka","kuningan","cirebon","kota cirebon",
        "pangandaran","banjar","kota banjar","gedung sate","bandung raya","lembang","ciwidey","parahyangan"
    }
    t = (title or "").lower(); s = (summary or "").lower(); u = (url or "").lower()
    if any(k in t or k in s for k in JABAR_KEYWORDS): return True
    heur = ["jabar","jawabarat","bandung","cirebon","bogor","bekasi","tasik","garut","cianjur","sukabumi","depok"]
    return any(h in u for h in heur)
