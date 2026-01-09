import json
import os
import random
import time
import subprocess
import urllib.parse
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI


# -----------------------------
# Config
# -----------------------------
client = OpenAI()
BASE = Path(__file__).resolve().parent
CATALOG_PATH = BASE / "asahi_catalog.json"

SELLER_OFFSETS = {"amazon": 1.00, "rakuten": 1.05, "lohaco": 1.03}
MAX_CART_ITEMS = 5

st.set_page_config(page_title="Asahi Group AIショッパー（デモ）", page_icon="🛒", layout="wide")

# -----------------------------
# Session State
# -----------------------------
if "welcome_shown" not in st.session_state:
    st.session_state["welcome_shown"] = False
if "bundles_cache" not in st.session_state:
    st.session_state["bundles_cache"] = None  # list of bundle options
if "selected_bundle_id" not in st.session_state:
    st.session_state["selected_bundle_id"] = "mid"  # default choice
if "conversation" not in st.session_state:
    st.session_state["conversation"] = []   # what you send to LLM (strings)
if "asked_qids" not in st.session_state:
    st.session_state["asked_qids"] = set()
if "messages" not in st.session_state:
    st.session_state["messages"] = []       # chat transcript for UI [{role, content}]
if "answers" not in st.session_state:
    st.session_state["answers"] = {}
if "llm_out" not in st.session_state:
    st.session_state["llm_out"] = None
if "stage" not in st.session_state:
    st.session_state["stage"] = "idle"      # idle | waiting_answer | plan_ready
if "pending_q" not in st.session_state:
    st.session_state["pending_q"] = None    # the current question dict
if "plan_cache" not in st.session_state:
    st.session_state["plan_cache"] = None
if "pending_action" not in st.session_state:
    st.session_state["pending_action"] = None  # {"kind": "user_prompt"|"answer", ...}
if "thinking" not in st.session_state:
    st.session_state["thinking"] = False
if "bundle_cache" not in st.session_state:
    st.session_state["bundle_cache"] = None
if "cart_started" not in st.session_state:
    st.session_state["cart_started"] = False
if "cart_cooldown_until" not in st.session_state:
    st.session_state["cart_cooldown_until"] = 0.0
if "cart_in_progress" not in st.session_state:
    st.session_state["cart_in_progress"] = False
if "cart_started_at" not in st.session_state:
    st.session_state["cart_started_at"] = 0.0
if "cart_last_error" not in st.session_state:
    st.session_state["cart_last_error"] = None


