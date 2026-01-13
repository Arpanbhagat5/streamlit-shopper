# =============================
# DROP-IN REPLACEMENT v4 (LLM + UI) — COMPLETE / SINGLE FILE
# =============================
# Keeps:
# - asahi_catalog.json loading
# - OpenAI Responses API w/ JSON schema output
# - Bundles + product cards + seller price badges + optional og:image fetch
# - Promo panel + (optional) auto rotate
# - Left hub: 人気の使い方 + クイックスタート (personal/business)
# Fixes:
# - NO duplicated chat rendering
# - NO st.rerun() inside callbacks (removes "no-op" toast)
# - NO blank screen during LLM call (renders UI first, then calls LLM)
# - Auto-rotate paused while "thinking" (prevents duplicate panels)
# - Bundles not forced every response; clarifies on intent switches (gift etc.)
#
# Requirements:
#   pip install openai streamlit requests
# Optional for auto-rotate:
#   pip install streamlit-autorefresh

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
# CSS (LIGHT + button overrides + layout)
# -----------------------------
st.markdown(
    """
<style>
:root { color-scheme: light; }
html, body { background:#ffffff !important; color:#111827 !important; }
.stApp, div[data-testid="stAppViewContainer"], div[data-testid="stMain"], div[data-testid="stMainBlockContainer"]{
  background:#ffffff !important; color:#111827 !important;
}
header[data-testid="stHeader"], div[data-testid="stToolbar"], div[data-testid="stDecoration"]{
  background:#ffffff !important; color:#111827 !important;
  border-bottom:1px solid rgba(17,24,39,0.10) !important;
}
div[data-testid="stBottom"], div[data-testid="stBottomBlockContainer"]{
  background:#ffffff !important;
  border-top:1px solid rgba(17,24,39,0.10) !important;
}
[data-testid="stMarkdownContainer"], .stCaption, .stCaption p { color:#111827 !important; }

/* Text input */
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

/* HARD button overrides */
div[data-testid="stButton"] button,
div[data-testid^="baseButton-"] button,
button[kind],
button[kind="primary"],
button[kind="secondary"],
button[kind="tertiary"],
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
button[kind] * , button * { color: inherit !important; fill: currentColor !important; }
div[data-testid="stButton"] button:hover,
div[data-testid^="baseButton-"] button:hover,
button:hover{
  background:#F9FAFB !important;
  border-color: rgba(17,24,39,0.28) !important;
  transform: translateY(-1px);
}

/* Promo arrows: small square */
.promo-nav div[data-testid="stButton"] button,
.promo-nav div[data-testid^="baseButton-"] button,
.promo-nav button{
  border-radius: 12px !important;
  padding: 8px 10px !important;
}

/* Chips: tighter */
.chips-tight div[data-testid="stButton"] button{
  padding: 8px 12px !important;
  font-weight: 700 !important;
  white-space: nowrap !important;
}

/* Cards */
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
  display:inline-flex; align-items:center; gap:6px;
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

/* Promo */
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

/* Left Hub */
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
  font-size:12px; padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid rgba(17,24,39,0.18);
  background: #F9FAFB;
  color: rgba(17,24,39,0.75);
}

/* Typing animation */
.typing { display:inline-flex; align-items:center; gap:8px; font-size:13px; color: rgba(17,24,39,0.65); }
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
</style>
""",
    unsafe_allow_html=True,
)


