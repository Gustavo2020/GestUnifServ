import asyncio
import json
from pathlib import Path
import httpx

BASE_URL = "http://127.0.0.1:8000"


async def main():
    template = {
        "user_id": "user_123",
        "name": "Ruta Semanal Demo",
        "description": "Plantilla de ejemplo (Bogotá → Cartagena / Bogotá → Soacha)",
        "days": [
            {
                "day_of_week": "Mon",
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
                        "notes": "demo lunes"
                    }
                ],
            },
            {
                "day_of_week": "Tue",
                "segments": [
                    {
                        "segment_index": 1,
                        "origin_departamento": "Cundinamarca",
                        "origin_municipio": "Bogotá",
                        "dest_tipo": "municipio",
                        "dest_id": None,
                        "dest_departamento": "Cundinamarca",
                        "dest_municipio": "Soacha",
                        "companions_count": 0,
                        "companions_json": [],
                        "activity_type": "Visita de Mantenimiento",
                        "vehicle_type": "Automóvil",
                        "vehicle_plate": "DEF45",
                        "driver_national_id": "80223344",
                        "driver_first_name": "Carlos",
                        "driver_last_name": "Ramírez",
                        "driver_phone": "+573118765432",
                        "notes": "demo martes"
                    }
                ],
            },
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        # Create template
        r = await client.post(f"{BASE_URL}/templates", json=template)
        print("create status:", r.status_code)
        if r.status_code != 200:
            print(r.text)
            return
        meta = r.json()
        tpl_id = meta.get("template_id")
        print("template_id:", tpl_id)

        # Apply template for a given week and evaluate immediately
        body = {
            "week_start": "2025-09-22",  # lunes de referencia para demo
            "user": {
                "user_id": "user_123",
                "user_national_id": "1078901234",
                "user_first_name": "María",
                "user_last_name": "Gómez",
                "user_phone": "+573001234567",
                "filial": "ENLAZA",
            },
            "evaluate": False,
        }
        r2 = await client.post(f"{BASE_URL}/templates/{tpl_id}/apply", json=body)
        print("apply status:", r2.status_code)
        print(r2.json())


if __name__ == "__main__":
    asyncio.run(main())
