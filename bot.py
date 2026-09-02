import os
import sys
import asyncio
import json
import re
import shutil
import subprocess
import time

import yt_dlp
from playwright.sync_api import sync_playwright

from telegram import (
    Update,
    InputMediaPhoto,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN


# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

ALLOWED_USER_ID = 725751

DOWNLOAD_FOLDER = "downloads"
GALLERY_FOLDER = "gallery_dl"

INSTAGRAM_COOKIES = "instagram_cookies.txt"

# Dedicated Chrome profile for TikTok.
# This is intentionally separate from your normal Chrome profile.
TIKTOK_PROFILE_DIR = "tiktok_chrome_profile"

CHROME_USER_DATA_DIR = r"C:\Users\user\AppData\Local\Google\Chrome\User Data"
CHROME_PROFILE_NAME = "Default"

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(GALLERY_FOLDER, exist_ok=True)
os.makedirs(TIKTOK_PROFILE_DIR, exist_ok=True)


# --------------------------------------------------
# SECURITY
# --------------------------------------------------

def is_allowed(update: Update):
    return (
        update.effective_user
        and update.effective_user.id == ALLOWED_USER_ID
    )


# --------------------------------------------------
# URL HELPERS
# --------------------------------------------------

def is_instagram_url(url):
    return "instagram.com/" in url.lower()


def is_tiktok_photo_url(url):
    url = url.lower()
    return (
        "tiktok.com/" in url
        and "/photo/" in url
    )
def is_tiktok_video_url(url):
    url = url.lower()
    return (
        "tiktok.com/" in url
        and "/video/" in url
    )
def is_twitter_url(url):
    url = url.lower()
    return (
        "x.com/" in url
        or "twitter.com/" in url
    )


# --------------------------------------------------
# FILE HELPERS
# --------------------------------------------------

def get_extension(filepath):
    return os.path.splitext(filepath)[1].lower()


def is_image_file(filepath):
    return get_extension(filepath) in (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    )


def collect_files(folder):
    collected = []

    for root, _, filenames in os.walk(folder):
        for filename in filenames:
            filepath = os.path.join(
                root,
                filename,
            )

            if filename.endswith(
                (".part", ".ytdl")
            ):
                continue

            if os.path.isfile(filepath):
                collected.append(filepath)

    return collected


def reset_gallery_folder():
    if os.path.exists(GALLERY_FOLDER):
        shutil.rmtree(GALLERY_FOLDER)

    os.makedirs(
        GALLERY_FOLDER,
        exist_ok=True,
    )


def extension_from_url_or_type(
    image_url,
    content_type=None,
):
    content_type = (
        content_type
        or ""
    ).lower()

    clean_url = (
        image_url.lower()
        .split("?")[0]
    )

    if (
        "png" in content_type
        or clean_url.endswith(".png")
    ):
        return ".png"

    if (
        "webp" in content_type
        or clean_url.endswith(".webp")
    ):
        return ".webp"

    return ".jpg"


# --------------------------------------------------
# /START
# --------------------------------------------------

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_allowed(update):
        await update.message.reply_text(
            "⛔ This is a private bot."
        )
        return

    await update.message.reply_text(
        "📥 Media Downloader is ready!\n\n"
        "Send me a public social-media link."
    )


# --------------------------------------------------
# YT-DLP VIDEO DOWNLOADER
# --------------------------------------------------

def download_with_ytdlp(url):
    before_files = set(
        os.listdir(DOWNLOAD_FOLDER)
    )

    ydl_opts = {
        "format": (
            "bestvideo[height<=720]+bestaudio/"
            "best[height<=720]/best"
        ),
        "outtmpl": os.path.join(
            DOWNLOAD_FOLDER,
            "%(title).70s [%(id)s].%(ext)s",
        ),
        "merge_output_format": "mp4",
        "noplaylist": False,
        "quiet": False,
    }

    with yt_dlp.YoutubeDL(
        ydl_opts
    ) as ydl:
        info = ydl.extract_info(
            url,
            download=True,
        )

    after_files = set(
        os.listdir(DOWNLOAD_FOLDER)
    )

    new_files = (
        after_files - before_files
    )

    media_files = []

    for filename in new_files:
        filepath = os.path.join(
            DOWNLOAD_FOLDER,
            filename,
        )

        if filename.endswith(
            (".part", ".ytdl")
        ):
            continue

        if os.path.isfile(filepath):
            media_files.append(filepath)

    if not media_files:
        raise FileNotFoundError(
            "yt-dlp finished but no media files were found."
        )

    mp4_files = [
        filepath
        for filepath in media_files
        if filepath.lower().endswith(".mp4")
    ]

    if mp4_files:
        media_files = mp4_files

    title = info.get(
        "title",
        "Downloaded media",
    )

    return media_files, title


# --------------------------------------------------
# Twitter-X IMAGE DOWNLOADER
# --------------------------------------------------

def download_twitter_images(url):
    print()
    print("X/Twitter image fallback activated.")

    # Start with a clean gallery-dl folder.
    if os.path.exists(GALLERY_FOLDER):
        shutil.rmtree(GALLERY_FOLDER)

    os.makedirs(
        GALLERY_FOLDER,
        exist_ok=True,
    )

    command = [
        sys.executable,
        "-m",
        "gallery_dl",
        "--dest",
        GALLERY_FOLDER,
        url,
    ]

    print("Running gallery-dl for X/Twitter...")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError(
            "gallery-dl could not download "
            "the X/Twitter post."
        )

    downloaded_files = []

    for root, dirs, files in os.walk(
        GALLERY_FOLDER
    ):
        for filename in files:
            filepath = os.path.join(
                root,
                filename,
            )

            if filename.lower().endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                )
            ):
                downloaded_files.append(
                    filepath
                )

    if not downloaded_files:
        raise RuntimeError(
            "No images were found in "
            "the X/Twitter post."
        )

    downloaded_files.sort()

    print(
        f"X/Twitter downloaded "
        f"{len(downloaded_files)} image(s)."
    )

    return (
        downloaded_files,
        "X/Twitter image post",
    )

