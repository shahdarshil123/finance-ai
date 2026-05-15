import asyncio
import os
import re
from collections.abc import Callable

import httpx
import pdfplumber
from bs4 import BeautifulSoup

EDGAR_BASE = "https://www.sec.gov"
EDGAR_DATA = "https://data.sec.gov"
HEADERS = {
    "User-Agent": "financial-ai-agent/1.0 (academic research; contact: research@example.com)",
    "Accept-Encoding": "gzip, deflate",
}


async def get_cik(ticker: str) -> str:
    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        resp = await client.get(f"{EDGAR_BASE}/files/company_tickers.json")
        resp.raise_for_status()

    ticker_upper = ticker.upper()
    for entry in resp.json().values():
        if entry["ticker"].upper() == ticker_upper:
            return str(entry["cik_str"]).zfill(10)

    raise ValueError(f"Ticker '{ticker}' not found in SEC EDGAR company list.")


async def get_10k_filings(cik: str) -> list[dict]:
    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        resp = await client.get(f"{EDGAR_DATA}/submissions/CIK{cik}.json")
        resp.raise_for_status()
        data = resp.json()

    recent       = data.get("filings", {}).get("recent", {})
    forms        = recent.get("form", [])
    dates        = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    accessions   = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    # Pad report_dates in case the field is missing or shorter
    report_dates = list(report_dates) + [""] * max(0, len(forms) - len(report_dates))

    return [
        {
            "filing_date":  date,
            "fiscal_year":  int(report_date[:4]) if report_date else int(date[:4]),
            "accession":    accession,
            "primary_doc":  doc,
        }
        for form, date, report_date, accession, doc
        in zip(forms, dates, report_dates, accessions, primary_docs)
        if form in ("10-K", "10-K405")
    ]


def filing_url(cik: str, accession: str, doc_name: str) -> str:
    return (
        f"{EDGAR_BASE}/Archives/edgar/data/"
        f"{int(cik)}/{accession.replace('-', '')}/{doc_name}"
    )


def _filing_dir_url(cik: str, accession: str) -> str:
    """Base URL for the filing's document directory on EDGAR."""
    return f"{EDGAR_BASE}/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"


def _resolve_href(href: str, filing_dir: str) -> str:
    """
    Turn an href from the EDGAR index page into a full URL.
    Handles three cases:
      - already absolute:  https://...
      - root-relative:     /Archives/edgar/data/...
      - bare filename:     aapl-20230930.pdf
    """
    href = href.strip()
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"{EDGAR_BASE}{href}"
    return f"{filing_dir}/{href}"


async def _find_pdf_in_index(
    cik: str,
    accession: str,
    emit: Callable[[str], None] | None = None,
) -> str | None:
    """
    Fetch the EDGAR filing index page and return the URL of the primary PDF.
    Returns None if no PDF is listed (caller should fall back to HTML).
    """
    def log(msg: str):
        if emit:
            emit(msg)

    filing_dir = _filing_dir_url(cik, accession)
    index_url  = f"{filing_dir}/{accession}-index.htm"

    log(f"Fetching filing index: {index_url}")
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=20) as client:
            resp = await client.get(index_url)

        if resp.status_code != 200:
            log(f"Index page returned HTTP {resp.status_code} — will use HTML fallback.")
            return None

        soup = BeautifulSoup(resp.text, "html5lib")
        for a in soup.find_all("a", href=True):
            href      = a["href"].strip()
            name_only = href.split("/")[-1].lower()

            if not name_only.endswith(".pdf"):
                continue
            # Skip exhibits: ex21d.pdf, exhibit99.pdf, ex-99.pdf, etc.
            if re.search(r"\bex\b|exhibit", name_only):
                continue

            full_url = _resolve_href(href, filing_dir)
            log(f"Found PDF: {name_only}")
            return full_url

        log("No main PDF found in filing index — will use HTML fallback.")
    except Exception as exc:
        log(f"Index parse error ({exc}) — will use HTML fallback.")

    return None


