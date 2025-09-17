"""GestUnifServ news collector.

This module orchestrates the retrieval of external news articles that may
impact travel risk assessments. It reads configuration files describing
news sources, fetches and normalises articles, matches them against the
municipalities present in a weekly summary, and produces structured reports
ready to be consumed by analysts or automated channels."""
from __future__ import annotations

import asyncio
import html
import csv
import json
import logging
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx
from pydantic import BaseModel, Field, ValidationInfo, field_validator

logger = logging.getLogger("news_collector")

_DEFAULT_TZ = timezone.utc
_RISK_LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2}


class NewsSourceConfig(BaseModel):
    """Structured configuration for a news provider.

Each entry tells the collector where to fetch data, which protocol to use
(JSON vs RSS), and how to map the payload into the standard article schema.
A single file can mix many providers without changing the collector code."""

    name: str
    url: str
    type: str = Field("json", description="Currently only 'json' feeds are supported")
    list_path: List[str] = Field(default_factory=list, description="Nested path where the list of articles lives")
    fields: Optional[Dict[str, List[str]]] = Field(
        default=None, description="Mapping of logical fields (title,url,published_at,content) to paths inside each article",
    )
    date_format: Optional[str] = Field(
        default=None, description="Optional datetime strptime pattern when feed is not ISO-8601",
    )
    timezone: Optional[str] = Field(
        default=None, description="IANA timezone name applied when dates are naive",
    )

    @field_validator("fields")
    def _validate_fields(
        cls,
        value: Optional[Dict[str, List[str]]],
        info: ValidationInfo,
    ) -> Optional[Dict[str, List[str]]]:
        source_type = (info.data or {}).get("type", "json")
        if value is None:
            if source_type == "json":
                raise ValueError("JSON sources must define field mappings")
            return None
        required = {"title", "url", "published_at", "content"}
        missing = required - set(value)
        if missing:
            raise ValueError(f"Missing field mappings: {', '.join(sorted(missing))}")
        return value


class NewsArticle(BaseModel):
    """Canonical in-memory representation of a news article.

Regardless of the original format (RSS, JSON, etc.), every article ends up in
this structure so the matching and reporting stages can operate uniformly."""

    source: str
    title: str
    url: str
    published_at: datetime
    content: str


@dataclass
class MunicipalityRisk:
    """Snapshot of risk metrics for a municipality derived from the weekly summary.

It keeps the figures that are most relevant when evaluating associated news
(average/max risk values, severity level and how many times the city appeared
in the reporting window)."""

    average_score: float
    max_score: float
    max_level: str
    occurrences: int


class MunicipalityNews(BaseModel):
    municipality: str
    risk: MunicipalityRisk
    news: List[Dict[str, Any]]


def load_keywords(path: Path) -> List[str]:
    """Load and validate the catalogue of risk keywords used for filtering.

Args:
    path: Path to a CSV file that must expose a `keyword` column.

Returns:
    A list of non-empty keywords preserving the file order so analysts can
    control priority downstream.

Raises:
    ValueError: If the CSV is present but does not contain the `keyword` column.

Notes:
    When the file is missing we log a warning and return an empty list so that
    the caller can decide whether to proceed without matches or abort.
"""

    if not path.exists():
        logger.warning("Keyword file not found at %s", path)
        return []

    keywords: List[str] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "keyword" not in (reader.fieldnames or []):
            raise ValueError("Keyword CSV must contain a 'keyword' column")
        for row in reader:
            kw = (row.get("keyword") or "").strip()
            if kw:
                keywords.append(kw)
    return keywords


