Asahi Group AIショッパー（デモ） - Streamlit

■ 目的
録画デモ向けに「意図→プラン→商品カード→バンドル」を“それっぽく・速く・綺麗に”見せるUIです。
（Amazon PA-API 連携がなくても成立する “Snapshot mode” 付き）

■ セットアップ
python -m venv .venv
source .venv/bin/activate  (Windows: .venv\Scripts\activate)
pip install streamlit pillow

■ 起動
streamlit run app.py

■ Snapshot data
products_snapshot.json
snapshot_images/ （プレースホルダー画像を同梱）

■ 追加で商品を増やす方法（超簡単）
products_snapshot.json に以下の項目を追加：
- id, category, title, price_jpy, prime, delivery_days, tags, image, url

image は snapshot_images/xxx.png を指すようにしてOK。
（画像は文字入りのプレースホルダーで十分デモ映えします）