st.markdown("""
<style>
/* --- Base canvas --- */
.stApp {
  background: #ffffff !important;
  color: #111827 !important;
}

/* Make sure typical text is readable */
html, body, [class*="css"]  {
  color: #111827 !important;
}

/* Main container spacing */
.block-container {
  padding-top: 1.2rem;
}

/* --- Cards --- */
.card {
  border: 1px solid rgba(17, 24, 39, 0.10);
  border-radius: 14px;
  padding: 12px;
  background: #ffffff;
  box-shadow: 0 8px 18px rgba(17, 24, 39, 0.06);
}

/* --- Small / helper text --- */
.small {
  color: rgba(17, 24, 39, 0.70);
  font-size: 13px;
}

/* --- Divider --- */
hr {
  border: none;
  border-top: 1px solid rgba(17, 24, 39, 0.10);
  margin: 10px 0;
}

/* --- Badges --- */
.badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid rgba(17, 24, 39, 0.12);
  margin-right: 6px;
  font-size: 12px;
  background: #F3F4F6;
  color: #111827;
}

.badge-amz { background: rgba(245, 158, 11, 0.18); }   /* amber */
.badge-rak { background: rgba(220, 38, 38, 0.14); }    /* red */
.badge-loh { background: rgba(37, 99, 235, 0.14); }    /* blue */

/* --- Buttons (optional polish) --- */
.stButton > button {
  border-radius: 10px;
  border: 1px solid rgba(17, 24, 39, 0.14);
  background: #ffffff;
  color: #111827;
}

.stButton > button:hover {
  background: #F9FAFB;
}

/* --- Inputs (optional polish) --- */
.stTextInput input, .stNumberInput input, .stDateInput input, textarea {
  background: #ffffff !important;
  color: #111827 !important;
  border: 1px solid rgba(17, 24, 39, 0.14) !important;
  border-radius: 10px !important;
}

/* --- Chat bubbles (helps the “chat feel” look clean on white) --- */
.stChatMessage {
  border-radius: 14px;
}

.stChatMessage [data-testid="stMarkdownContainer"] {
  color: #111827 !important;
}

/* --- Sidebar --- */
section[data-testid="stSidebar"] {
  background: #F6F7F9 !important;
  border-right: 1px solid rgba(17, 24, 39, 0.08);
}
            
# -----------------------------
/* Force light mode globally */
/* Force light mode rendering */
:root { color-scheme: light; }

/* App surfaces */
html, body { background: #ffffff !important; }
.stApp, div[data-testid="stAppViewContainer"], div[data-testid="stMain"], div[data-testid="stMainBlockContainer"]{
  background: #ffffff !important;
  color: #111827 !important;
}

/* --- Top area (the black bar region) --- */
div[data-testid="stDecoration"]{
  background: #ffffff !important;
}
header[data-testid="stHeader"]{
  background: #ffffff !important;
  border-bottom: 1px solid rgba(17,24,39,0.10) !important;
}
div[data-testid="stToolbar"]{
  background: #ffffff !important;
}
header[data-testid="stHeader"] * , div[data-testid="stToolbar"] *{
  color: #111827 !important;
}

/* --- Bottom sticky area (chat input strip) --- */
div[data-testid="stBottom"]{
  background: #ffffff !important;
  border-top: 1px solid rgba(17,24,39,0.10) !important;
}
div[data-testid="stBottomBlockContainer"]{
  background: #ffffff !important;
}

/* Chat input itself */
div[data-testid="stChatInput"]{
  background: #ffffff !important;
}
div[data-testid="stChatInput"] *{
  color: #111827 !important;
}

/* Optional: make the input look nicer on white */
div[data-testid="stChatInput"] textarea{
  background: #ffffff !important;
  color: #111827 !important;
  border: 1px solid rgba(17,24,39,0.18) !important;
}

/* Make the blinking typing cursor visible */
div[data-testid="stChatInput"] textarea,
div[data-testid="stChatInput"] input {
  caret-color: #111827 !important;   /* cursor color */
  color: #111827 !important;        /* typed text */
  background: #ffffff !important;
}

/* If placeholder text is too faint */
div[data-testid="stChatInput"] textarea::placeholder,
div[data-testid="stChatInput"] input::placeholder {
  color: rgba(17,24,39,0.45) !important;
}

/* Sometimes Streamlit wraps with contenteditable */
div[data-testid="stChatInput"] [contenteditable="true"]{
  caret-color: #111827 !important;
  color: #111827 !important;
}

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
  margin-right:8px;
  line-height:1.6;
}
.badge-link:hover{
  box-shadow: 0 2px 10px rgba(0,0,0,0.08);
  transform: translateY(-1px);
}
.badge-amz { background: rgba(255, 153, 0, 0.15); }
.badge-rak { background: rgba(191, 0, 0, 0.10); }
.badge-loh { background: rgba(0, 120, 255, 0.10); }

/* ===== Chat message bubbles ===== */
div[data-testid="stChatMessage"]{
  background: #F9FAFB !important;                 /* light tint so it’s not invisible on white */
  border: 1px solid rgba(17,24,39,0.16) !important;
  border-radius: 16px !important;
  padding: 12px 14px !important;
  margin: 10px 0 !important;
  box-shadow: 0 6px 14px rgba(17,24,39,0.06) !important;
}

/* Avoid inner container overriding the bubble look */
div[data-testid="stChatMessage"] [data-testid="stChatMessageContent"]{
  background: transparent !important;
  padding: 0 !important;
}

/* Make the avatar area look consistent */
div[data-testid="stChatMessageAvatar"]{
  border-radius: 999px !important;
  border: 1px solid rgba(17,24,39,0.10) !important;
  background: #ffffff !important;
}

/* ===== Make interactive widgets feel “boxed” too ===== */
div[data-testid="stSelectbox"] [role="combobox"]{
  border: 1px solid rgba(17,24,39,0.16) !important;
  border-radius: 12px !important;
  background: #ffffff !important;
}

div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input,
div[data-testid="stDateInput"] input,
div[data-testid="stChatInput"] textarea{
  border: 1px solid rgba(17,24,39,0.18) !important;
  border-radius: 12px !important;
  background: #ffffff !important;
}

/* Make the "info" bar more visible (optional) */
div[data-testid="stAlert"]{
  border-radius: 14px !important;
  border: 1px solid rgba(17,24,39,0.12) !important;
}
            
/* --- Assistant typing indicator --- */
.typing {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: rgba(17,24,39,0.65);
  font-size: 13px;
}
.typing .dots {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}
.typing .dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: rgba(17,24,39,0.35);
  animation: blink 1.2s infinite ease-in-out;
}
.typing .dot:nth-child(2) { animation-delay: 0.15s; }
.typing .dot:nth-child(3) { animation-delay: 0.30s; }

@keyframes blink {
  0%, 80%, 100% { opacity: 0.2; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-2px); }
}
            
</style>            

st.columns() + st.link_button()
""", unsafe_allow_html=True)


