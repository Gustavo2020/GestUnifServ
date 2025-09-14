import csv
import json
import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import httpx

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RUTA_CSV = DATA_DIR / "ruta.csv"
BASE_URL = "http://127.0.0.1:8000"


def detect_delim(header: str) -> str:
    return ";" if header.count(";") > header.count(",") else ","


def normalize_enum(value: str, allowed: List[str]) -> str:
    v = (value or "").strip()
    # try exact match first
    if v in allowed:
        return v
    # case-insensitive
    for a in allowed:
        if v.lower() == a.lower():
            return a
    raise ValueError(f"Invalid enum value '{value}'. Allowed: {allowed}")


async def evaluate_group(client: httpx.AsyncClient, date: str, rows: List[Dict[str, str]]):
    # Build user
    first = rows[0]
    user = {
        "user_id": first.get("user_id", ""),
        "user_national_id": first.get("user_national_id") or None,
        "user_first_name": first.get("user_first_name") or None,
        "user_last_name": first.get("user_last_name") or None,
        "user_phone": first.get("user_phone") or None,
        "filial": first.get("filial") or None,
    }

    # Allowed enumerations (must match risk_api.py)
    activity_allowed = [
        "Visita de Mantenimiento",
        "Visita de Inspección",
        "Gestión Social",
        "Emergencia",
    ]
    vehicle_allowed = [
        "Camioneta con platón",
        "SUV",
        "Automóvil",
        "Bus",
        "Minivan",
    ]

    # Build segments
    segments = []
    for r in rows:
        comp_json = r.get("companions_json") or "[]"
        try:
            companions = json.loads(comp_json)
            if not isinstance(companions, list):
                companions = []
        except Exception:
            companions = []

        dest_id = r.get("dest_id") or None
        seg = {
            "segment_index": int(r.get("segment_index", "1")),
            "origin_departamento": r.get("origin_departamento", "").strip(),
            "origin_municipio": r.get("origin_municipio", "").strip(),
            "dest_tipo": normalize_enum(r.get("dest_tipo", "municipio"), ["municipio", "activo"]),
            "dest_id": dest_id,
            "dest_departamento": r.get("dest_departamento", "").strip(),
            "dest_municipio": r.get("dest_municipio", "").strip(),
            "companions_count": int(r.get("companions_count", "0") or 0),
            "companions_json": companions,
            "activity_type": normalize_enum(r.get("activity_type", "Visita de Mantenimiento"), activity_allowed),
            "vehicle_type": normalize_enum(r.get("vehicle_type", "SUV"), vehicle_allowed),
            "vehicle_plate": (r.get("vehicle_plate", "").replace(" ", "").upper())[:7],
            "driver_national_id": r.get("driver_national_id", "").strip(),
            "driver_first_name": r.get("driver_first_name") or None,
            "driver_last_name": r.get("driver_last_name") or None,
            "driver_phone": r.get("driver_phone") or None,
            "notes": r.get("notes") or None,
        }
        segments.append(seg)

    payload = {"date": date, "user": user, "segments": segments}
    resp = await client.post(f"{BASE_URL}/evaluate_day", json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"evaluate_day failed {resp.status_code}: {resp.text}")
    return resp.json()


async def main():
    if not RUTA_CSV.exists():
        raise SystemExit(f"ruta.csv not found at {RUTA_CSV}")

    with RUTA_CSV.open("r", encoding="utf-8", errors="replace") as f:
        head = f.readline()
        delim = detect_delim(head)

    groups: Dict[Tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    with RUTA_CSV.open("r", encoding="utf-8", errors="replace", newline="") as f:
        r = csv.DictReader(f, delimiter=delim)
        for row in r:
            date = row.get("date", "").strip()
            user_id = row.get("user_id", "").strip()
            if not date or not user_id:
                print("[warn] skipping row without date/user_id")
                continue
            groups[(date, user_id)].append(row)

    async with httpx.AsyncClient(timeout=20) as client:
        success = 0
        results = []
        for (date, user_id), rows in sorted(groups.items()):
            try:
                data = await evaluate_group(client, date, rows)
                results.append((date, user_id, data.get("ruta_id"), data.get("overall_level")))
                success += 1
            except Exception as e:
                print(f"[error] {date} {user_id}: {e}")

    print("Evaluaciones generadas:")
    for date, user_id, rid, level in results:
        print(f" - {date} | {user_id} | {rid} | {level}")
    print(f"total grupos: {len(groups)} | ok: {success} | fail: {len(groups)-success}")


if __name__ == "__main__":
    asyncio.run(main())

