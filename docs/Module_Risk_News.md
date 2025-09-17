# Risk News Module Plan

## Overall Goal
Automate a weekly process that, every Thursday at midnight, reads the weekly displacement summary, searches the web for recent news (no older than 48 hours), detects risk-related keywords per municipality, and produces a combined report with evaluations and relevant news.

## Main Components
- **Weekly Scheduled Task**: A lightweight scheduler (e.g., APScheduler embedded in FastAPI or an external cron/Task Scheduler job) that runs every Thursday at 00:00 and triggers the full workflow.
- **Weekly Summary Reader**: Reuses `/summary/week` logic to obtain municipalities and their risk data; it can call the endpoint internally or consume JSON/DB backups directly.
- **News Fetcher**: Python module using `httpx` (or `requests`) to visit a predefined list of URLs (news outlets, RSS feeds, APIs). If responses are HTML, parsing is handled with `BeautifulSoup`.
- **Keyword Catalog**: Configurable file (for example `data/risk_keywords.csv` or JSON) containing phrases that signal potential risk. It is loaded when the job starts.
- **Analysis Engine**: Cross-references municipalities from the summary with the fetched articles, filters by time (≤48 hours), detects municipality + keyword matches, and extracts a context paragraph.
- **Report Builder**: Generates a JSON/CSV pairing each municipality with both the risk evaluation (total, average, level) and the list of relevant news (title, link, context paragraph, publication date, triggering keyword). Pydantic models ensure consistent output.

## Flow Sequence
1. **Scheduled trigger** fires (via scheduler) and launches the news coordinator.
2. **Coordinator** retrieves the current week summary and extracts municipalities plus their risk data.
3. **Lightweight crawler** hits every configured source and downloads HTML/JSON with `httpx`.
4. **Content parser** uses `BeautifulSoup` (or source-specific parsing) to obtain title, body, and publication date.
5. **Temporal filter** discards any article older than 48 hours relative to the query time.
6. **Municipality + keyword matching** looks for the municipality name and then checks for any risk keyword; when present, it captures the surrounding paragraph for context.
7. **Aggregation** builds a structure per municipality combining risk data and relevant news hits.
8. **Export** writes the result to `data/risk_news_<week>.json` (and optionally CSV).
9. **Optional notification** could send the report via email or to the Teams bot.

## Technologies and Usage
- **Python + FastAPI**: Host the module, expose an optional endpoint to run the search manually, and share existing configuration.
- **APScheduler**: Schedule the weekly job inside the service (cron-like). Alternative: standalone script plus cron/Task Scheduler.
- **httpx / requests**: HTTP clients to consume news sources; `httpx` supports async and integrates well with the service.
- **BeautifulSoup (bs4)**: Parse HTML content when clean JSON is not available.
- **pydantic**: Define input/output models for the module, ensuring proper validation.
- **pandas (optional)**: Handy if a tabular CSV export is needed for external consumers.
- **Structured logging**: Reuse existing logging setup to audit processed municipalities, visited sources, and matches.
- **pytest + respx (or responses)**: Mock HTTP sources during testing to validate filtering logic.

## Recommended Sources
- **GDELT Events API** (free/open): query daily CSV/JSON filtered by Colombia (`ActionGeo_CountryCode=CO`) and risk keywords; geocoded entries map easily to municipalities.
- **GNews API** (free tier, affordable paid tiers): JSON wrapper around Google News; run one query per municipality with risk terms, storing snippets along with canonical URLs.
- **NewsData.io** (free tier, low-cost paid tiers): supports language/country filtering and clear licensing; helpful for regional outlets or specific threat keywords.
- *(Optional add-on)* **Event Registry** basic plan: offers topic-focused searches and higher request limits if broader coverage becomes necessary.

## Optional Data Sources
- **INVÍAS SIV ArcGIS REST (MapServer)**: https://hermes.invias.gov.co/arcgis/rest/services/Sistema_informacion_vial/SIV_V20/MapServer
- **INVÍAS SIV ArcGIS REST (Server root)**: https://hermes2.invias.gov.co/server/rest/services/Sistema_informacion_vial

## Final Deliverables
- Scheduler configured for the weekly trigger.
- Module (e.g., `news_collector.py`) with functions `fetch_sources`, `filter_articles`, `extract_context`, `build_report`.
- Configuration files: `config/news_sources.json` and `data/risk_keywords.csv`.
- Automatic reports in `data/risk_news_<week>.json` (and optional CSV).
- Brief documentation (`docs/news_module.md` or similar) explaining how to set up sources, keywords, run the job manually, and verify optional data APIs.