st.markdown("## Asahi Group AIショッパー（デモ）")
st.caption("Asahi商品を提案 → 外部EC（Amazon / Rakuten / LOHACO）へ送客する想定のデモ")

# -----------------------------
# Data
# -----------------------------
@st.cache_data
def load_catalog():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

CATALOG = load_catalog()
PRODUCTS = CATALOG["products"]
PRODUCT_BY_ID = {p["asahi_id"]: p for p in PRODUCTS}
ASAHI_IDS = list(PRODUCT_BY_ID.keys())

def yen(x: int) -> str:
    return f"¥{x:,}"

def stable_base_price(asahi_id: str) -> int:
    random.seed(asahi_id)
    return random.choice([980, 1180, 1280, 1680, 1980, 2480, 2980, 3580, 3980, 4280, 4980])

def offer_price(product: dict, seller: str) -> int:
    # 1) if catalog has price, use it (best for video demo)
    p = product["offers"].get(seller, {}).get("price_jpy")
    if isinstance(p, int) and p > 0:
        return p

    # 2) else derive from amazon price if present
    base = product["offers"].get("amazon", {}).get("price_jpy")
    if isinstance(base, int) and base > 0:
        return int(base * SELLER_OFFSETS[seller])

    # 3) else fallback mock
    return int(stable_base_price(product["asahi_id"]) * SELLER_OFFSETS[seller])

# Badges for sellers
def pick_seller(prod: dict, seller_preference: str) -> str:
    if seller_preference in ("amazon", "rakuten", "lohaco"):
        return seller_preference
    # any -> prefer amazon if present
    return "amazon"

def bundle_est_total_jpy(bundle_items: list[dict]) -> int:
    total = 0
    for it in bundle_items:
        prod = PRODUCT_BY_ID.get(it["asahi_id"])
        if not prod:
            continue
        seller = pick_seller(prod, it.get("seller_preference", "any"))
        price = offer_price(prod, seller)
        total += price * int(it.get("qty", 1))
    return int(total)

