
from playwright.sync_api import sync_playwright
import pandas as pd
import requests
from PIL import Image
from io import BytesIO
from pathlib import Path
import time

# =========================
# SETTINGS
# =========================

BASE_URL = "https://th.shein.com/Women-Apparel-c-4436.html"
START_PAGE = 1
END_PAGE = 20

IMAGE_DIR = Path("IMAGES")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

URL_CSV = Path("image_urls.csv")
STATUS_CSV = Path("data_image.csv")

SELECTOR = "img.crop-image-container__img"
CDP_URL = "http://127.0.0.1:9222"


def get_page_url(page_number):
    """Page 1 uses the base URL; pages 2–20 use ?page=N."""
    if page_number == 1:
        return BASE_URL
    return f"{BASE_URL}?page={page_number}"


# =========================
# COLLECT IMAGE URLS
# =========================

def get_image_urls():
    all_records = []
    seen_urls = set()

    with sync_playwright() as p:
        print("Connecting to your Chrome window...")
        browser = p.chromium.connect_over_cdp(CDP_URL)

        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()

        try:
            for page_number in range(START_PAGE, END_PAGE + 1):
                url = get_page_url(page_number)

                print(f"\n{'=' * 45}")
                print(f"Listing page {page_number}/{END_PAGE}")
                print(url)

                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=120000
                )
                page.wait_for_timeout(2500)

                print("Current URL:", page.url)
                print("Page title:", page.title())

                if "/risk/challenge" in page.url:
                    print(
                        "\nVerification challenge detected. "
                        "Stopping collection."
                    )
                    break

                # Scroll to load lazy-loaded product images.
                for _ in range(6):
                    page.mouse.wheel(0, 900)
                    page.wait_for_timeout(700)

                urls = page.locator(SELECTOR).evaluate_all("""
                    imgs => imgs.map(img =>
                        img.currentSrc
                        || img.getAttribute("data-src")
                        || img.getAttribute("src")
                        || img.getAttribute("data-original")
                    ).filter(src => src && src.startsWith("http"))
                """)

                page_unique_count = 0

                for image_url in urls:
                    if image_url not in seen_urls:
                        seen_urls.add(image_url)
                        all_records.append({
                            "Page": page_number,
                            "ImageURL": image_url
                        })
                        page_unique_count += 1

                print(f"Images found on page: {len(urls)}")
                print(f"New unique URLs: {page_unique_count}")
                print(f"Total unique URLs: {len(all_records)}")

                # Save progress after each listing page.
                pd.DataFrame(all_records).to_csv(
                    URL_CSV,
                    index=False,
                    encoding="utf-8-sig"
                )

                time.sleep(1.5)

        except Exception as error:
            print("Collection error:", error)

        finally:
            # Disconnect Playwright without intentionally closing Chrome.
            browser.close()

    print(f"\nURL collection finished: {len(all_records)} unique URLs.")
    print(f"Saved to: {URL_CSV.resolve()}")

    return all_records


# =========================
# DOWNLOAD AND CONVERT TO JPG
# =========================

def download_images(records):
    if not records:
        print("No image URLs to download.")
        return

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
    }

    download_results = []

    with requests.Session() as session:
        session.headers.update(headers)

        for index, record in enumerate(records, start=1):
            image_url = record["ImageURL"]
            filename = f"blouse_{index:05d}.jpg"
            image_path = IMAGE_DIR / filename

            try:
                response = session.get(image_url, timeout=30)
                response.raise_for_status()

                with Image.open(BytesIO(response.content)) as image:
                    image.load()

                    # Convert transparent images to white-background RGB.
                    if (
                        image.mode in ("RGBA", "LA")
                        or (
                            image.mode == "P"
                            and "transparency" in image.info
                        )
                    ):
                        rgba = image.convert("RGBA")
                        jpg_image = Image.new(
                            "RGB", rgba.size, (255, 255, 255)
                        )
                        jpg_image.paste(
                            rgba,
                            mask=rgba.getchannel("A")
                        )
                    else:
                        jpg_image = image.convert("RGB")

                    jpg_image.save(
                        image_path,
                        format="JPEG",
                        quality=95,
                        optimize=True
                    )

                status = "Success"
                print(f"[{index}/{len(records)}] Saved {filename}")

            except Exception as error:
                status = f"Failed: {error}"
                print(f"[{index}/{len(records)}] {status}")

            download_results.append({
                "Filename": filename,
                "Page": record["Page"],
                "ImageURL": image_url,
                "Status": status
            })

            # Save progress after every attempted download.
            pd.DataFrame(download_results).to_csv(
                STATUS_CSV,
                index=False,
                encoding="utf-8-sig"
            )

            time.sleep(0.3)

    successful = sum(
        result["Status"] == "Success"
        for result in download_results
    )

    print("\n========== SUMMARY ==========")
    print(f"Pages requested: {START_PAGE}–{END_PAGE}")
    print(f"Unique URLs collected: {len(records)}")
    print(f"JPGs downloaded: {successful}")
    print(f"Failed downloads: {len(records) - successful}")
    print(f"Images folder: {IMAGE_DIR.resolve()}")
    print(f"Download report: {STATUS_CSV.resolve()}")


# =========================
# MAIN
# =========================

if __name__ == "__main__":
    records = get_image_urls()

    if records:
        download_images(records)
    else:
        print(
            "No URLs collected. Check the browser, listing page, "
            "and image selector."
        )
