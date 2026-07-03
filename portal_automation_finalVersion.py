import sys
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError, Dialog

LOGIN_URL = "https://enibandhan.bihar.gov.in/users/login"
FOLDER_PATH = "/Users/ujjwalkumar/Desktop/VOL-18-1961-SP-PDF-DONE"
HEADLESS = False
LOGIN_TIMEOUT_MS = 120000
PAGE_TIMEOUT_MS = 30000
NAV_TIMEOUT_MS = 60000
NEW_REQ_BTN = "#new_req_btn"
OFFICE_DISTRICT = "#office_district"
OFFICE_SRO = "#office_sro"
VOLUME_DISTRICT = "#volume_district"


VOLUME_SRO = "#volume_sro"
HIDDEN_DISTRICT_ID2 = "#district_id2"
HIDDEN_SRO_ID2 = "#sro_id2"
HIDDEN_DISTRICT_ID = "#district_id"


HIDDEN_SRO_ID = "#sro_id"
SUGGESTIONS = {OFFICE_DISTRICT: "#district_suggestions2", OFFICE_SRO: "#sro_suggestions2", VOLUME_DISTRICT: "#district_suggestions", VOLUME_SRO: "#sro_suggestions"}
VOLUME_YEAR = "#volume_year"
BOOK_TYPE_SELECT = "#bookType"
VOLUME_NO = "#volume_no"
RADIO_YES = "#isvolumeforwardedY"
RADIO_NO = "#isvolumeforwardedN"
ADD_VOLUME_BTN = "#addVolumeBtn"
PRESENTATION_YEAR = "#presentation_year"


DEED_NO = "#deed_no"
ADD_INDEX_BTN = "#addindexBtn"
SUBMIT_VOLUME_BTN = "#submitvolume"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("portal_automation.log", encoding="utf-8")])
log = logging.getLogger(__name__)



def login(page: Page) -> None:
    log.info("Navigating to login page: %s", LOGIN_URL)
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    log.info("Please log in manually in the browser window.\nWaiting up to %d seconds…", LOGIN_TIMEOUT_MS // 1000)

    try:
        page.wait_for_function("() => document.querySelector('#new_req_btn') !== null", timeout=LOGIN_TIMEOUT_MS)
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
    data = {}
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
    required = {"office_district", "office_sro", "volume_district", "volume_sro", "volume_no", "volume_year", "book_type", "radio"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"config.txt is missing keys: {missing}")
    log.info("Config loaded: %s", data)
    return data



def _fill_plain(page: Page, selector: str, value: str, label: str) -> None:
    loc = page.locator(selector)
    loc.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    loc.click()
    loc.click(click_count=3)
    loc.press("Control+a")
    loc.fill(value)
    log.info("  Filled %-22s → '%s'", label, value)

def _fill_autocomplete(page: Page, input_selector: str, suggestion_selector: str, hidden_selector: str, value: str, label: str) -> None:
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
        log.error("Suggestion list '%s' did not appear after typing '%s'. Check TYPE_CHARS or the selector.", suggestion_selector, partial)
        raise
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
        all_items = suggestion_ul.locator("li.list-group-item").all()
        visible = [li.inner_text().strip() for li in all_items]
        log.error("'%s' not found in suggestions for '%s'. Visible: %s", value, label, visible)
        raise ValueError(f"Could not find '{value}' in dropdown for '{label}'")
    page.wait_for_timeout(400)
    hidden_value = page.locator(hidden_selector).get_attribute("value") or "0"
    if hidden_value in ("0", ""):
        log.error("Hidden field '%s' is still '%s' after selecting '%s'. The click may not have fired the JS handler.", hidden_selector, hidden_value, value)
        raise RuntimeError(f"Hidden field {hidden_selector} not populated after selecting '{value}'")
    log.info("  Hidden field %-18s → '%s' ✓", hidden_selector, hidden_value)

def create_volume(page: Page, data: dict) -> None:
    log.info("Step 2: Create New Volume Index")
    log.info("Clicking #new_req_btn…")
    btn = page.locator(NEW_REQ_BTN)
    btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    btn.click()
    log.info("Waiting for volume form…")
    page.locator(OFFICE_DISTRICT).wait_for(state="visible", timeout=NAV_TIMEOUT_MS)
    _fill_autocomplete(page, OFFICE_DISTRICT, SUGGESTIONS[OFFICE_DISTRICT], HIDDEN_DISTRICT_ID2, data["office_district"], "office_district")
    _fill_autocomplete(page, OFFICE_SRO, SUGGESTIONS[OFFICE_SRO], HIDDEN_SRO_ID2, data["office_sro"], "office_sro")
    _fill_autocomplete(page, VOLUME_DISTRICT, SUGGESTIONS[VOLUME_DISTRICT], HIDDEN_DISTRICT_ID, data["volume_district"], "volume_district")
    _fill_autocomplete(page, VOLUME_SRO, SUGGESTIONS[VOLUME_SRO], HIDDEN_SRO_ID, data["volume_sro"], "volume_sro")
    _fill_plain(page, VOLUME_YEAR, data["volume_year"], "volume_year")
    _fill_plain(page, VOLUME_NO, data["volume_no"], "volume_no")
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
    index_div = page.locator("#indexdetailsdiv")
    index_div.wait_for(state="visible", timeout=NAV_TIMEOUT_MS)
    log.info("Volume created. Index Details section is now visible.")

def read_pdf_files(folder_path: str) -> list:
    folder = Path(folder_path)
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder}")
    pdf_files = sorted(folder.glob("*.pdf"), key=lambda p: (int(p.stem) if p.stem.isdigit() else float("inf"), p.stem))
    if not pdf_files:
        log.warning("No PDF files found in: %s", folder)
    else:
        log.info("Found %d PDF file(s) in '%s'.", len(pdf_files), folder)
    return pdf_files

