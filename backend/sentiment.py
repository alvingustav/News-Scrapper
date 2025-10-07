# backend/sentiment.py
import re
from typing import List, Dict
import streamlit as st
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline

@st.cache_resource(show_spinner=False)
def load_models():
    tried = []
    for model_name, tag in [
        ("w11wo/indonesian-roberta-base-sentiment-classifier", "id-3c"),
        ("nlptown/bert-base-multilingual-uncased-sentiment", "mstars"),
    ]:
        try:
            tok = AutoTokenizer.from_pretrained(model_name, use_fast=True)
            try:
                tok.model_max_length = min(int(tok.model_max_length or 512), 512)
            except Exception:
                tok.model_max_length = 512
            mdl = AutoModelForSequenceClassification.from_pretrained(model_name)
            clf = pipeline(
                "text-classification",
                model=mdl, tokenizer=tok, framework="pt",
                truncation=True, padding="max_length", max_length=512
            )
            return {"pipe": clf, "tag": tag, "model_name": model_name}
        except Exception as e:
            tried.append((model_name, str(e)))
            continue
    raise RuntimeError(f"Gagal memuat model. Tried: {tried}")

def _map_label(pred: Dict, tag: str):
    lab = pred["label"].lower(); sc = float(pred.get("score", 0.0))
    if tag == "id-3c":
        if "pos" in lab or lab.endswith("2"): return "positif", sc
        if "neu" in lab or lab.endswith("1"): return "netral", sc
        return "negatif", sc
    m = re.search(r"(\d)", lab); stars = int(m.group(1)) if m else 3
    if stars <= 2: return "negatif", sc
    if stars == 3: return "netral", sc
    return "positif", sc

def _safe_text(x): 
    s = "" if x is None else str(x)
    s = s.strip()
    return s[:6000] if len(s) > 6000 else s

def batch_sentiment(texts: List[str], clf_bundle: Dict, batch_size: int = 8):
    pipe = clf_bundle["pipe"]; tag = clf_bundle["tag"]
    labels, scores = [], []
    i = 0
    while i < len(texts):
        chunk = [_safe_text(t) for t in texts[i:i+batch_size]]
        try:
            results = pipe(chunk, truncation=True, padding="max_length", max_length=512)
            for r in results:
                l, s = _map_label(r, tag); labels.append(l); scores.append(float(s))
            i += batch_size
        except Exception:
            for t in chunk:
                try:
                    r = pipe(t, truncation=True, padding="max_length", max_length=512)[0]
                    l, s = _map_label(r, tag); labels.append(l); scores.append(float(s))
                except Exception:
                    labels.append("netral"); scores.append(0.0)
            i += batch_size
    return labels, scores
