# ─────────────────────────────────────────────────────────────
# risk_api.py — REST API for Risk Evaluation
#
# Objetivo:
# - Exponer un endpoint POST /evaluate que:
#     1) Valida ciudades contra un mapa oficial de riesgos (CSV).
#     2) Calcula riesgo por ciudad y riesgo general de la ruta.
#     3) Persiste la evaluación en PostgreSQL y genera un respaldo JSON.
# - Preparado para producción:
#     - Manejo de ciclo de vida (lifespan) en FastAPI.
#     - Logging estructurado (a través de src/log_config.setup_logging()).
#     - Middleware que añade un request_id por solicitud para trazabilidad.
#
# Notas sobre el CSV de riesgos:
# - Se carga una sola vez al iniciar la aplicación para eficiencia.
# - El puntaje oficial del CSV SIEMPRE prevalece sobre cualquier valor del cliente.
#
# Nota sobre RISK_CSV_PATH:
# - Ejecución local sin cambios: usará "data/riesgos.csv".
# - En producción, definir la variable de entorno y se usará automáticamente:
#       export RISK_CSV_PATH=/etc/app/config/riesgos.csv
# ─────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime
from contextlib import asynccontextmanager
import uuid
import os
import csv
import logging

from risk_api import EvaluationResponse, EvaluationRequest, load_city_risk_map_compat

# ─────────────────────────────────────────────────────────────
# Módulos internos del proyecto
# - db_handler: persistencia en PostgreSQL + respaldo JSON
# - log_config: configuración global de logging (formato JSON por stdout)
# ─────────────────────────────────────────────────────────────
from src.db_handler import save_evaluation_to_db_and_json, init_db
from src.log_config import setup_logging


# ─────────────────────────────────────────────────────────────
# Configuración global de logging
# - setup_logging() define formato JSON y nivel según LOG_LEVEL (.env)
# - logger para este módulo: "risk_api"
# ─────────────────────────────────────────────────────────────
setup_logging()
logger = logging.getLogger("risk_api")

# ─────────────────────────────────────────────────────────────
# Ruta del CSV configurable por entorno (RISK_CSV_PATH)
# - Local: "data/riesgos.csv"
# - Producción: export RISK_CSV_PATH=/etc/app/config/riesgos.csv
# ─────────────────────────────────────────────────────────────
RISK_CSV_PATH = os.getenv("RISK_CSV_PATH", "data/riesgos.csv")
CITY_RISK_MAP = load_city_risk_map_compat(RISK_CSV_PATH)

# ─────────────────────────────────────────────────────────────
# Clasificación de riesgo
# - Tramos ajustables según política de negocio.
# ─────────────────────────────────────────────────────────────
def classify_risk(score: float) -> str:
    if score >= 0.7:
        return "High"
    elif score >= 0.4:
        return "Medium"
    else:
        return "Low"

# ─────────────────────────────────────────────────────────────
# Manejo del ciclo de vida (lifespan) — reemplaza @app.on_event("startup")
# - init_db(): crea tablas si no existen.
# - Se registran eventos de inicio y fin de la app.
# ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        logger.info("Base de datos inicializada correctamente.")
        yield
    except Exception:
        # Si algo falla en el arranque, se deja traza completa y se propaga.
        logger.error("Error durante la inicialización de la aplicación.", exc_info=True)
        raise
    finally:
        logger.info("Aplicación finalizada; liberación de recursos completada.")

# ─────────────────────────────────────────────────────────────
# Inicialización de la aplicación FastAPI
# ─────────────────────────────────────────────────────────────
app = FastAPI(lifespan=lifespan)

# ─────────────────────────────────────────────────────────────
# Middleware de trazabilidad
# - Añade un X-Request-ID a cada respuesta.
# - Loggea inicio y fin de cada request con ruta y método.
# - request.state.request_id queda disponible para otros componentes.
# ─────────────────────────────────────────────────────────────
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    logger.info(
        "Solicitud entrante | request_id=%s | method=%s | path=%s",
        request_id,
        request.method,
        request.url.path,
    )

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id

    logger.info(
        "Solicitud procesada | request_id=%s | method=%s | path=%s | status=%s",
        request_id,
        request.method,
        request.url.path,
        getattr(response, "status_code", "unknown"),
    )
    return response

