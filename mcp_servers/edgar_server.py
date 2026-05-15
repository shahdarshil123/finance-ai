"""
MCP server exposing SEC EDGAR tools for discovering and downloading 10-K filings.
Core EDGAR logic lives in app/services/edgar_service.py — this file is the MCP wrapper.

Run standalone:
    python -m mcp_servers.edgar_server

Add to Claude Desktop (~/.claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "edgar": {
          "command": "python",
          "args": ["-m", "mcp_servers.edgar_server"],
          "cwd": "C:\\\\Users\\\\darsh\\\\Documents\\\\GitHub\\\\ai-finance-ii"
        }
      }
    }

Tools exposed:
  • list_10k_filings(ticker)          — show available 10-K years for a company
  • get_filing_metadata(ticker, year) — accession number, date, document URL
  • download_10k(ticker, year)        — full plain-text content ready for ingestion
"""

from mcp.server.fastmcp import FastMCP

from app.services.edgar_service import (
    download_10k as _download_10k,
    filing_url,
    get_10k_filings,
    get_cik,
)

mcp = FastMCP("edgar")


@mcp.tool()
async def list_10k_filings(ticker: str) -> str:
    """
    List all available 10-K annual report filings for a company on SEC EDGAR.
    Use this to discover which years are available before downloading.

    Args:
        ticker: Stock ticker symbol, e.g. AAPL, MSFT, TSLA
    """
    cik     = await get_cik(ticker)
    filings = await get_10k_filings(cik)

    if not filings:
        return f"No 10-K filings found for {ticker.upper()} (CIK: {int(cik)})"

    lines = [f"10-K filings for {ticker.upper()} (CIK: {int(cik)}):"]
    for f in filings[:20]:
        lines.append(f"  • filed {f['filing_date']}  →  use year={f['fiscal_year']}")
    return "\n".join(lines)


@mcp.tool()
async def get_filing_metadata(ticker: str, year: int) -> str:
    """
    Return metadata (accession number, filing date, direct URL) for a 10-K
    without downloading the full document. Use this to verify a filing exists
    before calling download_10k.

    Args:
        ticker: Stock ticker symbol
        year:   Calendar year the filing was submitted, e.g. 2024
    """
    cik     = await get_cik(ticker)
    filings = await get_10k_filings(cik)
    matches = [f for f in filings if f["fiscal_year"] == year]

    if not matches:
        available = sorted({f["fiscal_year"] for f in filings}, reverse=True)
        return (
            f"No 10-K found for {ticker.upper()} in {year}. "
            f"Available years: {available[:10]}"
        )

    f   = matches[0]
    url = filing_url(cik, f["accession"], f["primary_doc"])
    return (
        f"Ticker:    {ticker.upper()}\n"
        f"Filed:     {f['filing_date']}\n"
        f"Accession: {f['accession']}\n"
        f"URL:       {url}"
    )


@mcp.tool()
async def download_10k(ticker: str, year: int) -> str:
    """
    Download the full plain-text content of a 10-K annual report from SEC EDGAR.
    Returns extracted text ready to be passed to the ingestion pipeline.
    Note: 10-K filings are large (often 200-400 pages).

    Args:
        ticker: Stock ticker symbol, e.g. AAPL
        year:   Calendar year the filing was submitted, e.g. 2024
    """
    try:
        text, meta = await _download_10k(ticker, year)
    except ValueError as exc:
        return str(exc)

    header = (
        f"=== {ticker.upper()} 10-K ===\n"
        f"Filed:     {meta['filing_date']}\n"
        f"Accession: {meta['accession']}\n"
        f"Source:    SEC EDGAR\n"
        f"{'=' * 40}\n\n"
    )
    return header + text


if __name__ == "__main__":
    mcp.run()
