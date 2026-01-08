
import json
from datetime import datetime, timedelta
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Asahi Group AIショッパー（デモ）", page_icon="🛒", layout="wide")

# ---------- Styling ----------
st.markdown("""
<style>
.stApp {
  background: radial-gradient(1200px 600px at 10% 10%, rgba(255, 60, 60, 0.12), transparent 60%),
              radial-gradient(1200px 600px at 90% 20%, rgba(0, 160, 255, 0.10), transparent 60%),
              linear-gradient(180deg, rgba(255,255,255,1) 0%, rgba(250,250,252,1) 100%);
}
.header {
  padding: 18px 18px 10px 18px;
  border-radius: 18px;
  background: linear-gradient(90deg, rgba(10,10,12,1), rgba(28,28,34,1));
  color: white;
  box-shadow: 0 10px 24px rgba(0,0,0,0.12);
}
.header h1 { margin: 0; font-size: 26px; letter-spacing: 0.2px;}
.header p { margin: 6px 0 0 0; opacity: .85; font-size: 14px;}
.chip {
  display: inline-block;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(0,0,0,0.06);
  margin-right: 6px;
  margin-bottom: 6px;
  font-size: 12px;
}
.card {
  border-radius: 18px;
  border: 1px solid rgba(0,0,0,0.06);
  background: rgba(255,255,255,0.92);
  box-shadow: 0 10px 18px rgba(0,0,0,0.06);
  padding: 14px;
}
.subtle {
  color: rgba(0,0,0,0.62);
  font-size: 12px;
}
.kpi {
  border-radius: 14px;
  padding: 10px 12px;
  background: rgba(0,0,0,0.035);
  border: 1px solid rgba(0,0,0,0.05);
}
.sticky {
  position: sticky;
  bottom: 12px;
  z-index: 999;
  border-radius: 18px;
  padding: 14px 16px;
  background: rgba(255,255,255,0.94);
  border: 1px solid rgba(0,0,0,0.08);
  box-shadow: 0 16px 30px rgba(0,0,0,0.12);
}
</style>
""", unsafe_allow_html=True)

# ---------- Header ----------
st.markdown("""
<div class="header">
  <h1>Asahi Group AIショッパー（デモ）</h1>
  <p>Amazon（または将来のAsahi EC）で「探す→選ぶ→まとめる」を一瞬で。</p>
</div>
""", unsafe_allow_html=True)

# ---------- Load snapshot ----------
BASE = Path(__file__).resolve().parent
SNAPSHOT_PATH = BASE / "products_snapshot.json"

@st.cache_data
def load_products():
    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

PRODUCTS = load_products()

# ---------- Helpers ----------
def yen(x: int) -> str:
    return f"¥{x:,}"

def rank_items(items, prefer_prime=True, max_items=6):
    items_sorted = sorted(
        items,
        key=lambda it: (
            0 if (it.get("prime") and prefer_prime) else 1,
            it.get("delivery_days", 99),
            -float(it.get("rating", 0)),
            int(it.get("price_jpy", 10**9)),
        )
    )
    return items_sorted[:max_items]

def filter_products(category=None, must_tags=None, price_max=None):
    out = PRODUCTS
    if category:
        out = [p for p in out if p["category"] == category]
    if must_tags:
        for t in must_tags:
            out = [p for p in out if (t in p.get("tags", [])) or (t in p.get("title",""))]
    if price_max is not None:
        out = [p for p in out if p.get("price_jpy", 10**9) <= price_max]
    return out

def detect_intent(text: str) -> str:
    t = text.lower()
    if ("パーティ" in text) or ("party" in t) or ("30" in text) or ("ビール" in text):
        return "party"
    if ("セーター" in text) or ("sweater" in t) or ("赤" in text):
        return "sweater"
    if ("自転車" in text) or ("bike" in t) or ("娘" in text) or ("4歳" in text):
        return "kids_bike"
    return "unknown"