# ─────────────────────────────────────────────────────────────
# Endpoint principal /evaluate
# - Validaciones:
#     * Lista de ciudades no vacía.
#     * Cada ciudad debe existir en el mapa oficial.
# - Cálculo:
#     * Suma y promedio del riesgo.
#     * Clasificación por ciudad y global.
# - Persistencia:
#     * Guardado en DB (SQLAlchemy/async) y respaldo JSON (db_handler).
# - Manejo de errores:
#     * 400: errores de entrada (ciudad inválida, lista vacía).
#     * 500: errores internos (persistencia u otros).
# ─────────────────────────────────────────────────────────────
@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_risk(request: EvaluationRequest):
    # Log de alto nivel con datos críticos de la solicitud (sin PII sensible).
    logger.info(
        "Nueva solicitud /evaluate | user_id=%s | platform=%s | ciudades=%s",
        request.user_id,
        request.platform,
        [c.name for c in request.cities],
    )

    if not request.cities:
        logger.warning("Solicitud inválida: lista de ciudades vacía.")
        raise HTTPException(status_code=400, detail="City list is empty.")

    now = datetime.now()
    timestamp = now.isoformat()
    ruta_id = f"RUTA-{uuid.uuid4()}"

    city_results: List[Dict[str, str | float]] = []
    total_risk = 0.0

    for city in request.cities:
        city_name = city.name.strip()

        # Validación estricta: la ciudad debe existir en el CSV oficial.
        if city_name not in CITY_RISK_MAP:
            logger.error(
                "Ciudad no encontrada en el mapa oficial | ruta_id=%s | city=%s",
                ruta_id,
                city_name,
            )
            raise HTTPException(
                status_code=400,
                detail=f"City '{city_name}' not found in official risk map.",
            )

        # Se usa SIEMPRE el puntaje oficial del CSV.
        official_score = CITY_RISK_MAP[city_name]
        level = classify_risk(official_score)

        city_results.append(
            {
                "name": city_name,
                "risk_score": official_score,
                "risk_level": level,
            }
        )
        total_risk += official_score

        logger.debug(
            "Ciudad evaluada | ruta_id=%s | city=%s | score=%.2f | level=%s",
            ruta_id,
            city_name,
            official_score,
            level,
        )

    average_risk = total_risk / len(city_results)
    overall_level = classify_risk(average_risk)

    # Ensamblado de la respuesta
    output: Dict[str, object] = {
        "timestamp": timestamp,
        "ruta_id": ruta_id,
        "executed_by": {
            "user_id": request.user_id,
            "platform": request.platform,
        },
        "evaluated_by": "risk_api.py",
        "cities": city_results,
        "summary": {
            "total_risk": round(total_risk, 2),
            "average_risk": round(average_risk, 2),
        },
        "overall_level": overall_level,
        "status": "PendingValidation",
    }

    # Persistencia y respaldo con manejo de errores granular.
    try:
        await save_evaluation_to_db_and_json(output)
        logger.info(
            "Evaluación guardada correctamente | ruta_id=%s | overall_level=%s | total=%.2f | average=%.2f",
            ruta_id,
            overall_level,
            total_risk,
            average_risk,
        )
    except HTTPException:
        # Si alguna capa levantó HTTPException, se respeta su código.
        logger.error(
            "Error HTTP durante guardado | ruta_id=%s", ruta_id, exc_info=True
        )
        raise
    except Exception:
        # Errores inesperados en persistencia se devuelven como 500.
        logger.error(
            "Error interno al guardar evaluación | ruta_id=%s", ruta_id, exc_info=True
        )
        raise HTTPException(
            status_code=500, detail="Internal error while saving evaluation."
        )

    return output


