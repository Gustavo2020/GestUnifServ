# ─────────────────────────────────────────────────────────────
# db_handler.py — Persistencia en base de datos y respaldo JSON
#
# Objetivo:
# - Definir modelos ORM (SQLAlchemy) para evaluations y city_results.
# - Proveer funciones async para inicializar DB y guardar evaluaciones.
# - Guardar respaldo de cada evaluación como archivo JSON en data/.
#
# Preparado para producción:
# - Logging estructurado en JSON (via src/log_config.setup_logging()).
# - Manejo robusto de errores en inicialización y persistencia.
# ─────────────────────────────────────────────────────────────

import os
import json
import uuid
import logging
from datetime import datetime

from sqlalchemy import Column, String, Float, ForeignKey, DateTime, Date, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# ─────────────────────────────────────────────────────────────
# Módulos internos del proyecto
# - log_config: configuración global de logging estructurado
# ─────────────────────────────────────────────────────────────
from src.log_config import setup_logging

# Configuración global de logging
setup_logging()
logger = logging.getLogger("db_handler")

# ─────────────────────────────────────────────────────────────
# Configuración de la conexión a la base de datos
# - DATABASE_URL se toma de variable de entorno o usa fallback local.
#   Ejemplo de variable:
#   export DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/riskdb"
# ─────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/riskdb"
)

# Motor async para PostgreSQL
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

# Fábrica de sesiones async
AsyncSessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

# Base declarativa de SQLAlchemy
Base = declarative_base()

# ─────────────────────────────────────────────────────────────
# Definición de modelos
# ─────────────────────────────────────────────────────────────

class Evaluation(Base):
    """
    Representa una evaluación de riesgo (una solicitud /evaluate).
    """
    __tablename__ = "evaluations"

    id = Column(String, primary_key=True, index=True)  # UUID string (ruta_id)
    timestamp = Column(DateTime, default=datetime.utcnow)
    planned_date = Column(Date, nullable=True)
    user_id = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    overall_level = Column(String, nullable=False)
    total_risk = Column(Float, nullable=False)
    average_risk = Column(Float, nullable=False)
    status = Column(String, default="PendingValidation")

    # Relación uno-a-muchos con CityResult
    cities = relationship("CityResult", back_populates="evaluation", cascade="all, delete")

class CityResult(Base):
    """
    Resultado de riesgo para una ciudad dentro de una evaluación.
    """
    __tablename__ = "city_results"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    evaluation_id = Column(String, ForeignKey("evaluations.id"), nullable=False)
    name = Column(String, nullable=False)
    risk_score = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False)

    # Back reference a Evaluation
    evaluation = relationship("Evaluation", back_populates="cities")

# ─────────────────────────────────────────────────────────────
# Utilidad: Inicializar base de datos
# - Crea las tablas si no existen.
# - Se invoca en risk_api.py durante el ciclo de vida (lifespan).
# ─────────────────────────────────────────────────────────────
async def init_db():
    """
    Crea las tablas necesarias si no existen en la base.
    """
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Ensure new columns exist when upgrading without migrations
            try:
                await conn.execute(text("ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS planned_date DATE"))
            except Exception:
                logger.warning("Could not ensure planned_date column (may already exist)", exc_info=True)
        logger.info("Tablas creadas/verificadas correctamente en la base de datos.")
    except Exception:
        logger.error("Error inicializando la base de datos.", exc_info=True)
        raise

# ─────────────────────────────────────────────────────────────
# Persistencia: Guardar evaluación en DB + respaldo JSON
# - Inserta Evaluation y CityResult en PostgreSQL.
# - Escribe un archivo JSON en data/output_<ruta_id>.json
# ─────────────────────────────────────────────────────────────
async def save_evaluation_to_db_and_json(evaluation: dict):
    """
    Guarda una evaluación en PostgreSQL y en un archivo JSON.

    Args:
        evaluation (dict): Evaluación generada en risk_api.py
    """
    try:
        async with AsyncSessionLocal() as session:
            # Crear objeto Evaluation
            planned_date = None
            try:
                d = evaluation.get("date")
                if d:
                    planned_date = datetime.fromisoformat(d).date()
            except Exception:
                planned_date = None
            eval_obj = Evaluation(
                id=evaluation["ruta_id"],
                timestamp=datetime.fromisoformat(evaluation["timestamp"]),
                user_id=evaluation["executed_by"]["user_id"],
                platform=evaluation["executed_by"]["platform"],
                overall_level=evaluation["overall_level"],
                total_risk=evaluation["summary"]["total_risk"],
                average_risk=evaluation["summary"]["average_risk"],
                status=evaluation["status"],
                planned_date=planned_date,
            )

            # Crear objetos CityResult asociados
            for city in evaluation["cities"]:
                city_obj = CityResult(
                    evaluation_id=evaluation["ruta_id"],
                    name=city["name"],
                    risk_score=city["risk_score"],
                    risk_level=city["risk_level"]
                )
                eval_obj.cities.append(city_obj)

            # Insertar en DB
            session.add(eval_obj)
            await session.commit()

            logger.info(
                "Evaluación guardada en DB | ruta_id=%s | ciudades=%d | overall=%s",
                evaluation["ruta_id"],
                len(evaluation["cities"]),
                evaluation["overall_level"],
            )

    except Exception:
        logger.error(
            "Error guardando evaluación en DB | ruta_id=%s",
            evaluation.get("ruta_id"),
            exc_info=True,
        )
        raise

    # Respaldo en JSON
    try:
        output_dir = "data"
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, f"output_{evaluation['ruta_id']}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(evaluation, f, indent=4, ensure_ascii=False)

        logger.info("Respaldo JSON creado | path=%s", output_path)

    except Exception:
        logger.error(
            "Error guardando respaldo JSON | ruta_id=%s",
            evaluation.get("ruta_id"),
            exc_info=True,
        )
        raise