def load_sources(path: Path) -> List[NewsSourceConfig]:
    """Read the set of news sources that should be queried for a run.

Args:
    path: File containing a JSON list with the configuration for each source.

Returns:
    A list of `NewsSourceConfig` instances ready to be consumed by the fetcher.

Raises:
    FileNotFoundError: When the configuration file cannot be located.
    ValueError: When the JSON structure is not a list (most likely a typo).

Keeping this configuration external lets us add or tweak providers without
needing a code deployment."""

    if not path.exists():
        raise FileNotFoundError(f"News source configuration not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("News source configuration must be a list")
    return [NewsSourceConfig.model_validate(item) for item in data]


def _extract_value(payload: Any, path: Iterable[str]) -> Any:
    """Follow a sequence of keys inside a nested JSON-like payload."""

    value = payload
    for key in path:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            raise KeyError(f"Could not access key '{key}' in payload")
    return value


def _parse_datetime(value: Any, source: NewsSourceConfig) -> datetime:
    """Normalise feed timestamps into timezone-aware UTC datetimes.

Args:
    value: Raw timestamp value coming from the feed (ISO string, epoch, datetime).
    source: Source configuration providing optional parsing hints (format/tz).

Returns:
    A timezone-aware datetime in UTC, ready for comparisons.

Raises:
    ValueError: If the value cannot be interpreted as a datetime.
"""

    if isinstance(value, (int, float)):

        dt = datetime.fromtimestamp(float(value), tz=_DEFAULT_TZ)
    elif isinstance(value, str):
        if source.date_format:
            dt = datetime.strptime(value, source.date_format)
        else:
            dt = datetime.fromisoformat(value)
    elif isinstance(value, datetime):
        dt = value
    else:
        raise ValueError(f"Unsupported datetime value: {value!r}")

    if dt.tzinfo is None:
        if source.timezone:
            try:
                import zoneinfo

                tz = zoneinfo.ZoneInfo(source.timezone)
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning("Invalid timezone %s for source %s: %s", source.timezone, source.name, exc)
                tz = _DEFAULT_TZ
        else:
            tz = _DEFAULT_TZ
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(_DEFAULT_TZ)


async def _fetch_articles_from_source(client: httpx.AsyncClient, source: NewsSourceConfig) -> List[NewsArticle]:
    """Download every article exposed by a configured source and homogenise it.

Supports both JSON APIs (with explicit field mappings) and RSS feeds.  Each
article is converted into `NewsArticle` so later stages can work with a common
shape.  Errors are handled per-source so one failing feed does not break the
whole collection run.
"""

    try:
        response = await client.get(source.url, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch %s: %s", source.name, exc)
        return []

    if source.type.lower() == "rss":
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            logger.warning("Invalid RSS payload for %s: %s", source.name, exc)
            return []
        items = root.findall('.//item')
        normalized: List[NewsArticle] = []
        for item in items:
            title = (item.findtext('title') or '').strip()
            url = (item.findtext('link') or '').strip()
            description = item.findtext('description') or ''
            pub_raw = (item.findtext('pubDate') or '').strip()
            try:
                published_at = parsedate_to_datetime(pub_raw)
            except Exception:
                logger.debug("Could not parse pubDate for %s: %s", source.name, pub_raw)
                continue
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=_DEFAULT_TZ)
            else:
                published_at = published_at.astimezone(_DEFAULT_TZ)
            normalized.append(
                NewsArticle(
                    source=source.name,
                    title=title,
                    url=url,
                    published_at=published_at,
                    content=html.unescape(description),
                )
            )
        return normalized

    if not source.fields:
        logger.warning("JSON source %s is missing field mappings", source.name)
        return []

    json_payload = response.json()
    articles_payload = json_payload
    for key in source.list_path:
        if isinstance(articles_payload, dict) and key in articles_payload:
            articles_payload = articles_payload[key]
        else:
            logger.warning("Invalid list_path %s for source %s", source.list_path, source.name)
            return []

    if not isinstance(articles_payload, list):
        logger.warning("Expected list of articles for source %s", source.name)
        return []

    normalized: List[NewsArticle] = []
    for item in articles_payload:
        if not isinstance(item, dict):
            continue
        try:
            title = str(_extract_value(item, source.fields["title"]))
            url = str(_extract_value(item, source.fields["url"]))
            published_raw = _extract_value(item, source.fields["published_at"])
            content = str(_extract_value(item, source.fields["content"]))
            published_at = _parse_datetime(published_raw, source)
        except Exception as exc:
            logger.debug("Skipping article from %s due to parsing error: %s", source.name, exc)
            continue
        normalized.append(
            NewsArticle(
                source=source.name,
                title=title,
                url=url,
                published_at=published_at,
                content=content,
            )
        )
    return normalized


def _normalize_text(value: str) -> str:
    """Remove accents and case differences so comparisons are resilient."""

    return (

        unicodedata.normalize("NFKD", value or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )


def _extract_context(text: str, keyword: str, radius: int = 180) -> str:
    """Extract a short excerpt around the first appearance of a keyword."""

    lower_text = text.lower()

    idx = lower_text.find(keyword.lower())
    if idx < 0:
        return text[: min(radius, len(text))].strip()
    start = max(idx - radius, 0)
    end = min(idx + radius, len(text))
    return text[start:end].strip()


def _aggregate_risk(summary: Dict[str, Any]) -> Dict[str, MunicipalityRisk]:
    """Condense weekly summary records into per-municipality risk metrics."""

    by_city: Dict[str, Dict[str, Any]] = defaultdict(

        lambda: {"score_sum": 0.0, "count": 0, "max_score": 0.0, "max_level": "Low"}
    )
    records = summary.get("records", [])
    for record in records:
        for city in record.get("cities", []):
            name = city.get("name")
            if not name:
                continue
            score = float(city.get("risk_score", 0.0))
            level = str(city.get("risk_level", "Low"))
            entry = by_city[name]
            entry["score_sum"] += score
            entry["count"] += 1
            entry["max_score"] = max(entry["max_score"], score)
            if _RISK_LEVEL_ORDER.get(level.lower(), 0) >= _RISK_LEVEL_ORDER.get(entry["max_level"].lower(), 0):
                entry["max_level"] = level
    aggregated: Dict[str, MunicipalityRisk] = {}
    for name, data in by_city.items():
        count = data["count"] or 1
        aggregated[name] = MunicipalityRisk(
            average_score=round(data["score_sum"] / count, 2),
            max_score=round(data["max_score"], 2),
            max_level=data["max_level"],
            occurrences=count,
        )
    return aggregated


def _match_articles(
    articles: Iterable[NewsArticle],
    municipalities: Dict[str, MunicipalityRisk],
    keywords: List[str],
    now: datetime,
    window: timedelta,
) -> Dict[str, List[Dict[str, Any]]]:
    """Cross-reference articles against municipalities and risk keywords.

Args:
    articles: Iterable of normalised articles coming from one or more feeds.
    municipalities: Mapping of municipality names to their risk aggregates.
    keywords: Ordered list of risk keywords to look for inside the article.
    now: Reference timestamp used to enforce the time window.
    window: Maximum age an article can have to be considered relevant.

Returns:
    Dictionary keyed by municipality name, each containing a list of matched
    news entries augmented with metadata (source, matched keyword, context).

City names are checked first so we only inspect keywords for the articles that
mention the municipality, which significantly reduces false positives.
"""

    matches: Dict[str, List[Dict[str, Any]]] = {name: [] for name in municipalities}

    normalized_keywords = [_normalize_text(keyword) for keyword in keywords]
    for article in articles:
        if article.published_at < now - window:
            continue
        normalized_content = _normalize_text(article.content)
        normalized_title = _normalize_text(article.title)
        for municipality, risk in municipalities.items():
            norm_city = _normalize_text(municipality)
            if norm_city not in normalized_content and norm_city not in normalized_title:
                continue
            for keyword, normalized_keyword in zip(keywords, normalized_keywords):
                if not normalized_keyword:
                    continue
                if normalized_keyword == norm_city:
                    continue
                if normalized_keyword in normalized_content or normalized_keyword in normalized_title:
                    matches[municipality].append(
                        {
                            "source": article.source,
                            "title": article.title,
                            "url": article.url,
                            "published_at": article.published_at.isoformat(),
                            "matched_keyword": keyword,
                            "context": _extract_context(article.content, keyword),
                        }
                    )
                    break
    return matches


async def collect_risk_news(
    summary: Dict[str, Any],
    sources_path: Path,
    keywords_path: Path,
    *,
    now: Optional[datetime] = None,
    client: Optional[httpx.AsyncClient] = None,
    time_window: timedelta = timedelta(hours=48),
) -> Dict[str, Any]:
    """High-level orchestration coroutine that enriches a weekly summary with news.

Args:
    summary: Weekly summary payload (as produced by `/summary/week`).
    sources_path: Path to the JSON feed configuration file.
    keywords_path: Path to the CSV defining risk-related keywords.
    now: Optional reference datetime (defaults to current UTC).
    client: Optional shared `httpx.AsyncClient` instance (for dependency injection/testing).
    time_window: Maximum age of news items to include in the report.

Returns:
    Structured dictionary containing the original summary metadata and a list
    of municipalities enriched with matched news entries.

This function glues together the individual building blocks: it loads
configuration files, fetches articles, performs the matching and produces the
final report without persisting it anywhere.
"""

    now = now or datetime.now(tz=_DEFAULT_TZ)
    keywords = load_keywords(keywords_path)
    if not keywords:
        logger.info("No keywords configured; returning empty news report")
        keywords = []

    sources = load_sources(sources_path)
    municipalities = _aggregate_risk(summary)
    if not municipalities:
        logger.info("No municipalities found in summary; nothing to match")
        return {
            "generated_at": now.isoformat(),
            "week_start": summary.get("week_start"),
            "week_end": summary.get("week_end"),
            "items": [],
        }

    close_client = False
    if client is None:
        client = httpx.AsyncClient()
        close_client = True

    try:
        articles: List[NewsArticle] = []
        for source in sources:
            articles.extend(await _fetch_articles_from_source(client, source))
    finally:
        if close_client:
            await client.aclose()

    matched = _match_articles(articles, municipalities, keywords, now, time_window)

    items: List[Dict[str, Any]] = []
    for municipality, risk in municipalities.items():
        items.append(
            {
                "municipality": municipality,
                "risk": {
                    "average_score": risk.average_score,
                    "max_score": risk.max_score,
                    "max_level": risk.max_level,
                    "occurrences": risk.occurrences,
                },
                "news": matched.get(municipality, []),
            }
        )

    return {
        "generated_at": now.isoformat(),
        "week_start": summary.get("week_start"),
        "week_end": summary.get("week_end"),
        "items": items,
    }


async def collect_and_save(
    summary: Dict[str, Any],
    sources_path: Path,
    keywords_path: Path,
    output_path: Path,
    *,
    now: Optional[datetime] = None,
    time_window: timedelta = timedelta(hours=48),
) -> Dict[str, Any]:
    """Run the asynchronous pipeline and store the resulting report on disk.

Args mirror `collect_risk_news`, with the addition of `output_path` indicating
where to write the JSON report. The returned structure is the same that gets
saved to disk, which makes the function convenient for tests and scripts.
"""

    report = await collect_risk_news(
        summary,
        sources_path,
        keywords_path,
        now=now,
        time_window=time_window,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def collect_risk_news_sync(
    summary: Dict[str, Any],
    sources_path: Path,
    keywords_path: Path,
    output_path: Optional[Path] = None,
    *,
    now: Optional[datetime] = None,
    time_window: timedelta = timedelta(hours=48),
) -> Dict[str, Any]:
    """Execute the asynchronous pipeline from synchronous contexts (CLI/scripts).

The helper spins up an event loop, delegates to `collect_risk_news`/`collect_and_save`
depending on whether an output path is provided, and ensures the loop is closed
properly even when exceptions bubble up.
"""

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        if output_path:
            return loop.run_until_complete(
                collect_and_save(
                    summary,
                    sources_path,
                    keywords_path,
                    output_path,
                    now=now,
                    time_window=time_window,
                )
            )
        return loop.run_until_complete(
            collect_risk_news(
                summary,
                sources_path,
                keywords_path,
                now=now,
                time_window=time_window,
            )
        )
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


__all__ = [
    "collect_risk_news",
    "collect_and_save",
    "collect_risk_news_sync",
    "load_sources",
    "load_keywords",
    "NewsSourceConfig",
]
