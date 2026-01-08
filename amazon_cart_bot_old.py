import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

AMAZON_HOME = "https://www.amazon.co.jp/"
CART_URL = "https://www.amazon.co.jp/gp/cart/view.html"


def is_logged_in(page) -> bool:
    # Best-effort: if "サインイン" appears, likely logged out.
    try:
        if page.get_by_text("サインイン", exact=False).count() > 0:
            return False
    except Exception:
        pass
    # If "アカウント＆リスト" exists it may still show when logged out,
    # but in practice this heuristic is enough for demo.
    return True


def try_click_add_to_cart(page) -> bool:
    # small settle
    page.wait_for_timeout(300)
    page.mouse.wheel(0, 900)
    page.wait_for_timeout(200)

    # Subscription pages: try to switch to one-time purchase if present
    try:
        for label in ["1回のみの購入", "通常の注文", "定期おトク便ではない", "1回だけ購入"]:
            loc = page.get_by_text(label, exact=False)
            if loc.count() > 0:
                loc.first.click(timeout=1500)
                page.wait_for_timeout(200)
                break
    except Exception:
        pass

    # Prefer single-item add-to-cart only
    selectors = [
        "#add-to-cart-button",
        "input#add-to-cart-button",
        "input[name='submit.add-to-cart']",
        "span#submit.add-to-cart input",
        "form#addToCart input[type='submit']",
        "button[name='submit.add-to-cart']",
        "input[id*='submit.add-to-cart']",
    ]

    # Wait up to ~6s total for any add-to-cart control to appear
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=1500)
            page.locator(sel).first.click(timeout=2000)
            return True
        except Exception:
            continue

    # Fallback by visible text (single-item only)
    for name in ["カートに入れる", "Add to Cart"]:
        try:
            btn = page.get_by_role("button", name=name)
            if btn.count() > 0:
                btn.first.click(timeout=2000)
                return True
        except Exception:
            pass

    return False

def add_asins_to_cart(asins, user_data_dir: str, headless: bool = False, args=None):
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

        context.route("**/*", lambda route: route.continue_())

        page = context.new_page()
        # fix for stuck on LP loads
        page.set_default_timeout(8000)
        page.set_default_navigation_timeout(20000)

        # 1) Open Amazon so you can be logged in
        page.goto(AMAZON_HOME, wait_until="domcontentloaded")
        page.wait_for_timeout(300)

        # If you're NOT logged in, you must log in manually once.
        # We can't safely auto-login without credentials.
        # Quick heuristic: account menu exists even when logged out,
        # so we just tell you to confirm manually on first run.
        if not is_logged_in(page):
            print("\nPlease log into Amazon in the opened browser window, then press ENTER here.\n")
            input()

        # 2) Add each ASIN
        added = []
        failed = []

        for asin in asins:
            # url = f"https://www.amazon.co.jp/dp/{asin}"
            url = f"https://www.amazon.co.jp/dp/{asin}?th=1&psc=1"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(300)

                clicked = try_click_add_to_cart(page)
                if not clicked:
                    # Take a screenshot for debugging (super helpful)
                    page.screenshot(path=f"debug_{asin}.png", full_page=True)
                    failed.append({"asin": asin, "reason": "add-to-cart button not found (saved debug PNG)"})
                    continue

                # Wait for confirmation-ish state
                # Amazon varies; this is a soft check.
                # Faster: wait a bit + allow any navigation/overlay
                page.wait_for_timeout(350)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass
                added.append(asin)
                # Try closing common overlay dialogs (best effort)
                try:
                    # Close buttons sometimes show "いいえ" / "閉じる" / "スキップ"
                    for txt in ["閉じる", "いいえ", "スキップ", "次へ進む", "続行"]:
                        loc = page.get_by_role("button", name=txt)
                        if loc.count() > 0:
                            loc.first.click(timeout=1200)
                            page.wait_for_timeout(400)
                except Exception:
                    pass

            except Exception as e:
                failed.append({"asin": asin, "reason": str(e)})

        # 3) Open cart at end
        page.goto(CART_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        # Keep browser open for demo/video unless headless
        if args.keep_open and not headless:
            print("\nCart opened. Close the browser window to finish.")
            try:
                page.wait_for_timeout(9999999)
            except Exception:
                pass

        context.close()

        return {"added": added, "failed": failed}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asins", type=str, required=True, help="JSON array like ['B09NQYS7WF','B0753XS44S']")
    ap.add_argument("--profile", type=str, default="./pw_amazon_profile", help="persistent profile dir")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--keep_open", action="store_true")
    args = ap.parse_args()

    asins = json.loads(args.asins)
    result = add_asins_to_cart(asins, user_data_dir=args.profile, headless=args.headless, args=args)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()