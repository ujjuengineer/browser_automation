"""
Government Indexing Portal Automation Script
=============================================
Portal : Bihar e-Registration (enibandhan.bihar.gov.in)
Uses Playwright (sync API) to automate volume index creation and submission.

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
    Dialog,
)

# ─────────────────────────────────────────────
#  TOP-LEVEL CONFIGURATION  (edit these values)
# ─────────────────────────────────────────────
LOGIN_URL: str   = "https://enibandhan.bihar.gov.in/users/login"
FOLDER_PATH: str = "/Users/ujjwalkumar/Desktop/VOL-39-1961-KP-pdf"
HEADLESS: bool   = False

LOGIN_TIMEOUT_MS: int  = 120_000   # 2 min for manual login + CAPTCHA
PAGE_TIMEOUT_MS: int   =  30_000   # default element timeout
NAV_TIMEOUT_MS: int    =  60_000   # full-page navigation timeout

# ── Selectors (verified against portal HTML) ──────────────────────────────────
NEW_REQ_BTN      = "#new_req_btn"

# Autocomplete text inputs
OFFICE_DISTRICT  = "#office_district"
OFFICE_SRO       = "#office_sro"
VOLUME_DISTRICT  = "#volume_district"
VOLUME_SRO       = "#volume_sro"

# Hidden fields that hold the REAL validated IDs (read by JS validation)
HIDDEN_DISTRICT_ID2 = "#district_id2"
HIDDEN_SRO_ID2      = "#sro_id2"
HIDDEN_DISTRICT_ID  = "#district_id"
HIDDEN_SRO_ID       = "#sro_id"

# Suggestion list <ul> IDs (one per autocomplete field)
SUGGESTIONS = {
    OFFICE_DISTRICT: "#district_suggestions2",
    OFFICE_SRO:      "#sro_suggestions2",
    VOLUME_DISTRICT: "#district_suggestions",
    VOLUME_SRO:      "#sro_suggestions",
}

# Plain inputs / selects
VOLUME_YEAR      = "#volume_year"
BOOK_TYPE_SELECT = "#bookType"
VOLUME_NO        = "#volume_no"
RADIO_YES        = "#isvolumeforwardedY"
RADIO_NO         = "#isvolumeforwardedN"
ADD_VOLUME_BTN   = "#addVolumeBtn"

# Index entry fields
PRESENTATION_YEAR = "#presentation_year"
DEED_NO           = "#deed_no"
ADD_INDEX_BTN     = "#addindexBtn"
SUBMIT_VOLUME_BTN = "#submitvolume"

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
    Navigate to the login page and wait for the user to manually enter
    credentials and solve the CAPTCHA.
    Login is confirmed when #new_req_btn appears in the DOM.
    """
    log.info("Navigating to login page: %s", LOGIN_URL)
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    log.info(
        "⏳  Please log in manually in the browser window.\n"
        "    Waiting up to %d seconds…",
        LOGIN_TIMEOUT_MS // 1000,
    )
    try:
        page.wait_for_function(
            "() => document.querySelector('#new_req_btn') !== null",
            timeout=LOGIN_TIMEOUT_MS,
        )
        log.info("✅  Login detected. URL: %s", page.url)
    except PlaywrightTimeoutError:
        log.error("❌  Login not detected within %d s. Exiting.", LOGIN_TIMEOUT_MS // 1000)
        raise SystemExit(1)


# ═══════════════════════════════════════════
#  STEP 2a – READ VOLUME CONFIG
# ═══════════════════════════════════════════

def read_volume_data(folder_path: str) -> dict:
    """
    Parse config.txt from *folder_path*.

    Expected keys:
        office_district, office_sro, volume_district, volume_sro,
        volume_no, volume_year, book_type, radio
    """
    config_file = Path(folder_path) / "config.txt"
    if not config_file.exists():
        log.error("❌  config.txt not found: %s", config_file)
        raise FileNotFoundError(f"config.txt not found: {config_file}")

    log.info("Reading config from: %s", config_file)
    data: dict = {}

    with config_file.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                log.warning("Line %d skipped (no '='): %s", lineno, line)
                continue
            key, _, value = line.partition("=")
            data[key.strip()] = value.strip()

    required = {
        "office_district", "office_sro", "volume_district", "volume_sro",
        "volume_no", "volume_year", "book_type", "radio",
    }
    missing = required - data.keys()
    if missing:
        raise ValueError(f"config.txt is missing keys: {missing}")

    log.info("✅  Config loaded: %s", data)
    return data


# ═══════════════════════════════════════════
#  STEP 2b – HELPERS FOR VOLUME FORM
# ═══════════════════════════════════════════

def _fill_plain(page: Page, selector: str, value: str, label: str) -> None:
    """Fill a plain <input> field (no dropdown)."""
    loc = page.locator(selector)
    loc.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    loc.click()
    loc.click(click_count=3)
    loc.press("Control+a")
    loc.fill(value)
    log.info("  Filled %-22s → '%s'", label, value)


def _fill_autocomplete(page: Page, input_selector: str, suggestion_selector: str,
                       hidden_selector: str, value: str, label: str) -> None:
    """
    Fill a typeahead/autocomplete field on the Bihar portal.
    Types partial text, waits for the suggestion list, clicks the match,
    then verifies the hidden ID field was populated.
    """
    TYPE_CHARS = 4

    input_loc = page.locator(input_selector)
    input_loc.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    input_loc.click()
    input_loc.click(click_count=3)
    input_loc.press("Control+a")
    input_loc.press("Backspace")
    page.wait_for_timeout(300)

    partial = value[:TYPE_CHARS]
    log.info("  Typing '%s' in %-20s to open suggestions…", partial, label)
    input_loc.type(partial, delay=120)

    suggestion_ul = page.locator(suggestion_selector)
    try:
        suggestion_ul.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log.error(
            "❌  Suggestion list '%s' did not appear after typing '%s'.",
            suggestion_selector, partial
        )
        raise

    li_exact    = suggestion_ul.locator(f"li.list-group-item:text-is('{value}')")
    li_contains = suggestion_ul.locator(f"li.list-group-item:has-text('{value}')")

    if li_exact.count() > 0:
        li_exact.first.click()
        log.info("  Selected %-22s → '%s' (exact)", label, value)
    elif li_contains.count() > 0:
        chosen = li_contains.first.inner_text().strip()
        li_contains.first.click()
        log.info("  Selected %-22s → '%s' (contains match on '%s')", label, value, chosen)
    else:
        all_items = suggestion_ul.locator("li.list-group-item").all()
        visible = [li.inner_text().strip() for li in all_items]
        log.error("❌  '%s' not found in suggestions for '%s'. Visible: %s", value, label, visible)
        raise ValueError(f"Could not find '{value}' in dropdown for '{label}'")

    page.wait_for_timeout(400)

    hidden_value = page.locator(hidden_selector).get_attribute("value") or "0"
    if hidden_value in ("0", ""):
        log.error(
            "❌  Hidden field '%s' is still '%s' after selecting '%s'.",
            hidden_selector, hidden_value, value
        )
        raise RuntimeError(f"Hidden field {hidden_selector} not populated after selecting '{value}'")

    log.info("  Hidden field %-18s → '%s' ✓", hidden_selector, hidden_value)


# ═══════════════════════════════════════════
#  STEP 2c – CREATE VOLUME
# ═══════════════════════════════════════════

def create_volume(page: Page, data: dict) -> None:
    """
    Click 'New Request', fill every field in the volume form, and save.
    Waits for the Index Details section to become visible after save.
    """
    log.info("─── Step 2: Create New Volume Index ───")

    log.info("Clicking #new_req_btn…")
    btn = page.locator(NEW_REQ_BTN)
    btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    btn.click()

    log.info("Waiting for volume form…")
    page.locator(OFFICE_DISTRICT).wait_for(state="visible", timeout=NAV_TIMEOUT_MS)

    _fill_autocomplete(
        page, OFFICE_DISTRICT, SUGGESTIONS[OFFICE_DISTRICT],
        HIDDEN_DISTRICT_ID2, data["office_district"], "office_district"
    )
    _fill_autocomplete(
        page, OFFICE_SRO, SUGGESTIONS[OFFICE_SRO],
        HIDDEN_SRO_ID2, data["office_sro"], "office_sro"
    )
    _fill_autocomplete(
        page, VOLUME_DISTRICT, SUGGESTIONS[VOLUME_DISTRICT],
        HIDDEN_DISTRICT_ID, data["volume_district"], "volume_district"
    )
    _fill_autocomplete(
        page, VOLUME_SRO, SUGGESTIONS[VOLUME_SRO],
        HIDDEN_SRO_ID, data["volume_sro"], "volume_sro"
    )

    _fill_plain(page, VOLUME_YEAR, data["volume_year"], "volume_year")
    _fill_plain(page, VOLUME_NO,   data["volume_no"],   "volume_no")

    book_value_map = {"book1": "1", "book2": "2", "book3": "3", "book4": "4"}
    book_val = book_value_map.get(data["book_type"].lower(), data["book_type"])
    book_loc = page.locator(BOOK_TYPE_SELECT)
    book_loc.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    book_loc.select_option(value=book_val)
    log.info("  Selected %-22s → '%s' (value='%s')", "book_type", data["book_type"], book_val)

    radio_val = data["radio"].strip().lower()
    if radio_val == "yes":
        page.locator(RADIO_YES).check()
        log.info("  Checked radio                  → Yes")
    else:
        page.locator(RADIO_NO).check()
        log.info("  Checked radio                  → No")

    log.info("Clicking #addVolumeBtn and waiting for success alert…")
    save_btn = page.locator(ADD_VOLUME_BTN)
    save_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    with page.expect_event("dialog", timeout=NAV_TIMEOUT_MS) as dialog_info:
        save_btn.click()

    dialog = dialog_info.value
    log.info("  Alert text: '%s' → accepting", dialog.message)
    dialog.accept()

    log.info("Waiting for #indexdetailsdiv to become visible…")
    page.locator("#indexdetailsdiv").wait_for(state="visible", timeout=NAV_TIMEOUT_MS)
    log.info("✅  Volume created. Index Details section is now visible.")


# ═══════════════════════════════════════════
#  STEP 3a – READ PDF FILES
# ═══════════════════════════════════════════

def read_pdf_files(folder_path: str) -> list:
    """Return a list of PDF paths from *folder_path*, sorted numerically by stem."""
    folder = Path(folder_path)
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder}")

    pdf_files = sorted(
        folder.glob("*.pdf"),
        key=lambda p: (int(p.stem) if p.stem.isdigit() else float("inf"), p.stem),
    )

    if not pdf_files:
        log.warning("⚠️  No PDF files found in: %s", folder)
    else:
        log.info("Found %d PDF file(s) in '%s'.", len(pdf_files), folder)

    return pdf_files