def render_bundle_cards(bundle_items: list[dict]):
    st.markdown("#### 🛍️ バンドル内容（購入リンク）")
    for bi in bundle_items:
        prod = PRODUCT_BY_ID[bi["asahi_id"]]
        qty = int(bi["qty"])
        reason = bi.get("reason", "")

        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(f"**{prod['name_ja']}** × {qty}")
        if reason:
            st.markdown(f"<div class='small'>理由: {reason}</div>", unsafe_allow_html=True)

        amz_p = offer_price(prod, "amazon")
        rak_p = offer_price(prod, "rakuten")
        loh_p = offer_price(prod, "lohaco")

        amz_url = prod["offers"]["amazon"]["url"]
        rak_url = prod["offers"]["rakuten"]["url"]
        loh_url = prod["offers"]["lohaco"]["url"]

        st.markdown(
            f"""
            <div style="margin-top:6px">
              <a class="badge-link badge-amz" href="{amz_url}" target="_blank" rel="noopener noreferrer">
                Amazon <span>{yen(amz_p)}</span>
              </a>
              <a class="badge-link badge-rak" href="{rak_url}" target="_blank" rel="noopener noreferrer">
                Rakuten <span>{yen(rak_p)}</span>
              </a>
              <a class="badge-link badge-loh" href="{loh_url}" target="_blank" rel="noopener noreferrer">
                LOHACO <span>{yen(loh_p)}</span>
              </a>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

def handle_llm_out(out: dict):
    st.session_state["llm_out"] = out

    plan = out.get("plan", {}) or {}
    bundles = plan.get("bundles", []) or []

    # Only consider questions we still need answers for
    qs = [q for q in out.get("questions", []) if q["id"] not in st.session_state["answers"]]

    # Pick the next not-yet-asked question (prevents repeats)
    next_q = None
    for q in qs:
        if q["id"] not in st.session_state["asked_qids"]:
            next_q = q
            break

    if next_q:
        st.session_state["pending_q"] = next_q
        st.session_state["asked_qids"].add(next_q["id"])
        st.session_state["stage"] = "waiting_answer"
        st.session_state["messages"].append({"role": "assistant", "content": next_q["question"]})
        return

    # Plan ready
    st.session_state["pending_q"] = None
    st.session_state["stage"] = "plan_ready"
    st.session_state["plan_cache"] = plan
    st.session_state["bundles_cache"] = bundles

    # Default selected bundle if not set / invalid
    valid_ids = {b.get("id") for b in bundles if isinstance(b, dict)}
    if st.session_state.get("selected_bundle_id") not in valid_ids:
        st.session_state["selected_bundle_id"] = "mid" if "mid" in valid_ids else (next(iter(valid_ids)) if valid_ids else "mid")

    if plan and bundles:
        st.session_state["messages"].append({
            "role": "assistant",
            "content": render_plan_bubble(plan, bundles),
        })
    else:
        st.session_state["messages"].append({
            "role": "assistant",
            "content": "すみません、条件をもとにプランを作れませんでした。もう一度だけ別の言い方で教えてください。",
        })

def build_amazon_cart_add_url(plan_items: list[dict], max_items: int = MAX_CART_ITEMS) -> str | None:
    base = "https://www.amazon.co.jp/gp/aws/cart/add.html"
    params = {}
    i = 1
    for it in plan_items:
        pid = it["asahi_id"]
        qty = int(it.get("qty", 1))
        prod = PRODUCT_BY_ID.get(pid)
        if not prod:
            continue
        asin = prod["offers"]["amazon"].get("asin")
        if not asin:
            continue
        params[f"ASIN.{i}"] = asin
        params[f"Quantity.{i}"] = str(qty)
        i += 1
        if i > max_items:
            break
    if i == 1:
        return None
    return base + "?" + urllib.parse.urlencode(params)

def render_typing_bubble(text="考え中..."):
    with st.chat_message("assistant"):
        st.markdown(
            f"""
            <div class="typing">
              <span>{text}</span>
              <span class="dots">
                <span class="dot"></span><span class="dot"></span><span class="dot"></span>
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
def render_plan_bubble(plan: dict, bundles: list[dict]) -> str:
    title = plan.get("title", "")
    assumptions = plan.get("assumptions", [])
    note = plan.get("note", "")

    lines = [f"### ✅ {title}"]
    if assumptions:
        lines.append("**AIが前提としていること**")
        lines += [f"- {a}" for a in assumptions]
    if note:
        lines.append(f"\n_{note}_")

    lines.append("\n**おすすめの3プラン（価格帯別）**")
    for b in bundles:
        bid = b.get("id", "")
        label = b.get("label", "")
        concept = b.get("concept", "")
        emoji = {"low": "🟢", "mid": "🟡", "high": "🟣"}.get(bid, "✅")
        lines.append(f"- {emoji} **{label}**（{bid}）: {concept}")

    lines.append("\n下の選択肢から1つ選ぶと、購入リンク（Amazon/Rakuten/LOHACO）を表示します。")
    return "\n".join(lines)

# compact catalog grounding (small list)
CATALOG_LINES = []
for p in PRODUCTS:
    CATALOG_LINES.append(f'{p["asahi_id"]}: {p["name_ja"]} / tags={",".join(p.get("tags", []))}')
CATALOG_GROUNDING = "\n".join(CATALOG_LINES)

# -----------------------------
# LLM Schema (strict)
# -----------------------------
QUESTION_ID_ENUM = ["budget_jpy", "delivery_by", "alcohol_ratio", "days_count", "focus"]  # keep simple

BUNDLE_ID_ENUM = ["low", "mid", "high"]

PLAN_SCHEMA = {
  "type": "object",
  "properties": {
    "questions": {
      "type": "array",
      "maxItems": 2,
      "items": {
        "type": "object",
        "properties": {
          "id": {"type": "string", "enum": QUESTION_ID_ENUM},
          "question": {"type": "string", "maxLength": 140},
          "type": {"type": "string", "enum": ["choice", "number", "date"]},
          "options": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 8},
          "default": {"type": ["string", "integer", "null"]}
        },
        "required": ["id", "question", "type", "options", "default"],
        "additionalProperties": False
      }
    },
    "plan": {
      "type": "object",
      "properties": {
        "title": {"type": "string", "maxLength": 80},
        "assumptions": {"type": "array", "items": {"type": "string", "maxLength": 160}, "maxItems": 10},
        "bundles": {
          "type": "array",
          "minItems": 3,
          "maxItems": 3,
          "items": {
            "type": "object",
            "properties": {
              "id": {"type": "string", "enum": BUNDLE_ID_ENUM},
              "label": {"type": "string", "maxLength": 40},
              "concept": {"type": "string", "maxLength": 120},
              "bundle_items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 6,
                "items": {
                  "type": "object",
                  "properties": {
                    "asahi_id": {"type": "string", "enum": ASAHI_IDS},
                    "qty": {"type": "integer", "minimum": 1, "maximum": 20},
                    "seller_preference": {"type": "string", "enum": ["amazon", "rakuten", "lohaco", "any"]},
                    "reason": {"type": "string", "maxLength": 120}
                  },
                  "required": ["asahi_id", "qty", "seller_preference", "reason"],
                  "additionalProperties": False
                }
              }
            },
            "required": ["id", "label", "concept", "bundle_items"],
            "additionalProperties": False
          }
        },
        "note": {"type": "string", "maxLength": 220}
      },
      "required": ["title", "assumptions", "bundles", "note"],
      "additionalProperties": False
    }
  },
  "required": ["questions", "plan"],
  "additionalProperties": False
}

