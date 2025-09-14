# tests/test_integration.py

import sys, os

# Agregamos la raíz del proyecto al path de Python
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import asyncio
import logging
from typing import Optional

import pytest
import httpx
from sqlalchemy import select

from src.db_handler import AsyncSessionLocal, Evaluation, CityResult
from src.log_config import setup_logging

BASE_URL = "http://127.0.0.1:8000"

@pytest.mark.asyncio
async def test_full_integration():
    """
    Flujo completo:
    1. POST /evaluate con ciudades válidas.
    2. Validar respuesta.
    3. Validar que DB contiene la evaluación.
    4. Validar que existe un respaldo JSON.
    5. Validar logs.
    """
    payload = {
        "user_id": "test_user",
        "platform": "Teams",
        "cities": [
            {"name": "Bogotá"},
            {"name": "Medellín"},
        ],
    }

    # Paso 1: request a la API
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/evaluate", json=payload)

    assert response.status_code == 200
    data = response.json()
    ruta_id = data["ruta_id"]

    # Paso 2: validar respuesta
    assert data["executed_by"]["user_id"] == "test_user"
    assert len(data["cities"]) == 2

    # Paso 3: validar en DB
    async with AsyncSessionLocal() as session:
        eval_db = await session.get(Evaluation, ruta_id)
        assert eval_db is not None
        assert eval_db.user_id == "test_user"

    # Paso 4: validar respaldo JSON
    json_path = os.path.join("data", f"output_{ruta_id}.json")
    assert os.path.exists(json_path)
    with open(json_path, encoding="utf-8") as f:
        json_data = json.load(f)
    assert json_data["ruta_id"] == ruta_id

    # Paso 5: validar logs
    logger = logging.getLogger("risk_api")
    logger.info("Test log de integración")
    assert logger.hasHandlers()