# ═══════════════════════════════════════════
#  STEP 3b – CREATE INDEX ENTRIES
# ═══════════════════════════════════════════

def _read_volume_year_from_page(page: Page) -> str:
    loc = page.locator(VOLUME_YEAR)
    loc.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    year = loc.input_value().strip()
    if not year:
        raise RuntimeError("#volume_year is empty on the page")
    log.info("  Read #volume_year from page    → '%s'", year)
    return year


MAX_RETRIES: int = 3

DUPLICATE_SIGNALS = [
    "already exists",
    "deed number already exists",
]


def _get_index_row_count(page: Page) -> int:
    rows = page.locator("#indexdetails tbody tr")
    count = rows.count()
    if count == 1:
        if "no records" in rows.first.inner_text().strip().lower():
            return 0
    return count


def _fill_and_submit_entry(page: Page, volume_year: str, deed_no: str) -> str:
    """Fill presentation_year + deed_no and click Add Index once.
    Returns dialog message text if an alert fired, or '' on success."""
    dialog_text = []

    def _grab_dialog(d: Dialog) -> None:
        dialog_text.append(d.message)
        log.warning("  Portal alert: '%s'", d.message)
        d.accept()

    page.once("dialog", _grab_dialog)

    py_field = page.locator(PRESENTATION_YEAR)
    py_field.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    py_field.click()
    py_field.click(click_count=3)
    py_field.fill(volume_year)
    py_field.press("Tab")

    deed_field = page.locator(DEED_NO)
    deed_field.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    deed_field.click()
    deed_field.click(click_count=3)
    deed_field.fill(deed_no)

    add_btn = page.locator(ADD_INDEX_BTN)
    add_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    add_btn.click()

    try:
        page.remove_listener("dialog", _grab_dialog)
    except Exception:
        pass

    return dialog_text[0] if dialog_text else ""


