# NOTE : fixed the loggin issue, now correctly loggs the deed which was skipped !!
# completly create the indexing and uploading (uploading of files takes time)

# run the script with correct file path
# manually enter the login crediansals 
# indexing starts automatically : 

import sys
import logging
from pathlib import Path

from playwright.sync_api import (
    sync_playwright, Page, Browser, Dialog,
    TimeoutError as PlaywrightTimeoutError,
)

# ─────────────────────────────────────────────
#  TOP-LEVEL CONFIGURATION  (edit these values)
# ─────────────────────────────────────────────
LOGIN_URL: str   = "https://enibandhan.bihar.gov.in/users/login"
FOLDER_PATH: str = "/Users/ujjwalkumar/Desktop/PDF/VOL-31-1959-BHR-pdf-IND"
HEADLESS: bool   = False

# ── Volume config (previously in config.txt) ──────────────────────────────────
VOLUME_CONFIG: dict = {
    "office_district":  "Darbhanga",
    "office_sro":       "Darbhanga",
    "volume_district":  "Darbhanga",
    "volume_sro":       "Bahera",
    "volume_no":        "31",
    "volume_year":      "1959",
    "book_type":        "book1",
    "radio":            "no",
}

LOGIN_TIMEOUT_MS: int  = 120_000
PAGE_TIMEOUT_MS: int   =  30_000
NAV_TIMEOUT_MS: int    =  10_000
UPLOAD_TIMEOUT_MS: int = 120_000

# ── Selectors ─────────────────────────────────────────────────────────────────
NEW_REQ_BTN         = "#new_req_btn"
OFFICE_DISTRICT     = "#office_district"
OFFICE_SRO          = "#office_sro"
VOLUME_DISTRICT     = "#volume_district"
VOLUME_SRO          = "#volume_sro"
HIDDEN_DISTRICT_ID2 = "#district_id2"
HIDDEN_SRO_ID2      = "#sro_id2"
HIDDEN_DISTRICT_ID  = "#district_id"
HIDDEN_SRO_ID       = "#sro_id"
SUGGESTIONS = {
    OFFICE_DISTRICT: "#district_suggestions2",
    OFFICE_SRO:      "#sro_suggestions2",
    VOLUME_DISTRICT: "#district_suggestions",
    VOLUME_SRO:      "#sro_suggestions",
}
VOLUME_YEAR       = "#volume_year"
BOOK_TYPE_SELECT  = "#bookType"
VOLUME_NO         = "#volume_no"
RADIO_YES         = "#isvolumeforwardedY"
RADIO_NO          = "#isvolumeforwardedN"
ADD_VOLUME_BTN    = "#addVolumeBtn"
PRESENTATION_YEAR = "#presentation_year"
DEED_NO           = "#deed_no"
ADD_INDEX_BTN     = "#addindexBtn"
SUBMIT_VOLUME_BTN = "#submitvolume"

MAX_RETRIES: int = 3
DUPLICATE_SIGNALS = [
    "already exists",
    "deed number already exists",
    "please enter correct deed number",
]

# ─────────────────────────────────────────────
#  ANSI COLOR CODES
# ─────────────────────────────────────────────
class _C:
    RED     = "\033[91m"
    YELLOW  = "\033[93m"
    GREEN   = "\033[92m"
    CYAN    = "\033[96m"
    RESET   = "\033[0m"
    BOLD    = "\033[1m"


# ─────────────────────────────────────────────
#  LOGGING SETUP  (color-aware)
# ─────────────────────────────────────────────
class _ColorFormatter(logging.Formatter):
    """
    Adds ANSI colors to console output based on log level.
    File handler gets plain text (no escape codes).
    """
    LEVEL_COLORS = {
        logging.DEBUG:    _C.CYAN,
        logging.INFO:     "",           # default terminal color
        logging.WARNING:  _C.YELLOW,
        logging.ERROR:    _C.RED + _C.BOLD,
        logging.CRITICAL: _C.RED + _C.BOLD,
    }

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        color = self.LEVEL_COLORS.get(record.levelno, "")
        return f"{color}{msg}{_C.RESET}" if color else msg


