# consist the claude automation code for the file upload
# DONE FOR UPLOADING (CHECKED)
# NOTE : CHECKED !!

"""
Government Indexing Portal – Upload-Only Automation
====================================================
Portal : Bihar e-Registration (enibandhan.bihar.gov.in)

Automation starts ONLY when the user has reached the file upload section
(/digitize/indexScanned) AND the table has been populated by listDetails().
"""

import sys
import logging
from pathlib import Path

from playwright.sync_api import (
    sync_playwright, Page, Browser, Dialog,
    TimeoutError as PlaywrightTimeoutError,
)

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────
LOGIN_URL: str   = "https://enibandhan.bihar.gov.in/users/login"
FOLDER_PATH: str = "/Users/ujjwalkumar/Desktop/07-04-2026/VOL-43-1919-2700-BRS-PDF-DONE"
HEADLESS: bool   = False

WAIT_FOR_UPLOAD_PAGE_MS: int = 300_000   # 5 min for manual login + navigation
PAGE_TIMEOUT_MS: int         =  120_000
NAV_TIMEOUT_MS: int          =  120_000
UPLOAD_TIMEOUT_MS: int       = 120_000
MAX_UPLOAD_ITERATIONS: int   =  2_000

# The upload section URL fragment — automation only starts here
UPLOAD_PAGE_URL_FRAGMENT = "indexScanned"