st.markdown(
    """
<style>
/* Sticky left wrapper */
.sticky-left{
  position: sticky;
  top: 64px;
  max-height: calc(100vh - 80px); /* use max-height (safer than fixed height) */
  overflow-y: auto;
  align-self: flex-start;
  z-index: 5;
  background: #ffffff;
  width: 100%;
}

/* IMPORTANT: only the row that contains .sticky-left should top-align */
div[data-testid="stHorizontalBlock"]:has(.sticky-left){
  align-items: flex-start !important;
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


ss_init("messages", [])  # each msg: {role, content, turn_id?, bundles?, suggested_replies?}
ss_init("welcome_shown", False)
ss_init("thinking", False)
ss_init("pending_action", None)
ss_init("prefill_prompt", "")
ss_init("selected_bundle_id", "mid")
ss_init("promo_i", 0)
ss_init("promo_auto", True)
ss_init("turn_i", 0)


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
# Promo panel
# -----------------------------
PROMOS = [
    {"kicker": "ASAHI", "title": "Free Delivery", "copy": "On orders over ¥5,000. Get it delivered fresh.", "cta": "Order Now", "foot": "Demo promo panel (static)."},
    {"kicker": "SUPER DRY", "title": "Crisp & Clean", "copy": "A sharp finish that pairs well with food.", "cta": "Explore", "foot": "Later: fetch from real campaign feed."},
    {"kicker": "NON-ALC", "title": "0.00% Options", "copy": "Great taste without alcohol—perfect for mixed bundles.", "cta": "See lineup", "foot": "Demo promo panel (static)."},
]


def queue_user_message(text: str):
    text = (text or "").strip()
    if not text:
        return
    st.session_state["messages"].append({"role": "user", "content": text})
    st.session_state["pending_action"] = {"kind": "user_prompt"}
    st.session_state["thinking"] = True


def render_promo_panel():
    # Pause autorefresh while thinking/pending (prevents duplicate panels / blank moments)
    is_busy = bool(st.session_state.get("thinking")) or bool(st.session_state.get("pending_action"))

    c_auto, c_info = st.columns([0.55, 0.45])
    with c_auto:
        st.session_state["promo_auto"] = st.toggle("オートプレイ", value=bool(st.session_state["promo_auto"]))
    with c_info:
        if st.session_state["promo_auto"] and st_autorefresh is None:
            st.caption("※ auto-rotate: `pip install streamlit-autorefresh`")

    if (not is_busy) and st.session_state["promo_auto"] and st_autorefresh is not None:
        st_autorefresh(interval=3500, key="promo_refresh_v4")
        st.session_state["promo_i"] = (int(st.session_state["promo_i"]) + 1) % len(PROMOS)

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
    if c1.button("◀"):
        st.session_state["promo_i"] = (int(st.session_state["promo_i"]) - 1) % len(PROMOS)
    if c2.button("▶"):
        st.session_state["promo_i"] = (int(st.session_state["promo_i"]) + 1) % len(PROMOS)
    st.markdown("</div>", unsafe_allow_html=True)


def render_left_hub():
    st.markdown("<div class='hub-card'>", unsafe_allow_html=True)
    st.markdown("<div class='hub-title'>人気の使い方</div>", unsafe_allow_html=True)

    for i, (name, cnt, prompt) in enumerate(POPULAR_USES):
        c1, c2 = st.columns([0.78, 0.22])
        with c1:
            if st.button(name, key=f"pop_use_{i}", use_container_width=True):
                queue_user_message(prompt)
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
                    queue_user_message(prompt)

    with tab2:
        cols = st.columns(2)
        for i, (label, prompt) in enumerate(QUICKSTART_BUSINESS):
            with cols[i % 2]:
                if st.button(label, key=f"qs_b_{i}", use_container_width=True):
                    queue_user_message(prompt)

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
丁寧でフレンドリー。ユーザーの用途（パーティー/来客/BBQ/ギフト/日常ストック/業務用途など）に合わせて相談に乗る。

会話方針:
- 原則: 1ターンで「提案 +（必要なら）確認1つ」まで。質問攻めは禁止。
- ユーザーが条件変更を示したが、具体値が無い場合は確認を1つだけして bundles=[]。
- 条件が揃ったら bundles を 1〜3件返す（low/mid/high できれば）。
- 価格はUI側で算出するため、文中で「最安」など断定はしない（“目安”“比較できます” はOK）。

重要:
- 会話はフォームではない。質問攻めにしない。
- ただし「用途が切り替わった」(例: パーティー→ギフト) など、意図が変わった可能性がある時は、
  まず “確認の一問” を添えてから提案を出す（断定しない）。
- bundles は **条件が揃っている時だけ** 出すこと。
  例: ギフトなら「誰に/予算/好み(ビールorノンアル等)」が最低1-2個分からないと bundle を作らない。
  その場合 bundles=[] にして、assistant_message_md で短く確認して suggested_replies で選択肢を出す。
- 商品は asahi_id の一覧のみ。架空商品は禁止。
- 酒類が含まれる場合は最後に一言だけ「飲酒は20歳以上」。




出力:
- assistant_message_md: 6〜10行程度、読みやすく。bundle の商品羅列はしない。
- suggested_replies: 押しやすい短文（最大6）
- bundles: 0〜3（可能なら low/mid/high）。条件が薄い時は 0 でもOK。
- 今日の日付は {TODAY}（季節イベントが近ければ一言だけ雰囲気を添える）
"""
# 「条件変更」系の発話（例: 予算を増やす/減らす、ノンアル多めにする、人数が変わる、納期が変わる、ギフトに切り替える）では、
# いきなり新しい bundles を出さず、まずは短く確認してから次ターンで bundles を出す。

# ただし、ユーザーが明確な数値を同じ発話で指定している場合（例:「予算2万円にして」）は、その場で bundles を更新してOK。

def llm_chat(messages: list[dict]) -> dict:
    # Send only {role, content}
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


def pick_seller(prod: dict, pref: str) -> str:
    return pref if pref in ("amazon", "rakuten", "lohaco") else "amazon"


def product_image_url(prod: dict, seller: str) -> Optional[str]:
    if prod.get("image_url"):
        return prod["image_url"]
    img = prod.get("offers", {}).get(seller, {}).get("image_url")
    if img:
        return img
    url = prod.get("offers", {}).get(seller, {}).get("url")
    return fetch_og_image(url) if url else None


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
        seller = pick_seller(prod, it.get("seller_preference", "any"))
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
        seller = pick_seller(prod, bi.get("seller_preference", "any"))

        offers = prod.get("offers", {})
        amz_url = offers.get("amazon", {}).get("url", "#")
        rak_url = offers.get("rakuten", {}).get("url", "#")
        loh_url = offers.get("lohaco", {}).get("url", "#")

        img_url = product_image_url(prod, seller)

        amz_p = offer_price(prod, "amazon")
        rak_p = offer_price(prod, "rakuten")
        loh_p = offer_price(prod, "lohaco")

        img_html = f"<img class='prod-img' src='{img_url}' />" if img_url else "<div class='prod-img'></div>"

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
# Chat state handlers
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

    st.session_state["turn_i"] = int(st.session_state.get("turn_i", 0)) + 1
    turn_id = st.session_state["turn_i"]

    st.session_state["messages"].append(
        {"role": "assistant", "content": msg, "turn_id": turn_id, "bundles": bundles, "suggested_replies": suggested}
    )

    # only affects latest interactive block
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
# Layout (35/65) + scroll containers A
# -----------------------------
left, right = st.columns([0.35, 0.65], gap="large")

with left:
    st.markdown("<div class='sticky-left'>", unsafe_allow_html=True)

    st.markdown("### おすすめ商品")
    render_promo_panel()
    render_left_hub()
    st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown("### Asahi コンシェルジュ")
    st.caption("💡 相談 → 提案 → プラン選択 → 購入リンク（デモ）")

    latest_assistant = last_assistant_turn()
    latest_turn_id = latest_assistant.get("turn_id") if latest_assistant else None

    # render chat history
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

    # typing indicator
    if st.session_state.get("thinking"):
        with st.chat_message("assistant", avatar="🟡"):
            st.markdown("""<div class="typing">
  <span>考え中</span>
  <span class="dots"><span class="dot"></span><span class="dot"></span><span class="dot"></span></span>
</div>""", unsafe_allow_html=True)

    # chips (now submits)
    suggestions = (latest_assistant.get("suggested_replies") if latest_assistant else None) or []
    if not suggestions:
        suggestions = [
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
                queue_user_message(s)
    st.markdown("</div>", unsafe_allow_html=True)

    # chat input (stable)
    user_txt = st.chat_input("何かお手伝いできることはありますか？")
    if user_txt:
        queue_user_message(user_txt)

    # LLM call AFTER UI rendered
    if st.session_state.get("pending_action"):
        out = llm_chat(st.session_state["messages"])
        handle_llm_chat_out(out)
        st.session_state["pending_action"] = None
        st.session_state["thinking"] = False
        st.rerun()