def create_indexes(page: Page, pdf_files: list) -> list:
    """
    For every PDF file, fill presentation_year + deed_no and click Add.
    Returns list of all portal alert strings collected during indexing.
    """
    log.info("─── Step 3: Create Index Entries (%d file(s)) ───", len(pdf_files))

    if not pdf_files:
        log.warning("No PDF files to process. Skipping.")
        return []

    volume_year     = _read_volume_year_from_page(page)
    failed_files    = []
    duplicate_files = []
    all_alerts      = []

    for idx, pdf_path in enumerate(pdf_files, start=1):
        deed_no = pdf_path.stem
        log.info("[%d/%d] Processing: %s  →  deed_no='%s'",
                 idx, len(pdf_files), pdf_path.name, deed_no)

        rows_before  = _get_index_row_count(page)
        success      = False
        is_duplicate = False

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                log.warning("  Retry %d/%d for '%s'…", attempt, MAX_RETRIES, pdf_path.name)
                page.wait_for_timeout(1000 * attempt)

            alert_text = _fill_and_submit_entry(page, volume_year, deed_no)

            if alert_text:
                entry = f"{pdf_path.name}  →  {alert_text}"
                if entry not in all_alerts:
                    all_alerts.append(entry)

                if any(sig in alert_text.lower() for sig in DUPLICATE_SIGNALS):
                    log.warning("  ⚠️  Deed %s already exists — skipping.", deed_no)
                    duplicate_files.append(pdf_path.name)
                    is_duplicate = True
                    break
                else:
                    log.warning("  Validation alert on attempt %d — retrying.", attempt)
                    continue

            try:
                page.wait_for_function(
                    f"() => document.querySelectorAll('#indexdetails tbody tr').length > {rows_before}",
                    timeout=PAGE_TIMEOUT_MS,
                )
                rows_after = _get_index_row_count(page)
                log.info("  Table rows after: %d  (+%d) ✅", rows_after, rows_after - rows_before)
                success = True
                break

            except PlaywrightTimeoutError:
                log.warning("  Row count did not increase after attempt %d (still %d).",
                            attempt, rows_before)
                rows_before = _get_index_row_count(page)

        if not success and not is_duplicate:
            log.error("❌  FAILED: '%s' after %d attempts.", pdf_path.name, MAX_RETRIES)
            failed_files.append(pdf_path.name)

        log.info("  Done: '%s'  [%d/%d]", pdf_path.name, idx, len(pdf_files))

    final_count = _get_index_row_count(page)
    expected    = len(pdf_files) - len(duplicate_files)

    log.info("════════════════════════════════════")
    log.info("  Index creation complete.")
    log.info("  Total PDFs      : %d", len(pdf_files))
    log.info("  Created         : %d", final_count)
    log.info("  Duplicates skip : %d", len(duplicate_files))
    log.info("  Failed          : %d", len(failed_files))
    if duplicate_files:
        log.warning("  ⚠️  Skipped duplicates: %s", duplicate_files)
    if failed_files:
        log.error("  ❌ Failed: %s", failed_files)
    else:
        log.info("  No failures ✅")
    if final_count != expected:
        log.warning("  ⚠️  Expected %d rows but table has %d.", expected, final_count)
    log.info("════════════════════════════════════")

    return all_alerts


