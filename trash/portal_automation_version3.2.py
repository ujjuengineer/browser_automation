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
FOLDER_PATH: str = "/Users/ujjwalkumar/Desktop/NALANDA/21-5-26/2701-1923-17-hilsha"
HEADLESS: bool   = False

LOGIN_TIMEOUT_MS: int = 120_000   # 2 min for manual login + CAPTCHA
PAGE_TIMEOUT_MS: int  =  30_000   # default element timeout
NAV_TIMEOUT_MS: int   =  60_000   # full-page navigation timeout
MANUAL_TIMEOUT_MS: int = 600_000  # 10 min for manual login + volume creation

# ── Selectors (verified against portal HTML) ──────────────────────────────────
NEW_REQ_BTN      = "#new_req_btn"

# Autocomplete text inputs
OFFICE_DISTRICT  = "#office_district"
OFFICE_SRO       = "#office_sro"
VOLUME_DISTRICT  = "#volume_district"
VOLUME_SRO       = "#volume_sro"

# Hidden fields that hold the REAL validated IDs (read by JS validation)
HIDDEN_DISTRICT_ID2 = "#district_id2"   # office district id
HIDDEN_SRO_ID2      = "#sro_id2"        # office sro id
HIDDEN_DISTRICT_ID  = "#district_id"    # volume district id
HIDDEN_SRO_ID       = "#sro_id"         # volume sro id

# Suggestion list <ul> IDs (one per autocomplete field)
SUGGESTIONS = {
    OFFICE_DISTRICT: "#district_suggestions2",
    OFFICE_SRO:      "#sro_suggestions2",
    VOLUME_DISTRICT: "#district_suggestions",
    VOLUME_SRO:      "#sro_suggestions",
}

# Plain inputs / selects
VOLUME_YEAR      = "#volume_year"        # plain <input type="text">
BOOK_TYPE_SELECT = "#bookType"           # <select> — NOTE: bookType not book_type
VOLUME_NO        = "#volume_no"
RADIO_YES        = "#isvolumeforwardedY"
RADIO_NO         = "#isvolumeforwardedN"
ADD_VOLUME_BTN   = "#addVolumeBtn"

# Index entry fields
PRESENTATION_YEAR = "#presentation_year"  # must be filled BEFORE deed_no
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
#  STEP 1 – WAIT FOR MANUAL SETUP
# ═══════════════════════════════════════════

