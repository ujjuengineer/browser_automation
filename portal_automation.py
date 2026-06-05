"""
Government Indexing Portal Automation Script
=============================================
Uses Playwright (sync API) to automate volume index creation and submission.

Configuration is read from variables at the top of the script and from
a config.txt file inside the provided folder path.

Usage:
    python portal_automation.py

Requirements:
    pip install playwright
    playwright install chromium
"""

import sys
import logging
from pathlib import Path

from playwright.sync_api import (
    sync_playwright, Page, Browser,
    TimeoutError as PlaywrightTimeoutError,
)

# ─────────────────────────────────────────────
#  TOP-LEVEL CONFIGURATION  (edit these values)
# ─────────────────────────────────────────────
LOGIN_URL: str    = "https://enibandhan.bihar.gov.in/users/login"   # Login page URL
FOLDER_PATH: str  = "/Users/ujjwalkumar/Desktop/VOL-13-1961-SP-PDF-DONE"    # Folder with config.txt + PDFs
HEADLESS: bool    = False         # Keep browser visible
LOGIN_TIMEOUT_MS: int = 120_000   # 2 min – time allowed for manual login + CAPTCHA
PAGE_TIMEOUT_MS: int  =  30_000   # Default timeout for page interactions
NAV_TIMEOUT_MS: int   =  60_000   # Timeout for full-page navigations

# Selectors used across steps
NEW_REQ_BTN:       str = "#new_req_btn"
OFFICE_DISTRICT:   str = "#office_district" # checked
OFFICE_SRO:        str = "#office_sro"      # checked
VOLUME_DISTRICT:   str = "#volume_district" # checked
VOLUME_SRO:        str = "#volume_sro"      # checked
VOLUME_NO:         str = "#volume_no"       # checked
VOLUME_YEAR:       str = "#volume_year"     # checked
BOOK_TYPE_SELECT:  str = "#bookType"        # <select> for book type, checked
ADD_VOLUME_BTN:    str = "#addVolumeBtn"    # checked
DEED_NO:           str = "#deed_no"         # checked
PRESENTATION_YEAR:  str = "#presentation_year"  # checked    # fixed this bug
ADD_INDEX_BTN:     str = "#addindexBtn"         # checked
SUBMIT_VOLUME_BTN: str = "#submitvolume"        # checked

