# ─────────────────────────────────────────────────────────────
# tests/test_integration.py — Test de integración de todo el flujo
#
# Valida que:
# - risk_api.py recibe requests y responde correctamente.
# - db_handler.py guarda los datos en PostgreSQL y genera JSON.
# - log_config.py produce logs estructurados.
# ─────────────────────────────────────────────────────────────

import os
import json
import httpx
import pytest
import asyncio
import logging
from sqlalchemy import select
import sys

# Asegurar que la raíz del repo esté en sys.path para poder importar src/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db_handler import AsyncSessionLocal, Evaluation, CityResult

BASE_URL = "http://127.0.0.1:8000"

@pytest.mark.asyncio
async def test_full_integration(tmp_path):
    """
    Flujo completo:
    1. POST /evaluate con ciudades válidas.
    2. Validar respuesta.
    3. Validar que DB contiene la evaluación y las ciudades.
    4. Validar que existe un respaldo JSON.
    5. Validar logs.
    """

    # ─────────────────────────────────────────────
    # Paso 1: enviar request a la API
    # ─────────────────────────────────────────────
    payload = {
        "user_id": "test_user",
        "platform": "Teams",
        "cities": [
            {"name": "Bogotá", "risk_score": 0.1},
            {"name": "Medellín", "risk_score": 0.2},
        ],
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/evaluate", json=payload)

    assert response.status_code == 200
    data = response.json()
    ruta_id = data["ruta_id"]

    # ─────────────────────────────────────────────
    # Paso 2: validar respuesta API
    # ─────────────────────────────────────────────
    assert data["executed_by"]["user_id"] == "test_user"
    assert data["overall_level"] in ("Low", "Medium", "High")
    assert len(data["cities"]) == 2

    # ─────────────────────────────────────────────
    # Paso 3: validar en DB
    # ─────────────────────────────────────────────
    async with AsyncSessionLocal() as session:
        eval_db = await session.get(Evaluation, ruta_id)
        assert eval_db is not None
        assert eval_db.user_id == "test_user"

        # Revisar ciudades asociadas
        results = (
            await session.execute(
                select(CityResult.name, CityResult.risk_level).where(
                    CityResult.evaluation_id == ruta_id
                )
            )
        ).all()
        assert len(results) == 2

    # ─────────────────────────────────────────────
    # Paso 4: validar respaldo JSON
    # ─────────────────────────────────────────────
    json_path = os.path.join("data", f"output_{ruta_id}.json")
    assert os.path.exists(json_path)

    with open(json_path, encoding="utf-8") as f:
        json_data = json.load(f)
    assert json_data["ruta_id"] == ruta_id

    # ─────────────────────────────────────────────
    # Paso 5: validar logs (formato JSON)
    # ─────────────────────────────────────────────
    logger = logging.getLogger("risk_api")
    logger.info("Test log de integración")
    # Solo validamos que el logger esté configurado con un handler activo
    assert logger.hasHandlers()
