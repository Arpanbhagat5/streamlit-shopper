import argparse
import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

AMAZON_HOME = "https://www.amazon.co.jp/"
CART_URL = "https://www.amazon.co.jp/gp/cart/view.html"


def is_logged_in(page) -> bool:
    try:
        loc = page.locator("#nav-link-accountList-nav-line-1")
        if loc.count() == 0:
            return False  # IMPORTANT: don't assume logged-in on about:blank
        text = (loc.first.inner_text(timeout=2000) or "").strip()
        return ("ログイン" not in text) and ("サインイン" not in text)
    except Exception:
        return False


def wait_for_login(page, seconds: int = 180) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if is_logged_in(page):
            return True
        page.wait_for_timeout(1000)
        try:
            page.reload(wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
    return False


def try_click_add_to_cart(page) -> bool:
    page.wait_for_timeout(300)
    page.mouse.wheel(0, 900)
    page.wait_for_timeout(200)

    # Switch away from subscription if present
    try:
        for label in ["1回のみの購入", "通常の注文", "定期おトク便ではない", "1回だけ購入"]:
            loc = page.get_by_text(label, exact=False)
            if loc.count() > 0:
                loc.first.click(timeout=1500)
                page.wait_for_timeout(200)
                break
    except Exception:
        pass

    selectors = [
        "#add-to-cart-button",
        "input#add-to-cart-button",
        "input[name='submit.add-to-cart']",
        "span#submit.add-to-cart input",
        "form#addToCart input[type='submit']",
        "button[name='submit.add-to-cart']",
        "input[id*='submit.add-to-cart']",
    ]

    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=1500)
            page.locator(sel).first.click(timeout=2000)
            return True
        except Exception:
            continue

    for name in ["カートに入れる", "Add to Cart"]:
        try:
            btn = page.get_by_role("button", name=name)
            if btn.count() > 0:
                btn.first.click(timeout=2000)
                return True
        except Exception:
            pass

    return False


def add_items_to_cart(items, user_data_dir: str, headless: bool, keep_open: bool, wait_login_seconds: int):
    user_data_dir = str(Path(user_data_dir).resolve())
    os.makedirs(user_data_dir, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            channel="chrome",
            locale="ja-JP",
            viewport={"width": 1280, "height": 860},
        )

        page = context.new_page()
        page.set_default_timeout(8000)
        page.set_default_navigation_timeout(60000)

        # IMPORTANT: go to home before login check
        page.goto(AMAZON_HOME, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(500)

        if not is_logged_in(page):
            print(f"[BOT] Not logged in. Please login in the opened Chrome window (waiting up to {wait_login_seconds}s)...")
            ok = wait_for_login(page, wait_login_seconds)
            if not ok:
                print("[BOT] Login not detected within timeout.")
                if keep_open and not headless:
                    try:
                        page.wait_for_timeout(9999999)
                    except Exception:
                        pass
                context.close()
                return {"added": [], "failed": [{"asin": "*", "reason": "login not detected"}]}

        added, failed = [], []

        for it in items:
            asin = it.get("asin")
            qty = int(it.get("qty", 1) or 1)
            if not asin or qty <= 0:
                continue

            url = f"https://www.amazon.co.jp/dp/{asin}?th=1&psc=1"

            for n in range(qty):  # <-- quantity support (minimal + reliable)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(300)

                    if not try_click_add_to_cart(page):
                        page.screenshot(path=f"debug_{asin}.png", full_page=True)
                        failed.append({"asin": asin, "reason": "add-to-cart button not found (saved debug PNG)"})
                        break

                    page.wait_for_timeout(450)
                    added.append(asin)

                    # Close common overlays best-effort
                    try:
                        for txt in ["閉じる", "いいえ", "スキップ", "次へ進む", "続行"]:
                            loc = page.get_by_role("button", name=txt)
                            if loc.count() > 0:
                                loc.first.click(timeout=1200)
                                page.wait_for_timeout(200)
                    except Exception:
                        pass

                except Exception as e:
                    failed.append({"asin": asin, "reason": str(e)})
                    break

        page.goto(CART_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(800)

        if keep_open and not headless:
            print("[BOT] Cart opened. Close the Chrome window when done.")
            try:
                page.wait_for_timeout(9999999)
            except Exception:
                pass

        context.close()
        return {"added": added, "failed": failed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", type=str, required=True, help="JSON: [{asin, qty}, ...]")
    ap.add_argument("--profile", type=str, default="./pw_amazon_profile")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--keep_open", action="store_true")
    ap.add_argument("--wait_login_seconds", type=int, default=180)
    args = ap.parse_args()

    items = json.loads(args.items)
    result = add_items_to_cart(
        items=items,
        user_data_dir=args.profile,
        headless=args.headless,
        keep_open=args.keep_open,
        wait_login_seconds=args.wait_login_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()