# --------------------------------------------------
# INSTAGRAM IMAGE DOWNLOADER
# --------------------------------------------------

def download_instagram_images(url):
    if not os.path.exists(
        INSTAGRAM_COOKIES
    ):
        raise FileNotFoundError(
            f"{INSTAGRAM_COOKIES} was not found."
        )

    reset_gallery_folder()

    command = [
        "gallery-dl",
        "--cookies",
        INSTAGRAM_COOKIES,
        "--dest",
        GALLERY_FOLDER,
        url,
    ]

    print(
        "\nTrying Instagram image fallback..."
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError(
            "gallery-dl could not download "
            "the Instagram post."
        )

    files = collect_files(
        GALLERY_FOLDER
    )

    image_files = [
        filepath
        for filepath in files
        if is_image_file(filepath)
    ]

    if not image_files:
        raise FileNotFoundError(
            "gallery-dl finished but no "
            "Instagram images were found."
        )

    image_files.sort()

    return (
        image_files,
        "Instagram image post",
    )


# --------------------------------------------------
# TIKTOK CHROME PROFILE SETUP
# --------------------------------------------------

def import_existing_chrome_profile():
    source_profile = os.path.join(
        CHROME_USER_DATA_DIR,
        CHROME_PROFILE_NAME,
    )

    source_local_state = os.path.join(
        CHROME_USER_DATA_DIR,
        "Local State",
    )

    if not os.path.isdir(source_profile):
        raise FileNotFoundError(
            f"Chrome profile was not found: {source_profile}"
        )

    print("=" * 60)
    print("Import existing Chrome profile for TikTok")
    print("=" * 60)
    print()
    print("Source profile:")
    print(source_profile)
    print()
    print(
        "IMPORTANT: Close ALL Google Chrome windows before "
        "continuing. Brave may stay open."
    )
    print()

    input(
        "After Chrome is fully closed, press Enter to continue..."
    )

    # Remove the old dedicated profile so the import is clean.
    if os.path.exists(TIKTOK_PROFILE_DIR):
        shutil.rmtree(TIKTOK_PROFILE_DIR)

    os.makedirs(
        TIKTOK_PROFILE_DIR,
        exist_ok=True,
    )

    destination_profile = os.path.join(
        TIKTOK_PROFILE_DIR,
        CHROME_PROFILE_NAME,
    )

    print()
    print("Copying Chrome profile...")
    print(
        "This may take a little while depending on profile size."
    )

    shutil.copytree(
        source_profile,
        destination_profile,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "Cache",
            "Code Cache",
            "GPUCache",
            "Service Worker\\CacheStorage",
            "Service Worker\\ScriptCache",
            "Crashpad",
        ),
    )

    if os.path.isfile(source_local_state):
        shutil.copy2(
            source_local_state,
            os.path.join(
                TIKTOK_PROFILE_DIR,
                "Local State",
            ),
        )

    print()
    print(
        "Chrome profile imported successfully into:"
    )
    print(
        os.path.abspath(TIKTOK_PROFILE_DIR)
    )
    print()
    print(
        "The bot will use this copy, not your live Chrome profile."
    )


def prepare_tiktok_login():
    print("=" * 60)
    print("TikTok dedicated profile login")
    print("=" * 60)
    print()
    print(
        "A dedicated Chrome window will open using:"
    )
    print(
        os.path.abspath(TIKTOK_PROFILE_DIR)
    )
    print()
    print(
        "Use this only if the imported Chrome profile is not "
        "already logged into TikTok."
    )
    print()

    with sync_playwright() as playwright:
        context = (
            playwright.chromium.launch_persistent_context(
                user_data_dir=os.path.abspath(
                    TIKTOK_PROFILE_DIR
                ),
                channel="chrome",
                headless=False,
                args=[
                    f"--profile-directory={CHROME_PROFILE_NAME}",
                ],
                locale="en-US",
                viewport={
                    "width": 1280,
                    "height": 900,
                },
            )
        )

        try:
            pages = context.pages

            if pages:
                page = pages[0]
            else:
                page = context.new_page()

            page.goto(
                "https://www.tiktok.com/",
                wait_until="domcontentloaded",
                timeout=60000,
            )

            input(
                "When TikTok shows you as logged in, "
                "press Enter here to save/close the profile..."
            )

            print()
            print(
                "TikTok profile session saved."
            )

        finally:
            context.close()


# --------------------------------------------------
# TIKTOK DATA HELPERS
# --------------------------------------------------

def extract_post_id(url):
    match = re.search(
        r"/(?:photo|video)/(\d+)",
        url,
    )

    if match:
        return match.group(1)

    return None


