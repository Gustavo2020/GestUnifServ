# ─────────────────────────────────────────────────────────────
# risk_api.py — REST API for Risk Evaluation
#
# - Loads risk map from riesgos.csv
# - Evaluates cities and classifies risk levels
# - Calls db_handler to persist results in DB + JSON
# ─────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from datetime import datetime
import uuid
import os
import csv

from db_handler import save_evaluation_to_db_and_json, init_db

# ─────────────────────────────────────────────────────────────
# Load city risk map (from CSV)
# ─────────────────────────────────────────────────────────────

def load_city_risk_map(filepath: str) -> Dict[str, float]:
    """
    Loads risk scores for cities from a CSV file.
    """
    city_risks = {}
    with open(filepath, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if "Ciudad" not in reader.fieldnames or "Riesgo" not in reader.fieldnames:
            raise RuntimeError("CSV must contain 'Ciudad' and 'Riesgo' columns.")
        for row in reader:
            city = row["Ciudad"].strip()
            city_risks[city] = float(row["Riesgo"])
    return city_risks

# Load CSV file path from environment variable, fallback to default
# -----------------------------------------------------------------
# Usage:
# - Run locally without changes → defaults to "data/riesgos.csv"
# - In production, set environment variable:
#       export RISK_CSV_PATH=/etc/app/config/riesgos.csv
#   The API will then automatically use that file.
# -----------------------------------------------------------------
RISK_CSV_PATH = os.getenv("RISK_CSV_PATH", "data/riesgos.csv")
CITY_RISK_MAP = load_city_risk_map(RISK_CSV_PATH)

# ─────────────────────────────────────────────────────────────
# Input/Output Schemas
# ─────────────────────────────────────────────────────────────

class CityRisk(BaseModel):
    name: str
    risk_score: float = None  # Optional, ignored for now

class EvaluationRequest(BaseModel):
    user_id: str
    platform: str
    cities: List[CityRisk]

class CityResult(BaseModel):
    name: str
    risk_score: float
    risk_level: str

class EvaluationResponse(BaseModel):
    timestamp: str
    ruta_id: str
    executed_by: Dict[str, str]
    evaluated_by: str
    cities: List[CityResult]
    summary: Dict[str, float]
    overall_level: str
    status: str

# ─────────────────────────────────────────────────────────────
# Risk Classification
# ─────────────────────────────────────────────────────────────

def classify_risk(score: float) -> str:
    if score >= 0.7:
        return "High"
    elif score >= 0.4:
        return "Medium"
    else:
        return "Low"

# ─────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Risk Evaluation API",
    description="API that evaluates route risks and saves them to PostgreSQL + JSON backup.",
    version="2.0.0"
)

@app.on_event("startup")
async def on_startup():
    """
    Initialize database tables at startup.
    """
    await init_db()

# ─────────────────────────────────────────────────────────────
# POST /evaluate
# ─────────────────────────────────────────────────────────────

@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_risk(request: EvaluationRequest):
    if not request.cities:
        raise HTTPException(status_code=400, detail="City list is empty.")

    now = datetime.now()
    timestamp = now.isoformat()
    ruta_id = f"RUTA-{uuid.uuid4()}"

    city_results = []
    total_risk = 0.0

    for city in request.cities:
        city_name = city.name.strip()

        if city_name not in CITY_RISK_MAP:
            raise HTTPException(
                status_code=400,
                detail=f"City '{city_name}' not found in official risk map."
            )

        official_score = CITY_RISK_MAP[city_name]
        level = classify_risk(official_score)

        city_results.append({
            "name": city_name,
            "risk_score": official_score,
            "risk_level": level
        })
        total_risk += official_score

    average_risk = total_risk / len(city_results)
    overall_level = classify_risk(average_risk)

    output = {
        "timestamp": timestamp,
        "ruta_id": ruta_id,
        "executed_by": {
            "user_id": request.user_id,
            "platform": request.platform
        },
        "evaluated_by": "risk_api.py",
        "cities": city_results,
        "summary": {
            "total_risk": round(total_risk, 2),
            "average_risk": round(average_risk, 2)
        },
        "overall_level": overall_level,
        "status": "PendingValidation"
    }

    # Save both in DB and JSON backup
    await save_evaluation_to_db_and_json(output)

    return output
