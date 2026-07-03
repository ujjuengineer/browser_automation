# NOTE : FAILED IN UPLOADING FILES, CRASHES AFTER INDEX CREATION

import sys
import logging
from pathlib import Path

from playwright.sync_api import (
    sync_playwright, Page, Browser,
    TimeoutError as PlaywrightTimeoutError,
    Dialog,
)

LOGIN_URL: str   = "https://enibandhan.bihar.gov.in/users/login"
HEADLESS: bool   = False

LOGIN_TIMEOUT_MS: int = 120_000   
PAGE_TIMEOUT_MS: int  =  30_000   
NAV_TIMEOUT_MS: int   =  60_000   


NEW_REQ_BTN      = "#new_req_btn"


OFFICE_DISTRICT  = "#office_district"
OFFICE_SRO       = "#office_sro"
VOLUME_DISTRICT  = "#volume_district"
VOLUME_SRO       = "#volumee_sro"


HIDDEN_DISTRICT_ID2 = ".district_id2"   
HIDDEN_SRO_ID2      = ".sro_id2"        
HIDDEN_DISTRICT_ID  = ".district_id"    
HIDDEN_SRO_ID       = ".sro_id"         


# Plain inputs 
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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("portal_automation.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def login(page: Page) -> None:
    log.info("Navigating to login page: %s", LOGIN_URL)
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    log.info(
        "Please log in manually in the browser window.\n"
        "    Waiting up to %d seconds…",
        LOGIN_TIMEOUT_MS // 1000,
    )
    try:
        # #new_req_btn only appears after a successful login
        page.wait_for_function(
            "() => document.querySelector('#new_req_btn') !== null",
            timeout=LOGIN_TIMEOUT_MS,
        )
        log.info("Login detected. URL: %s", page.url)
    except PlaywrightTimeoutError:
        log.error("Login not detected within %d s. Exiting.", LOGIN_TIMEOUT_MS // 1000)
        raise SystemExit(1)


def read_volume_data(folder_path: str) -> dict:
    config_file = Path(folder_path) / "config.txt"
    if not config_file.exists():
        log.error("config.txt not found: %s", config_file)
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

    log.info("Config loaded: %s", data)
    return data


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
            "Suggestion list '%s' did not appear after typing '%s'. "
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
            "'%s' not found in suggestions for '%s'. Visible: %s",
            value, label, visible
        )
        raise ValueError(f"Could not find '{value}' in dropdown for '{label}'")

    # Wait briefly for the hidden field to be populated by the click handler
    page.wait_for_timeout(400)

    # Verify hidden field was actually set (not 0 or empty)
    hidden_value = page.locator(hidden_selector).get_attribute("value") or "0"
    if hidden_value in ("0", ""):
        log.error(
            "Hidden field '%s' is still '%s' after selecting '%s'. "
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

    log.info(" Volume created. Index Details section is now visible.")


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
        log.warning(" No PDF files found in: %s", folder)
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


def create_indexes(page: Page, pdf_files: list) -> None:
    """
    For every PDF file:
      1. Extract deed_no from the filename stem (e.g. "1001" from "1001.pdf").
      2. Fill #presentation_year with the volume year read from the page
         (the portal requires presentation_year ≤ volume_year).
      3. Fill #deed_no with the deed number.
      4. Click #addindexBtn.
      5. Wait for the button to re-enable before processing the next file.

    Note on presentation_year:
      The portal's createindex() validates that presentation_year is filled
      and that it is <= volume_year.  Since we are indexing historical records,
      the volume_year itself is the correct presentation_year.
    """
    log.info("─── Step 3: Create Index Entries (%d file(s)) ───", len(pdf_files))

    if not pdf_files:
        log.warning("No PDF files to process. Skipping.")
        return

    # Read volume year once — it is constant for all entries
    volume_year = _read_volume_year_from_page(page)

    for idx, pdf_path in enumerate(pdf_files, start=1):
        deed_no = pdf_path.stem   # "1001" from "1001.pdf"
        log.info("[%d/%d] %s  →  deed_no='%s'",
                 idx, len(pdf_files), pdf_path.name, deed_no)

        # 3a  Fill presentation_year (required before deed_no)
        py_field = page.locator(PRESENTATION_YEAR)
        py_field.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
        py_field.click()
        py_field.click(click_count=3)
        py_field.fill(volume_year)
        # Trigger blur so the portal's year-validation JS runs
        py_field.press("Tab")
        page.wait_for_timeout(300)
        log.info("  Filled presentation_year      → '%s'", volume_year)

        # 3b  Fill deed_no
        deed_field = page.locator(DEED_NO)
        deed_field.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
        deed_field.click()
        deed_field.click(click_count=3)
        deed_field.fill(deed_no)
        log.info("  Filled deed_no                → '%s'", deed_no)

        # 3c  Click Add Index button
        add_btn = page.locator(ADD_INDEX_BTN)
        add_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
        # Handle any unexpected alert (e.g. validation warning)
        page.once("dialog", lambda d: (log.warning("  Alert: %s", d.message), d.accept()))
        add_btn.click()

        # 3d  Wait for the button to become enabled again (server round-trip done)
        page.wait_for_timeout(800)
        page.locator(ADD_INDEX_BTN).wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
        # Also wait until it is not disabled
        page.wait_for_function(
            "() => !document.querySelector('#addindexBtn').disabled",
            timeout=PAGE_TIMEOUT_MS,
        )

        log.info("   Index entry created for '%s'.", pdf_path.name)

    log.info(" All %d index entries created.", len(pdf_files))


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
        log.info(" Volume submitted successfully.")
    except PlaywrightTimeoutError:
        log.warning(
            " No success indicator found after submit — "
            "but the request was sent. Please verify in the browser."
        )
    finally:
        page.remove_listener("dialog", handle_dialog)


# main

def main() -> None:
    log.info("  Bihar Portal Automation")
    log.info("URL    : %s", LOGIN_URL)

    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page: Page = context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            login(page)

            volume_data = read_volume_data(FOLDER_PATH)
            create_volume(page, volume_data)

            pdf_files = read_pdf_files(FOLDER_PATH)
            create_indexes(page, pdf_files)

            submit_volume(page)

            log.info("  Automation completed successfully 🎉")

        except Exception as exc:
            log.exception(" Automation failed: %s", exc)
            raise

        finally:
            log.info("Browser closes in 5 s…")
            page.wait_for_timeout(5_000)
            browser.close()


if __name__ == "__main__":
    main()