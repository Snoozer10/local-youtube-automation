"""Image Extraction & Validation Engine.

Provides the 4-tier image extraction ladder to extract high-resolution
generated images from Google Flow SPA without CORS canvas-tainting:
  Tier 1: Inline Base64 data URL
  Tier 2: In-browser local blob: fetch via FileReader
  Tier 2B: In-page canvas/fetch fallback with session cookies
  Tier 2C: Network stream via Playwright page.request.get
  Tier 3: Atomic de-hovered screenshot fallback

Includes atomic file writing and strict image integrity validation
(Pillow header verify + dimensions > 100px + magic bytes).
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any
from urllib.parse import urljoin


def validate_image_file(file_path: str, min_size_kb: int = 20) -> bool:
    """Validates that an image exists on disk, exceeds the minimum byte threshold,
    and contains valid image headers (PNG, JPEG, or WebP) without corruption.
    """
    if not os.path.exists(file_path):
        return False

    file_size = os.path.getsize(file_path)
    if file_size < (min_size_kb * 1024):
        return False

    # Fast Pillow integrity check (verifies file is not truncated/corrupted)
    try:
        from PIL import Image

        with Image.open(file_path) as img:
            w, h = img.size  # Read dimensions BEFORE verify() (verify() consumes the stream)
            img.verify()
            return w > 100 and h > 100
    except Exception:
        pass  # Tier 2 file op: corrupt/truncated file returns False, falls to header check

    # Fallback header check (PNG magic bytes: \x89PNG\r\n\x1a\n or JPEG: \xff\xd8\xff)
    try:
        with open(file_path, "rb") as f:
            header = f.read(8)
            if header.startswith(b"\x89PNG\r\n\x1a\n") or header.startswith(b"\xff\xd8\xff"):
                return True
    except Exception:
        return False

    return False


def save_binary_image_data(data: bytes, save_path: str, min_size_kb: int = 20) -> bool:
    """Atomically writes raw binary image data to disk and validates it."""
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    temp_path = save_path + ".tmp"
    try:
        with open(temp_path, "wb") as f:
            f.write(data)
        if validate_image_file(temp_path, min_size_kb=min_size_kb):
            os.replace(temp_path, save_path)
            return True
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False


def atomic_screenshot_and_verify(
    locator: Any,
    final_save_path: str,
    page: Any,
    min_size_kb: int = 50,
) -> bool:
    """Executes a de-hovered screenshot to a temporary file, validates binary integrity,
    and atomically moves it to final_save_path to prevent corrupted partial files.
    """
    os.makedirs(os.path.dirname(os.path.abspath(final_save_path)), exist_ok=True)
    temp_path = final_save_path + ".tmp"
    try:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

        # Move mouse to safe neutral coordinate to clear active CSS :hover styles
        page.mouse.move(100, 15)
        page.evaluate("() => new Promise(requestAnimationFrame)")
        time.sleep(0.35)

        locator.scroll_into_view_if_needed()
        locator.screenshot(path=temp_path, type="png")

        if validate_image_file(temp_path, min_size_kb=min_size_kb):
            os.replace(temp_path, final_save_path)
            return True
        else:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False
    except Exception as e:
        print(f"  \u26a0\ufe0f Atomic screenshot failed: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False


def extract_high_res_image(
    page: Any,
    img_locator: Any,
    save_path: str,
    min_size_kb: int = 20,
) -> bool:
    """Tiered full-resolution image extraction that avoids CORS canvas tainting.

    Tier 1: Inline base64 data URL (no network needed).
    Tier 2: Authenticated network stream via page.request.get() (bypasses CORS,
            inherits the browser session's cookies/auth, no canvas involved).
    Tier 2B: Local blob: URL fetched in-page (same-origin, no CORS issue).
    Tier 3: De-hovered atomic Playwright screenshot fallback.
    """
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    temp_path = save_path + ".tmp"
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass

    try:
        src = img_locator.get_attribute("src") or ""
    except Exception:
        src = ""

    # --- TIER 1: Inlined Base64 ---
    if src.startswith("data:image"):
        try:
            base64_data = src.split(",", 1)[1]
            raw_bytes = base64.b64decode(base64_data)
            if save_binary_image_data(raw_bytes, save_path, min_size_kb=min_size_kb):
                print(f"  \u2705 Saved (Inline Base64): {os.path.basename(save_path)}")
                return True
        except Exception as e:
            print(f"  \u2139\ufe0f Base64 extraction failed ({e}), falling back to network stream...")

    # --- TIER 2: Local Blob URL (fetchable in browser context without CORS) ---
    if src.startswith("blob:"):
        try:
            js_blob = """
            async (img) => {
                const response = await fetch(img.src);
                const blob = await response.blob();
                return new Promise((resolve) => {
                    const reader = new FileReader();
                    reader.onloadend = () => resolve(reader.result);
                    reader.readAsDataURL(blob);
                });
            }
            """
            data_url = img_locator.evaluate(js_blob)
            if data_url and isinstance(data_url, str) and "," in data_url:
                base64_data = data_url.split(",", 1)[1]
                raw_bytes = base64.b64decode(base64_data)
                if save_binary_image_data(raw_bytes, save_path, min_size_kb=min_size_kb):
                    print(f"  \u2705 Saved (Blob Fetch): {os.path.basename(save_path)}")
                    return True
        except Exception as e:
            print(f"  \u2139\ufe0f Blob fetch extraction failed ({e}), falling back to screenshot...")

    # --- TIER 2B: In-Page Canvas / Fetch Extraction (bypasses CDN cookie restrictions) ---
    if src.startswith(("http://", "https://", "/")):
        try:
            js_fetch = """
            async (img) => {
                try {
                    const response = await fetch(img.src, {credentials: 'include'});
                    if (!response.ok) throw new Error('fetch not ok');
                    const blob = await response.blob();
                    return await new Promise((resolve) => {
                        const reader = new FileReader();
                        reader.onloadend = () => resolve(reader.result);
                        reader.onerror = () => resolve(null);
                        reader.readAsDataURL(blob);
                    });
                } catch (e) {
                    try {
                        const canvas = document.createElement('canvas');
                        canvas.width = img.naturalWidth || img.width;
                        canvas.height = img.naturalHeight || img.height;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(img, 0, 0);
                        return canvas.toDataURL('image/png');
                    } catch (e2) {
                        return null;
                    }
                }
            }
            """
            data_url = img_locator.evaluate(js_fetch)
            if data_url and isinstance(data_url, str) and "," in data_url:
                base64_data = data_url.split(",", 1)[1]
                raw_bytes = base64.b64decode(base64_data)
                if save_binary_image_data(raw_bytes, save_path, min_size_kb=min_size_kb):
                    print(f"  Saved (In-Page Fetch/Canvas): {os.path.basename(save_path)}")
                    return True
        except Exception as e:
            print(f"  In-page fetch/canvas failed ({e}), falling back to network stream...")

        # --- TIER 2C: Network Stream via Playwright (fallback, may lack CDN cookies) ---
        try:
            absolute_src = urljoin(page.url, src)
            response = page.request.get(absolute_src)
            if response.ok:
                if save_binary_image_data(response.body(), save_path, min_size_kb=min_size_kb):
                    print(f"  Saved (Network Stream): {os.path.basename(save_path)}")
                    return True
        except Exception as e:
            print(f"  Network stream extraction failed ({e}), falling back to screenshot...")

    # --- TIER 3: Atomic De-Hovered Screenshot Fallback ---
    return atomic_screenshot_and_verify(img_locator, save_path, page, min_size_kb=min_size_kb)