def find_image_post_object(
    data,
    post_id=None,
):
    if isinstance(data, dict):
        object_id = (
            data.get("id")
            or data.get("aweme_id")
            or data.get("itemId")
        )

        has_images = (
            isinstance(
                data.get("imagePost"),
                dict,
            )
            or isinstance(
                data.get("image_post_info"),
                dict,
            )
        )

        if has_images:
            if (
                not post_id
                or not object_id
                or str(object_id)
                == str(post_id)
            ):
                return data

        for value in data.values():
            found = find_image_post_object(
                value,
                post_id,
            )

            if found is not None:
                return found

    elif isinstance(data, list):
        for value in data:
            found = find_image_post_object(
                value,
                post_id,
            )

            if found is not None:
                return found

    return None


def first_url_from_object(data):
    if not isinstance(data, dict):
        return None

    for key in (
        "urlList",
        "url_list",
    ):
        values = data.get(key)

        if isinstance(values, list):
            for value in values:
                if (
                    isinstance(value, str)
                    and value.startswith("http")
                ):
                    return value

    return None


def image_urls_from_item(item):
    image_post = (
        item.get("imagePost")
        or item.get("image_post_info")
    )

    if not isinstance(
        image_post,
        dict,
    ):
        return []

    images = image_post.get(
        "images",
        [],
    )

    image_urls = []

    for image in images:
        if not isinstance(
            image,
            dict,
        ):
            continue

        preferred_objects = [
            image.get("imageURL"),
            image.get("display_image"),
            image.get(
                "owner_watermark_image"
            ),
            image.get("thumbnail"),
        ]

        image_url = None

        for candidate in preferred_objects:
            image_url = (
                first_url_from_object(
                    candidate
                )
            )

            if image_url:
                break

        if not image_url:
            image_url = (
                first_url_from_object(
                    image
                )
            )

        if image_url:
            image_urls.append(
                image_url
            )

    return image_urls


def description_from_item(item):
    return (
        item.get("desc")
        or item.get("description")
        or "TikTok photo post"
    )


# --------------------------------------------------
# TIKTOK PHOTO DOWNLOADER
# --------------------------------------------------

def detect_tiktok_verification(page):
    """
    Detect common signs of TikTok's human-verification / CAPTCHA UI.
    This does not bypass the challenge; it only keeps Chrome open long
    enough for you to solve it manually when TikTok asks.
    """
    try:
        page_text = page.locator("body").inner_text(
            timeout=2000
        ).lower()
    except Exception:
        page_text = ""

    challenge_terms = (
        "verify to continue",
        "drag the puzzle piece",
        "select 2 objects",
        "captcha",
        "verification",
        "security verification",
    )

    if any(
        term in page_text
        for term in challenge_terms
    ):
        return True

    # TikTok verification widgets often arrive inside iframes.
    try:
        for frame in page.frames:
            frame_url = (
                frame.url
                or ""
            ).lower()

            if any(
                term in frame_url
                for term in (
                    "captcha",
                    "verify",
                    "challenge",
                )
            ):
                return True
    except Exception:
        pass

    return False


def try_find_tiktok_photo_payload(
    page,
    captured_json,
    post_id,
):
    """
    Look for TikTok photo data in captured API JSON first, then in
    rendered JSON scripts, then in large rendered image elements.
    """

    # 1) Captured network JSON.
    for response_url, payload in captured_json:
        candidate = find_image_post_object(
            payload,
            post_id,
        )

        if candidate is None:
            continue

        urls = image_urls_from_item(
            candidate
        )

        if urls:
            return (
                candidate,
                urls,
                response_url,
            )

    # 2) Fully rendered JSON script tags.
    try:
        scripts = page.evaluate(
            """
            () => {
                const output = [];

                for (const script of document.scripts) {
                    const text = script.textContent || "";

                    if (!text.trim()) continue;

                    if (
                        script.type === "application/json"
                        || script.id === "__UNIVERSAL_DATA_FOR_REHYDRATION__"
                        || script.id === "SIGI_STATE"
                    ) {
                        try {
                            output.push({
                                id: script.id || "",
                                data: JSON.parse(text)
                            });
                        } catch (e) {}
                    }
                }

                return output;
            }
            """
        )
    except Exception:
        scripts = []

    for script in scripts:
        candidate = find_image_post_object(
            script.get("data"),
            post_id,
        )

        if candidate is None:
            continue

        urls = image_urls_from_item(
            candidate
        )

        if urls:
            return (
                candidate,
                urls,
                "rendered page JSON",
            )

    # 3) Rendered large TikTok CDN images.
    try:
        dom_images = page.evaluate(
            """
            () => {
                const output = [];

                for (const img of document.images) {
                    const src = img.currentSrc || img.src || "";

                    if (!src.startsWith("http")) continue;

                    const width =
                        img.naturalWidth || img.width || 0;
                    const height =
                        img.naturalHeight || img.height || 0;

                    if (width >= 500 && height >= 500) {
                        output.push({
                            src,
                            width,
                            height
                        });
                    }
                }

                return output;
            }
            """
        )
    except Exception:
        dom_images = []

    seen = set()
    dom_urls = []

    for image in dom_images:
        src = image.get(
            "src",
            "",
        )

        lower_src = src.lower()

        if (
            src
            and src not in seen
            and (
                "tiktokcdn" in lower_src
                or "byteimg" in lower_src
                or "tos-" in lower_src
            )
        ):
            seen.add(src)
            dom_urls.append(src)

    if dom_urls:
        return (
            {
                "desc":
                    "TikTok photo post"
            },
            dom_urls,
            "rendered large image elements",
        )

    return (
        None,
        [],
        None,
    )