# ═══════════════════════════════════════════
#  STEP 4 – SUBMIT VOLUME INDEX
# ═══════════════════════════════════════════

def submit_volume(page: Page, alerts: list) -> None:
    """
    Click #submitvolume. The portal fires:
      1. confirm("Are you sure you want to proceed?")  → accept
      2. alert("Volume details submitted…")            → accept
    Then redirects back to the dashboard/index-creation page.
    """
    log.info("─── Step 4: Submit Volume ───")

    submit_btn = page.locator(SUBMIT_VOLUME_BTN)
    submit_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    def _handle(dialog: Dialog) -> None:
        log.info("  Dialog [%s]: '%s' → accepting", dialog.type, dialog.message)
        dialog.accept()

    page.on("dialog", _handle)
    submit_btn.click()

    # Wait for the portal to redirect away from the index-creation page
    try:
        page.wait_for_url(
            # this lambda is an addition ----------
            lambda url: "indexCreation" not in url and "indexCreate" not in url,
            timeout=NAV_TIMEOUT_MS,
        )
        log.info("✅  Volume submitted. Redirected to: %s", page.url)
    except PlaywrightTimeoutError:
        log.warning("⚠️  No redirect detected after submit — continuing anyway.")
    finally:
        page.remove_listener("dialog", _handle)

    # Print all portal alerts collected during indexing
    if alerts:
        log.info("")
        log.info("╔══════════════════════════════════════════════════════╗")
        log.info("  PORTAL ALERTS DURING INDEXING (%d total)", len(alerts))
        log.info("╚══════════════════════════════════════════════════════╝")
        for i, alert in enumerate(alerts, 1):
            log.warning("  [%d] %s", i, alert)
        log.info("══════════════════════════════════════════════════════")
    else:
        log.info("  No portal alerts were raised during indexing ✅")


