import os
import json
import asyncio
from datetime import datetime, timedelta

# Configure DB to SQLite before importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./riskdb.sqlite3")

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import risk_api  # noqa: E402
from src.db_handler import init_db  # noqa: E402


async def main():
    user_id = os.getenv("FLOW_USER", "flow_user")
    week_start_env = os.getenv("FLOW_WEEK_START")
    if week_start_env:
        base = datetime.fromisoformat(week_start_env)
    else:
        base = datetime.now()
    # normalize to Monday (0)
    week_start = (base - timedelta(days=base.weekday())).date().isoformat()

    # Ensure DB schema
    await init_db()

    # Pick 3 valid cities from the risk map
    city_names = list(risk_api.CITY_RISK_MAP.keys())[:3]
    if len(city_names) < 3:
        raise RuntimeError("Not enough cities in CITY_RISK_MAP to build demo")

    # Build 5 days template (Mon..Fri) with simple one-segment per day
    segments_by_day = []
    for i in range(5):
        c = city_names[i % len(city_names)]
        seg = risk_api.ItinerarySegment(
            segment_index=1,
            origin_departamento="",
            origin_municipio=c,
            dest_tipo="municipio",
            dest_id=None,
            dest_departamento="",
            dest_municipio=c,
            companions_count=0,
            companions_json=[],
            activity_type="Visita de Mantenimiento",
            vehicle_type="SUV",
            vehicle_plate="ABC123",
            driver_national_id="1234567890",
            driver_first_name="Juan",
            driver_last_name="Pérez",
            driver_phone="3000000000",
            notes="",
        )
        segments_by_day.append(seg)

    # Create template object
    tpl = risk_api.TemplateCreate(
        user_id=user_id,
        name="Demo Semana",
        description="Plantilla demo",
        days=[
            risk_api.TemplateDay(day_of_week=dw, segments=[segments_by_day[idx]])
            for idx, dw in enumerate(["Lun", "Mar", "Mie", "Jue", "Vie"])  # Mon..Fri
        ],
    )

    meta = await risk_api.create_template(tpl)

    # Apply template to write ruta.csv only (no evaluation from here)
    req = risk_api.ApplyTemplateRequest(week_start=week_start, user=risk_api.UserInfo(user_id=user_id), evaluate=False)
    await risk_api.apply_template(meta.template_id, req)

    # Evaluate each day (build payloads explicitly to avoid forward-ref issues)
    dates = [(datetime.fromisoformat(week_start) + timedelta(days=i)).date().isoformat() for i in range(5)]
    for i, date in enumerate(dates):
        c = city_names[i % len(city_names)]
        payload = {
            "date": date,
            "user": {"user_id": user_id},
            "segments": [
                {
                    "segment_index": 1,
                    "origin_departamento": "",
                    "origin_municipio": c,
                    "dest_tipo": "municipio",
                    "dest_id": None,
                    "dest_departamento": "",
                    "dest_municipio": c,
                    "companions_count": 0,
                    "companions_json": [],
                    "activity_type": "Visita de Mantenimiento",
                    "vehicle_type": "SUV",
                    "vehicle_plate": "ABC123",
                    "driver_national_id": "1234567890",
                    "driver_first_name": "Juan",
                    "driver_last_name": "Pérez",
                    "driver_phone": "3000000000",
                    "notes": "",
                }
            ],
        }
        req_day = risk_api.EvaluateDayRequest(**payload)
        await risk_api.evaluate_day(req_day)

    # Build summary (JSON source) and write file
    summary = await risk_api.summary_week(user_id=user_id, week_start=week_start, source="json", req=None)
    os.makedirs("data", exist_ok=True)
    out_json = os.path.join("data", f"summary_json_{week_start}_{user_id}.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(), f, ensure_ascii=False, indent=2)

    # Build summary (DB source) and write file
    summary_db = await risk_api.summary_week(user_id=user_id, week_start=week_start, source="db", req=None)
    out_db_json = os.path.join("data", f"summary_db_{week_start}_{user_id}.json")
    with open(out_db_json, "w", encoding="utf-8") as f:
        json.dump(summary_db.model_dump(), f, ensure_ascii=False, indent=2)

    print("Ruta CSV:", os.path.abspath("data/ruta.csv"))
    print("Resumen JSON:", os.path.abspath(out_json))
    print("Resumen DB:", os.path.abspath(out_db_json))


if __name__ == "__main__":
    asyncio.run(main())
