# =============================
# DROP-IN REPLACEMENT v4 (LLM + UI) — COMPLETE / SINGLE FILE
# =============================
# Keeps what works from v3:
# - asahi_catalog.json load
# - OpenAI Responses API with JSON schema
# - bundles + product cards + seller links + price calc + optional og:image fetch
# - promo + popular uses + quickstart (personal/business)
# Fixes:
# - RecursionError in ss_init (no self-calls)
# - Duplicate UI / repeated panels during thinking
# - "Calling st.rerun() within a callback is a no-op." (remove rerun from callbacks)
# - History-safe bundles + suggestions per assistant turn
# - LLM can return bundles=[] when intent is unclear (gift etc.) and asks 1 question

from __future__ import annotations

import html
import json
import os
import random
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import streamlit as st
from openai import OpenAI

# Optional og:image fetch
try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

# Optional auto-refresh (promo auto-rotate)
try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
except Exception:
    st_autorefresh = None  # type: ignore


# -----------------------------
# Config
# -----------------------------
st.set_page_config(page_title="Asahi Group AIショッパー（デモ）", page_icon="🛒", layout="wide")

client = OpenAI()
BASE = Path(__file__).resolve().parent
CATALOG_PATH = BASE / "asahi_catalog.json"

SELLER_OFFSETS = {"amazon": 1.00, "rakuten": 1.05, "lohaco": 1.03}
TODAY = datetime.now().strftime("%Y-%m-%d")


