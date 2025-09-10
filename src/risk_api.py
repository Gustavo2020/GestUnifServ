# ─────────────────────────────────────────────────────────────
# risk_api.py — REST API for Risk Evaluation
# Validates incoming cities against riesgos.csv and returns
# structured evaluation results. Each evaluation is saved
# to a uniquely named JSON file.
# ─────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from datetime import datetime
import uuid
import json
import os
import csv

# ─────────────────────────────────────────────────────────────
# Load official city risk map from riesgos.csv
# ─────────────────────────────────────────────────────────────

def load_city_risk_map(filepath: str) -> Dict[str, float]:
    city_risks = {}
    try:
        with open(filepath, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                city = row["Ciudad"].strip()
                score = float(row["Riesgo"])
                city_risks[city] = score
    except Exception as e:
        raise RuntimeError(f"Failed to load risk map: {e}")
    return city_risks

# Load once at startup
CITY_RISK_MAP = load_city_risk_map("data/riesgos.csv")

# ─────────────────────────────────────────────────────────────
# Input Schema Definitions
# ─────────────────────────────────────────────────────────────

class CityRisk(BaseModel):
    name: str               # City name (must match riesgos.csv)
    risk_score: float       # Optional client-provided score

class EvaluationRequest(BaseModel):
    user_id: str            # User identifier (e.g., MS Teams ID)
    platform: str           # Source platform
    cities: List[CityRisk]  # List of cities to evaluate

# ─────────────────────────────────────────────────────────────
# Output Schema Definitions
# ─────────────────────────────────────────────────────────────

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
# Risk Classification Logic
# ─────────────────────────────────────────────────────────────

def classify_risk(score: float) -> str:
    if score >= 0.7:
        return "High"
    elif score >= 0.4:
        return "Medium"
    else:
        return "Low"

# ─────────────────────────────────────────────────────────────
# FastAPI Application Setup
# ─────────────────────────────────────────────────────────────

app = FastAPI()

# ─────────────────────────────────────────────────────────────
# POST /evaluate Endpoint
# ─────────────────────────────────────────────────────────────

@app.post("/evaluate", response_model=EvaluationResponse)
def evaluate_risk(request: EvaluationRequest):
    if not request.cities:
        raise HTTPException(status_code=400, detail="City list is empty.")

    now = datetime.now()
    timestamp = now.isoformat()
    ruta_id = f"RUTA-{uuid.uuid4()}"

    city_results = []
    total_risk = 0.0

    for city in request.cities:
        city_name = city.name.strip()

        # Validate city existence in official map
        if city_name not in CITY_RISK_MAP:
            raise HTTPException(
                status_code=400,
                detail=f"City '{city_name}' not found in official risk map."
            )

        # Use official score from riesgos.csv
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

    # Ensure output directory exists
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)

    # Save evaluation to uniquely named JSON file
    output_path = os.path.join(output_dir, f"output_{ruta_id}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

    return output