def make_plan(intent: str, text: str, height_cm: int|None = None):
    now = datetime.now()
    if intent == "party":
        people = 30
        beers_per_person = 2
        cans = people * beers_per_person
        plan = {
            "title": "パーティー準備（30人想定）",
            "assumptions": [
                f"人数: {people}人",
                f"飲み物: 1人あたり{beers_per_person}本（合計{cans}本）",
                "スナックは“甘い/しょっぱい”のミックス",
                "紙皿・紙コップ・割り箸・ウェットティッシュを同梱",
            ],
            "bundle": [
                {"section": "ビール/飲料", "category": "beer", "qty_hint": f"合計{cans}本（例: 24本×2 + 12本など）"},
                {"section": "おつまみ/スナック", "category": "snack", "qty_hint": "大袋/まとめ買いで時短"},
                {"section": "備品（紙コップ/紙皿/割り箸等）", "category": "party", "qty_hint": "不足しがちな消耗品を一括"},
            ],
            "order_by": (now + timedelta(days=0)).strftime("%Y/%m/%d 18:00"),
            "note": "※お届け日は商品ページで最終確認してください。",
        }
        return plan, None

    if intent == "sweater":
        plan = {
            "title": "メンズ赤セーター（予算：¥4,000以下）",
            "assumptions": [
                "カラー: 赤",
                "性別: メンズ",
                "価格上限: ¥4,000",
                "まずは“首元（クルー/タートル）”と“素材感”で絞り込み",
            ],
            "bundle": [
                {"section": "候補一覧", "category": "apparel", "qty_hint": "好みの素材/首元で選択"},
            ],
            "order_by": (now + timedelta(days=0)).strftime("%Y/%m/%d 18:00"),
            "note": "※サイズ感はレビューを優先して確認してください。",
        }
        return plan, None

    if intent == "kids_bike":
        if height_cm is None:
            follow = {
                "question": "娘さんの身長は何cmくらいですか？（目安でOK）",
                "hint": "かわいいですね😊 身長に合うインチを絞ると失敗しにくいです。",
            }
            return None, follow

        if height_cm < 95:
            inch = "12インチ（キックバイク）"
            tags = ["12インチ"]
        elif height_cm < 110:
            inch = "14インチ"
            tags = ["14インチ"]
        elif height_cm < 120:
            inch = "16インチ"
            tags = ["16インチ"]
        else:
            inch = "18インチ"
            tags = ["18インチ"]

        plan = {
            "title": "4歳向け 自転車選び（身長ベース）",
            "assumptions": [
                f"身長: {height_cm}cm",
                f"おすすめサイズ: {inch}",
                "安全のためヘルメット/プロテクターも同時提案",
                "補助輪付き or キックバイクを優先",
            ],
            "bundle": [
                {"section": "自転車本体（候補）", "category": "bike", "qty_hint": inch, "must_tags": tags},
                {"section": "ヘルメット", "category": "bike_accessory", "qty_hint": "Sサイズ目安", "must_tags": ["ヘルメット"]},
                {"section": "プロテクター/安全小物", "category": "bike_accessory", "qty_hint": "ケガ予防", "must_tags": ["プロテクター"]},
            ],
            "order_by": (now + timedelta(days=0)).strftime("%Y/%m/%d 18:00"),
            "note": "※適合サイズはメーカー表もご確認ください。",
        }
        return plan, None

    plan = {
        "title": "もう少し情報が欲しいです",
        "assumptions": [
            "例：予算、期限、サイズ、用途などを追記してください。",
            "（デモでは左の例ボタンを押すと確実に動きます）",
        ],
        "bundle": [],
        "order_by": (now + timedelta(days=0)).strftime("%Y/%m/%d 18:00"),
        "note": "",
    }
    return plan, None

def render_plan(plan: dict):
    st.markdown(f"<div class='card'><b>🧠 AIプラン</b><br><span class='subtle'>{plan.get('title','')}</span><hr>", unsafe_allow_html=True)
    for a in plan.get("assumptions", []):
        st.markdown(f"- {a}")
    st.markdown(f"<div class='subtle'>注文目安: {plan.get('order_by','')}<br>{plan.get('note','')}</div></div>", unsafe_allow_html=True)

def render_items_grid(items, cols=3, pick_state_key=None):
    if not items:
        st.info("該当候補が見つかりませんでした（スナップショット範囲外）")
        return
    rows = (len(items) + cols - 1) // cols
    idx = 0
    for _ in range(rows):
        cs = st.columns(cols)
        for c in cs:
            if idx >= len(items):
                break
            it = items[idx]
            idx += 1
            with c:
                img = Path(it["image"])

                # If it's relative, resolve it under the app folder
                if not img.is_absolute():
                    img = (BASE / img)

                # If it's an old absolute path that doesn't exist on this machine,
                # fall back to snapshot_images/<filename>
                if not img.exists():
                    img = BASE / "snapshot_images" / Path(it["image"]).name

                st.image(str(img), use_container_width=True)
                st.markdown(f"**{it['title']}**")
                chips = []
                if it.get("prime"): chips.append("Prime")
                chips.append(f"{it.get('delivery_days','-')}日以内")
                if it.get("deal"): chips.append("お得")
                for ch in chips[:3]:
                    st.markdown(f"<span class='chip'>{ch}</span>", unsafe_allow_html=True)
                st.markdown(f"### {yen(int(it['price_jpy']))}")
                st.caption(f"⭐ {it.get('rating')}（{it.get('reviews'):,}件）")
                if pick_state_key:
                    if st.button("バンドルに追加", key=f"add_{pick_state_key}_{it['id']}"):
                        st.session_state[pick_state_key].append(it["id"])

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("### ⚙️ デモ設定")
    mode = st.selectbox("データ取得", ["スナップショット（推奨）", "Amazon PA-API（将来）"])
    st.markdown("""
- これは **録画デモ向け** のUIです。  
- Amazon PA-API は鍵が揃えば差し替えできます（本サンプルは未実装）。
""")
    st.markdown("### 🎬 例（ワンクリック）")
    if st.button("例：30人パーティー"):
        st.session_state["intent_text"] = "30人でパーティーをします。ビールなどはOK。"
    if st.button("例：赤いセーター"):
        st.session_state["intent_text"] = "男性向けで赤いセーター、4000円以下で探して。"
    if st.button("例：4歳の娘に自転車"):
        st.session_state["intent_text"] = "4歳の娘に自転車を買いたいです。"