def download_tiktok_images(url, status_callback=None):
    reset_gallery_folder()

    post_id = extract_post_id(
        url
    )

    print(
        "\nTikTok photo URL detected."
    )

    print(
        "Launching persistent Chrome profile..."
    )

    captured_json = []
    captured_urls = []

    with sync_playwright() as playwright:
        context = (
            playwright.chromium.launch_persistent_context(
                user_data_dir=os.path.abspath(
                    TIKTOK_PROFILE_DIR
                ),
                channel="chrome",
                headless=False,
                args=[
                    f"--profile-directory={CHROME_PROFILE_NAME}",
                ],
                locale="en-US",
                viewport={
                    "width": 1280,
                    "height": 900,
                },
            )
        )

        try:
            pages = context.pages

            if pages:
                page = pages[0]
            else:
                page = context.new_page()

            def handle_response(response):
                response_url = (
                    response.url
                )

                interesting = (
                    "/api/" in response_url
                    or (
                        post_id
                        and post_id
                        in response_url
                    )
                )

                if not interesting:
                    return

                captured_urls.append(
                    response_url
                )

                try:
                    content_type = (
                        response.headers
                        .get(
                            "content-type",
                            "",
                        )
                        .lower()
                    )

                    if (
                        "json"
                        not in content_type
                    ):
                        return

                    payload = (
                        response.json()
                    )

                    if isinstance(
                        payload,
                        (dict, list),
                    ):
                        captured_json.append(
                            (
                                response_url,
                                payload,
                            )
                        )

                except Exception:
                    pass

            page.on(
                "response",
                handle_response,
            )

            print(
                "Opening TikTok photo post..."
            )

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.bring_to_front()

            print(
                "TikTok page loaded in persistent Chrome."
            )

            print(
                "Waiting for TikTok photo data..."
            )

            item = None
            image_urls = []
            source = None

            # TikTok sometimes exposes item/detail only after the page has
            # settled or after a little normal interaction. We retry for
            # up to about 3 minutes. If a verification puzzle appears,
            # Chrome remains open so it can be solved manually.
            verification_announced = False
            verification_was_visible = False

            for attempt in range(
                1,
                37,
            ):
                page.wait_for_timeout(
                    5000
                )

                (
                    item,
                    image_urls,
                    source,
                ) = try_find_tiktok_photo_payload(
                    page,
                    captured_json,
                    post_id,
                )

                if image_urls:
                    break

                verification_visible = (
                    detect_tiktok_verification(
                        page
                    )
                )

                if verification_visible:
                    verification_was_visible = True

                    if not verification_announced:
                        print()
                        print(
                            "TikTok verification detected."
                        )
                        print(
                            "If a puzzle is visible in Chrome, "
                            "solve it manually."
                        )
                        print(
                            "The bot will keep waiting automatically..."
                        )
                        print()

                        if status_callback:
                            try:
                                status_callback(
                                    "🧩 TikTok verification required.\n\n"
                                    "Please solve the puzzle in the Chrome "
                                    "window.\n\n"
                                    "I’ll keep waiting and continue "
                                    "automatically."
                                )
                            except Exception:
                                pass

                        verification_announced = True

                elif (
                    verification_was_visible
                    and verification_announced
                ):
                    print(
                        "TikTok verification appears to be cleared. "
                        "Continuing..."
                    )

                    if status_callback:
                        try:
                            status_callback(
                                "✅ TikTok verification cleared.\n\n"
                                "Continuing the download..."
                            )
                        except Exception:
                            pass

                    verification_was_visible = False

                # Normal, harmless interaction to encourage lazy-loaded
                # content and API requests. No login button is clicked.
                try:
                    page.bring_to_front()

                    page.mouse.move(
                        640,
                        450,
                    )

                    if attempt % 2:
                        page.mouse.wheel(
                            0,
                            450,
                        )
                    else:
                        page.mouse.wheel(
                            0,
                            -300,
                        )

                except Exception:
                    pass

                # Halfway through, perform a soft reload once. If a
                # verification challenge was solved, this often causes
                # TikTok to issue a fresh item/detail request.
                if (
                    attempt in (12, 24)
                    and not image_urls
                ):
                    try:
                        print(
                            "Refreshing TikTok post once "
                            "to request fresh photo data..."
                        )

                        page.reload(
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )

                        page.bring_to_front()

                    except Exception as error:
                        print(
                            "TikTok refresh was skipped:",
                            error,
                        )

            final_url = (
                page.url
            )

            print(
                f"Final browser URL: "
                f"{final_url}"
            )

            print(
                f"Captured "
                f"{len(captured_json)} "
                f"JSON response(s)."
            )

            if not image_urls:
                print()
                print(
                    "No TikTok photo images "
                    "could be extracted."
                )

                print(
                    "Captured network URLs:"
                )

                for captured_url in (
                    captured_urls[:20]
                ):
                    # Keep terminal output readable.
                    clean_url = (
                        captured_url
                        .split("?")[0]
                    )

                    print(
                        clean_url
                    )

                raise RuntimeError(
                    "TikTok did not expose the photo data "
                    "within the extended waiting period. If a verification "
                    "puzzle appeared, solve it and send the link again."
                )

            image_urls = list(
                dict.fromkeys(
                    image_urls
                )
            )

            clean_source = source

            if (
                isinstance(source, str)
                and source.startswith("http")
            ):
                clean_source = source.split("?")[0]

            print(
                f"TikTok photo data found via: "
                f"{clean_source}"
            )

            print(
                f"Found {len(image_urls)} "
                f"TikTok image(s)."
            )

            image_files = []

            for index, image_url in enumerate(
                image_urls,
                start=1,
            ):
                response = (
                    context.request.get(
                        image_url,
                        headers={
                            "Referer": final_url,
                        },
                        timeout=30000,
                    )
                )

                if not response.ok:
                    raise RuntimeError(
                        f"TikTok image {index} "
                        f"failed with HTTP "
                        f"{response.status}."
                    )

                content_type = (
                    response.headers
                    .get(
                        "content-type",
                        "",
                    )
                )

                extension = (
                    extension_from_url_or_type(
                        image_url,
                        content_type,
                    )
                )

                filepath = os.path.join(
                    GALLERY_FOLDER,
                    f"tiktok_"
                    f"{post_id or 'post'}_"
                    f"{index:02d}"
                    f"{extension}",
                )

                with open(
                    filepath,
                    "wb",
                ) as output_file:
                    output_file.write(
                        response.body()
                    )

                image_files.append(
                    filepath
                )

                print(
                    f"Downloaded TikTok image "
                    f"{index} of "
                    f"{len(image_urls)}."
                )

            title = (
                description_from_item(
                    item
                )
            )

            return (
                image_files,
                title,
            )

        finally:
            context.close()