def _extract_pdf_text(file_path: str) -> str:
    with pdfplumber.open(file_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


async def _fetch_raw(cik: str, accession: str, primary_doc: str) -> str:
    url = filing_url(cik, accession, primary_doc)
    async with httpx.AsyncClient(headers=HEADERS, timeout=120, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return resp.text


def _strip_html(raw: str, primary_doc: str) -> str:
    if not primary_doc.lower().endswith((".htm", ".html")):
        return raw
    soup = BeautifulSoup(raw, "html5lib")
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)


async def filing_text(cik: str, accession: str, primary_doc: str) -> str:
    raw = await _fetch_raw(cik, accession, primary_doc)
    return _strip_html(raw, primary_doc)


# ---------------------------------------------------------------------------
# Public download helpers
# ---------------------------------------------------------------------------

async def find_10k_pdf_url(ticker: str, year: int) -> str | None:
    """Return the direct EDGAR PDF URL for a 10-K, or None if not available."""
    try:
        cik     = await get_cik(ticker)
        filings = await get_10k_filings(cik)
        matches = [f for f in filings if f["fiscal_year"] == year]
        if not matches:
            return None
        return await _find_pdf_in_index(cik, matches[0]["accession"])
    except Exception:
        return None


async def fetch_bytes(url: str) -> bytes:
    """Download raw bytes from an EDGAR URL."""
    async with httpx.AsyncClient(
        headers=HEADERS, timeout=180, follow_redirects=True
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return resp.content


async def download_10k(ticker: str, year: int) -> tuple[str, dict]:
    """Download 10-K text only (no file saved). Used by the MCP server."""
    cik     = await get_cik(ticker)
    filings = await get_10k_filings(cik)
    matches = [f for f in filings if f["fiscal_year"] == year]

    if not matches:
        available = sorted({f["fiscal_year"] for f in filings}, reverse=True)
        raise ValueError(
            f"No 10-K found for {ticker.upper()} in {year}. "
            f"Available years: {available[:10]}"
        )

    f    = matches[0]
    text = await filing_text(cik, f["accession"], f["primary_doc"])
    meta = {
        "ticker":      ticker.upper(),
        "year":        year,
        "filing_date": f["filing_date"],
        "accession":   f["accession"],
        "url":         filing_url(cik, f["accession"], f["primary_doc"]),
    }
    return text, meta


async def download_and_save_10k(
    ticker:   str,
    year:     int,
    save_dir: str = "data",
    emit:     Callable[[str], None] | None = None,
) -> tuple[str, dict]:
    """
    Download the 10-K, save it to *save_dir* (PDF preferred, HTML fallback),
    and return (stripped_text_for_ingestion, metadata).
    metadata includes 'file_path' pointing to the saved file.
    """
    def log(msg: str):
        if emit:
            emit(msg)

    log(f"Looking up CIK for {ticker.upper()}…")
    cik     = await get_cik(ticker)
    log(f"CIK found: {int(cik)} — fetching filing list…")
    filings = await get_10k_filings(cik)
    matches = [f for f in filings if f["fiscal_year"] == year]

    if not matches:
        available = sorted({f["fiscal_year"] for f in filings}, reverse=True)
        raise ValueError(
            f"No 10-K found for {ticker.upper()} in {year}. "
            f"Available years: {available[:10]}"
        )

    f = matches[0]
    log(f"Filing found: {f['accession']} (filed {f['filing_date']})")
    os.makedirs(save_dir, exist_ok=True)

    # ── Try PDF first ──────────────────────────────────────────────────────
    pdf_url = await _find_pdf_in_index(cik, f["accession"], emit=log)

    if pdf_url:
        log("Downloading PDF…")
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=180, follow_redirects=True
        ) as client:
            pdf_resp = await client.get(pdf_url)
            pdf_resp.raise_for_status()

        abs_path = os.path.abspath(
            os.path.join(save_dir, f"{ticker.upper()}_{year}_10K.pdf")
        )
        with open(abs_path, "wb") as fp:
            fp.write(pdf_resp.content)

        size_mb = len(pdf_resp.content) / 1_048_576
        log(f"PDF saved ({size_mb:.1f} MB) — extracting text…")

        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, _extract_pdf_text, abs_path)
        log(f"Extracted {len(text):,} characters from PDF.")

    # ── Fall back to HTML ──────────────────────────────────────────────────
    else:
        log("Downloading HTML filing…")
        raw  = await _fetch_raw(cik, f["accession"], f["primary_doc"])
        ext  = ".html" if f["primary_doc"].lower().endswith((".htm", ".html")) else ".txt"
        abs_path = os.path.abspath(
            os.path.join(save_dir, f"{ticker.upper()}_{year}_10K{ext}")
        )
        with open(abs_path, "w", encoding="utf-8") as fp:
            fp.write(raw)

        text = _strip_html(raw, f["primary_doc"])
        log(f"HTML saved — extracted {len(text):,} characters.")

    meta = {
        "ticker":      ticker.upper(),
        "year":        year,
        "filing_date": f["filing_date"],
        "accession":   f["accession"],
        "url":         filing_url(cik, f["accession"], f["primary_doc"]),
        "file_path":   abs_path,
    }
    return text, meta