# ═══════════════════════════════════════════════════════
#  STEP 5 – NAVIGATE TO UPLOAD SCANNED DOCUMENT PAGE
# ═══════════════════════════════════════════════════════

def navigate_to_upload_page(page: Page) -> None:
    """
    Click the 'Upload Scanned Document' link in the left sidebar.
    The link calls the portal's redirectToURL() JS function which navigates
    the browser to /digitize/uploadScannedDocument.
    """
    log.info("─── Step 5: Navigate to Upload Scanned Document page ───")

    upload_link = page.locator("text=Upload Scanned Document").first
    upload_link.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    upload_link.click()

    page.wait_for_url(lambda url: "uploadScannedDocument" in url, timeout=NAV_TIMEOUT_MS)
    # Wait for the pending list table body to appear
    page.locator("#rr tbody, #tableBody").first.wait_for(state="visible", timeout=NAV_TIMEOUT_MS)
    log.info("✅  Upload Scanned Document page loaded. URL: %s", page.url)


# ═══════════════════════════════════════════════════════
#  STEP 6 – FIND VOLUME IN LIST AND CLICK PROCESS
# ═══════════════════════════════════════════════════════

def _go_to_last_pagination_page(page: Page) -> None:
    """Click the 'Last' pagination button if it is not already disabled."""
    last_btn = page.locator("#pagination .page-item.last:not(.disabled) a")
    if last_btn.count() > 0:
        last_btn.first.click()
        page.wait_for_timeout(1200)
        log.info("  Navigated to last pagination page.")
    else:
        log.info("  Already on last page (or single page).")


def _go_to_prev_pagination_page(page: Page) -> bool:
    """Click 'Previous'. Returns False if already on the first page."""
    prev_btn = page.locator("#pagination .page-item.prev:not(.disabled) a")
    if prev_btn.count() > 0:
        prev_btn.first.click()
        page.wait_for_timeout(1000)
        return True
    return False


def _find_volume_row_on_current_page(page: Page, volume_no: str, volume_district: str):
    """
    Scan rows on the current page for a row matching BOTH:
      - Volume No.      → column index 5  (6th <td>)
      - Volume District → column index 3  (4th <td>)

    Pending list table columns (0-based index):
      0  S.No.
      1  Vault District
      2  Vault Registration office
      3  Volume District            ← match here
      4  Volume Registration office
      5  Volume No.                 ← match here
      6  Is Volume Forwarded
      7  Volume Year
      8  Action

    District matching strips the numeric code in brackets so that
    "Samastipur (19)" from config.txt matches a cell showing "Samastipur".
    """
    target_no       = volume_no.strip()
    target_district = volume_district.split("(")[0].strip().lower()

    rows = page.locator("#rr tbody tr, #tableBody tr")
    for i in range(rows.count()):
        row   = rows.nth(i)
        cells = row.locator("td")
        if cells.count() < 6:
            continue

        row_vol_no   = cells.nth(5).inner_text().strip()
        row_district = cells.nth(3).inner_text().strip().lower()

        vol_match      = (row_vol_no == target_no)
        district_match = (target_district in row_district or row_district in target_district)

        if vol_match and district_match:
            log.debug("  Row match — vol_no='%s' district='%s'", row_vol_no, row_district)
            return row

    return None