# --------------------------------------------------
# TIKTOK VIDEO FALLBACK - PLAYWRIGHT
# --------------------------------------------------

def find_video_object(data, post_id=None):
    if isinstance(data, dict):
        object_id = (
            data.get("id")
            or data.get("aweme_id")
            or data.get("itemId")
        )

        if isinstance(data.get("video"), dict):
            if (
                not post_id
                or not object_id
                or str(object_id) == str(post_id)
            ):
                return data

        for value in data.values():
            found = find_video_object(
                value,
                post_id,
            )

            if found is not None:
                return found

    elif isinstance(data, list):
        for value in data:
            found = find_video_object(
                value,
                post_id,
            )

            if found is not None:
                return found

    return None


def first_video_url_from_item(item):
    video = item.get("video")

    if not isinstance(video, dict):
        return None

    # First try TikTok's normal playback/download addresses.
    candidates = [
        video.get("playAddr"),
        video.get("play_addr"),
        video.get("downloadAddr"),
        video.get("download_addr"),
    ]

    for candidate in candidates:
        url = first_url_from_object(
            candidate
        )

        if url:
            return url

    # Some responses store playback URLs inside bitrate information.
    bitrate_info = (
        video.get("bitrateInfo")
        or video.get("bit_rate")
        or video.get("bitrate_info")
        or []
    )

    if isinstance(bitrate_info, list):
        for entry in bitrate_info:
            if not isinstance(entry, dict):
                continue

            play_addr = (
                entry.get("PlayAddr")
                or entry.get("playAddr")
                or entry.get("play_addr")
            )

            url = first_url_from_object(
                play_addr
            )

            if url:
                return url

    return None


def try_find_tiktok_video_payload(
    page,
    captured_json,
    post_id,
):
    # Method 1:
    # Look through JSON captured from TikTok network requests.
    for response_url, payload in captured_json:
        candidate = find_video_object(
            payload,
            post_id,
        )

        if candidate is None:
            continue

        video_url = first_video_url_from_item(
            candidate
        )

        if video_url:
            return (
                candidate,
                video_url,
                response_url,
            )

    # Method 2:
    # Look through JSON embedded in the rendered page.
    try:
        scripts = page.evaluate(
            """
            () => {
                const output = [];

                for (const script of document.scripts) {
                    const text = script.textContent || "";

                    if (!text.trim()) {
                        continue;
                    }

                    if (
                        script.type === "application/json"
                        || script.id === "__UNIVERSAL_DATA_FOR_REHYDRATION__"
                        || script.id === "SIGI_STATE"
                    ) {
                        try {
                            output.push({
                                id: script.id || "",
                                data: JSON.parse(text)
                            });
                        } catch (e) {
                        }
                    }
                }

                return output;
            }
            """
        )

    except Exception:
        scripts = []

    for script in scripts:
        candidate = find_video_object(
            script.get("data"),
            post_id,
        )

        if candidate is None:
            continue

        video_url = first_video_url_from_item(
            candidate
        )

        if video_url:
            return (
                candidate,
                video_url,
                "rendered page JSON",
            )

    # Method 3:
    # Last resort: inspect the actual HTML5 video element.
    try:
        dom_video_url = page.evaluate(
            """
            () => {
                const videos =
                    document.querySelectorAll("video");

                for (const video of videos) {
                    const candidates = [
                        video.currentSrc,
                        video.src
                    ];

                    for (const src of candidates) {
                        if (
                            src
                            && src.startsWith("http")
                        ) {
                            return src;
                        }
                    }

                    const source =
                        video.querySelector("source");

                    if (
                        source
                        && source.src
                        && source.src.startsWith("http")
                    ) {
                        return source.src;
                    }
                }

                return null;
            }
            """
        )

    except Exception:
        dom_video_url = None

    if dom_video_url:
        return (
            {
                "desc": "TikTok video",
            },
            dom_video_url,
            "rendered video element",
        )

    return (
        None,
        None,
        None,
    )