# -----------------------------
# CSS
# -----------------------------
st.markdown(
    """
<style>
:root { color-scheme: light; }
html, body { background:#ffffff !important; color:#111827 !important; }
.stApp, div[data-testid="stAppViewContainer"], div[data-testid="stMain"], div[data-testid="stMainBlockContainer"]{
  background:#ffffff !important;
  color:#111827 !important;
}
header[data-testid="stHeader"], div[data-testid="stToolbar"], div[data-testid="stDecoration"]{
  background:#ffffff !important;
  color:#111827 !important;
  border-bottom:1px solid rgba(17,24,39,0.10) !important;
}
div[data-testid="stBottom"], div[data-testid="stBottomBlockContainer"]{
  background:#ffffff !important;
  border-top:1px solid rgba(17,24,39,0.10) !important;
}

[data-testid="stMarkdownContainer"], .stCaption, .stCaption p { color:#111827 !important; }

div[data-testid="stTextInput"] input{
  background:#ffffff !important;
  color:#111827 !important;
  border:1px solid rgba(17,24,39,0.18) !important;
  border-radius:12px !important;
  padding:10px 12px !important;
  box-shadow: 0 6px 14px rgba(17,24,39,0.05) !important;
}
div[data-testid="stTextInput"] input::placeholder{
  color: rgba(17,24,39,0.45) !important;
}

/* Buttons: kill dark pills across versions */
div[data-testid="stButton"] button,
div[data-testid^="baseButton-"] button,
button[kind],
button {
  background: #ffffff !important;
  color: #111827 !important;
  border: 1px solid rgba(17,24,39,0.18) !important;
  border-radius: 999px !important;
  box-shadow: 0 6px 14px rgba(17,24,39,0.06) !important;
  padding: 8px 14px !important;
}
div[data-testid="stButton"] button * ,
div[data-testid^="baseButton-"] button * ,
button * {
  color: inherit !important;
  fill: currentColor !important;
}
div[data-testid="stButton"] button:hover,
div[data-testid^="baseButton-"] button:hover,
button:hover{
  background:#F9FAFB !important;
  border-color: rgba(17,24,39,0.28) !important;
  transform: translateY(-1px);
}

/* Promo arrows */
.promo-nav div[data-testid="stButton"] button{
  border-radius: 12px !important;
  padding: 8px 10px !important;
}

/* Chips */
.chips-tight div[data-testid="stButton"] button{
  padding: 8px 12px !important;
  font-weight: 700 !important;
  white-space: nowrap !important;
}

/* Promo card */
.promo-card {
  border-radius: 22px;
  padding: 18px;
  height: 520px;
  border: 1px solid rgba(17,24,39,0.10);
  box-shadow: 0 12px 28px rgba(17,24,39,0.08);
  background: linear-gradient(180deg, #EBCB77 0%, #D8B25A 100%);
  position: relative;
  overflow: hidden;
}
.promo-badge {
  display:inline-flex; align-items:center; gap:10px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255,255,255,0.55);
  border: 1px solid rgba(255,255,255,0.55);
  font-weight: 800;
}
.promo-title { margin-top: 26px; font-size: 38px; font-weight: 900; letter-spacing: -0.02em; }
.promo-copy { margin-top: 10px; font-size: 16px; opacity: 0.95; }
.promo-cta {
  margin-top: 22px;
  display:inline-flex;
  align-items:center;
  padding: 12px 18px;
  border-radius: 999px;
  background: rgba(17,24,39,0.88);
  color: white;
  font-weight: 800;
  border: 1px solid rgba(0,0,0,0.15);
}

/* Hub cards */
.hub-card{
  border: 1px solid rgba(17,24,39,0.10);
  border-radius: 16px;
  padding: 12px;
  background: #ffffff;
  box-shadow: 0 10px 22px rgba(17,24,39,0.06);
  margin-top: 12px;
}
.hub-title{ font-weight: 900; font-size: 14px; margin-bottom: 8px; }
.kbd{
  font-size:12px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid rgba(17,24,39,0.18);
  background: #F9FAFB;
  color: rgba(17,24,39,0.75);
}

/* Bundle shell + product cards */
.bundle-shell{
  border: 1px solid rgba(17,24,39,0.10);
  border-radius: 16px;
  padding: 12px;
  background: #ffffff;
  box-shadow: 0 10px 22px rgba(17,24,39,0.06);
  margin-top: 12px;
}
.bundle-grid{ display:flex; flex-direction:column; gap:10px; }
.prod-card{
  display:flex; gap:12px;
  border:1px solid rgba(17,24,39,0.10);
  border-radius:14px;
  padding:10px;
  background:#ffffff;
  box-shadow: 0 10px 22px rgba(17,24,39,0.05);
}
.prod-img{
  width:84px; height:84px;
  border-radius:12px;
  object-fit:cover;
  border:1px solid rgba(17,24,39,0.10);
  background:#F3F4F6;
}
.prod-meta{ flex:1; min-width:0; }
.prod-title{ font-weight:900; font-size:14px; margin-bottom:2px; }
.prod-sub{ font-size:12px; color: rgba(17,24,39,0.70); margin-bottom:4px; }
.prod-reason{ font-size:12px; color: rgba(17,24,39,0.70); margin-bottom:8px; }
.prod-links{ display:flex; flex-wrap:wrap; gap:8px; }
.badge-link{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:3px 10px;
  border-radius:999px;
  border:1px solid rgba(0,0,0,0.14);
  text-decoration:none !important;
  font-size:12px;
  font-weight:600;
  color:#111827 !important;
  line-height:1.6;
  background:#F9FAFB;
}

/* Typing */
.typing {
  display:inline-flex; align-items:center; gap:8px;
  font-size:13px; color: rgba(17,24,39,0.65);
}
.typing .dots { display:inline-flex; gap:5px; }
.typing .dot{
  width:7px; height:7px; border-radius:999px;
  background: rgba(17,24,39,0.35);
  animation: blink 1.2s infinite ease-in-out;
}
.typing .dot:nth-child(2){ animation-delay: 0.15s; }
.typing .dot:nth-child(3){ animation-delay: 0.30s; }
@keyframes blink {
  0%, 80%, 100% { opacity:0.2; transform: translateY(0); }
  40% { opacity:1; transform: translateY(-2px); }
}

/* Sticky left column (optional) */
.sticky-left {
  position: sticky;
  top: 4.2rem; /* below Streamlit header */
  align-self: flex-start;
}
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------
# Session State (NO recursion)
# -----------------------------
def ss_init(key: str, default: Any):
    if key not in st.session_state:
        st.session_state[key] = default


ss_init("messages", [])                 # list[{role, content, turn_id?, bundles?, suggested_replies?}]
ss_init("welcome_shown", False)
ss_init("thinking", False)
ss_init("pending_action", None)
ss_init("prompt_draft", "")
ss_init("prefill_prompt", "")
ss_init("selected_bundle_id", "mid")
ss_init("promo_auto", True)
ss_init("promo_i", 0)
ss_init("turn_i", 0)                    # increments per assistant response
ss_init("promo_tick_last", 0)           # for st_autorefresh counter tracking


# -----------------------------
# Data
# -----------------------------
@st.cache_data
def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


CATALOG = load_catalog()
PRODUCTS = CATALOG.get("products", [])
PRODUCT_BY_ID = {p["asahi_id"]: p for p in PRODUCTS if "asahi_id" in p}
ASAHI_IDS = list(PRODUCT_BY_ID.keys())

CATALOG_GROUNDING = "\n".join(
    f'{p["asahi_id"]}: {p.get("name_ja","")} / tags={",".join(p.get("tags", []))}'
    for p in PRODUCTS
    if "asahi_id" in p
)


# -----------------------------
# Left Hub data
# -----------------------------
POPULAR_USES = [
    ("忘年会準備", 1234, "忘年会の準備をしたい。人数/予算/希望ジャンルを一緒に決めたい。"),
    ("自宅飲み会", 892, "自宅飲み会用におすすめのセットを作って。人数は6人くらい。"),
    ("BBQセット", 756, "BBQ向けに飲み物とおつまみのセットを作って。屋外で飲みやすいもの中心。"),
    ("オフィス備品", 543, "オフィス用の飲料ストックを用意したい。ノンアルやソフトドリンクも混ぜたい。"),
]

QUICKSTART_PERSONAL = [
    ("ホームパーティー", "ホームパーティー用におすすめを提案して。人数はだいたい◯人、予算は◯円。"),
    ("BBQ・アウトドア", "BBQ/アウトドア向けのおすすめセットを作って。持ち運びやすさ重視。"),
    ("ギフト・贈り物", "ギフト用におすすめを提案して。相手の好みは◯◯で、予算は◯円。"),
    ("自宅ストック", "自宅ストック用に定番中心で組んで。ノンアルも混ぜたい。"),
]

QUICKSTART_BUSINESS = [
    ("居酒屋在庫補充", "居酒屋の在庫補充用に提案して。回転が良い定番中心で。"),
    ("オフィス補充", "オフィスの飲料補充をしたい。ノンアル/ソフトドリンク多めで。"),
    ("イベント・ケータリング", "イベント用にまとめ買いしたい。人数◯人、予算◯円。"),
    ("レストラン仕入れ", "レストランの仕入れ向けに提案して。料理に合う飲料中心で。"),
]


# -----------------------------
# Promo
# -----------------------------
PROMOS = [
    {"kicker": "ASAHI", "title": "Free Delivery", "copy": "On orders over ¥5,000. Get it delivered fresh.", "cta": "Order Now", "foot": "Demo promo panel (static content)."},
    {"kicker": "SUPER DRY", "title": "Crisp & Clean", "copy": "A sharp finish that pairs well with food.", "cta": "Explore", "foot": "Later: fetch from real campaign feed."},
    {"kicker": "NON-ALC", "title": "0.00% Options", "copy": "Great taste without alcohol—perfect for mixed bundles.", "cta": "See lineup", "foot": "Demo promo panel (static content)."},
]


def render_promo_panel():
    # Auto rotate: disable while thinking to avoid weird intermediate states
    col_a, col_b = st.columns([0.55, 0.45])
    with col_a:
        st.session_state["promo_auto"] = st.toggle("Auto rotate", value=bool(st.session_state["promo_auto"]), key="promo_auto_toggle")
    with col_b:
        if st.session_state["promo_auto"] and st_autorefresh is None:
            st.caption("※ auto-rotate を使うなら `pip install streamlit-autorefresh`")

    if st.session_state["promo_auto"] and (st_autorefresh is not None) and (not st.session_state["thinking"]):
        tick = st_autorefresh(interval=3500, key="promo_refresh_tick")
        # tick is an int counter; only update promo_i when it changes
        if isinstance(tick, int) and tick != int(st.session_state["promo_tick_last"]):
            st.session_state["promo_tick_last"] = tick
            st.session_state["promo_i"] = tick % len(PROMOS)

    p = PROMOS[int(st.session_state["promo_i"]) % len(PROMOS)]
    st.markdown(
        f"""
        <div class="promo-card">
          <div class="promo-badge">朝 <span>{html.escape(p["kicker"])}</span></div>
          <div class="promo-title">{html.escape(p["title"])}</div>
          <div class="promo-copy">{html.escape(p["copy"])}</div>
          <div class="promo-cta">{html.escape(p["cta"])}</div>
          <div style="position:absolute; bottom:16px; left:18px; right:18px; font-size:12px; color:rgba(17,24,39,0.75);">
            {html.escape(p["foot"])}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='promo-nav'>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    # NO st.rerun() here — Streamlit reruns automatically on click
    if c1.button("◀", key="promo_prev"):
        st.session_state["promo_i"] = (int(st.session_state["promo_i"]) - 1) % len(PROMOS)
        st.session_state["promo_tick_last"] = int(st.session_state["promo_tick_last"]) + 1
    if c2.button("▶", key="promo_next"):
        st.session_state["promo_i"] = (int(st.session_state["promo_i"]) + 1) % len(PROMOS)
        st.session_state["promo_tick_last"] = int(st.session_state["promo_tick_last"]) + 1
    st.markdown("</div>", unsafe_allow_html=True)


def render_left_hub():
    st.markdown("<div class='hub-card'>", unsafe_allow_html=True)
    st.markdown("<div class='hub-title'>人気の使い方</div>", unsafe_allow_html=True)
    for i, (name, cnt, prompt) in enumerate(POPULAR_USES):
        c1, c2 = st.columns([0.78, 0.22])
        with c1:
            if st.button(name, key=f"pop_use_{i}", use_container_width=True):
                st.session_state["prefill_prompt"] = prompt
        with c2:
            st.markdown(
                f"<div style='padding-top:10px; text-align:right;'><span class='kbd'>{cnt:,}</span></div>",
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='hub-card'>", unsafe_allow_html=True)
    st.markdown("<div class='hub-title'>クイックスタート</div>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["個人向け", "ビジネス向け"])
    with tab1:
        cols = st.columns(2)
        for i, (label, prompt) in enumerate(QUICKSTART_PERSONAL):
            with cols[i % 2]:
                if st.button(label, key=f"qs_p_{i}", use_container_width=True):
                    st.session_state["prefill_prompt"] = prompt
    with tab2:
        cols = st.columns(2)
        for i, (label, prompt) in enumerate(QUICKSTART_BUSINESS):
            with cols[i % 2]:
                if st.button(label, key=f"qs_b_{i}", use_container_width=True):
                    st.session_state["prefill_prompt"] = prompt
    st.markdown("</div>", unsafe_allow_html=True)


# -----------------------------
# LLM Schema + Prompt
# -----------------------------
CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "assistant_message_md": {"type": "string", "maxLength": 2500},
        "suggested_replies": {"type": "array", "items": {"type": "string", "maxLength": 60}, "maxItems": 6},
        "bundles": {
            "type": "array",
            "minItems": 0,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "enum": ["low", "mid", "high"]},
                    "label": {"type": "string", "maxLength": 40},
                    "concept": {"type": "string", "maxLength": 140},
                    "why_this_feels_right": {"type": "string", "maxLength": 220},
                    "bundle_items": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 10,
                        "items": {
                            "type": "object",
                            "properties": {
                                "asahi_id": {"type": "string", "enum": ASAHI_IDS},
                                "qty": {"type": "integer", "minimum": 1, "maximum": 30},
                                "seller_preference": {"type": "string", "enum": ["amazon", "rakuten", "lohaco", "any"]},
                                "reason": {"type": "string", "maxLength": 140},
                            },
                            "required": ["asahi_id", "qty", "seller_preference", "reason"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["id", "label", "concept", "why_this_feels_right", "bundle_items"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["assistant_message_md", "suggested_replies", "bundles"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = f"""
あなたはAsahi Groupの“AIショッパー”。
口調は丁寧でフレンドリー。ユーザーの計画（パーティー/来客/ギフト/日常のストック/業務用途など）を一緒に作る「相談相手」。

重要:
- 会話はフォームではない。質問攻めにしない。
- ユーザーが既に書いた情報（人数/予算/納期/用途）は繰り返し聞かない。
- 不足があっても、まずは仮定して提案し、必要なら “最優先の質問を1つだけ” やんわり添える。
- 「質問しないと進めない」動作は禁止。ただし、目的が切り替わった（例: ギフト）などで決定情報が不足している場合は
  bundles を無理に出さず、bundles=[] にして意図確認を優先してよい。

bundles を出す基準:
- ユーザーの用途が明確で、提案が成立する最低限が揃ったときだけ。
- 例: ギフト → 受け取る相手（性別/年代/関係性）/予算/アルコール可否 が不明なら bundles=[] でOK。

制約:
- 提案できる商品は asahi_id の一覧のみ。それ以外は絶対に出さない。
- 酒類が含まれる場合は最後に一言だけ「飲酒は20歳以上」を添える。

出力:
- assistant_message_md: 自然な会話文（短め 6〜10行）+ 次の一手
- suggested_replies: 次に押しやすい短い返答（最大6）
- bundles: 0〜3件（可能なら low/mid/high）。条件が薄い時は mid だけでもOK。
- 商品の羅列は assistant_message_md に長々書かず、bundle UI に任せる。
- 今日の日付は {TODAY}（季節イベントが近ければ一言だけ雰囲気を添える）
"""


def llm_chat(messages: list[dict]) -> dict:
    # only role/content to the model
    context = messages[-16:] if len(messages) > 16 else messages
    context_clean = [{"role": m["role"], "content": m["content"]} for m in context]

    resp = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06"),
        input=[
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "system", "content": "利用可能な商品一覧（asahi_id）:\n" + CATALOG_GROUNDING},
            *context_clean,
        ],
        text={"format": {"type": "json_schema", "name": "asahi_chat", "schema": CHAT_SCHEMA, "strict": True}},
        temperature=0.6,
    )
    return json.loads(resp.output_text)


# -----------------------------
# Product helpers
# -----------------------------
@st.cache_data(show_spinner=False)
def fetch_og_image(url: str) -> Optional[str]:
    try:
        if requests is not None:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=6)
            if r.status_code != 200:
                return None
            text = r.text
        else:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as res:
                text = res.read().decode("utf-8", errors="ignore")

        m = re.search(r'property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', text, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r'content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', text, re.IGNORECASE)
        if m:
            return m.group(1)
        return None
    except Exception:
        return None


def pick_seller(pref: str) -> str:
    return pref if pref in ("amazon", "rakuten", "lohaco") else "amazon"


def product_image_url(prod: dict, seller: str) -> Optional[str]:
    if prod.get("image_url"):
        return prod["image_url"]
    img = prod.get("offers", {}).get(seller, {}).get("image_url")
    if img:
        return img
    url = prod.get("offers", {}).get(seller, {}).get("url")
    if url:
        return fetch_og_image(url)
    return None


def yen(x: int) -> str:
    return f"¥{x:,}"


def stable_base_price(asahi_id: str) -> int:
    random.seed(asahi_id)
    return random.choice([980, 1180, 1280, 1680, 1980, 2480, 2980, 3580, 3980, 4280, 4980])


def offer_price(product: dict, seller: str) -> int:
    p = product.get("offers", {}).get(seller, {}).get("price_jpy")
    if isinstance(p, int) and p > 0:
        return p
    base = product.get("offers", {}).get("amazon", {}).get("price_jpy")
    if isinstance(base, int) and base > 0:
        return int(base * SELLER_OFFSETS.get(seller, 1.0))
    return int(stable_base_price(product["asahi_id"]) * SELLER_OFFSETS.get(seller, 1.0))


def bundle_est_total_jpy(bundle_items: list[dict]) -> int:
    total = 0
    for it in bundle_items:
        prod = PRODUCT_BY_ID.get(it["asahi_id"])
        if not prod:
            continue
        seller = pick_seller(it.get("seller_preference", "any"))
        total += offer_price(prod, seller) * int(it.get("qty", 1))
    return int(total)


def render_bundle_cards_with_images(bundle_items: list[dict]):
    st.markdown("<div class='bundle-grid'>", unsafe_allow_html=True)
    for bi in bundle_items:
        prod = PRODUCT_BY_ID.get(bi["asahi_id"])
        if not prod:
            continue

        qty = int(bi.get("qty", 1))
        reason = bi.get("reason", "")
        seller = pick_seller(bi.get("seller_preference", "any"))

        offers = prod.get("offers", {})
        amz_url = offers.get("amazon", {}).get("url", "#")
        rak_url = offers.get("rakuten", {}).get("url", "#")
        loh_url = offers.get("lohaco", {}).get("url", "#")

        img_url = product_image_url(prod, seller)
        img_html = f"<img class='prod-img' src='{img_url}' />" if img_url else "<div class='prod-img ph'></div>"

        amz_p = offer_price(prod, "amazon")
        rak_p = offer_price(prod, "rakuten")
        loh_p = offer_price(prod, "lohaco")

        st.markdown(
            f"""
            <div class="prod-card">
              {img_html}
              <div class="prod-meta">
                <div class="prod-title">{html.escape(prod.get("name_ja",""))}</div>
                <div class="prod-sub">数量: <b>{qty}</b></div>
                <div class="prod-reason">{html.escape(reason)}</div>
                <div class="prod-links">
                  <a class="badge-link" href="{amz_url}" target="_blank" rel="noopener noreferrer">Amazon <span>{yen(amz_p)}</span></a>
                  <a class="badge-link" href="{rak_url}" target="_blank" rel="noopener noreferrer">Rakuten <span>{yen(rak_p)}</span></a>
                  <a class="badge-link" href="{loh_url}" target="_blank" rel="noopener noreferrer">LOHACO <span>{yen(loh_p)}</span></a>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


# -----------------------------
# Chat helpers (history-safe)
# -----------------------------
def last_assistant_turn() -> Optional[dict]:
    for m in reversed(st.session_state.get("messages", [])):
        if m.get("role") == "assistant":
            return m
    return None


def handle_llm_chat_out(out: dict):
    msg = (out.get("assistant_message_md") or "").strip() or "（すみません、もう一度だけ言い方を変えて教えてください）"
    bundles = out.get("bundles", []) or []
    suggested = out.get("suggested_replies", []) or []

    st.session_state["turn_i"] = int(st.session_state["turn_i"]) + 1
    turn_id = int(st.session_state["turn_i"])

    st.session_state["messages"].append(
        {
            "role": "assistant",
            "content": msg,
            "turn_id": turn_id,
            "bundles": bundles,
            "suggested_replies": suggested,
        }
    )

    bids = [b.get("id") for b in bundles if isinstance(b, dict)]
    if "mid" in bids:
        st.session_state["selected_bundle_id"] = "mid"
    elif bids:
        st.session_state["selected_bundle_id"] = bids[0]


def render_bundles_block(bundles: list[dict], key_prefix: str, interactive: bool):
    if not bundles:
        return

    id_to_bundle = {b["id"]: b for b in bundles if isinstance(b, dict) and b.get("id")}
    options = list(id_to_bundle.keys())
    if not options:
        return

    labels = {}
    for bid, b in id_to_bundle.items():
        total = bundle_est_total_jpy(b.get("bundle_items", []))
        labels[bid] = f"{b.get('label','')}（目安 {yen(total)}）"

    st.markdown("<div class='bundle-shell'>", unsafe_allow_html=True)

    if interactive:
        bsel = st.radio(
            "プラン",
            options=options,
            index=options.index(st.session_state.get("selected_bundle_id", options[0]))
            if st.session_state.get("selected_bundle_id") in options
            else 0,
            format_func=lambda x: labels.get(x, x),
            horizontal=True,
            label_visibility="collapsed",
            key=f"{key_prefix}_bundle_choice",
        )
        st.session_state["selected_bundle_id"] = bsel
        b = id_to_bundle[bsel]

        st.markdown(f"**{b.get('concept','')}**")
        st.caption(b.get("why_this_feels_right", ""))
        render_bundle_cards_with_images(b.get("bundle_items", []))

        st.markdown("---")
        st.caption("※ デモ用：後で本物のカート連携（Saleor等）に置き換えできます。")
        st.button("🛒 カートを確認する（デモ）", key=f"{key_prefix}_mock_cart_btn")

    else:
        for bid in options:
            b = id_to_bundle[bid]
            total = bundle_est_total_jpy(b.get("bundle_items", []))
            title = f"{b.get('label','')}（目安 {yen(total)}）"
            with st.expander(title, expanded=False):
                st.markdown(f"**{b.get('concept','')}**")
                st.caption(b.get("why_this_feels_right", ""))
                render_bundle_cards_with_images(b.get("bundle_items", []))

    st.markdown("</div>", unsafe_allow_html=True)


# -----------------------------
# Actions (NO st.rerun in callbacks)
# -----------------------------
def set_prompt(text: str):
    st.session_state["prompt_draft"] = text


def send_prompt():
    txt = (st.session_state.get("prompt_draft") or "").strip()
    if not txt:
        return
    st.session_state["messages"].append({"role": "user", "content": txt})
    st.session_state["pending_action"] = {"kind": "user_prompt"}
    st.session_state["thinking"] = True
    st.session_state["prompt_draft"] = ""


# -----------------------------
# Welcome
# -----------------------------
WELCOME_MD = (
    "🤗 **Asahiへようこそ！** 今日はどんなシーンですか？\n\n"
    "例）ホームパーティー／予算1.5万円／今週末まで\n"
    "例）オフィス補充（ノンアル多め）／予算2万円／毎月の定期購入を検討"
)
if (not st.session_state["welcome_shown"]) and (len(st.session_state["messages"]) == 0):
    st.session_state["messages"].append({"role": "assistant", "content": WELCOME_MD, "turn_id": 0, "bundles": [], "suggested_replies": []})
    st.session_state["welcome_shown"] = True


# -----------------------------
# If we have a pending LLM action, do it ONCE per run (prevents weird intermediate UI)
# -----------------------------
if st.session_state.get("pending_action"):
    try:
        with st.spinner("プランを作成中…"):
            out = llm_chat(st.session_state["messages"])
        handle_llm_chat_out(out)
    except Exception as e:
        st.session_state["messages"].append({"role": "assistant", "content": f"すみません、エラーが起きました: {e}", "bundles": [], "suggested_replies": []})
    finally:
        st.session_state["pending_action"] = None
        st.session_state["thinking"] = False


# -----------------------------
# Layout (35/65 split)
# -----------------------------
left, right = st.columns([0.35, 0.65], gap="large")

with left:
    # Sticky wrapper (optional)
    st.markdown("<div class='sticky-left'>", unsafe_allow_html=True)
    st.markdown("### Promo")
    render_promo_panel()
    render_left_hub()
    st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown("### Chat")
    st.caption("💡 相談 → 提案 → プラン選択 → 購入リンク（デモ）")

    # Apply prefill before input renders
    prefill = st.session_state.pop("prefill_prompt", "")
    if prefill:
        set_prompt(prefill)

    # Latest assistant = which turn is interactive
    latest_assistant = last_assistant_turn()
    latest_turn_id = latest_assistant.get("turn_id") if latest_assistant else None

    # Render chat history (ONCE) + bundles inline
    for m in st.session_state["messages"]:
        role = m["role"]
        avatar = "🟡" if role == "assistant" else "🧑‍💼"

        with st.chat_message(role, avatar=avatar):
            st.markdown(m["content"])

            if role == "assistant" and m.get("bundles"):
                is_latest = (m.get("turn_id") == latest_turn_id)
                render_bundles_block(
                    bundles=m.get("bundles", []),
                    key_prefix=f"turn_{m.get('turn_id','x')}",
                    interactive=is_latest,
                )

    # Thinking indicator (always bottom)
    if st.session_state.get("thinking"):
        with st.chat_message("assistant", avatar="🟡"):
            st.markdown(
                """
<div class="typing">
  <span>考え中</span>
  <span class="dots">
    <span class="dot"></span><span class="dot"></span><span class="dot"></span>
  </span>
</div>
""",
                unsafe_allow_html=True,
            )

    # Suggested replies from latest assistant
    suggestions = (latest_assistant.get("suggested_replies", []) if latest_assistant else []) or [
        "おすすめの使い方を教えて",
        "ノンアル多めで組んで",
        "予算は1万円くらい",
        "今週末までに欲しい",
        "ビール中心で",
        "ビジネス向けに提案して",
    ]

    st.markdown("<div class='chips-tight'>", unsafe_allow_html=True)
    cols = st.columns(min(6, len(suggestions)))
    for i, s in enumerate(suggestions[:6]):
        with cols[i]:
            if st.button(s, key=f"dyn_chip_{latest_turn_id}_{i}", use_container_width=True):
                st.session_state["prefill_prompt"] = s
    st.markdown("</div>", unsafe_allow_html=True)

    # Input row
    st.markdown("---")
    ip1, ip2 = st.columns([0.85, 0.15])
    ip1.text_input(
        " ",
        key="prompt_draft",
        placeholder="例）ギフトにしたい（相手: 30代男性 / 予算5,000円 / ノンアル希望）",
        label_visibility="collapsed",
    )
    ip2.button("送信", use_container_width=True, on_click=send_prompt)