SYSTEM_PROMPT = f"""
あなたはAsahi Groupの“商品提案”アシスタント。Asahiは自社ECではなく、購入は外部EC（Amazon/Rakuten/LOHACO）に送客する想定。

目的：手動検索より速く、買い忘れなく、数量まで具体化して提案する。

- 質問は最大2つ。結果が大きく変わる時だけ質問する。
- 質問しない場合は妥当なデフォルトで進め、assumptionsに明記する。
- bundle_items は必ず1つ以上。数量 qty も必須。
- 選べる商品は asahi_id の一覧のみ。それ以外は絶対に出さない。
- party の場合は「人数→本数の計算式」を assumptions に1行含める（例：30人×2本=60本）。
- お酒が含まれる場合、note に「飲酒は20歳以上」を一言入れる。
- 最終出力は必ず bundles を3つ（low/mid/high）返す。
- low はコスパ重視、mid はバランス、high はプレミアム（少し良い/多様性）にする。
- 3つの bundles は、少なくとも1つ以上の商品 or 数量が違うようにする。
- 質問は最大2つ。価格帯（low/mid/high）は質問せず、ユーザーがUIで選べる前提で bundles を作る。
"""

def llm_make_plan(conversation: list[str], answers: dict):
    payload = {
        "conversation": conversation,
        "answers": answers
    }
    resp = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06"),
        input=[
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "system", "content": "利用可能な商品一覧（asahi_id）:\n" + CATALOG_GROUNDING},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
        ],
        text={"format": {"type": "json_schema", "name": "asahi_plan", "schema": PLAN_SCHEMA, "strict": True}},
        temperature=0.2,
    )
    return json.loads(resp.output_text)