def download_tiktok_video_with_playwright(
    url,
    status_callback=None,
):
    post_id = extract_post_id(
        url
    )

    print()
    print(
        "TikTok video fallback activated."
    )
    print(
        "Launching persistent Chrome profile..."
    )

    captured_json = []
    captured_urls = []
    captured_media_candidates = []

    with sync_playwright() as playwright:
        context = (
            playwright.chromium.launch_persistent_context(
                user_data_dir=os.path.abspath(
                    TIKTOK_PROFILE_DIR
                ),
                channel="chrome",
                headless=False,
                args=[
                    f"--profile-directory={CHROME_PROFILE_NAME}",
                ],
                locale="en-US",
                viewport={
                    "width": 1280,
                    "height": 900,
                },
            )
        )

        try:
            def get_active_page():
                available_pages = [
                    p
                    for p in context.pages
                    if not p.is_closed()
                ]
            
                if available_pages:
                    return available_pages[-1]
            
                return context.new_page()
            
            
            page = get_active_page()

            def handle_response(response):
                response_url = response.url
            
                try:
                    content_type = (
                        response.headers.get(
                            "content-type",
                            "",
                        ).lower()
                    )
                except Exception:
                    content_type = ""
            
                # ------------------------------------------
                # Capture actual TikTok video/media streams
                # ------------------------------------------
                looks_like_video = (
                    content_type.startswith("video/")
                    or "video_mp4" in response_url.lower()
                    or ".mp4" in response_url.lower()
                    or "/video/tos/" in response_url.lower()
                    or "mime_type=video" in response_url.lower()
                )
            
                if looks_like_video:
                    try:
                        content_length = int(
                            response.headers.get(
                                "content-length",
                                "0",
                            )
                        )
                    except Exception:
                        content_length = 0
                
                    # TikTok often serves media using HTTP 206.
                    # Content-Range may reveal the full file size.
                    content_range = response.headers.get(
                        "content-range",
                        "",
                    )
                
                    total_size = content_length
                
                    if "/" in content_range:
                        try:
                            range_total = (
                                content_range
                                .split("/")[-1]
                                .strip()
                            )
                
                            if range_total.isdigit():
                                total_size = max(
                                    total_size,
                                    int(range_total),
                                )
                        except Exception:
                            pass
                
                    already_seen = any(
                        candidate["url"] == response_url
                        for candidate in captured_media_candidates
                    )
                
                    if not already_seen:
                        captured_media_candidates.append(
                            {
                                "url": response_url,
                                "size": total_size,
                                "content_type": content_type,
                            }
                        )
                
                        print(
                            "Captured possible TikTok "
                            f"video stream "
                            f"({total_size / 1024 / 1024:.2f} MB)."
        )
            
                # ------------------------------------------
                # Capture useful TikTok JSON API responses
                # ------------------------------------------
                interesting = (
                    "/api/" in response_url
                    or (
                        post_id
                        and post_id in response_url
                    )
                )
            
                if not interesting:
                    return
            
                captured_urls.append(
                    response_url
                )
            
                try:
                    if "json" not in content_type:
                        return
            
                    payload = response.json()
            
                    if isinstance(
                        payload,
                        (dict, list),
                    ):
                        captured_json.append(
                            (
                                response_url,
                                payload,
                            )
                        )
            
                except Exception:
                    pass

            context.on(
                "response",
                handle_response,
            )

            print(
                "Opening TikTok video post..."
            )

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.bring_to_front()

            print(
                "TikTok video page loaded."
            )
            print(
                "Waiting for video data..."
            )

            item = None
            video_url = None
            source = None

            verification_announced = False
            verification_was_visible = False

            for attempt in range(
                1,
                37,
            ):
                time.sleep(
                    5
                )
                
                page = get_active_page()

                (
                    item,
                    video_url,
                    source,
                ) = try_find_tiktok_video_payload(
                    page,
                    captured_json,
                    post_id,
                )
                # Don't immediately accept TikTok's first MP4.
                # Small intro/logo clips can appear before the real post.
                if (
                    not video_url
                    and captured_media_candidates
                    and attempt >= 3
                ):
                    best_candidate = max(
                        captured_media_candidates,
                        key=lambda candidate: candidate["size"],
                    )
                
                    # Ignore very small TikTok UI/logo videos.
                    # 300 KB is intentionally conservative.
                    if best_candidate["size"] >= 300 * 1024:
                        video_url = best_candidate["url"]
                        source = "largest browser video stream"
                
                        if item is None:
                            item = {
                                "desc": "TikTok video",
                            }

                if video_url:
                    break

                verification_visible = (
                    detect_tiktok_verification(
                        page
                    )
                )

                if verification_visible:
                    verification_was_visible = True

                    if not verification_announced:
                        print()
                        print(
                            "TikTok verification detected."
                        )
                        print(
                            "If a puzzle is visible in Chrome, "
                            "solve it manually."
                        )
                        print(
                            "The bot will keep waiting automatically..."
                        )
                        print()

                        if status_callback:
                            try:
                                status_callback(
                                    "🧩 TikTok verification required.\n\n"
                                    "Please solve the puzzle in the Chrome "
                                    "window.\n\n"
                                    "I'll keep waiting and continue "
                                    "automatically."
                                )

                            except Exception:
                                pass

                        verification_announced = True

                elif (
                    verification_was_visible
                    and verification_announced
                ):
                    print(
                        "TikTok verification appears "
                        "to be cleared. Continuing..."
                    )

                    if status_callback:
                        try:
                            status_callback(
                                "✅ TikTok verification cleared.\n\n"
                                "Continuing the download..."
                            )

                        except Exception:
                            pass

                    verification_was_visible = False

                # Small harmless interaction to encourage
                # TikTok to finish lazy-loading the page.
                try:
                    page.bring_to_front()

                    page.mouse.move(
                        640,
                        450,
                    )

                    if attempt % 2:
                        page.mouse.wheel(
                            0,
                            350,
                        )
                    else:
                        page.mouse.wheel(
                            0,
                            -250,
                        )

                except Exception:
                    pass

                # Two soft refreshes during the extended wait.
                

            page = get_active_page()
            final_url = page.url

            print(
                f"Final browser URL: "
                f"{final_url}"
            )

            print(
                f"Captured "
                f"{len(captured_json)} "
                f"JSON response(s)."
            )

            if not video_url:
                print()
                print(
                    "No TikTok video URL could be extracted."
                )

                print(
                    "Captured network endpoints:"
                )

                for captured_url in captured_urls[:20]:
                    print(
                        captured_url.split("?")[0]
                    )

                raise RuntimeError(
                    "TikTok did not expose the video data "
                    "within the extended waiting period. "
                    "If a verification puzzle appeared, "
                    "solve it and send the link again."
                )

            clean_source = source

            if (
                isinstance(source, str)
                and source.startswith("http")
            ):
                clean_source = (
                    source.split("?")[0]
                )
                
                if captured_media_candidates:
                    print(
                        "Browser media candidates:"
                    )
                
                    for candidate in sorted(
                        captured_media_candidates,
                        key=lambda candidate: candidate["size"],
                        reverse=True,
                    ):
                        print(
                            "  "
                            f"{candidate['size'] / 1024 / 1024:.2f} MB "
                            f"- {candidate['content_type']}"
                        )

            print(
                f"TikTok video data found via: "
                f"{clean_source}"
            )

            title = description_from_item(
                item
            )

            os.makedirs(
                DOWNLOAD_FOLDER,
                exist_ok=True,
            )

            filepath = os.path.join(
                DOWNLOAD_FOLDER,
                (
                    f"TikTok video "
                    f"[{post_id or 'post'}].mp4"
                ),
            )

            print(
                "Downloading TikTok video..."
            )

            response = context.request.get(
                video_url,
                headers={
                    "Referer": final_url,
                },
                timeout=60000,
            )

            if not response.ok:
                raise RuntimeError(
                    "TikTok video download failed "
                    f"with HTTP {response.status}."
                )

            with open(
                filepath,
                "wb",
            ) as output_file:
                output_file.write(
                    response.body()
                )

            print(
                "TikTok video downloaded successfully."
            )

            return (
                [filepath],
                title,
            )

        finally:
            context.close()
