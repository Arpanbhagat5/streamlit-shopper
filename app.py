import json
import os
import random
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

st.markdown("""
<style>
.stApp { background: light blue; }
.card { border: 1px solid rgba(0,0,0,0.08); border-radius: 14px; padding: 12px; background: grey; }
.badge { display:inline-block; padding:3px 8px; border-radius:999px; border:1px solid rgba(0,0,0,0.12); margin-right:6px; font-size:12px;}
.badge-amz { background: rgba(255, 153, 0, 0.15); }
.badge-rak { background: rgba(191, 0, 0, 0.10); }
.badge-loh { background: rgba(0, 120, 255, 0.10); }
.small { color: rgba(0,0,0,0.65); font-size: 13px; }
hr { border: none; border-top: 1px solid rgba(0,0,0,0.08); margin: 10px 0; }
</style>
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

# compact catalog grounding (small list)
CATALOG_LINES = []
for p in PRODUCTS:
    CATALOG_LINES.append(f'{p["asahi_id"]}: {p["name_ja"]} / tags={",".join(p.get("tags", []))}')
CATALOG_GROUNDING = "\n".join(CATALOG_LINES)

# -----------------------------
# LLM Schema (strict)
# -----------------------------
QUESTION_ID_ENUM = ["budget_jpy", "delivery_by", "alcohol_ratio", "days_count", "focus"]  # keep simple

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
          "default": {"type": ["string","integer","null"]}
        },
        "required": ["id","question","type","options","default"],
        "additionalProperties": False
      }
    },
    "plan": {
      "type": "object",
      "properties": {
        "title": {"type": "string", "maxLength": 80},
        "assumptions": {"type": "array", "items": {"type": "string", "maxLength": 160}, "maxItems": 10},
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
            "required": ["asahi_id","qty","seller_preference","reason"],
            "additionalProperties": False
          }
        },
        "note": {"type": "string", "maxLength": 220}
      },
      "required": ["title","assumptions","bundle_items","note"],
      "additionalProperties": False
    }
  },
  "required": ["questions","plan"],
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
# Session State
# -----------------------------
if "conversation" not in st.session_state:
    st.session_state["conversation"] = []
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "answers" not in st.session_state:
    st.session_state["answers"] = {}
if "llm_out" not in st.session_state:
    st.session_state["llm_out"] = None
if "confirmed" not in st.session_state:
    st.session_state["confirmed"] = False

# -----------------------------
# Sidebar (examples + debug)
# -----------------------------
with st.sidebar:
    st.markdown("### 🎬 例（ワンクリック）")
    if st.button("例：30人パーティー"):
        st.session_state["conversation"] = ["30人でパーティーをします。ビールなどはOK。予算と到着日も考慮して提案して。"]
        st.session_state["answers"] = {}
        st.session_state["llm_out"] = None
        st.session_state["confirmed"] = False
        st.rerun()

    if st.button("例：アマノフーズのストック"):
        st.session_state["conversation"] = ["アマノフーズで平日ランチのストックをしたい。買い忘れない組み合わせで提案して。"]
        st.session_state["answers"] = {}
        st.session_state["llm_out"] = None
        st.session_state["confirmed"] = False
        st.rerun()

    st.divider()
    if st.checkbox("DEBUG: LLM JSONを表示"):
        st.json(st.session_state.get("llm_out"))

# -----------------------------
# Chat Input
# -----------------------------
st.markdown("### 💬 Chat")

# Render chat history
for m in st.session_state["messages"]:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# Input
prompt = st.chat_input("Tell me what you want (e.g., party for 30, budget 10,000 yen, include non-alcohol options)")
if prompt:
    st.session_state["messages"].append({"role": "user", "content": prompt})
    st.session_state["conversation"].append(prompt)
    st.session_state["confirmed"] = False

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            st.session_state["llm_out"] = llm_make_plan(
                st.session_state["conversation"],
                st.session_state["answers"],
            )

    st.rerun()

# -----------------------------
# If no LLM output yet, stop here
# -----------------------------
out = st.session_state.get("llm_out")
if not out:
    st.info("Type your request above to start. I’ll ask up to 2 quick questions, then build a bundle.")
    st.stop()

questions = out.get("questions", [])
plan = out.get("plan", {})
# One-time: append assistant summary into chat if not already appended
if "last_plan_hash" not in st.session_state:
    st.session_state["last_plan_hash"] = None

plan_hash = json.dumps(plan, ensure_ascii=False)
if plan_hash != st.session_state["last_plan_hash"]:
    st.session_state["last_plan_hash"] = plan_hash
    summary = f"**{plan.get('title','')}**\n\n" + "\n".join([f"- {a}" for a in plan.get("assumptions", [])])
    if plan.get("note"):
        summary += f"\n\n_{plan['note']}_"
    st.session_state["messages"].append({"role": "assistant", "content": summary})
    st.rerun()

# -----------------------------
# Questions UI (0–2)
# -----------------------------
if questions and not st.session_state["confirmed"]:
    st.markdown("### ❓ 追加で確認（最大2つ）")
    new_answers = dict(st.session_state["answers"])

    for q in questions:
        qid = q["id"]
        label = q["question"]
        qtype = q["type"]
        opts = q.get("options", [])
        default = q.get("default")

        if qtype == "choice":
            if default is None and opts:
                default = opts[0]
            val = st.selectbox(label, options=opts, index=(opts.index(default) if default in opts else 0), key=f"q_{qid}")
            new_answers[qid] = val

        elif qtype == "number":
            dv = int(default) if isinstance(default, int) else 0
            val = st.number_input(label, min_value=0, value=dv, step=100, key=f"q_{qid}")
            new_answers[qid] = int(val)

        elif qtype == "date":
            # store as ISO string
            today = datetime.now().date()
            val = st.date_input(label, value=today, key=f"q_{qid}")
            new_answers[qid] = str(val)

    if st.button("この条件で提案を更新", type="primary"):
        st.session_state["answers"] = new_answers
        st.session_state["llm_out"] = llm_make_plan(st.session_state["conversation"], st.session_state["answers"])
        st.rerun()

# -----------------------------
# Plan + Bundle Cards
# -----------------------------
st.markdown("### 🧠 提案プラン")
st.markdown(f"<div class='card'><b>{plan.get('title','')}</b><hr>", unsafe_allow_html=True)
for a in plan.get("assumptions", []):
    st.markdown(f"- {a}")
st.markdown(f"<div class='small'>{plan.get('note','')}</div></div>", unsafe_allow_html=True)

bundle_items = plan.get("bundle_items", [])

st.markdown("### 🛍️ バンドル（外部ECへ送客）")
for bi in bundle_items:
    prod = PRODUCT_BY_ID[bi["asahi_id"]]
    qty = int(bi["qty"])
    reason = bi.get("reason", "")
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown(f"**{prod['name_ja']}**  × {qty}")
    if reason:
        st.markdown(f"<div class='small'>理由: {reason}</div>", unsafe_allow_html=True)

    # seller offers with mocked prices
    amz_p = offer_price(prod, "amazon")
    rak_p = offer_price(prod, "rakuten")
    loh_p = offer_price(prod, "lohaco")

    amz = prod["offers"]["amazon"]["url"]
    rak = prod["offers"]["rakuten"]["url"]
    loh = prod["offers"]["lohaco"]["url"]

    st.markdown(
        f"<span class='badge badge-amz'>Amazon</span> {yen(amz_p)}  ｜ "
        f"<span class='badge badge-rak'>Rakuten</span> {yen(rak_p)}  ｜ "
        f"<span class='badge badge-loh'>LOHACO</span> {yen(loh_p)}",
        unsafe_allow_html=True
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.link_button("Amazonで見る", amz)
    with c2:
        st.link_button("Rakutenで見る", rak)
    with c3:
        st.link_button("LOHACOで見る", loh)

    st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------
# Confirm + Amazon Cart Add (demo)
# -----------------------------
st.markdown("---")
col1, col2 = st.columns([0.5, 0.5])
with col1:
    if st.button("✅ このプランで確定（デモ）", type="primary"):
        st.session_state["confirmed"] = True
        st.success("確定しました。Amazonまとめて追加（デモ）を有効化しました。")
with col2:
    st.caption("※デモではAmazonのみ“まとめてカート投入”を実演（最大5商品）。")

if st.session_state["confirmed"]:
    asins = []
    for it in bundle_items[:MAX_CART_ITEMS]:
        prod = PRODUCT_BY_ID.get(it["asahi_id"])
        if prod:
            asin = prod["offers"]["amazon"].get("asin")
            if asin:
                asins.append(asin)

    if not asins:
        st.warning("No Amazon ASINs found in the current bundle.")
    else:
        colA, colB = st.columns([0.35, 0.65])
        with colA:
            if st.button("🛒 Add bundle to Amazon cart (Playwright)", type="primary"):
                cmd = [
                    "python",
                    str(BASE / "amazon_cart_bot.py"),
                    "--asins",
                    json.dumps(asins, ensure_ascii=False),
                    "--profile",
                    str(BASE / "pw_amazon_profile"),
                    "--keep_open",
                ]
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log_path = BASE / "cart_bot.log"
                with open(log_path, "a", encoding="utf-8") as f:
                    subprocess.Popen(cmd, stdout=f, stderr=f)
                st.success("Started cart prep. If it closes, open cart_bot.log to see why.")
                st.code(str(log_path))

                # record a state so we can show a “next step” panel
                st.session_state["cart_started"] = True
                st.success("Amazon cart prep started in a Chrome window.")
                st.rerun()

        with colB:
            st.caption("Demo flow: click → switch to Chrome window → cart is ready → come back here.")

        if st.session_state.get("cart_started"):
            st.info(
                "✅ Next step: Switch to the **Chrome window** that opened, confirm items in the **Amazon cart**, "
                "then come back to this page to continue the conversation."
            )