_fmt = "%(asctime)s [%(levelname)s] %(message)s"

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_ColorFormatter(_fmt))

_file_handler = logging.FileHandler("portal_automation.log", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter(_fmt))

logging.basicConfig(level=logging.INFO, handlers=[_console_handler, _file_handler])
log = logging.getLogger(__name__)


def _log_skipped(deed_no: str, reason: str) -> None:
    """Always prints skipped deed in bright red regardless of log level."""
    line = (
        f"{_C.RED}{_C.BOLD}"
        f"  ⛔  SKIPPED deed {deed_no!r} — {reason}"
        f"{_C.RESET}"
    )
    # Print directly so color is guaranteed even if logging handler strips it
    print(line, flush=True)
    # Also write plain version to log file
    _file_handler.stream.write(
        f"[SKIPPED] deed={deed_no!r} reason={reason}\n"
    )
    _file_handler.stream.flush()


# ═══════════════════════════════════════════
#  STEP 1 – LOGIN
# ═══════════════════════════════════════════

def login(page: Page) -> None:
    log.info("Navigating to login page: %s", LOGIN_URL)
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    log.info(
        "⏳  Please log in manually.\n"
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
    loc = page.locator(selector)
    loc.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    loc.click()
    loc.click(click_count=3)
    loc.press("Control+a")
    loc.fill(value)
    log.info("  Filled %-22s → '%s'", label, value)


def _fill_autocomplete(
    page: Page,
    input_selector: str,
    suggestion_selector: str,
    hidden_selector: str,
    value: str,
    label: str,
) -> None:
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
        log.error("❌  Suggestion list '%s' did not appear.", suggestion_selector)
        raise

    li_exact    = suggestion_ul.locator(f"li.list-group-item:text-is('{value}')")
    li_contains = suggestion_ul.locator(f"li.list-group-item:has-text('{value}')")

    if li_exact.count() > 0:
        li_exact.first.click()
        log.info("  Selected %-22s → '%s' (exact)", label, value)
    elif li_contains.count() > 0:
        chosen = li_contains.first.inner_text().strip()
        li_contains.first.click()
        log.info("  Selected %-22s → '%s' (contains: '%s')", label, value, chosen)
    else:
        visible = [li.inner_text().strip()
                   for li in suggestion_ul.locator("li.list-group-item").all()]
        log.error("❌  '%s' not found in suggestions for '%s'. Visible: %s",
                  value, label, visible)
        raise ValueError(f"Could not find '{value}' in dropdown for '{label}'")

    page.wait_for_timeout(400)

    hidden_value = page.locator(hidden_selector).get_attribute("value") or "0"
    if hidden_value in ("0", ""):
        log.error("❌  Hidden field '%s' still '%s' after selecting '%s'.",
                  hidden_selector, hidden_value, value)
        raise RuntimeError(
            f"Hidden field {hidden_selector} not populated after selecting '{value}'"
        )
    log.info("  Hidden field %-18s → '%s' ✓", hidden_selector, hidden_value)


# ═══════════════════════════════════════════
#  STEP 2c – CREATE VOLUME
# ═══════════════════════════════════════════

def create_volume(page: Page, data: dict) -> None:
    log.info("─── Step 2: Create New Volume Index ───")

    btn = page.locator(NEW_REQ_BTN)
    btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    btn.click()

    page.locator(OFFICE_DISTRICT).wait_for(state="visible", timeout=NAV_TIMEOUT_MS)

    _fill_autocomplete(page, OFFICE_DISTRICT, SUGGESTIONS[OFFICE_DISTRICT],
                       HIDDEN_DISTRICT_ID2, data["office_district"], "office_district")
    _fill_autocomplete(page, OFFICE_SRO, SUGGESTIONS[OFFICE_SRO],
                       HIDDEN_SRO_ID2, data["office_sro"], "office_sro")
    _fill_autocomplete(page, VOLUME_DISTRICT, SUGGESTIONS[VOLUME_DISTRICT],
                       HIDDEN_DISTRICT_ID, data["volume_district"], "volume_district")
    _fill_autocomplete(page, VOLUME_SRO, SUGGESTIONS[VOLUME_SRO],
                       HIDDEN_SRO_ID, data["volume_sro"], "volume_sro")

    _fill_plain(page, VOLUME_YEAR, data["volume_year"], "volume_year")
    _fill_plain(page, VOLUME_NO,   data["volume_no"],   "volume_no")

    book_value_map = {"book1": "1", "book2": "2", "book3": "3", "book4": "4"}
    book_val = book_value_map.get(data["book_type"].lower(), data["book_type"])
    book_loc = page.locator(BOOK_TYPE_SELECT)
    book_loc.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    book_loc.select_option(value=book_val)
    log.info("  Selected %-22s → '%s' (value='%s')",
             "book_type", data["book_type"], book_val)

    if data["radio"].strip().lower() == "yes":
        page.locator(RADIO_YES).check()
        log.info("  Checked radio → Yes")
    else:
        page.locator(RADIO_NO).check()
        log.info("  Checked radio → No")

    save_btn = page.locator(ADD_VOLUME_BTN)
    save_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    with page.expect_event("dialog", timeout=NAV_TIMEOUT_MS) as dialog_info:
        save_btn.click()

    dialog = dialog_info.value
    log.info("  Alert: '%s' → accepting", dialog.message)
    dialog.accept()

    page.locator("#indexdetailsdiv").wait_for(state="visible", timeout=NAV_TIMEOUT_MS)
    log.info("✅  Volume created. Index Details section visible.")


# ═══════════════════════════════════════════
#  STEP 3a – READ PDF FILES
# ═══════════════════════════════════════════

def read_pdf_files(folder_path: str) -> list:
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

def _get_index_row_count(page: Page) -> int:
    rows = page.locator("#indexdetails tbody tr")
    count = rows.count()
    if count == 1 and "no records" in rows.first.inner_text().strip().lower():
        return 0
    return count


def _read_volume_year_from_page(page: Page) -> str:
    loc = page.locator(VOLUME_YEAR)
    loc.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    year = loc.input_value().strip()
    if not year:
        raise RuntimeError("#volume_year is empty on the page")
    log.info("  Volume year from page: '%s'", year)
    return year


def _fill_and_submit_entry(page: Page, volume_year: str, deed_no: str) -> str:
    """
    Fill presentation_year + deed_no and click Add Index.

    Returns the portal alert message if one fired (duplicate / validation),
    or "" if the entry was accepted with no alert.

    POLLING STRATEGY — zero extra wait on the happy path:
      1. Register a page.once("dialog") listener BEFORE clicking so we never
         miss a dialog that fires synchronously or near-synchronously.
      2. Click Add.
      3. Poll every 200 ms for up to PAGE_TIMEOUT_MS checking EITHER:
           a. captured_dialog is populated  → error/duplicate, return message
           b. row count increased           → success, return ""
      4. Whichever fires first wins — no fixed sleep on the success path.
    """
    # Fill presentation year
    py_field = page.locator(PRESENTATION_YEAR)
    py_field.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    py_field.click()
    py_field.click(click_count=3)
    py_field.fill(volume_year)
    py_field.press("Tab")

    # Fill deed number
    deed_field = page.locator(DEED_NO)
    deed_field.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    deed_field.click()
    deed_field.click(click_count=3)
    deed_field.fill(deed_no)

    add_btn = page.locator(ADD_INDEX_BTN)
    add_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    # Snapshot row count BEFORE clicking
    rows_before = _get_index_row_count(page)

    # Register listener BEFORE click so fast-firing dialogs are never missed
    captured_dialog: list[str] = []

    def _grab(d: Dialog) -> None:
        captured_dialog.append(d.message)
        d.accept()

    page.once("dialog", _grab)
    add_btn.click()

    # Poll: success path returns almost instantly (one poll cycle after the
    # row appears). Duplicate/error path returns as soon as dialog fires.
    deadline_ms   = PAGE_TIMEOUT_MS
    poll_ms       = 200

    while deadline_ms > 0:
        if captured_dialog:
            # Dialog fired — duplicate or validation alert
            try:
                page.remove_listener("dialog", _grab)
            except Exception:
                pass
            return captured_dialog[0]

        if _get_index_row_count(page) > rows_before:
            # New row appeared — entry accepted
            try:
                page.remove_listener("dialog", _grab)
            except Exception:
                pass
            return ""

        page.wait_for_timeout(poll_ms)
        deadline_ms -= poll_ms

    # Timeout — neither dialog nor new row
    try:
        page.remove_listener("dialog", _grab)
    except Exception:
        pass
    log.warning(
        "  Neither row increase nor dialog within %d ms for deed %s",
        PAGE_TIMEOUT_MS, deed_no,
    )
    return ""


def create_indexes(page: Page, pdf_files: list) -> list:
    log.info("─── Step 3: Create Index Entries (%d file(s)) ───", len(pdf_files))

    if not pdf_files:
        log.warning("No PDF files to process. Skipping.")
        return []

    volume_year     = _read_volume_year_from_page(page)
    failed_files:    list[str] = []
    duplicate_files: list[str] = []   # stores deed stems (not filenames)
    all_alerts:      list[str] = []

    for idx, pdf_path in enumerate(pdf_files, start=1):
        deed_no = pdf_path.stem
        log.info("[%d/%d] Processing: %s  →  deed_no='%s'",
                 idx, len(pdf_files), pdf_path.name, deed_no)

        success      = False
        is_duplicate = False

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                log.warning("  Retry %d/%d for deed '%s'…",
                            attempt, MAX_RETRIES, deed_no)
                page.wait_for_timeout(1000 * attempt)

            alert_text = _fill_and_submit_entry(page, volume_year, deed_no)

            if alert_text:
                # ── Record the alert against the CORRECT deed number ──────
                entry = f"deed {deed_no!r}  →  {alert_text}"
                if entry not in all_alerts:
                    all_alerts.append(entry)

                if any(sig in alert_text.lower() for sig in DUPLICATE_SIGNALS):
                    # Print in bright red so skipped deeds are unmissable
                    _log_skipped(deed_no, f"portal says: \"{alert_text}\"")
                    duplicate_files.append(deed_no)   # store stem, not filename
                    is_duplicate = True
                    break
                else:
                    log.warning(
                        "  Validation alert on attempt %d for deed %s: '%s'",
                        attempt, deed_no, alert_text,
                    )
                    continue

            # No alert — verify row actually appeared
            rows_now = _get_index_row_count(page)
            log.info(
                "  ✅  Deed %s indexed (table rows now: %d)", deed_no, rows_now
            )
            success = True
            break

        if not success and not is_duplicate:
            log.error("❌  FAILED after %d attempts: deed '%s'",
                      MAX_RETRIES, deed_no)
            failed_files.append(deed_no)

    # ── Final summary ─────────────────────────────────────────────────────
    final_count = _get_index_row_count(page)
    expected    = len(pdf_files) - len(duplicate_files)

    log.info("════════════════════════════════════")
    log.info("  Index creation complete.")
    log.info("  Total PDFs      : %d", len(pdf_files))
    log.info("  Created         : %d", final_count)
    log.info("  Duplicates skip : %d", len(duplicate_files))
    log.info("  Failed          : %d", len(failed_files))

    if duplicate_files:
        # Print the full skipped-deed list in red at the end for easy review
        print(
            f"\n{_C.RED}{_C.BOLD}"
            f"  ⛔  SKIPPED DEEDS (duplicates already on portal):\n"
            + "\n".join(f"       • {d}" for d in duplicate_files)
            + f"{_C.RESET}\n",
            flush=True,
        )
        _file_handler.stream.write(
            "[SKIPPED DEEDS SUMMARY] " + ", ".join(duplicate_files) + "\n"
        )
        _file_handler.stream.flush()

    if failed_files:
        log.error("  ❌ Failed deeds: %s", failed_files)
    else:
        log.info("  No failures ✅")

    if final_count != expected:
        log.warning("  ⚠️  Expected %d rows but table shows %d.",
                    expected, final_count)
    log.info("════════════════════════════════════")

    return all_alerts


# ═══════════════════════════════════════════
#  STEP 4 – SUBMIT VOLUME INDEX
# ═══════════════════════════════════════════

def submit_volume(page: Page, alerts: list) -> None:
    log.info("─── Step 4: Submit Volume ───")

    submit_btn = page.locator(SUBMIT_VOLUME_BTN)
    submit_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    def _handle(dialog: Dialog) -> None:
        log.info("  Dialog [%s]: '%s' → accepting", dialog.type, dialog.message)
        dialog.accept()

    page.on("dialog", _handle)
    submit_btn.click()

    try:
        page.wait_for_url(
            lambda url: "indexCreation" not in url and "indexCreate" not in url,
            timeout=NAV_TIMEOUT_MS,
        )
        log.info("✅  Volume submitted. Redirected to: %s", page.url)
    except PlaywrightTimeoutError:
        log.warning("⚠️  No redirect detected after submit — continuing.")
    finally:
        page.remove_listener("dialog", _handle)

    if alerts:
        log.info("╔══════════════════════════════════════╗")
        log.info("  PORTAL ALERTS DURING INDEXING (%d)", len(alerts))
        log.info("╚══════════════════════════════════════╝")
        for i, alert in enumerate(alerts, 1):
            log.warning("  [%d] %s", i, alert)
    else:
        log.info("  No portal alerts during indexing ✅")


# ═══════════════════════════════════════════════════════
#  STEP 5 – NAVIGATE TO UPLOAD SCANNED DOCUMENT PAGE
# ═══════════════════════════════════════════════════════

def navigate_to_upload_page(page: Page) -> None:
    log.info("─── Step 5: Navigate to Upload Scanned Document page ───")

    upload_link = page.locator("text=Upload Scanned Document").first
    upload_link.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    upload_link.click()

    page.wait_for_url(lambda url: "uploadScannedDocument" in url,
                      timeout=NAV_TIMEOUT_MS)
    page.locator("#rr tbody, #tableBody").first.wait_for(
        state="visible", timeout=NAV_TIMEOUT_MS
    )
    log.info("✅  Upload Scanned Document page loaded. URL: %s", page.url)


# ═══════════════════════════════════════════════════════
#  STEP 6 – FIND VOLUME IN LIST AND CLICK PROCESS
# ═══════════════════════════════════════════════════════

def _go_to_last_pagination_page(page: Page) -> None:
    last_btn = page.locator("#pagination .page-item.last:not(.disabled) a")
    if last_btn.count() > 0:
        last_btn.first.click()
        page.wait_for_timeout(1200)
        log.info("  Navigated to last pagination page.")
    else:
        log.info("  Already on last (or only) page.")


def _go_to_prev_pagination_page(page: Page) -> bool:
    prev_btn = page.locator("#pagination .page-item.prev:not(.disabled) a")
    if prev_btn.count() > 0:
        prev_btn.first.click()
        page.wait_for_timeout(1000)
        return True
    return False


def _find_volume_row_on_current_page(page: Page, volume_no: str, volume_year: str):
    target_no   = volume_no.strip()
    target_year = volume_year.strip()

    rows = page.locator("#rr tbody tr, #tableBody tr")
    for i in range(rows.count()):
        row   = rows.nth(i)
        cells = row.locator("td")
        if cells.count() < 8:
            continue
        row_vol_no   = cells.nth(5).inner_text().strip()
        row_vol_year = cells.nth(7).inner_text().strip()
        if row_vol_no == target_no and row_vol_year == target_year:
            return row
    return None


def find_and_process_volume(page: Page, volume_no: str, volume_year: str) -> None:
    log.info("─── Step 6: Find volume no='%s', year='%s' and click Process ───",
             volume_no, volume_year)

    _go_to_last_pagination_page(page)

    for _ in range(20):
        row = _find_volume_row_on_current_page(page, volume_no, volume_year)
        if row:
            log.info("  Found matching volume. Clicking Process…")
            process_btn = row.locator("button:has-text('Process')")
            process_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

            with page.expect_navigation(
                wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS
            ):
                process_btn.click()

            log.info("✅  Process clicked. URL: %s", page.url)

            try:
                page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
                page.wait_for_selector(
                    "#table-section table tbody tr input[type='file']",
                    state="attached",
                    timeout=NAV_TIMEOUT_MS,
                )
                total = page.locator("#table-section table tbody tr").count()
                log.info("  Upload table ready: %d rows.", total)
            except PlaywrightTimeoutError:
                log.warning("⚠️  File inputs not detected — trying row fallback.")
                page.locator("#table-section table tbody tr").first.wait_for(
                    state="visible", timeout=NAV_TIMEOUT_MS
                )
            return

        if not _go_to_prev_pagination_page(page):
            break

    raise RuntimeError(
        f"Volume no='{volume_no}' year='{volume_year}' not found "
        "in the pending list after scanning all pages."
    )


# ═══════════════════════════════════════════════════════
#  STEP 7 – UPLOAD PDF FILES TO EACH INDEX ROW
# ═══════════════════════════════════════════════════════

def upload_pdf_files(page: Page, folder_path: str) -> None:
    log.info("─── Step 7: Upload PDF files to index rows ───")

    folder         = Path(folder_path)
    uploaded_deeds: set  = set()
    failed_uploads: list = []
    missing_pdfs:   list = []

    for iteration in range(500):
        try:
            page.wait_for_load_state("networkidle", timeout=5_000)
        except PlaywrightTimeoutError:
            log.debug("  Network not fully idle — proceeding.")

        try:
            page.wait_for_selector(
                "#table-section table tbody tr input[type='file']",
                state="attached",
                timeout=5_000,
            )
        except PlaywrightTimeoutError:
            log.info("  No pending file inputs. Checking if all rows done.")

        rows      = page.locator("#table-section table tbody tr")
        row_count = rows.count()
        log.info("  [iter %d] Table has %d rows.", iteration, row_count)

        if row_count == 0:
            log.info("  No rows in upload table. Done.")
            break

        target_deed_no: str | None       = None
        target_file_input_id: str | None = None

        for i in range(row_count):
            row   = rows.nth(i)
            cells = row.locator("td")
            if cells.count() < 8:
                continue

            deed_no = cells.nth(6).inner_text().strip()
            if not deed_no or deed_no in uploaded_deeds:
                continue

            file_input = cells.nth(7).locator("input[type='file']")
            if file_input.count() == 0:
                log.info("  Row %d deed=%-8s — already uploaded", i + 1, deed_no)
                uploaded_deeds.add(deed_no)
                continue

            target_deed_no       = deed_no
            target_file_input_id = file_input.get_attribute("id")
            break

        if target_deed_no is None:
            log.info("  All rows processed or no pending file inputs remain.")
            break

        pdf_path = folder / f"{target_deed_no}.pdf"
        if not pdf_path.exists():
            log.error("  ❌  PDF not found for deed %s: %s", target_deed_no, pdf_path)
            missing_pdfs.append(f"{target_deed_no}.pdf")
            uploaded_deeds.add(target_deed_no)
            continue

        log.info("  [%d] Uploading deed %-8s ← %s",
                 iteration + 1, target_deed_no, pdf_path.name)

        file_input_loc = page.locator(f"#{target_file_input_id}")

        try:
            with page.expect_event("dialog", timeout=UPLOAD_TIMEOUT_MS) as dialog_info:
                file_input_loc.set_input_files(str(pdf_path))

            dialog = dialog_info.value
            msg    = dialog.message
            log.info("  Alert: '%s' → accepting", msg)
            dialog.accept()

            msg_lower = msg.lower()
            if "success" in msg_lower or "uploaded" in msg_lower:
                log.info("  ✅  Deed %s uploaded successfully.", target_deed_no)
            elif any(k in msg_lower for k in ("size", "large", "30")):
                log.error("  ❌  File too large for deed %s: '%s'",
                          target_deed_no, msg)
                failed_uploads.append(f"{target_deed_no}.pdf  (too large)")
                uploaded_deeds.add(target_deed_no)
                continue
            else:
                log.warning("  ⚠️  Unexpected alert for deed %s: '%s'",
                            target_deed_no, msg)
                failed_uploads.append(f"{target_deed_no}.pdf  (alert: {msg})")
                uploaded_deeds.add(target_deed_no)
                continue

        except PlaywrightTimeoutError:
            log.warning("  ⚠️  No dialog within %d s for deed %s — failed.",
                        UPLOAD_TIMEOUT_MS // 1000, target_deed_no)
            failed_uploads.append(f"{target_deed_no}.pdf  (timeout)")
            uploaded_deeds.add(target_deed_no)
            continue

        try:
            page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
            page.wait_for_load_state("networkidle",      timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(2_500)
        except PlaywrightTimeoutError:
            log.warning("  Page reload didn't fully settle for deed %s.",
                        target_deed_no)

        uploaded_deeds.add(target_deed_no)
        log.info("  Page reloading for next deed…")

    total_ok = len(uploaded_deeds) - len(missing_pdfs) - len(failed_uploads)
    log.info("════════════════════════════════════════════")
    log.info("  Upload complete.")
    log.info("  Uploaded OK     : %d", total_ok)
    log.info("  Missing PDFs    : %d", len(missing_pdfs))
    log.info("  Failed uploads  : %d", len(failed_uploads))
    if missing_pdfs:
        log.error("  Missing  : %s", missing_pdfs)
    if failed_uploads:
        log.error("  Failed   : %s", failed_uploads)
    log.info("════════════════════════════════════════════")


# ═══════════════════════════════════════════════════════
#  STEP 8 – SUBMIT UPLOADED VOLUME
# ═══════════════════════════════════════════════════════

def submit_uploaded_volume(page: Page) -> None:
    log.info("─── Step 8: Submit uploaded volume ───")

    submit_btn = page.locator("button[onclick='submitVolume();']")
    if submit_btn.count() == 0:
        log.warning("  Exact onclick selector missed — trying fallback.")
        submit_btn = page.locator("button[onclick*='submitVolume']").first

    submit_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    collected:          list[Dialog] = []
    validation_blocked: list[bool]   = [False]

    def _handle(dialog: Dialog) -> None:
        msg = dialog.message
        log.info("  Dialog [%s]: '%s' → accepting", dialog.type, msg)
        collected.append(dialog)
        if "please upload" in msg.lower():
            validation_blocked[0] = True
        dialog.accept()

    page.on("dialog", _handle)

    try:
        submit_btn.click()

        page.wait_for_timeout(1_500)

        if validation_blocked[0]:
            raise RuntimeError(
                "Portal validation failed — not all deeds uploaded. "
                f"Dialogs: {[d.message for d in collected]}"
            )

        try:
            page.wait_for_url(
                lambda url: "uploadScannedDocument" in url,
                timeout=NAV_TIMEOUT_MS,
            )
            log.info("✅  Uploaded volume submitted. URL: %s", page.url)
        except PlaywrightTimeoutError:
            log.critical("⚠️  No redirect after submit within %d s. URL: %s",
                         NAV_TIMEOUT_MS // 1000, page.url)

        if not collected:
            log.warning("  ⚠️  No dialogs fired — portal may have silently failed.")
        else:
            log.info("  %d dialog(s) handled:", len(collected))
            for i, d in enumerate(collected, 1):
                log.info("    [%d] %s: %s", i, d.type, d.message)

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
        context          = browser.new_context()
        page: Page       = context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            login(page)

            # initally it was reading the config.txt file from the config data, now we have defined the config information in the current script as well, so we don't need to read the config file, we can just define our config in the current script and we are good to go

            # volume_data = read_volume_data(FOLDER_PATH)
            volume_data = VOLUME_CONFIG
            create_volume(page, volume_data)

            pdf_files = read_pdf_files(FOLDER_PATH)
            alerts    = create_indexes(page, pdf_files)

            submit_volume(page, alerts)
            navigate_to_upload_page(page)

            find_and_process_volume(
                page,
                volume_no   = volume_data["volume_no"],
                volume_year = volume_data["volume_year"],   # ← was volume_district
            )

            upload_pdf_files(page, FOLDER_PATH)
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