# --------------------------------------------------
# DOWNLOAD ROUTER
# --------------------------------------------------

def download_media(
    url,
    status_callback=None,
):
    # TikTok photo posts always use
    # our Playwright photo extractor.
    if is_tiktok_photo_url(url):
        return download_tiktok_images(
            url,
            status_callback=status_callback,
        )

    try:
        # First choice for normal videos:
        # YouTube, Instagram video, TikTok video, etc.
        return download_with_ytdlp(
            url
        )

    except Exception as ytdlp_error:
        print()
        print(
            "yt-dlp could not handle this link:"
        )
        print(
            ytdlp_error
        )

        # Instagram image/carousel fallback.
        if is_instagram_url(url):
            return download_instagram_images(
                url
            )

        # TikTok video fallback.
        if is_tiktok_video_url(url):
            print()
            print(
                "Switching to TikTok "
                "Playwright video fallback..."
            )

            if status_callback:
                try:
                    status_callback(
                        "⚙️ TikTok needs the browser fallback.\n\n"
                        "Opening Chrome and trying another method..."
                    )

                except Exception:
                    pass

            return download_tiktok_video_with_playwright(
                url,
                status_callback=status_callback,
            )
        
        # X fallback.
        if is_twitter_url(url):
            print()
            print(
                "Switching to X/Twitter "
                "gallery-dl image fallback..."
            )
        
            if status_callback:
                try:
                    status_callback(
                        "🖼️ X/Twitter image post detected.\n\n"
                        "Trying image downloader..."
                    )
                except Exception:
                    pass
        
            return download_twitter_images(
                url
            )

        # Unknown failure:
        # preserve the original yt-dlp error.
        raise


# --------------------------------------------------
# SEND ONE MEDIA FILE
# --------------------------------------------------

async def send_media_file(
    update,
    filepath,
    title,
    index,
    total_items,
):
    filesize = os.path.getsize(
        filepath
    )

    size_mb = (
        filesize / (1024 * 1024)
    )

    if size_mb > 49:
        await update.message.reply_text(
            f"⚠️ Item {index} is "
            f"{size_mb:.1f} MB and is too "
            f"large for the bot to upload."
        )
        return

    caption = (
        f"📥 {title}"
    )

    if total_items > 1:
        caption += (
            f"\n\n"
            f"Item {index} of "
            f"{total_items}"
        )

    extension = get_extension(
        filepath
    )

    with open(
        filepath,
        "rb",
    ) as media_file:
        if extension in (
            ".mp4",
            ".mov",
            ".m4v",
            ".webm",
        ):
            await update.message.reply_video(
                video=media_file,
                caption=caption,
                supports_streaming=True,
                write_timeout=120,
                read_timeout=120,
                connect_timeout=30,
            )

        elif extension in (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        ):
            await update.message.reply_photo(
                photo=media_file,
                caption=caption,
                write_timeout=120,
                read_timeout=120,
                connect_timeout=30,
            )

        else:
            await update.message.reply_document(
                document=media_file,
                caption=caption,
                write_timeout=120,
                read_timeout=120,
                connect_timeout=30,
            )


# --------------------------------------------------
# SEND IMAGE ALBUM
# --------------------------------------------------

