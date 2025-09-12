# ─────────────────────────────────────────────────────────────
# db_handler.py — Database and persistence utilities
#
# - Defines SQLAlchemy models for evaluations and city results.
# - Provides async functions to insert evaluations into PostgreSQL.
# - Also writes JSON files for audit/backup purposes.
# ─────────────────────────────────────────────────────────────

import os
import json
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Float, ForeignKey, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# ─────────────────────────────────────────────────────────────
# Database Setup
# ─────────────────────────────────────────────────────────────

# Read DB URL from environment variable or fallback to local default
# Example: export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/riskdb"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/riskdb"
)

# Async engine for PostgreSQL
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

# Session factory for async DB operations
AsyncSessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

# SQLAlchemy base model
Base = declarative_base()

# ─────────────────────────────────────────────────────────────
# Database Models
# ─────────────────────────────────────────────────────────────

class Evaluation(Base):
    """
    Represents a risk evaluation (one request to /evaluate).
    """
    __tablename__ = "evaluations"

    id = Column(String, primary_key=True, index=True)  # UUID string
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    overall_level = Column(String, nullable=False)
    total_risk = Column(Float, nullable=False)
    average_risk = Column(Float, nullable=False)
    status = Column(String, default="PendingValidation")

    # One-to-many relationship with cities
    cities = relationship("CityResult", back_populates="evaluation", cascade="all, delete")


class CityResult(Base):
    """
    Represents the result for a single city in an evaluation.
    """
    __tablename__ = "city_results"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    evaluation_id = Column(String, ForeignKey("evaluations.id"), nullable=False)
    name = Column(String, nullable=False)
    risk_score = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False)

    # Back reference to Evaluation
    evaluation = relationship("Evaluation", back_populates="cities")

# ─────────────────────────────────────────────────────────────
# Utility: Create tables (call once at startup if needed)
# ─────────────────────────────────────────────────────────────

async def init_db():
    """
    Creates database tables if they do not exist.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# ─────────────────────────────────────────────────────────────
# Persistence Functions
# ─────────────────────────────────────────────────────────────

async def save_evaluation_to_db_and_json(evaluation: dict):
    """
    Saves an evaluation to PostgreSQL and also writes a JSON backup.

    Args:
        evaluation (dict): Evaluation data (same as API response).
    """
    async with AsyncSessionLocal() as session:
        # Create Evaluation object
        eval_obj = Evaluation(
            id=evaluation["ruta_id"],
            timestamp=datetime.fromisoformat(evaluation["timestamp"]),
            user_id=evaluation["executed_by"]["user_id"],
            platform=evaluation["executed_by"]["platform"],
            overall_level=evaluation["overall_level"],
            total_risk=evaluation["summary"]["total_risk"],
            average_risk=evaluation["summary"]["average_risk"],
            status=evaluation["status"]
        )

        # Create CityResult objects
        for city in evaluation["cities"]:
            city_obj = CityResult(
                evaluation_id=evaluation["ruta_id"],
                name=city["name"],
                risk_score=city["risk_score"],
                risk_level=city["risk_level"]
            )
            eval_obj.cities.append(city_obj)

        # Add and commit to DB
        session.add(eval_obj)
        await session.commit()

    # ─── Write JSON backup for audit ─────────────────────────
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, f"output_{evaluation['ruta_id']}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(evaluation, f, indent=4, ensure_ascii=False)