def wait_for_manual_setup(page: Page) -> None:
    """
    Open the login page and wait for the user to:
      1. Log in manually (credentials + CAPTCHA).
      2. Click the New Request button themselves.
      3. Fill the volume form manually and click Save.
      4. Wait until the volume is created and the Index Details section
         appears — specifically until #presentation_year and #deed_no
         are both visible on the page.

    Automation begins only after both fields are detected.
    """
    log.info("Navigating to login page: %s", LOGIN_URL)
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    log.info(
        "⏳  Please complete the following steps manually in the browser:\n"
        "    1. Enter your credentials and solve the CAPTCHA to log in.\n"
        "    2. Click the 'New Request' button.\n"
        "    3. Fill in the volume form and click Save.\n"
        "    4. Wait for the success popup and click OK.\n"
        "\n"
        "    Automation will start automatically once the Presentation Year\n"
        "    and Deed No. fields appear on screen.\n"
        "    (You have up to %d minutes.)",
        MANUAL_TIMEOUT_MS // 60_000,
    )

    try:
        # Wait until BOTH #presentation_year AND #deed_no are visible —
        # this only happens after the volume is saved and #indexdetailsdiv
        # is revealed by the portal JS.
        page.wait_for_function(
            """() => {
                var py = document.querySelector('#presentation_year');
                var dn = document.querySelector('#deed_no');
                if (!py || !dn) return false;
                var pyRect = py.getBoundingClientRect();
                var dnRect = dn.getBoundingClientRect();
                return pyRect.width > 0 && pyRect.height > 0
                    && dnRect.width > 0 && dnRect.height > 0;
            }""",
            timeout=MANUAL_TIMEOUT_MS,
        )
        log.info("✅  Presentation Year and Deed No. fields detected. Starting automation…")
    except PlaywrightTimeoutError:
        log.error(
            "❌  Fields not detected within %d minutes. Exiting.",
            MANUAL_TIMEOUT_MS // 60_000,
        )
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

    How the portal works (from the HTML source):
      1. User types into a plain <input> (e.g. #office_district).
      2. JS listens on the 'input' event, filters a preloaded list, and
         injects matching <li class="list-group-item"> into a <ul>
         (e.g. #district_suggestions2).
      3. Clicking an <li> sets the visible input text AND stores the
         numeric ID into a hidden <input> (e.g. #district_id2).
      4. Form validation reads the hidden field — NOT the visible text.

    So we must:
      a. Type enough chars to trigger suggestions.
      b. Wait for the matching <li> to appear.
      c. Click it (which also fills the hidden field automatically).
      d. Verify the hidden field is no longer 0.
    """
    TYPE_CHARS = 4   # type first 4 characters to trigger suggestions

    input_loc = page.locator(input_selector)
    input_loc.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    # Clear any existing text
    input_loc.click()
    input_loc.click(click_count=3)
    input_loc.press("Control+a")
    input_loc.press("Backspace")
    page.wait_for_timeout(300)

    # Type slowly so the JS 'input' event fires correctly
    partial = value[:TYPE_CHARS]
    log.info("  Typing '%s' in %-20s to open suggestions…", partial, label)
    input_loc.type(partial, delay=120)

    # Wait for the suggestion list to become visible
    suggestion_ul = page.locator(suggestion_selector)
    try:
        suggestion_ul.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log.error(
            "❌  Suggestion list '%s' did not appear after typing '%s'. "
            "Check TYPE_CHARS or the selector.", suggestion_selector, partial
        )
        raise

    # Find the matching <li> — try exact text first, then contains
    li_exact = suggestion_ul.locator(f"li.list-group-item:text-is('{value}')")
    li_contains = suggestion_ul.locator(f"li.list-group-item:has-text('{value}')")

    if li_exact.count() > 0:
        li_exact.first.click()
        log.info("  Selected %-22s → '%s' (exact)", label, value)
    elif li_contains.count() > 0:
        chosen = li_contains.first.inner_text().strip()
        li_contains.first.click()
        log.info("  Selected %-22s → '%s' (contains match on '%s')", label, value, chosen)
    else:
        # Log all visible options to help debug
        all_items = suggestion_ul.locator("li.list-group-item").all()
        visible = [li.inner_text().strip() for li in all_items]
        log.error(
            "❌  '%s' not found in suggestions for '%s'. Visible: %s",
            value, label, visible
        )
        raise ValueError(f"Could not find '{value}' in dropdown for '{label}'")

    # Wait briefly for the hidden field to be populated by the click handler
    page.wait_for_timeout(400)

    # Verify hidden field was actually set (not 0 or empty)
    hidden_value = page.locator(hidden_selector).get_attribute("value") or "0"
    if hidden_value in ("0", ""):
        log.error(
            "❌  Hidden field '%s' is still '%s' after selecting '%s'. "
            "The click may not have fired the JS handler.",
            hidden_selector, hidden_value, value
        )
        raise RuntimeError(
            f"Hidden field {hidden_selector} not populated after selecting '{value}'"
        )

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

    # 2.1  Click New Request
    log.info("Clicking #new_req_btn…")
    btn = page.locator(NEW_REQ_BTN)
    btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    btn.click()

    # 2.2  Wait for the form to load (office_district input appears)
    log.info("Waiting for volume form…")
    page.locator(OFFICE_DISTRICT).wait_for(state="visible", timeout=NAV_TIMEOUT_MS)

    # 2.3  Autocomplete fields (each sets a hidden ID field on click)
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

    # 2.4  Plain text inputs
    _fill_plain(page, VOLUME_YEAR, data["volume_year"], "volume_year")
    _fill_plain(page, VOLUME_NO,   data["volume_no"],   "volume_no")

    # 2.5  Book type <select> — portal uses id="bookType" with values 1-4
    book_value_map = {"book1": "1", "book2": "2", "book3": "3", "book4": "4"}
    book_val = book_value_map.get(data["book_type"].lower(), data["book_type"])
    book_loc = page.locator(BOOK_TYPE_SELECT)
    book_loc.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    book_loc.select_option(value=book_val)
    log.info("  Selected %-22s → '%s' (value='%s')", "book_type", data["book_type"], book_val)

    # 2.6  Radio button — portal uses id="isvolumeforwardedY" / "isvolumeforwardedN"
    radio_val = data["radio"].strip().lower()
    if radio_val == "yes":
        page.locator(RADIO_YES).check()
        log.info("  Checked radio                  → Yes")
    else:
        page.locator(RADIO_NO).check()
        log.info("  Checked radio                  → No")

    # 2.7  Click Save
    # The portal fires an alert() AFTER the AJAX call completes:
    #   "The volume has been created successfully."
    # Only after the user clicks OK does the JS set #indexdetailsdiv to visible.
    # We use page.expect_event("dialog") as a context manager so Playwright
    # waits for the dialog to actually appear before we try to accept it.
    log.info("Clicking #addVolumeBtn and waiting for success alert…")
    save_btn = page.locator(ADD_VOLUME_BTN)
    save_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    with page.expect_event("dialog", timeout=NAV_TIMEOUT_MS) as dialog_info:
        save_btn.click()

    dialog = dialog_info.value
    log.info("  Alert text: '%s' → accepting", dialog.message)
    dialog.accept()

    # 2.8  Now wait for #indexdetailsdiv to become visible
    # The portal JS sets display:block immediately after the alert is dismissed
    log.info("Waiting for #indexdetailsdiv to become visible…")
    index_div = page.locator("#indexdetailsdiv")
    index_div.wait_for(state="visible", timeout=NAV_TIMEOUT_MS)

    log.info("✅  Volume created. Index Details section is now visible.")


# ═══════════════════════════════════════════
#  STEP 3a – READ PDF FILES
# ═══════════════════════════════════════════

def read_pdf_files(folder_path: str) -> list:
    """
    Return a list of PDF paths from *folder_path*, sorted numerically by stem.
    """
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
    """
    Read the current value of #volume_year from the page.
    The portal renders it as a plain <input type="text" id="volume_year">.
    """
    loc = page.locator(VOLUME_YEAR)
    loc.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    year = loc.input_value().strip()
    if not year:
        raise RuntimeError("#volume_year is empty on the page")
    log.info("  Read #volume_year from page    → '%s'", year)
    return year


MAX_RETRIES: int = 3   # max attempts per PDF before giving up

# Portal alert messages that mean "already saved, don't retry"
DUPLICATE_SIGNALS = [
    "already exists",
    "deed number already exists",
]

def _get_index_row_count(page: Page) -> int:
    """Return the current number of data rows in the #indexdetails table."""
    rows = page.locator("#indexdetails tbody tr")
    count = rows.count()
    if count == 1:
        text = rows.first.inner_text().strip()
        if "no records" in text.lower():
            return 0
    return count


def _fill_and_submit_entry(page: Page, volume_year: str, deed_no: str) -> str:
    """
    Fill presentation_year + deed_no and click Add Index once.

    Returns the dialog message text if a validation alert fired, or "" on success.

    Speed improvements:
    - Removed wait_for_timeout() pauses — Playwright waits are event-driven,
      not time-based, so fixed sleeps just waste time.
    - Dialog is captured via a registered handler set BEFORE the click, then
      immediately removed after. This avoids the 10-second timeout on every
      successful entry that was adding ~30 minutes to a 188-file run.
    """
    # Capture dialog in a simple list via a pre-registered handler
    # (avoids both the "already handled" crash and the 10s timeout penalty)
    dialog_text = []

    def _grab_dialog(d: Dialog) -> None:
        dialog_text.append(d.message)
        log.warning("  Portal alert: '%s'", d.message)
        d.accept()

    page.once("dialog", _grab_dialog)

    # Fill presentation_year
    py_field = page.locator(PRESENTATION_YEAR)
    py_field.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    py_field.click()
    py_field.click(click_count=3)
    py_field.fill(volume_year)
    py_field.press("Tab")   # triggers portal year-validation JS

    # Fill deed_no
    deed_field = page.locator(DEED_NO)
    deed_field.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    deed_field.click()
    deed_field.click(click_count=3)
    deed_field.fill(deed_no)

    # Click Add Index
    add_btn = page.locator(ADD_INDEX_BTN)
    add_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    add_btn.click()

    # If no dialog fired the handler is still registered but harmless —
    # remove it so it doesn't bleed into the next iteration
    try:
        page.remove_listener("dialog", _grab_dialog)
    except Exception:
        pass  # already consumed by the once() call — that's fine

    return dialog_text[0] if dialog_text else ""


def create_indexes(page: Page, pdf_files: list) -> None:
    """
    For every PDF file, fill presentation_year + deed_no and click Add.

    - Uses row count increase as the definitive success signal.
    - Detects duplicate deed alerts and skips immediately (no retry).
    - Retries up to MAX_RETRIES for genuine failures (network etc).
    - Prints a full summary at the end.
    """
    log.info("─── Step 3: Create Index Entries (%d file(s)) ───", len(pdf_files))

    if not pdf_files:
        log.warning("No PDF files to process. Skipping.")
        return

    volume_year = _read_volume_year_from_page(page)

    failed_files    = []   # genuine failures after all retries
    duplicate_files = []   # skipped because portal said duplicate

    for idx, pdf_path in enumerate(pdf_files, start=1):
        deed_no = pdf_path.stem
        log.info("[%d/%d] Processing: %s  →  deed_no='%s'",
                 idx, len(pdf_files), pdf_path.name, deed_no)

        rows_before = _get_index_row_count(page)
        log.info("  Table rows before: %d", rows_before)

        success   = False
        is_duplicate = False

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                log.warning("  Retry %d/%d for '%s'…", attempt, MAX_RETRIES, pdf_path.name)
                page.wait_for_timeout(1000 * attempt)

            alert_text = _fill_and_submit_entry(page, volume_year, deed_no)

            # ── If any alert fired, the entry was rejected — no need to wait ──
            if alert_text:
                if any(sig in alert_text.lower() for sig in DUPLICATE_SIGNALS):
                    log.warning("  ⚠️  Deed %s already exists — skipping.", deed_no)
                    duplicate_files.append(pdf_path.name)
                    is_duplicate = True
                    break
                else:
                    # Other validation alert (e.g. "please click save button")
                    # — row will never increase, so skip the wait and retry immediately
                    log.warning("  Validation alert on attempt %d — retrying.", attempt)
                    continue

            # ── No alert fired — confirm row count increased ──────────────
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
                log.warning(
                    "  Row count did not increase after attempt %d (still %d).",
                    attempt, rows_before,
                )
                rows_before = _get_index_row_count(page)

        if not success and not is_duplicate:
            log.error("❌  FAILED: '%s' after %d attempts.", pdf_path.name, MAX_RETRIES)
            failed_files.append(pdf_path.name)

        log.info("  Done: '%s'  [%d/%d]", pdf_path.name, idx, len(pdf_files))

    # ── Final summary ─────────────────────────────────────────────────────────
    final_count = _get_index_row_count(page)
    expected    = len(pdf_files) - len(duplicate_files)

    log.info("════════════════════════════════════")
    log.info("  Index creation complete.")
    log.info("  Total PDFs      : %d", len(pdf_files))
    log.info("  Created         : %d", final_count)
    log.info("  Duplicates skip : %d", len(duplicate_files))
    log.info("  Failed          : %d", len(failed_files))

    if duplicate_files:
        log.warning("  ⚠️  Skipped duplicates:")
        for name in duplicate_files:
            log.warning("     - %s", name)

    if failed_files:
        log.error("  ❌ Failed files:")
        for name in failed_files:
            log.error("     - %s", name)
    else:
        log.info("  No failures ✅")

    if final_count != expected:
        log.warning(
            "  ⚠️  Expected %d rows but table has %d. Some entries may be missing.",
            expected, final_count,
        )
    log.info("════════════════════════════════════")


# ═══════════════════════════════════════════
#  STEP 4 – SUBMIT VOLUME
# ═══════════════════════════════════════════

def submit_volume(page: Page) -> None:
    """
    Click #submitvolume.
    The portal fires a confirm() dialog — we accept it automatically.
    Then it fires a success alert — we accept that too.
    """
    log.info("─── Step 4: Submit Volume ───")

    submit_btn = page.locator(SUBMIT_VOLUME_BTN)
    submit_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    # The portal calls confirm('Are you sure you want to proceed?')
    def handle_dialog(dialog: Dialog) -> None:
        log.info("  Dialog [%s]: '%s' → accepting", dialog.type, dialog.message)
        dialog.accept()

    page.on("dialog", handle_dialog)
    submit_btn.click()

    # Wait for the success alert / page change
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
        log.warning(
            "⚠️  No success indicator found after submit — "
            "but the request was sent. Please verify in the browser."
        )
    finally:
        page.remove_listener("dialog", handle_dialog)


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
            wait_for_manual_setup(page)

            pdf_files = read_pdf_files(FOLDER_PATH)
            create_indexes(page, pdf_files)

            submit_volume(page)

            log.info("════════════════════════════════════════")
            log.info("  Automation completed successfully 🎉")
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