def _read_volume_year_from_page(page: Page) -> str:
    loc = page.locator(VOLUME_YEAR)
    loc.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    year = loc.input_value().strip()
    if not year:
        raise RuntimeError("#volume_year is empty on the page")
    log.info("  Read #volume_year from page    → '%s'", year)
    return year

MAX_RETRIES = 3
DUPLICATE_SIGNALS = ["already exists", "deed number already exists"]

def _get_index_row_count(page: Page) -> int:
    rows = page.locator("#indexdetails tbody tr")
    count = rows.count()
    if count == 1:
        text = rows.first.inner_text().strip()
        if "no records" in text.lower():
            return 0
    return count

def _fill_and_submit_entry(page: Page, volume_year: str, deed_no: str) -> str:
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
    log.info("Step 3: Create Index Entries (%d file(s))", len(pdf_files))
    if not pdf_files:
        log.warning("No PDF files to process. Skipping.")
        return []
    volume_year = _read_volume_year_from_page(page)
    failed_files = []
    duplicate_files = []
    all_alerts = []
    for idx, pdf_path in enumerate(pdf_files, start=1):
        deed_no = pdf_path.stem
        log.info("[%d/%d] Processing: %s  →  deed_no='%s'", idx, len(pdf_files), pdf_path.name, deed_no)
        rows_before = _get_index_row_count(page)
        log.info("  Table rows before: %d", rows_before)
        success = False
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
                    log.warning("  Deed %s already exists — skipping.", deed_no)
                    duplicate_files.append(pdf_path.name)
                    is_duplicate = True
                    break
                else:
                    log.warning("  Validation alert on attempt %d — retrying.", attempt)
                    continue
            try:
                page.wait_for_function(f"() => document.querySelectorAll('#indexdetails tbody tr').length > {rows_before}", timeout=PAGE_TIMEOUT_MS)
                rows_after = _get_index_row_count(page)
                log.info("  Table rows after: %d  (+%d)", rows_after, rows_after - rows_before)
                success = True
                break
            except PlaywrightTimeoutError:
                log.warning("  Row count did not increase after attempt %d (still %d).", attempt, rows_before)
                rows_before = _get_index_row_count(page)
        if not success and not is_duplicate:
            log.error("FAILED: '%s' after %d attempts.", pdf_path.name, MAX_RETRIES)
            failed_files.append(pdf_path.name)
        log.info("  Done: '%s'  [%d/%d]", pdf_path.name, idx, len(pdf_files))
    final_count = _get_index_row_count(page)
    expected = len(pdf_files) - len(duplicate_files)
    log.info("Index creation complete.")
    log.info("  Total PDFs      : %d", len(pdf_files))
    log.info("  Created         : %d", final_count)
    log.info("  Duplicates skip : %d", len(duplicate_files))
    log.info("  Failed          : %d", len(failed_files))
    if duplicate_files:
        for name in duplicate_files:
            log.warning("     - %s", name)
    if failed_files:
        for name in failed_files:
            log.error("     - %s", name)
    if final_count != expected:
        log.warning("Expected %d rows but table has %d. Some entries may be missing.", expected, final_count)
    return all_alerts

def submit_volume(page: Page, alerts: list) -> None:
    log.info("Step 4: Submit Volume")
    submit_btn = page.locator(SUBMIT_VOLUME_BTN)
    submit_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    def handle_dialog(dialog: Dialog) -> None:
        log.info("  Dialog [%s]: '%s' → accepting", dialog.type, dialog.message)
        dialog.accept()
    page.on("dialog", handle_dialog)
    submit_btn.click()
    try:
        page.wait_for_function("() => document.querySelector('.success-message, .alert-success, #success_msg') || window.location.href.includes('success') || window.location.href.includes('submitted')", timeout=NAV_TIMEOUT_MS)
        log.info("Volume submitted successfully.")
    except PlaywrightTimeoutError:
        log.warning("No success indicator found after submit — but the request was sent. Please verify in the browser.")
    finally:
        page.remove_listener("dialog", handle_dialog)
    if alerts:
        log.info("  PORTAL ALERTS DURING INDEXING (%d total)", len(alerts))
        for i, alert in enumerate(alerts, 1):
            log.warning("  [%d] %s", i, alert)

def main() -> None:
    log.info("Bihar Portal Automation")
    log.info("Folder : %s", FOLDER_PATH)
    log.info("URL    : %s", LOGIN_URL)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)
        try:
            login(page)
            volume_data = read_volume_data(FOLDER_PATH)
            create_volume(page, volume_data)
            pdf_files = read_pdf_files(FOLDER_PATH)
            alerts = create_indexes(page, pdf_files)
            submit_volume(page, alerts)
            log.info("Automation completed successfully")
        except Exception as exc:
            log.exception("Automation failed: %s", exc)
            raise
        finally:
            log.info("Browser closes in 5 s…")
            page.wait_for_timeout(5000)
            browser.close()

if __name__ == "__main__":
    main()

```