def find_and_process_volume(page: Page, volume_no: str, volume_district: str) -> None:
    """
    Search all pages of the pending list (last → first) for the row that
    matches both volume_no AND volume_district, then click its Process button.

    Two different districts can share the same volume number, so both fields
    are required for a unique match.
    """
    log.info(
        "─── Step 6: Find volume no='%s', district='%s' and click Process ───",
        volume_no, volume_district,
    )

    _go_to_last_pagination_page(page)

    for _ in range(20):   # safety cap — 20 pages max
        row = _find_volume_row_on_current_page(page, volume_no, volume_district)
        if row:
            log.info("  Found matching volume. Clicking Process…")
            process_btn = row.locator("button:has-text('Process')")
            process_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

            with page.expect_navigation(wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS):
                process_btn.click()

            log.info("✅  Process clicked. Now on: %s", page.url)
            # Wait for the upload table to render at least one row
            page.locator("#table-section table tbody tr").first.wait_for(
                state="visible", timeout=NAV_TIMEOUT_MS
            )
            return

        if not _go_to_prev_pagination_page(page):
            break

    raise RuntimeError(
        f"Volume no='{volume_no}' district='{volume_district}' not found "
        f"in the pending list after scanning all pages."
    )


# ═══════════════════════════════════════════════════════
#  STEP 7 – UPLOAD PDF FILES TO EACH INDEX ROW
# ═══════════════════════════════════════════════════════

def upload_pdf_files(page: Page, folder_path: str) -> None:
    """
    On the process/upload page, match each row's deed number to a PDF file
    in *folder_path* and upload it using Playwright's set_input_files().

    After each upload the portal:
      1. Validates + uploads the file via AJAX.
      2. Shows alert "The deed document has been uploaded successfully."
      3. Does a form POST that reloads the page.

    We accept each alert and wait for the page reload before moving on.
    The page reloads completely after every single upload, so we re-read
    the table on every iteration.

    Upload table columns (0-based):
      0  S.No.
      1  Volume District
      2  Volume Registration office
      3  Volume No.
      4  Volume Year
      5  Presentation Year
      6  Deed No.          ← read this
      7  Upload Deed Document  ← file input here
    """
    log.info("─── Step 7: Upload PDF files to index rows ───")

    folder          = Path(folder_path)
    uploaded_deeds  = set()   # deed numbers already uploaded this session
    failed_uploads  = []
    missing_pdfs    = []

    for iteration in range(500):   # safety cap
        # Re-read the table on every iteration (page reloads after each upload)
        rows = page.locator("#table-section table tbody tr")
        if rows.count() == 0:
            log.info("  No rows in upload table. Done.")
            break

        # Find the first row that still has a file input (not yet uploaded)
        target_deed_no       = None
        target_file_input_id = None

        for i in range(rows.count()):
            row   = rows.nth(i)
            cells = row.locator("td")
            if cells.count() < 7:
                continue

            deed_no = cells.nth(6).inner_text().strip()   # column index 6
            if deed_no in uploaded_deeds:
                continue

            file_input = row.locator("input[type='file']")
            if file_input.count() == 0:
                # File input absent = already uploaded by the portal
                uploaded_deeds.add(deed_no)
                continue

            target_deed_no       = deed_no
            target_file_input_id = file_input.get_attribute("id")
            break

        if target_deed_no is None:
            log.info("  All rows processed or no pending file inputs remain.")
            break

        # Locate matching PDF
        pdf_path = folder / f"{target_deed_no}.pdf"
        if not pdf_path.exists():
            log.error("  ❌  PDF not found for deed %s: %s", target_deed_no, pdf_path)
            missing_pdfs.append(f"{target_deed_no}.pdf")
            uploaded_deeds.add(target_deed_no)
            continue

        log.info("  [%d] Uploading deed %-8s ← %s",
                 iteration + 1, target_deed_no, pdf_path.name)

        # Upload the file — Playwright's set_input_files bypasses the OS picker
        file_input_loc = page.locator(f"#{target_file_input_id}")
        file_input_loc.set_input_files(str(pdf_path))

        # Portal fires alert "The deed document has been uploaded successfully."
        # then does a form POST reload. Capture the alert and wait for reload.
        try:
            with page.expect_event("dialog", timeout=60_000) as dialog_info:
                pass   # dialog fires from AJAX success handler
            dialog = dialog_info.value
            log.info("  Alert: '%s' → accepting", dialog.message)
            dialog.accept()
        except PlaywrightTimeoutError:
            log.warning("  No dialog after upload for deed %s — may have failed.",
                        target_deed_no)
            failed_uploads.append(f"{target_deed_no}.pdf")
            uploaded_deeds.add(target_deed_no)
            continue

        # Wait for the page to reload and the table to re-render
        try:
            page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
            page.locator("#table-section table tbody tr").first.wait_for(
                state="visible", timeout=NAV_TIMEOUT_MS
            )
        except PlaywrightTimeoutError:
            log.warning("  Page did not reload cleanly after deed %s.", target_deed_no)

        uploaded_deeds.add(target_deed_no)
        log.info("  ✅  Deed %s uploaded.", target_deed_no)

    # Summary
    total_ok = len(uploaded_deeds) - len(missing_pdfs) - len(failed_uploads)
    log.info("════════════════════════════════════════════")
    log.info("  Upload complete.")
    log.info("  Uploaded successfully : %d", total_ok)
    log.info("  Missing PDFs          : %d", len(missing_pdfs))
    log.info("  Failed uploads        : %d", len(failed_uploads))
    if missing_pdfs:
        log.error("  Missing  : %s", missing_pdfs)
    if failed_uploads:
        log.error("  Failed   : %s", failed_uploads)
    log.info("════════════════════════════════════════════")