# ─────────────────────────────────────────────
#  LOGGING SETUP
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("portal_automation.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#  STEP 1 – LOGIN
# ═══════════════════════════════════════════

def login(page: Page) -> None:
    """
    Open the login page and wait for the user to manually enter credentials
    and solve the CAPTCHA.  Automation resumes only after a successful login
    is detected (#new_req_btn becomes visible after login).
    """
    log.info("Navigating to login page: %s", LOGIN_URL)
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    log.info(
        "⏳  Please enter your credentials and solve the CAPTCHA in the browser window.\n"
        "    Waiting up to %d seconds for successful login…",
        LOGIN_TIMEOUT_MS // 1000,
    )

    # Wait until #new_req_btn appears — it only exists after a successful login
    try:
        page.wait_for_function(
            "() => document.querySelector('#new_req_btn') !== null",
            timeout=LOGIN_TIMEOUT_MS,
        )
        log.info("✅  Login detected. Current URL: %s", page.url)
    except PlaywrightTimeoutError:
        log.error("❌  Login not detected within %d seconds. Exiting.", LOGIN_TIMEOUT_MS // 1000)
        raise SystemExit(1)


# ═══════════════════════════════════════════
#  STEP 2a – READ VOLUME CONFIG
# ═══════════════════════════════════════════

def read_volume_data(folder_path: str) -> dict:
    """
    Read config.txt from *folder_path* and return a dict of key=value pairs.

    Expected keys (all strings):
        office_district, office_sro, volume_district, volume_sro,
        volume_no, volume_year, book_type, radio
    """
    config_file = Path(folder_path) / "config.txt"
    if not config_file.exists():
        log.error("❌  config.txt not found at: %s", config_file)
        raise FileNotFoundError(f"config.txt not found: {config_file}")

    log.info("Reading volume configuration from: %s", config_file)
    data: dict = {}

    with config_file.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue                        # skip blank lines and comments
            if "=" not in line:
                log.warning("Line %d skipped (no '='): %s", line_no, line)
                continue
            key, _, value = line.partition("=")
            data[key.strip()] = value.strip()
            log.debug("  Config key '%s' = '%s'", key.strip(), value.strip())

    # FIX Bug 1: volume_year added to required keys
    required_keys = {
        "office_district", "office_sro", "volume_district",
        "volume_sro", "volume_no", "volume_year", "book_type", "radio",
    }
    missing = required_keys - data.keys()
    if missing:
        log.error("❌  Missing required config keys: %s", missing)
        raise ValueError(f"config.txt is missing keys: {missing}")

    log.info("✅  Volume configuration loaded successfully.")
    return data


# ═══════════════════════════════════════════
#  STEP 2b – CREATE VOLUME INDEX
# ═══════════════════════════════════════════

def _fill_text_field(page: Page, selector: str, value: str, label: str) -> None:
    """Clear and fill a text / input field; raise if the element is absent."""
    locator = page.locator(selector)
    locator.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    locator.clear()
    locator.fill(value)
    log.info("  Filled %-22s → '%s'", label, value)


def _select_option(page: Page, selector: str, value: str, label: str) -> None:
    """Select an <option> in a <select> element by its value attribute."""
    locator = page.locator(selector)
    locator.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    locator.select_option(value=value)
    log.info("  Selected %-21s → '%s'", label, value)


# ERROR in this 
# def _click_radio(page: Page, value: str) -> None:
#     """
#     Click the radio button whose value matches *value* (case-insensitive).
#     Tries common radio patterns: input[type='radio'][value='…']
#     """
#     selector = f"input[type='radio'][value='{value}']"
#     locator = page.locator(selector)
#     try:
#         locator.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
#         locator.check()
#         log.info("  Checked radio button          → value='%s'", value)
#     except PlaywrightTimeoutError:
#         # Fall back: try case-insensitive search through all radio inputs
#         log.warning("Radio value '%s' not found directly; trying case-insensitive fallback.", value)
#         radios = page.locator("input[type='radio']")
#         count = radios.count()
#         for i in range(count):
#             radio = radios.nth(i)
#             if radio.get_attribute("value", timeout=2000).lower() == value.lower():
#                 radio.check()
#                 log.info("  Checked radio (fallback)       → value='%s'", value)
#                 return
#         raise ValueError(f"No radio button found with value='{value}'")
    

def _click_radio(page: Page, value: str) -> None:
    """
    Click the radio button whose value matches *value*.
    Supports:
        radio=yes
        radio=no
    """

    radio_map = {
        "yes": "#isvolumeforwardedY",
        "no": "#isvolumeforwardedN"
    }

    selector = radio_map.get(value.lower())

    if not selector:
        raise ValueError(f"Invalid radio value '{value}'. Expected yes or no.")

    locator = page.locator(selector)

    try:
        locator.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
        locator.check()
        log.info("  Checked radio button          → value='%s'", value)

    except PlaywrightTimeoutError:
        log.error(
            "Radio button for value '%s' was not found. Selector used: %s",
            value,
            selector
        )
        raise


def create_volume(page: Page, data: dict) -> None:
    """
    Click 'New Request', fill in all volume fields from *data*, and save.
    Waits for navigation to the Index Details page before returning.
    """
    log.info("─── Step 2: Create New Volume Index ───")

    # 2.1  Click the 'New Request' button
    log.info("Clicking 'New Request' button (#new_req_btn)…")
    new_req = page.locator(NEW_REQ_BTN)
    new_req.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    new_req.click()

    # 2.2  Wait for the volume-creation form to appear
    log.info("Waiting for volume form to load…")
    page.locator(OFFICE_DISTRICT).wait_for(state="visible", timeout=NAV_TIMEOUT_MS)

    # 2.3  Fill all text fields (FIX Bug 2: volume_year now filled here)
    _fill_text_field(page, OFFICE_DISTRICT, data["office_district"], "office_district")
    _fill_text_field(page, OFFICE_SRO,      data["office_sro"],      "office_sro")
    _fill_text_field(page, VOLUME_DISTRICT, data["volume_district"], "volume_district")
    _fill_text_field(page, VOLUME_SRO,      data["volume_sro"],      "volume_sro")
    _fill_text_field(page, VOLUME_NO,       data["volume_no"],       "volume_no")
    _fill_text_field(page, VOLUME_YEAR,     data["volume_year"],     "volume_year")

    # 2.4  Select book type from dropdown
    _select_option(page, BOOK_TYPE_SELECT, data["book_type"], "book_type")

    # 2.5  Select radio button (yes / no)
    _click_radio(page, data["radio"])

    # 2.6  Click Save / Add Volume
    log.info("Clicking 'Save' button (#addVolumeBtn)…")
    # save_btn = page.locator(ADD_VOLUME_BTN)
    # save_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    # with page.expect_navigation(wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS):
    #     save_btn.click()
    save_btn = page.locator(ADD_VOLUME_BTN)
    save_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    save_btn.click()

    page.locator(DEED_NO).wait_for(
        state="visible",
        timeout=NAV_TIMEOUT_MS
    )
    log.info("✅  Volume created. Index Details form loaded.")
    

# ═══════════════════════════════════════════
#  STEP 3a – READ PDF FILES
# ═══════════════════════════════════════════

def read_pdf_files(folder_path: str) -> list[Path]:
    """
    Return a sorted list of PDF file paths from *folder_path*.
    Sorting is ascending by the numeric stem when possible, else lexicographic.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        log.error("❌  Folder not found: %s", folder)
        raise NotADirectoryError(f"Not a directory: {folder}")

    pdf_files = sorted(
        folder.glob("*.pdf"),
        key=lambda p: (int(p.stem) if p.stem.isdigit() else float("inf"), p.stem),
    )

    if not pdf_files:
        log.warning("⚠️  No PDF files found in folder: %s", folder)
    else:
        log.info("Found %d PDF file(s) in '%s'.", len(pdf_files), folder)
        for f in pdf_files:
            log.debug("  %s", f.name)

    return pdf_files


# ═══════════════════════════════════════════
#  STEP 3b – CREATE INDEX ENTRIES
# ═══════════════════════════════════════════

def _read_volume_year(page: Page) -> str:
    """
    Extract the year value displayed inside #volume_year.

    The DOM contains a contenteditable=false div with the year value:
        <div contenteditable="false">1961</div>
    We grab the text content of that div.
    """
    year_locator = page.locator(f"{VOLUME_YEAR} div[contenteditable='false']")
    try:
        year_locator.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
        year = year_locator.inner_text().strip()
        log.info("  Read volume_year from page     → '%s'", year)
        return year
    except PlaywrightTimeoutError:
        # Fallback: try input value
        log.warning("contenteditable year div not found; trying input value fallback.")
        fallback = page.locator(VOLUME_YEAR)
        fallback.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
        year = fallback.input_value().strip()
        log.info("  Read volume_year (fallback)    → '%s'", year)
        return year


def create_indexes(page: Page, pdf_files: list[Path]) -> None:
    """
    For every PDF in *pdf_files*:
      1. Extract deed number from the file name.
      2. Fill deed_no field with deed number.
      3. Append the volume year to deed_no field (re-enter combined value).
      4. Click addindexBtn to create the index entry.
    """
    log.info("─── Step 3: Create Index Entries (%d file(s)) ───", len(pdf_files))

    if not pdf_files:
        log.warning("No PDF files to process. Skipping index creation.")
        return

    # FIX Bug 3: read volume_year ONCE before the loop — it never changes
    volume_year = _read_volume_year(page)

    for idx, pdf_path in enumerate(pdf_files, start=1):
        deed_no = pdf_path.stem          # e.g. "1001" from "1001.pdf"
        log.info("[%d/%d] Processing: %s  →  deed_no='%s'",
                 idx, len(pdf_files), pdf_path.name, deed_no)

        # 3a  Fill deed_no with extracted value
        deed_field = page.locator(DEED_NO)
        deed_field.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
        deed_field.clear()
        deed_field.fill(deed_no)
        log.info("  Filled deed_no                 → '%s'", deed_no)

        # FIX Bug 4
        # 3b Fill presentation year
        presentation_field = page.locator(PRESENTATION_YEAR)
        presentation_field.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
        presentation_field.clear()
        presentation_field.fill(volume_year)

        log.info(
            "  Filled presentation_year      → '%s'",
            volume_year
        )

        # buggy code block 

        # deed_field = page.locator(DEED_NO)
        # combined_value = f"{deed_no}{volume_year}"
        # deed_field.clear()
        # deed_field.fill(combined_value)
        # log.info("  Updated deed_no (with year)    → '%s'", combined_value)

        # 3c  Click 'Add Index' button
        log.info("  Clicking #addindexBtn…")
        add_idx_btn = page.locator(ADD_INDEX_BTN)
        add_idx_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
        add_idx_btn.click()

        # 3d  Wait for the page to accept the entry (button becomes clickable again)
        page.wait_for_timeout(800)   # brief pause for server round-trip
        page.locator(ADD_INDEX_BTN).wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

        log.info("  ✅  Index entry created for '%s'.", pdf_path.name)

    log.info("✅  All %d index entries created.", len(pdf_files))


# ═══════════════════════════════════════════
#  STEP 4 – SUBMIT VOLUME
# ═══════════════════════════════════════════

def submit_volume(page: Page) -> None:
    """Click the 'Submit Volume' button and wait for confirmation."""
    log.info("─── Step 4: Submit Volume ───")

    submit_btn = page.locator(SUBMIT_VOLUME_BTN)
    submit_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    log.info("Clicking #submitvolume…")
    submit_btn.click()

    # Wait for any of: a success alert, a URL change, or a success element
    try:
        page.wait_for_function(
            """() =>
                document.querySelector('.success-message, .alert-success, #success_msg')
                || window.location.href.includes('success')
                || window.location.href.includes('submitted')
            """,
            timeout=NAV_TIMEOUT_MS,
        )
        log.info("✅  Volume submitted successfully.")
    except PlaywrightTimeoutError:
        # Non-fatal: the portal might not have an obvious success signal
        log.warning(
            "⚠️  No explicit success indicator detected after submit, "
            "but the click was sent. Please verify in the browser."
        )


# ═══════════════════════════════════════════
#  MAIN ORCHESTRATOR
# ═══════════════════════════════════════════

def main() -> None:
    log.info("════════════════════════════════════════════")
    log.info("  Government Indexing Portal Automation")
    log.info("════════════════════════════════════════════")
    log.info("Folder path : %s", FOLDER_PATH)
    log.info("Login URL   : %s", LOGIN_URL)
    log.info("Headless    : %s", HEADLESS)

    with sync_playwright() as pw:
        # Launch Chromium with visible browser
        browser: Browser = pw.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page: Page = context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            # ── Step 1: Manual login ──────────────────────────────────────────
            login(page)

            # ── Step 2: Read config and create volume ─────────────────────────
            volume_data = read_volume_data(FOLDER_PATH)
            create_volume(page, volume_data)

            # ── Step 3: Read PDFs and create index entries ────────────────────
            pdf_files = read_pdf_files(FOLDER_PATH)
            create_indexes(page, pdf_files)

            # ── Step 4: Submit volume ─────────────────────────────────────────
            submit_volume(page)

            log.info("════════════════════════════════════════════")
            log.info("  Automation completed successfully. 🎉")
            log.info("════════════════════════════════════════════")

        except Exception as exc:
            log.exception("❌  Unhandled error during automation: %s", exc)
            raise

        finally:
            # Give the user a moment to review the final state before closing
            log.info("Browser will close in 5 seconds…")
            page.wait_for_timeout(5_000)
            browser.close()


if __name__ == "__main__":
    main()