# Table is built by listDetails() AJAX — wait for first <td>
TABLE_BODY_SELECTOR = "#table-section table tbody tr td input[type='file']"
SUBMIT_BTN_SELECTOR = "button[onclick='submitVolume();']"

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("upload_only.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#  STEP 1 – OPEN LOGIN PAGE AND WAIT FOR
#           THE EXACT UPLOAD SECTION
# ═══════════════════════════════════════════


def wait_for_upload_page(page: Page) -> tuple[int, int]:
    """
    Wait until URL contains 'indexScanned' AND the page has settled.
    Returns (total_uploaded, count_deed) read from hidden fields so the
    caller can decide whether uploads are needed or we can go straight to submit.
    """
    log.info("Opening login page: %s", LOGIN_URL)
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    log.info(
        "⏳  Waiting for the file upload section to appear…\n"
        "    Please complete these steps manually:\n"
        "      1. Log in and solve the CAPTCHA\n"
        "      2. Click 'Upload Scanned Document' in the left menu\n"
        "      3. Click 'Process' on your volume row\n"
        "    Automation will start ONLY after the indexScanned upload page loads.\n"
        "    Waiting up to %d minutes…",
        WAIT_FOR_UPLOAD_PAGE_MS // 60_000,
    )

    deadline_ms = WAIT_FOR_UPLOAD_PAGE_MS
    poll_ms     = 500

    while deadline_ms > 0:
        on_upload_page = UPLOAD_PAGE_URL_FRAGMENT in page.url   # "indexScanned"

        if on_upload_page:
            # Wait for listDetails() AJAX to finish — it sets #count_deed and
            # #total_uploaded, and either renders file inputs (pending) or just
            # eye-buttons (all already uploaded).
            # We detect readiness by waiting for #count_deed to have a non-empty value.
            count_deed_val = ""
            try:
                count_deed_val = page.locator("#count_deed").get_attribute("value") or ""
            except Exception:
                pass

            if count_deed_val:
                # AJAX has settled — read the counters
                try:
                    total_uploaded = int(page.locator("#total_uploaded").get_attribute("value") or "0")
                    count_deed     = int(count_deed_val)
                except ValueError:
                    total_uploaded, count_deed = 0, 0

                log.info(
                    "✅  indexScanned page ready.\n"
                    "    URL           : %s\n"
                    "    total_uploaded: %d\n"
                    "    count_deed    : %d",
                    page.url, total_uploaded, count_deed,
                )

                file_input_count = page.locator("input[type='file']").count()
                log.info("    File inputs on page: %d", file_input_count)

                if total_uploaded >= count_deed and count_deed > 0:
                    log.info(
                        "  ℹ️  All %d deeds already uploaded (total_uploaded=%d). "
                        "Skipping upload loop — proceeding to submit.",
                        count_deed, total_uploaded,
                    )
                elif file_input_count == 0:
                    log.warning(
                        "  ⚠️  total_uploaded (%d) < count_deed (%d) but no file inputs "
                        "found. Something is wrong with the page state.",
                        total_uploaded, count_deed,
                    )

                return total_uploaded, count_deed
            else:
                # listDetails() AJAX not yet finished
                if deadline_ms % 2000 < poll_ms:
                    log.info(
                        "  On indexScanned page — waiting for listDetails() AJAX… "
                        "(%d s remaining)", deadline_ms // 1000,
                    )
        else:
            if deadline_ms % 10_000 < poll_ms:
                log.info(
                    "  Current page: %s\n"
                    "  Waiting for '%s' in URL… (%d s remaining)",
                    page.url, UPLOAD_PAGE_URL_FRAGMENT, deadline_ms // 1000,
                )

        page.wait_for_timeout(poll_ms)
        deadline_ms -= poll_ms

    log.error("❌  Timed out waiting for indexScanned page. Last URL: %s", page.url)
    raise SystemExit(1)


# ═══════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════

def _wait_for_table_ready(page: Page) -> None:
    """
    After each per-file form POST to /digitize/indexScanned, the page
    reloads and listDetails() re-runs. Wait for it to settle before
    reading the next row.

    Correct sequence:
      1. domcontentloaded  — POST response received, ready() is about to run
      2. 800 ms pause      — lets $(document).ready() fire and send the AJAX
      3. wait_for_selector — blocks until listDetails() writes the table
      4. networkidle       — confirms the AJAX has fully settled
      5. 2 s buffer        — CSRF token refresh + trailing microtasks
    """
    try:
        page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log.warning("  domcontentloaded timeout — continuing.")

    # Let $(document).ready() fire and send the listDetails() AJAX request
    page.wait_for_timeout(800)

    try:
        page.wait_for_selector(
            TABLE_BODY_SELECTOR,
            state="attached",
            timeout=NAV_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError:
        log.warning("  Table rows not found after reload — may be fully uploaded.")

    try:
        page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log.warning("  networkidle timeout after table loaded — continuing.")

    # Buffer for CSRF token refresh
    page.wait_for_timeout(2_000)


def _get_pending_row(page: Page, uploaded_deeds: set) -> tuple[str | None, str | None]:
    """
    Scan the table for the first row that:
      - Has a non-empty Deed No (column index 6)
      - Has not already been processed this session
      - Still has an <input type='file'> in column 7

    Column layout (0-indexed):
      0: S.No  1: District  2: SRO  3: Vol No  4: Vol Year
      5: Pres. Year  6: Deed No  7: Upload cell

    Returns (deed_no, file_input_id) or (None, None) if nothing pending.
    """
    rows  = page.locator("#table-section table tbody tr")
    count = rows.count()

    for i in range(count):
        row   = rows.nth(i)
        cells = row.locator("td")

        if cells.count() < 8:
            continue

        deed_no = cells.nth(6).inner_text().strip()
        if not deed_no:
            continue

        if deed_no in uploaded_deeds:
            continue

        file_input = cells.nth(7).locator("input[type='file']")
        if file_input.count() == 0:
            # Eye button only → already uploaded
            log.debug("  Row %d deed=%-8s — already uploaded", i + 1, deed_no)
            uploaded_deeds.add(deed_no)
            continue

        return deed_no, file_input.get_attribute("id")

    return None, None


# ═══════════════════════════════════════════
#  STEP 2 – UPLOAD PDF FILES
# ═══════════════════════════════════════════

def upload_pdf_files(page: Page, folder_path: str) -> tuple[list, list]:
    """
    Upload loop. For each pending deed row:
      set_input_files() → onchange → checkFileSize → validatePDF (FileReader)
      → fileupload (AJAX) → createindex (AJAX)
      → alert("The deed document has been uploaded successfully.")
      → form POST to /digitize/indexScanned  ← full page reload

    Returns (failed_uploads, missing_pdfs) for pre-submit validation.
    """
    log.info("─── Uploading PDF files from: %s ───", folder_path)

    folder = Path(folder_path)
    uploaded_deeds:   set  = set()
    successful_deeds: list = []
    failed_uploads:   list = []
    missing_pdfs:     list = []

    for iteration in range(MAX_UPLOAD_ITERATIONS):
        deed_no, input_id = _get_pending_row(page, uploaded_deeds)

        if deed_no is None:
            log.info("  No more pending rows — upload loop complete.")
            break

        pdf_path = folder / f"{deed_no}.pdf"
        if not pdf_path.exists():
            log.error("  ❌  PDF not found: %s", pdf_path)
            missing_pdfs.append(f"{deed_no}.pdf")
            uploaded_deeds.add(deed_no)
            continue

        log.info(
            "  [%d] Uploading deed %-8s ← %s",
            iteration + 1, deed_no, pdf_path.name,
        )

        file_input_loc = page.locator(f"#{input_id}")

        try:
            # expect_event registered BEFORE set_input_files so the async
            # alert (fired after two AJAX calls complete) is always captured
            with page.expect_event("dialog", timeout=UPLOAD_TIMEOUT_MS) as dialog_info:
                file_input_loc.set_input_files(str(pdf_path))

            dialog: Dialog = dialog_info.value
            msg            = dialog.message
            msg_lower      = msg.lower()
            log.info("  Alert: '%s'", msg)

            is_success = "successfully" in msg_lower or "uploaded" in msg_lower

            if not is_success:
                dialog.accept()
                if any(k in msg_lower for k in ("30 mb", "size", "large", "greater than")):
                    log.error("  ❌  File too large for deed %s", deed_no)
                    failed_uploads.append(f"{deed_no}.pdf  (too large)")
                elif "valid" in msg_lower:
                    log.error("  ❌  Invalid file for deed %s: '%s'", deed_no, msg)
                    failed_uploads.append(f"{deed_no}.pdf  (invalid: {msg})")
                else:
                    log.warning("  ⚠️  Unexpected alert for deed %s: '%s'", deed_no, msg)
                    failed_uploads.append(f"{deed_no}.pdf  (alert: {msg})")
                uploaded_deeds.add(deed_no)
                continue

            # Accept the dialog inside expect_navigation so Playwright waits
            # for the form POST navigation to actually start and complete.
            # Without this, wait_for_load_state can catch the OLD page before
            # form.submit() has fired — causing stale row reads.
            try:
                with page.expect_navigation(
                    wait_until="domcontentloaded",
                    timeout=NAV_TIMEOUT_MS,
                ):
                    dialog.accept()
            except PlaywrightTimeoutError:
                log.warning(
                    "  Navigation after accept() timed out for deed %s "
                    "— continuing anyway.", deed_no,
                )

            log.info("  ✅  Deed %s uploaded — waiting for page reload.", deed_no)
            successful_deeds.append(deed_no)

        except PlaywrightTimeoutError:
            log.warning(
                "  ⚠️  No alert within %d s for deed %s — marking failed.",
                UPLOAD_TIMEOUT_MS // 1000, deed_no,
            )
            failed_uploads.append(f"{deed_no}.pdf  (timeout — no alert)")
            uploaded_deeds.add(deed_no)
            continue

        uploaded_deeds.add(deed_no)
        _wait_for_table_ready(page)
        log.info("  Table ready — moving to next deed.")

    # ── Summary ───────────────────────────────────────────────────────────
    log.info("════════════════════════════════════════════")
    log.info("  Upload loop finished.")
    log.info("  Accepted by portal : %d", len(successful_deeds))
    log.info("  Missing PDFs       : %d", len(missing_pdfs))
    log.info("  Failed / skipped   : %d", len(failed_uploads))
    if missing_pdfs:
        log.error("  Missing  : %s", missing_pdfs)
    if failed_uploads:
        log.error("  Failed   : %s", failed_uploads)
    log.info("════════════════════════════════════════════")

    return failed_uploads, missing_pdfs


# ═══════════════════════════════════════════
#  STEP 3 – SUBMIT
# ═══════════════════════════════════════════

def submit_uploaded_volume(
    page: Page,
    failed_uploads: list,
    missing_pdfs: list,
) -> None:
    """
    submitVolume() JS flow:
      1. Validates total_uploaded == count_deed
         → alert("Please upload all deed documents.") if not — aborts
      2. confirm("Are you sure you want to submit?") → we accept
      3. AJAX POST to status/update
      4. alert("The volume has been submitted for verification.") → we accept
      5. redirectToDashBoard() → /digitize/uploadScannedDocument
    """
    log.info("─── Submitting uploaded volume ───")

    # Pre-submit guard — avoid the 60 s redirect timeout from portal validation
    if failed_uploads or missing_pdfs:
        msg = (
            f"Cannot submit — {len(failed_uploads)} failed upload(s) and "
            f"{len(missing_pdfs)} missing PDF(s).\n"
            f"  Failed  : {failed_uploads}\n"
            f"  Missing : {missing_pdfs}"
        )
        log.error("❌  %s", msg)
        raise RuntimeError(msg)

    submit_btn = page.locator(SUBMIT_BTN_SELECTOR)
    if submit_btn.count() == 0:
        log.warning("  Exact selector not found — trying partial match.")
        submit_btn = page.locator("button[onclick*='submitVolume']").first

    submit_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    collected_dialogs: list[Dialog] = []
    validation_failed: list[bool]   = [False]

    def _on_dialog(d: Dialog) -> None:
        log.info("  Dialog [%s]: '%s' → accepting", d.type, d.message)
        collected_dialogs.append(d)
        if "please upload" in d.message.lower():
            validation_failed[0] = True
        d.accept()

    page.on("dialog", _on_dialog)

    try:
        submit_btn.click()

        # Short pause to let the first dialog (confirm or validation) fire
        page.wait_for_timeout(1_500)
        if validation_failed[0]:
            raise RuntimeError(
                "Portal validation blocked submit — not all deeds uploaded. "
                f"Dialogs: {[d.message for d in collected_dialogs]}"
            )

        try:
            page.wait_for_url(
                lambda url: "uploadScannedDocument" in url,
                timeout=NAV_TIMEOUT_MS,
            )
            log.info("✅  Submitted. Redirected to: %s", page.url)
        except PlaywrightTimeoutError:
            log.critical(
                "⚠️  No redirect after submit within %d s. URL: %s",
                NAV_TIMEOUT_MS // 1000, page.url,
            )

        if not collected_dialogs:
            log.warning("  ⚠️  No dialogs fired — portal may have silently failed.")
        else:
            log.info("  %d dialog(s) during submit:", len(collected_dialogs))
            for i, d in enumerate(collected_dialogs, 1):
                log.info("    [%d] %s: %s", i, d.type, d.message)

    finally:
        page.remove_listener("dialog", _on_dialog)


# ═══════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════

def main() -> None:
    log.info("════════════════════════════════════════")
    log.info("  Bihar Portal — Upload-Only Automation")
    log.info("════════════════════════════════════════")
    log.info("Folder : %s", FOLDER_PATH)

    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch(headless=HEADLESS)
        context          = browser.new_context()
        page: Page       = context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            total_uploaded, count_deed = wait_for_upload_page(page)

            if total_uploaded < count_deed:
                # Uploads needed
                failed_uploads, missing_pdfs = upload_pdf_files(page, FOLDER_PATH)
            else:
                # Already fully uploaded — go straight to submit
                log.info("  All deeds already uploaded — skipping upload loop.")
                failed_uploads, missing_pdfs = [], []

            submit_uploaded_volume(page, failed_uploads, missing_pdfs)

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