# ═══════════════════════════════════════════════════════
#  STEP 8 – SUBMIT UPLOADED VOLUME
# ═══════════════════════════════════════════════════════

def submit_uploaded_volume(page: Page) -> None:
    """
    Click the Submit button on the upload page.
    The portal fires:
      1. confirm("Are you sure you want to submit?")          → accept
      2. alert("The volume has been submitted for verification.") → accept
    Then redirects back to the upload list page.
    """
    log.info("─── Step 8: Submit uploaded volume ───")

    # The submit button on the upload page calls submitVolume() — no id,
    # so we match by the onclick attribute text.
    submit_btn = page.locator("button[onclick*='submitVolume']")
    submit_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    def _handle(dialog: Dialog) -> None:
        log.info("  Dialog [%s]: '%s' → accepting", dialog.type, dialog.message)
        dialog.accept()

    page.on("dialog", _handle)
    submit_btn.click()

    try:
        page.wait_for_url(
            lambda url: "uploadScannedDocument" in url,
            timeout=NAV_TIMEOUT_MS,
        )
        log.info("✅  Uploaded volume submitted successfully.")
    except PlaywrightTimeoutError:
        log.warning("⚠️  No redirect detected after upload submit — check browser.")
    finally:
        page.remove_listener("dialog", _handle)


# ═══════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════

def main() -> None:
    log.info("════════════════════════════════════════")
    log.info("  Bihar Portal Automation")
    log.info("════════════════════════════════════════")
    log.info("Folder : %s", FOLDER_PATH)
    log.info("URL    : %s", LOGIN_URL)

    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page: Page = context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            # ── Step 1: Manual login ──────────────────────────────────────
            login(page)

            # ── Step 2: Read config and create volume ─────────────────────
            volume_data = read_volume_data(FOLDER_PATH)
            create_volume(page, volume_data)

            # ── Step 3: Create index entries for every PDF ────────────────
            pdf_files = read_pdf_files(FOLDER_PATH)
            alerts    = create_indexes(page, pdf_files)

            # ── Step 4: Submit the volume index ───────────────────────────
            submit_volume(page, alerts)

            # ── Step 5: Go to Upload Scanned Document page ────────────────
            navigate_to_upload_page(page)

            # ── Step 6: Find the volume we just created and open it ───────
            find_and_process_volume(
                page,
                volume_no       = volume_data["volume_no"],
                volume_district = volume_data["volume_district"],
            )

            # ── Step 7: Upload each PDF to its matching row ───────────────
            upload_pdf_files(page, FOLDER_PATH)

            # ── Step 8: Submit the uploaded volume ────────────────────────
            submit_uploaded_volume(page)

            log.info("════════════════════════════════════════")
            log.info("  Full automation completed successfully 🎉")
            log.info("════════════════════════════════════════")

        except Exception as exc:
            log.exception("❌  Automation failed: %s", exc)
            raise

        finally:
            log.info("Browser closes in 5 s…")
            page.wait_for_timeout(5_000)
            browser.close()


if __name__ == "__main__":
    main()