# ---------- Main ----------
st.markdown("## 🧾 やりたいことを入力")
intent_text = st.text_input("例）30人でパーティー。ビールOK / メンズ赤セーター4000円以下 / 4歳の娘に自転車", key="intent_text")
go = st.button("提案を見る", type="primary")

if "bundle_ids" not in st.session_state:
    st.session_state["bundle_ids"] = []

if go and intent_text.strip():
    st.session_state["bundle_ids"] = []
    st.session_state["last_intent"] = detect_intent(intent_text)
    st.session_state["height_cm"] = None

intent = st.session_state.get("last_intent")
height_cm = st.session_state.get("height_cm")

if intent:
    plan, follow = make_plan(intent, intent_text, height_cm=height_cm)

    if follow:
        st.markdown("### 💬 追加で1つだけ質問")
        st.info(follow["hint"])
        h = st.slider(follow["question"], min_value=85, max_value=130, value=105, step=1)
        if st.button("この条件で探す", type="primary"):
            st.session_state["height_cm"] = h
            plan, follow = make_plan(intent, intent_text, height_cm=h)

    if plan:
        left, right = st.columns([0.38, 0.62], gap="large")
        with left:
            render_plan(plan)
            st.markdown("#### ✅ この提案のポイント")
            st.markdown("""
<div class="kpi"><b>質問は最大1回</b><br><span class="subtle">“会話の摩擦”を最小化して、すぐカード表示。</span></div>
<div style="height:10px"></div>
<div class="kpi"><b>バンドルで購入を短縮</b><br><span class="subtle">必要量・関連商品・お得条件をまとめて提案。</span></div>
<div style="height:10px"></div>
<div class="kpi"><b>根拠を見せる</b><br><span class="subtle">数量の前提や選定ロジックをUIに明示。</span></div>
""", unsafe_allow_html=True)

        with right:
            st.markdown("### 🛍️ おすすめ商品")
            for b in plan.get("bundle", []):
                section = b.get("section","")
                category = b.get("category")
                must_tags = b.get("must_tags")
                st.markdown(f"#### {section}  <span class='subtle'>— {b.get('qty_hint','')}</span>", unsafe_allow_html=True)

                if mode.startswith("スナップショット"):
                    items = filter_products(category=category, must_tags=must_tags,
                                           price_max=4000 if intent=="sweater" else None)
                    items = rank_items(items, prefer_prime=True, max_items=6)
                else:
                    st.warning("Amazon PA-API モードは未実装です。スナップショットをご利用ください。")
                    items = []
                render_items_grid(items, cols=3, pick_state_key="bundle_ids")
                st.divider()

        picked = st.session_state.get("bundle_ids", [])
        picked_items = [p for p in PRODUCTS if p["id"] in picked]
        total = sum(int(p["price_jpy"]) for p in picked_items) if picked_items else 0
        min_delivery = min([p.get("delivery_days", 99) for p in picked_items], default=None)

        st.markdown("---")
        st.markdown("<div class='sticky'>", unsafe_allow_html=True)
        st.markdown(
            f"**🧺 バンドル合計:** {yen(total)}　"
            f"**追加点数:** {len(picked_items)}　"
            f"**最短お届け:** {str(min_delivery)+'日以内' if min_delivery else '—'}",
            unsafe_allow_html=True
        )
        st.markdown("<div class='subtle'>※価格/在庫/配送条件は購入時に変動する場合があります。最終情報は商品ページでご確認ください。</div>", unsafe_allow_html=True)

        c1, c2, c3 = st.columns([0.5, 0.25, 0.25])
        with c1:
            st.caption("録画デモでは、ここをクリックして“Amazonで確認”に遷移する演出ができます。")
        with c2:
            if st.button("バンドルをクリア"):
                st.session_state["bundle_ids"] = []
                st.rerun()
        with c3:
            st.link_button("Amazonで確認（デモ）", "https://www.amazon.co.jp/")
        st.markdown("</div>", unsafe_allow_html=True)
else:
    st.caption("左のサイドバーから例を選ぶか、上の入力欄に日本語で目的を書いてください。")
