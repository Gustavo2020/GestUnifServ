import asyncio
import json
from pathlib import Path
import httpx

BASE_URL = "http://127.0.0.1:8000"

payload = {
    "date": "2025-09-22",
    "user": {
        "user_id": "user_123",
        "user_national_id": "1078901234",
        "user_first_name": "María",
        "user_last_name": "Gómez",
        "user_phone": "+573001234567",
        "filial": "ENLAZA",
    },
    "segments": [
        {
            "segment_index": 1,
            "origin_departamento": "Cundinamarca",
            "origin_municipio": "Bogotá",
            "dest_tipo": "municipio",
            "dest_id": None,
            "dest_departamento": "Bolívar",
            "dest_municipio": "Cartagena de Indias",
            "companions_count": 1,
            "companions_json": [
                {"id_number": "10203040", "first_name": "Ana", "last_name": "Pérez"}
            ],
            "activity_type": "Visita de Inspección",
            "vehicle_type": "SUV",
            "vehicle_plate": "ABC123",
            "driver_national_id": "80223344",
            "driver_first_name": "Carlos",
            "driver_last_name": "Ramírez",
            "driver_phone": "+573118765432",
            "notes": "reunión"
        }
    ],
}


async def main():
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{BASE_URL}/evaluate_day", json=payload)
        print("status:", r.status_code)
        if r.status_code != 200:
            print(r.text)
            return
        data = r.json()
        print("ruta_id:", data.get("ruta_id"))
        print("overall_level:", data.get("overall_level"))
        print("cities:", [c.get("name") for c in data.get("cities", [])])


if __name__ == "__main__":
    asyncio.run(main())