# -----------------------------
# Sidebar (examples + debug)
# -----------------------------
with st.sidebar:
    st.markdown("### 🎬 例（ワンクリック）")
    if st.button("例：30人パーティー"):
        st.session_state["conversation"] = ["30人でパーティーをします。ビールなどはOK。予算と到着日も考慮して提案して。"]
        st.session_state["answers"] = {}
        st.session_state["llm_out"] = None
        st.rerun()

    if st.button("例：アマノフーズのストック"):
        st.session_state["conversation"] = ["アマノフーズで平日ランチのストックをしたい。買い忘れない組み合わせで提案して。"]
        st.session_state["answers"] = {}
        st.session_state["llm_out"] = None
        st.rerun()

    st.divider()
    if st.checkbox("DEBUG: LLM JSONを表示"):
        st.json(st.session_state.get("llm_out"))

# -----------------------------
# Chat Input
# -----------------------------
# initial bubble 
WELCOME_BUBBLE = """
**Asahiの世界へようこそ!!!**  
今日はどのようなお手伝いをしましょうか？

<div style="margin-top:10px, "margin-bottom:10px;">
例：6人のパーティー。ビール中心。予算3万円。来週までに必要。  
&nbsp;
例：アマノフーズで平日ランチのストックをしたい。  
</div>
&nbsp;
"""

if (not st.session_state["welcome_shown"]) and (len(st.session_state["messages"]) == 0):
    st.session_state["messages"].append({"role": "assistant", "content": WELCOME_BUBBLE})
    st.session_state["welcome_shown"] = True
# Render chat history
for m in st.session_state["messages"]:
    with st.chat_message(m["role"]):
        st.markdown(m["content"], unsafe_allow_html=True)

# Show typing indicator while we compute
if st.session_state.get("thinking"):
    render_typing_bubble("考え中...")

# Single place where LLM is called
if st.session_state.get("pending_action"):
    out = llm_make_plan(st.session_state["conversation"], st.session_state["answers"])

    handle_llm_out(out)

    st.session_state["pending_action"] = None
    st.session_state["thinking"] = False
    st.rerun()


prompt = st.chat_input("例：30人のパーティー。予算10,000円。ノンアルも混ぜたい。")
if prompt:
    st.session_state["messages"].append({"role": "user", "content": prompt})
    st.session_state["conversation"].append(prompt)

    st.session_state["pending_action"] = {"kind": "user_prompt"}
    st.session_state["thinking"] = True
    st.rerun()

