# CLAUDE.md

## Project Overview

Korea Investment & Securities (KIS) Open Trading API sample code repository. Provides Python examples for integrating with KIS trading APIs, structured for both LLM agents and human developers. Covers 166 APIs across domestic/overseas stocks, bonds, derivatives, ETF/ETN, and ELW.

## Setup

```bash
# Install dependencies (requires Python 3.9+, recommends 3.13+)
uv sync

# Configure credentials
# Edit kis_devlp.yaml with your API keys and account info (never commit secrets)
```

## Running Examples

```bash
# LLM examples - single API verification
uv run python examples_llm/domestic_stock/inquire_price/chk_inquire_price.py

# User examples - integrated usage
uv run python examples_user/domestic_stock/domestic_stock_examples.py

# MCP server (Docker)
cd "MCP/Kis Trading MCP"
docker build -t kis-trade-mcp .
docker run -d --name kis-trade-mcp -p 3000:3000 kis-trade-mcp
```

## Project Structure

- `examples_llm/` — LLM-optimized: one function per folder, each with `chk_*.py` test file
- `examples_user/` — Human-friendly: category-integrated `*_functions.py` + `*_examples.py` files
- `stocks_info/` — Reference data (stock codes, mappings)
- `MCP/Kis Trading MCP/` — FastMCP server for Claude Desktop integration
- `legacy/` — Previous version samples
- `docs/convention.md` — Full coding conventions

## Code Conventions

- **Language:** Python
- **Package manager:** `uv` (not pip/poetry)
- **Naming:** `snake_case` for modules, variables, functions; `PascalCase` for classes; `UPPER_SNAKE_CASE` for constants
- **Imports:** Standard library → third-party → local (no wildcard imports)
- **Type hints:** Required on all function signatures
- **Docstrings:** Google/Sphinx/NumPy style with Args, Returns, Examples, Exceptions
- **Error handling:** Specific exception types (not bare `except`), use `logging` module
- **Data return type:** `pandas.DataFrame` for API results
- **Security:** No hardcoded credentials; use `kis_devlp.yaml` for config

## Key Files

- `kis_devlp.yaml` — API credentials and endpoint configuration (do not commit secrets)
- `examples_llm/kis_auth.py` / `examples_user/kis_auth.py` — Authentication and token management
- `docs/convention.md` — Detailed coding standards reference
- `pyproject.toml` — Dependency declarations

## Testing

No automated test framework (pytest, etc.). Verification is done via `chk_*.py` files in `examples_llm/` that make sample API calls and display results. Each test file includes column mapping dictionaries for Korean translation of output fields.

## Important Notes

- Dual structure: `examples_llm/` (one-API-per-folder for LLM navigation) vs `examples_user/` (integrated per-category for humans)
- WebSocket variants use `_ws` suffix (e.g., `domestic_stock_functions_ws.py`)
- Authentication tokens are cached locally at `~/.KIS/config/KIS[YYYYMMDD]`
- Supports both real trading (`prod` endpoint) and paper/demo trading (`vps` endpoint)