async def send_image_album(
    update,
    filepaths,
    title,
):
    for batch_start in range(
        0,
        len(filepaths),
        10,
    ):
        batch = filepaths[
            batch_start:batch_start + 10
        ]

        media_group = []
        open_files = []

        try:
            for index, filepath in enumerate(
                batch
            ):
                media_file = open(
                    filepath,
                    "rb",
                )

                open_files.append(
                    media_file
                )

                caption = None

                if index == 0:
                    overall_start = (
                        batch_start + 1
                    )

                    overall_end = (
                        batch_start
                        + len(batch)
                    )

                    caption = (
                        f"📥 {title}\n\n"
                        f"Images "
                        f"{overall_start}-"
                        f"{overall_end} "
                        f"of {len(filepaths)}"
                    )

                media_group.append(
                    InputMediaPhoto(
                        media=media_file,
                        caption=caption,
                    )
                )

            await update.message.reply_media_group(
                media=media_group,
                write_timeout=120,
                read_timeout=120,
                connect_timeout=30,
            )

        finally:
            for media_file in open_files:
                try:
                    media_file.close()

                except Exception:
                    pass


# --------------------------------------------------
# HANDLE URL
# --------------------------------------------------

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_allowed(update):
        await update.message.reply_text(
            "⛔ This is a private bot."
        )
        return

    url = (
        update.message.text.strip()
    )

    if not (
        url.startswith("http://")
        or url.startswith("https://")
    ):
        await update.message.reply_text(
            "🔗 Please send me a valid URL."
        )
        return

    status = (
        await update.message.reply_text(
            "⬇️ Downloading...\n\n"
            "Please wait."
        )
    )

    filepaths = []

    try:
        loop = asyncio.get_running_loop()

        def status_callback(text):
            future = asyncio.run_coroutine_threadsafe(
                status.edit_text(text),
                loop,
            )

            # Do not block the Playwright thread waiting for Telegram.
            # Any Telegram-side error will simply be ignored here.
            def consume_result(done_future):
                try:
                    done_future.result()
                except Exception:
                    pass

            future.add_done_callback(
                consume_result
            )

        filepaths, title = (
            await asyncio.to_thread(
                download_media,
                url,
                status_callback,
            )
        )

        total_size = sum(
            os.path.getsize(
                filepath
            )
            for filepath in filepaths
        )

        total_size_mb = (
            total_size / (1024 * 1024)
        )

        await status.edit_text(
            f"✅ Download complete!\n\n"
            f"📥 {title}\n"
            f"📦 {total_size_mb:.1f} MB\n"
            f"📁 {len(filepaths)} media file(s)\n\n"
            f"Uploading to Telegram..."
        )

        total_items = len(
            filepaths
        )

        image_files = [
            filepath
            for filepath in filepaths
            if is_image_file(filepath)
        ]

        if (
            total_items > 1
            and len(image_files)
            == total_items
        ):
            print(
                f"Sending {total_items} images "
                f"as a Telegram album..."
            )

            await send_image_album(
                update,
                image_files,
                title,
            )

        else:
            print(
                f"Sending {total_items} media "
                f"item(s) individually..."
            )

            for index, filepath in enumerate(
                filepaths,
                start=1,
            ):
                await send_media_file(
                    update,
                    filepath,
                    title,
                    index,
                    total_items,
                )

        await status.delete()

    except Exception as error:
        print(
            "\nDOWNLOAD ERROR:"
        )
        print(
            error
        )

        try:
            await status.edit_text(
                "❌ I couldn't download that link.\n\n"
                "Check the Command Prompt for the error."
            )

        except Exception:
            pass

    finally:
        for filepath in filepaths:
            if filepath.startswith(
                DOWNLOAD_FOLDER
            ):
                if os.path.exists(
                    filepath
                ):
                    try:
                        os.remove(
                            filepath
                        )

                    except Exception as cleanup_error:
                        print(
                            "Could not delete temporary file:",
                            cleanup_error,
                        )

        if os.path.exists(
            GALLERY_FOLDER
        ):
            try:
                shutil.rmtree(
                    GALLERY_FOLDER
                )

            except Exception as cleanup_error:
                print(
                    "Could not delete gallery folder:",
                    cleanup_error,
                )

            os.makedirs(
                GALLERY_FOLDER,
                exist_ok=True,
            )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    if (
        len(sys.argv) > 1
        and sys.argv[1]
        == "--import-chrome-profile"
    ):
        import_existing_chrome_profile()
        return

    if (
        len(sys.argv) > 1
        and sys.argv[1]
        == "--tiktok-login"
    ):
        prepare_tiktok_login()
        return

    print("=" * 50)
    print("Telegram Media Bot")
    print("=" * 50)

    print(
        f"Authorized user: "
        f"{ALLOWED_USER_ID}"
    )

    print(
        f"Download folder: "
        f"{DOWNLOAD_FOLDER}"
    )

    print(
        f"Gallery folder: "
        f"{GALLERY_FOLDER}"
    )

    print(
        f"TikTok Chrome profile: "
        f"{TIKTOK_PROFILE_DIR}"
    )

    print(
        f"Imported from Chrome profile: "
        f"{CHROME_PROFILE_NAME}"
    )

    if os.path.exists(
        INSTAGRAM_COOKIES
    ):
        print(
            "Instagram cookies: found"
        )
    else:
        print(
            "Instagram cookies: NOT FOUND"
        )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_message,
        )
    )

    print(
        "\nBot is running."
    )

    print(
        "Send a media URL through Telegram."
    )

    print(
        "Press Ctrl+C to stop.\n"
    )

    app.run_polling()


if __name__ == "__main__":
    main()