# Put “bundle cards + clickable badges” inside the assistant plan turn
if st.session_state["stage"] == "plan_ready" and st.session_state.get("bundles_cache"):
    bundles = st.session_state["bundles_cache"]

    # Build radio labels with estimated totals
    id_to_bundle = {b["id"]: b for b in bundles}
    options = []
    labels = {}
    for b in bundles:
        bid = b["id"]
        total = bundle_est_total_jpy(b["bundle_items"])
        label = f"{b['label']}（目安 合計: {yen(total)}）"
        options.append(bid)
        labels[bid] = label

    with st.chat_message("assistant"):
        st.markdown("どの価格帯で用意しますか？（あとから切り替え可能）")

        chosen = st.radio(
            "プランを選択",
            options=options,
            index=options.index(st.session_state.get("selected_bundle_id", "mid")) if st.session_state.get("selected_bundle_id", "mid") in options else 0,
            format_func=lambda x: labels.get(x, x),
        )
        st.session_state["selected_bundle_id"] = chosen

        selected_bundle = id_to_bundle[chosen]
        bundle_items = selected_bundle["bundle_items"]

        # Show EC cards + badges (back!)
        render_bundle_cards(bundle_items)

        st.markdown("---")
        st.markdown("よろしければ、Amazon カートを今すぐ準備できます。")

        now = time.time()
        cooldown_until = float(st.session_state.get("cart_cooldown_until", 0.0))
        in_cooldown = now < cooldown_until
        in_progress = bool(st.session_state.get("cart_in_progress", False))

        clicked = st.button(
            "🛒 Amazonカートを準備する",
            type="primary",
            disabled=(in_cooldown or in_progress),
        )

        if clicked:
            st.session_state["cart_last_error"] = None
            st.session_state["cart_in_progress"] = True
            st.session_state["cart_started_at"] = time.time()
            st.session_state["cart_cooldown_until"] = time.time() + 60

            from collections import defaultdict

            # build ASIN+qty list from selected bundle
            qty_by_asin = defaultdict(int)

            for it in bundle_items[:MAX_CART_ITEMS]:
                prod = PRODUCT_BY_ID.get(it["asahi_id"])
                if not prod:
                    continue
                asin = prod["offers"]["amazon"].get("asin")
                if not asin:
                    continue
                qty_by_asin[asin] += int(it.get("qty", 1))

            items = [{"asin": asin, "qty": qty} for asin, qty in qty_by_asin.items()]

            try:
                cmd = [
                    "python",
                    str(BASE / "amazon_cart_bot.py"),
                    "--items", json.dumps(items, ensure_ascii=False),
                    "--profile", str(BASE / "pw_amazon_profile"),
                    "--keep_open",
                ]
                log_path = BASE / "cart_bot.log"
                with open(log_path, "a", encoding="utf-8") as f:
                    subprocess.Popen(cmd, stdout=f, stderr=f)
                st.session_state["cart_started"] = True
            except Exception as e:
                st.session_state["cart_last_error"] = str(e)
                st.session_state["cart_in_progress"] = False

        if st.session_state.get("cart_last_error"):
            st.error("カート準備の起動に失敗しました。cart_bot.log を確認してください。")
            st.code(st.session_state["cart_last_error"])

        if st.session_state.get("cart_in_progress"):
            st.info("準備を開始しました。数秒だけこの画面のままでお待ちください…")
            prog = st.progress(0)
            for i in range(30):
                time.sleep(0.1)
                prog.progress((i + 1) / 30)
            st.session_state["cart_in_progress"] = False
            st.success("✅ そろそろ Chrome ウィンドウに切り替えて、Amazonカートをご確認ください。")
            st.caption("（環境によっては表示にもう少し時間がかかる場合があります）")

        if in_cooldown and not st.session_state.get("cart_in_progress"):
            remaining = int(max(0, cooldown_until - time.time()))
            st.caption(f"※ 連打防止のため、あと {remaining} 秒は再実行できません。")

if st.session_state["stage"] == "waiting_answer" and st.session_state["pending_q"]:
    q = st.session_state["pending_q"]

    with st.chat_message("assistant"):
        qid = q["id"]
        qtype = q["type"]
        opts = q.get("options", [])
        default = q.get("default")

        # Render the answer widget inside the chat bubble
        if qtype == "choice":
            if default is None and opts:
                default = opts[0]
            val = st.selectbox(
                "お選びください",
                options=opts,
                index=(opts.index(default) if default in opts else 0),
                key=f"active_q_{qid}",
            )
        elif qtype == "number":
            dv = int(default) if isinstance(default, int) else 0
            val = st.number_input(
                "数値を入力してください",
                min_value=0,
                value=dv,
                step=100,
                key=f"active_q_{qid}",
            )
            val = int(val)
        else:  # date
            today = datetime.now().date()
            picked = st.date_input("日にちを指定してください", value=today, key=f"active_q_{qid}")
            val = str(picked)

        # # Optional quick-replies (chips) for choice
        # if qtype == "choice" and opts:
        #     st.markdown("<div class='small'></div>", unsafe_allow_html=True)
        #     cols = st.columns(min(4, len(opts)))
        #     for i, opt in enumerate(opts[:4]):
        #         if cols[i].button(opt, key=f"chip_{qid}_{i}"):
        #             st.session_state[f"active_q_{qid}"] = opt
        #             st.rerun()

        if st.button("送信", type="primary", key=f"submit_{qid}"):
            st.session_state["answers"][qid] = val
            st.session_state["messages"].append({"role": "user", "content": str(val)})
            st.session_state["conversation"].append(f"{q['question']} → {val}")

            st.session_state["pending_action"] = {"kind": "answer", "qid": qid}
            st.session_state["thinking"] = True
            st.rerun()
