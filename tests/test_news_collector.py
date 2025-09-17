import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src import news_collector


@pytest.mark.asyncio
async def test_collect_risk_news_filters_by_time_and_keywords(tmp_path: Path):
    summary = {
        "week_start": "2025-09-15",
        "week_end": "2025-09-21",
        "records": [
            {
                "date": "2025-09-15",
                "ruta_id": "R1",
                "summary": {"average_risk": 0.5},
                "overall_level": "Medium",
                "cities": [
                    {"name": "Bogota", "risk_score": 0.5, "risk_level": "Medium"},
                    {"name": "Medellin", "risk_score": 0.2, "risk_level": "Low"},
                ],
            }
        ],
    }

    sources_path = tmp_path / "sources.json"
    keywords_path = tmp_path / "keywords.csv"

    sources_path.write_text(
        json.dumps(
            [
                {
                    "name": "MockFeed",
                    "url": "https://news.local/feed",
                    "type": "json",
                    "list_path": ["articles"],
                    "fields": {
                        "title": ["title"],
                        "url": ["url"],
                        "published_at": ["published_at"],
                        "content": ["body"],
                    },
                    "date_format": "%Y-%m-%dT%H:%M:%S",
                }
            ]
        ),
        encoding="utf-8",
    )

    keywords_path.write_text("keyword\nprotest\nroadblock\n", encoding="utf-8")

    now = datetime(2025, 9, 17, 0, 0, tzinfo=timezone.utc)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://news.local/feed")
        payload = {
            "articles": [
                {
                    "title": "Protest in Bogota causes delays",
                    "url": "https://example.com/bogota",
                    "published_at": "2025-09-16T23:00:00",
                    "body": "Authorities reported a protest in Bogota with possible roadblock.",
                },
                {
                    "title": "Festival in Medellin",
                    "url": "https://example.com/medellin",
                    "published_at": "2025-09-10T12:00:00",
                    "body": "Cultural events without incidents.",
                },
                {
                    "title": "Traffic update",
                    "url": "https://example.com/traffic",
                    "published_at": "2025-09-16T10:00:00",
                    "body": "General traffic advice without keywords",
                },
            ]
        }
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        report = await news_collector.collect_risk_news(
            summary,
            sources_path,
            keywords_path,
            client=client,
            now=now,
        )

    bogota_news = next(item for item in report["items"] if item["municipality"] == "Bogota")
    medellin_news = next(item for item in report["items"] if item["municipality"] == "Medellin")

    assert bogota_news["news"], "Bogota should have matched protest article"
    assert bogota_news["news"][0]["matched_keyword"] == "protest"
    assert "roadblock" in bogota_news["news"][0]["context"].lower()
    assert medellin_news["news"] == []


def test_load_keywords_requires_column(tmp_path: Path):
    csv_path = tmp_path / "keywords.csv"
    csv_path.write_text("term\nfoo\n", encoding="utf-8")
    with pytest.raises(ValueError):
        news_collector.load_keywords(csv_path)


def test_collect_risk_news_sync_writes_output(tmp_path: Path):
    summary = {"records": [], "week_start": "2025-09-15"}
    sources = tmp_path / "sources.json"
    keywords = tmp_path / "keywords.csv"
    output = tmp_path / "report.json"

    sources.write_text(json.dumps([]), encoding="utf-8")
    keywords.write_text("keyword\n", encoding="utf-8")

    report = news_collector.collect_risk_news_sync(
        summary,
        sources,
        keywords,
        output_path=output,
        now=datetime(2025, 9, 17, tzinfo=timezone.utc),
    )

    assert output.exists()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved == report
    assert report["items"] == []

@pytest.mark.asyncio
async def test_collect_risk_news_supports_rss(tmp_path: Path):
    summary = {
        "week_start": "2025-09-15",
        "week_end": "2025-09-21",
        "records": [
            {
                "date": "2025-09-15",
                "ruta_id": "R1",
                "summary": {"average_risk": 0.4},
                "overall_level": "Medium",
                "cities": [
                    {"name": "Medellin", "risk_score": 0.4, "risk_level": "Medium"}
                ],
            }
        ],
    }

    sources_path = tmp_path / "sources.json"
    keywords_path = tmp_path / "keywords.csv"

    sources_path.write_text(
        json.dumps(
            [
                {
                    "name": "MockRSS",
                    "url": "https://news.local/rss",
                    "type": "rss",
                }
            ]
        ),
        encoding="utf-8",
    )
    keywords_path.write_text("keyword\nseguridad\n", encoding="utf-8")

    rss_payload = """<?xml version='1.0' encoding='UTF-8'?>
<rss version='2.0'>
  <channel>
    <title>Mock Feed</title>
    <item>
      <title>Seguridad en Medellin mejora segun autoridades</title>
      <link>https://example.com/medellin-security</link>
      <description>Reportes indican mejoria de seguridad en Medellin.</description>
      <pubDate>Tue, 16 Sep 2025 18:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Noticias generales</title>
      <link>https://example.com/general</link>
      <description>Sin relacion.</description>
      <pubDate>Tue, 09 Sep 2025 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://news.local/rss")
        return httpx.Response(200, text=rss_payload, headers={"Content-Type": "application/rss+xml"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        report = await news_collector.collect_risk_news(
            summary,
            sources_path,
            keywords_path,
            client=client,
            now=datetime(2025, 9, 17, tzinfo=timezone.utc),
        )

    medellin_news = next(item for item in report["items"] if item["municipality"] == "Medellin")
    assert medellin_news["news"], "Medellin should have matched RSS article"
    assert medellin_news["news"][0]["matched_keyword"] == "seguridad"
