import os
import json
import asyncio
from datetime import datetime, timedelta

# Ensure src import
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.risk_api import summary_week  # type: ignore


def write_demo_outputs(user_id: str, week_start: str):
    base = datetime.fromisoformat(week_start)
    days = [base + timedelta(days=i) for i in range(5)]  # Mon..Fri
    os.makedirs("data", exist_ok=True)
    cities_pool = [
        {
            "name": "Bogotá",
            "risk_score": 0.3,
            "risk_level": "Low",
            "Jurisdiccion_fuerza_militar": "Brigada 13",
            "Jurisdiccion_policia": "MEBOG",
        },
        {
            "name": "Medellín",
            "risk_score": 0.5,
            "risk_level": "Medium",
            "Jurisdiccion_fuerza_militar": "IV Brigada",
            "Jurisdiccion_policia": "MEVAL",
        },
        {
            "name": "Cali",
            "risk_score": 0.6,
            "risk_level": "Medium",
            "Jurisdiccion_fuerza_militar": "III Brigada",
            "Jurisdiccion_policia": "MECAL",
        },
    ]

    for i, day in enumerate(days, start=1):
        ruta_id = f"RUTA-DEMO-{day.date().isoformat()}"
        cities = [cities_pool[i % len(cities_pool)]]
        avg = sum(c["risk_score"] for c in cities) / len(cities)
        obj = {
            "timestamp": datetime.now().isoformat(),
            "date": day.date().isoformat(),
            "ruta_id": ruta_id,
            "executed_by": {"user_id": user_id, "platform": "MS Teams"},
            "evaluated_by": "demo",
            "user": {"user_id": user_id},
            "segments": [{"segment_index": 1, "origin_municipio": cities[0]["name"], "dest_municipio": cities[0]["name"]}],
            "cities": cities,
            "summary": {"total_risk": round(avg, 2), "average_risk": round(avg, 2)},
            "overall_level": cities[0]["risk_level"],
            "status": "PendingValidation",
        }
        with open(os.path.join("data", f"output_{ruta_id}.json"), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)


async def main():
    user_id = os.getenv("DEMO_USER", "demo_user")
    week_start = os.getenv("DEMO_WEEK_START", datetime.now().date().isoformat())
    # Normalize to Monday
    dt = datetime.fromisoformat(week_start)
    week_start = (dt - timedelta(days=dt.weekday())).date().isoformat()

    write_demo_outputs(user_id, week_start)
    resp = await summary_week(user_id=user_id, week_start=week_start, source="json")
    os.makedirs("data", exist_ok=True)
    out_path = os.path.join("data", f"summary_json_{week_start}_{user_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resp.model_dump(), f, ensure_ascii=False, indent=2)
    print(json.dumps(resp.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
