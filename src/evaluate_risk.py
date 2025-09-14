import csv
import os
from typing import List, Dict, Tuple

# ─────────────────────────────────────────────────────────────
# Function: load_cities_from_csv
# Purpose: Reads a CSV file containing a list of cities (one per row)
# Returns: A list of city names as strings
# Notes:
# - Assumes the first row is a header and skips it
# - Ignores empty rows or blank cells
# ─────────────────────────────────────────────────────────────
def load_cities_from_csv(path: str) -> List[str]:
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        # Support headers: Departamento,Municipio and legacy 'Ciudad'
        col_city = None
        headers = [h.strip() for h in (reader.fieldnames or [])]
        for h in headers:
            if h.lower() in ("municipio", "ciudad"):
                col_city = h
                break

        cities: List[str] = []
        if col_city:
            for row in reader:
                name = (row.get(col_city) or "").strip()
                if name:
                    cities.append(name)
        return cities


# ─────────────────────────────────────────────────────────────
# Function: validate_city_risk_map
# Purpose: Reads and validates a CSV file containing city names
#          and their associated risk scores.
# Returns: A dictionary {city_name: risk_score} with only valid entries.
# Validation includes:
# - File existence
# - Non-empty rows
# - No duplicate cities
# - Risk values must be numeric and within [0.0, 1.0]
# - Skips malformed or invalid rows with warnings
# ─────────────────────────────────────────────────────────────
def validate_city_risk_map(path: str) -> Dict[str, float]:

    # Ensure the file exists before attempting to read
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    risk_map = {}  # Dictionary to store valid city-risk pairs
    seen = set()   # Set to track duplicate city names

    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        # Accept new columns Departamento,Municipio,Riesgo and legacy Ciudad,Riesgo
        col_city = None
        col_risk = None
        headers = [h.strip() for h in (reader.fieldnames or [])]
        for h in headers:
            h_low = h.lower()
            if h_low in ("municipio", "ciudad"):
                col_city = h
            if h_low in ("riesgo", "risk"):
                col_risk = h

        for row_num, row in enumerate(reader, start=2):
            city = (row.get(col_city) or "").strip() if col_city else ""
            risk_str = (row.get(col_risk) or "").strip() if col_risk else ""
            if not city or not risk_str:
                print(f"[Warning] Incomplete row at line {row_num}")
                continue

            # Detect and skip duplicate city entries
            if city in seen:
                print(f"[Warning] Duplicate city: {city} at line {row_num}")
                continue

            try:
                risk = float(risk_str)
                # Validate that risk score is within acceptable range
                if not (0.0 <= risk <= 1.0):
                    print(f"[Error] Risk out of range for city {city} at line {row_num}")
                    continue
            except ValueError:
                print(f"[Error] Invalid risk value for city {city} at line {row_num}")
                continue

            # Store valid entry and mark city as seen
            risk_map[city] = risk
            seen.add(city)

    # Ensure at least one valid entry was found
    if not risk_map:
        raise ValueError("No valid city-risk entries found in the file.")

    return risk_map


# -------------------------------------------------------------
# Function: load_city_meta_map
# Purpose: Loads an enriched map for each city with risk and jurisdictions
# Returns: Dict[city_name, { 'risk': float,
#                           'Jurisdiccion_fuerza_militar': str,
#                           'Jurisdiccion_policia': str }]
# Notes:
# - Tolerates extra columns and different header cases.
# -------------------------------------------------------------
def load_city_meta_map(path: str) -> Dict[str, Dict[str, object]]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    meta_map: Dict[str, Dict[str, object]] = {}
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        headers = [h.strip() for h in (reader.fieldnames or [])]
        # Map columns ignoring case/diacritics basic
        col_city = None
        col_risk = None
        col_jfm = None
        col_jpol = None
        for h in headers:
            low = h.lower()
            if low in ("municipio", "ciudad"):
                col_city = h
            elif low in ("riesgo", "risk"):
                col_risk = h
            elif low == "jurisdiccion_fuerza_militar":
                col_jfm = h
            elif low == "jurisdiccion_policia":
                col_jpol = h

        for row in reader:
            city = (row.get(col_city) or "").strip() if col_city else ""
            r = (row.get(col_risk) or "").strip() if col_risk else ""
            if not city or not r:
                continue
            try:
                risk = float(r)
            except ValueError:
                continue
            meta_map[city] = {
                'risk': risk,
                'Jurisdiccion_fuerza_militar': (row.get(col_jfm) or "").strip() if col_jfm else "",
                'Jurisdiccion_policia': (row.get(col_jpol) or "").strip() if col_jpol else "",
            }

    if not meta_map:
        raise ValueError("No valid entries in riesgos.csv")
    return meta_map


# ─────────────────────────────────────────────────────────────
# Function: validate_route_csv
# Purpose: Validates the contents of ruta.csv before risk evaluation
# Returns: A list of valid city names
# Notes:
# - Checks file existence
# - Skips empty rows and duplicates
# - Verifies that each city exists in the risk map
# - Raises an error if no valid cities are found
# ─────────────────────────────────────────────────────────────
def validate_route_csv(path: str, city_risk_map: Dict[str, float]) -> List[str]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    valid_cities = []
    seen = set()

    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        # Support Departamento,Municipio and legacy single 'ciudad'
        col_city = None
        headers = [h.strip() for h in (reader.fieldnames or [])]
        for h in headers:
            if h.lower() in ("municipio", "ciudad"):
                col_city = h

        for row_num, row in enumerate(reader, start=2):
            city = (row.get(col_city) or "").strip() if col_city else ""
            if not city:
                print(f"[Warning] Empty row at line {row_num}")
                continue

            if city in seen:
                print(f"[Warning] Duplicate city: {city} at line {row_num}")
                continue

            if city not in city_risk_map:
                print(f"[Error] Unknown city: {city} not found in city_risk_map")
                continue

            valid_cities.append(city)
            seen.add(city)

    if not valid_cities:
        raise ValueError("No valid cities found in the route file.")

    return valid_cities

# ─────────────────────────────────────────────────────────────
# Function: evaluate_risk
# Purpose: Calculates individual and overall risk levels for a list of cities
# Returns: A dictionary with detailed risk metrics
# Output includes:
# - Risk score and level per city
# - Total and average risk
# - Overall risk classification
# ─────────────────────────────────────────────────────────────
def evaluate_risk(cities: List[str], city_meta_map: Dict[str, Dict[str, object]]) -> Dict:
    city_risks = {}

    # Assign risk score and classification to each city
    for city in cities:
        risk_score = (city_meta_map.get(city, {}).get('risk', 0.0)  # type: ignore
                      if city_meta_map else 0.0)
        if risk_score >= 0.7:
            level = "High"
        elif risk_score >= 0.4:
            level = "Medium"
        else:
            level = "Low"
        city_risks[city] = {
            "score": risk_score,
            "level": level,
            "Jurisdiccion_fuerza_militar": city_meta_map.get(city, {}).get('Jurisdiccion_fuerza_militar', ""),
            "Jurisdiccion_policia": city_meta_map.get(city, {}).get('Jurisdiccion_policia', ""),
        }

    # Aggregate total and average risk
    total_risk = sum(city_risks[city]["score"] for city in cities)
    average_risk = total_risk / len(cities) if cities else 0.0

    # Classify overall risk level
    if average_risk >= 0.7:
        overall_level = "High"
    elif average_risk >= 0.4:
        overall_level = "Medium"
    else:
        overall_level = "Low"

    return {
        "city_risks": city_risks,
        "total_risk": round(total_risk, 2),
        "average_risk": round(average_risk, 2),
        "overall_level": overall_level
    }
# ─────────────────────────────────────────────────────────────
# Main Execution Block
# Purpose: Loads data, validates input, evaluates risk, and prints result
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ruta_path = "D:/Github/GestUnifServ/data/ruta.csv"
    riesgos_path = "D:/Github/GestUnifServ/data/riesgos.csv"

    # Build meta map (risk + jurisdictions) from riesgos.csv
    city_meta_map = load_city_meta_map(riesgos_path)
    # For validation, just pass risk view
    city_risk_map = {k: v['risk'] for k, v in city_meta_map.items()}
    cities = validate_route_csv(ruta_path, city_risk_map)
    result = evaluate_risk(cities, city_meta_map)
    print(result)
# ─────────────────────────────────────────────────────────────
# Post-Evaluation Export Block
# Purpose: Structure and persist the risk evaluation result
# Output: JSON file with metadata, city-level scores, and summary
# ─────────────────────────────────────────────────────────────
import json
from datetime import datetime
# Capture current timestamp and generate a unique route ID
now = datetime.now()
timestamp = now.isoformat()  # ISO 8601 format for traceability
ruta_id = f"RUTA-{now.strftime('%Y%m%d-%H%M')}"  # e.g., RUTA-20250909-1810
# Simulated user identity; in production, this should be dynamically retrieved
executed_by = {
    "user_id": "gustavo.martinez@yourdomain.com",  # Replace with actual MS Teams user ID
    "platform": "MS Teams"  # Execution platform identifier
}
# Construct the structured output object
output = {
    "timestamp": timestamp,               # When the evaluation was performed
    "ruta_id": ruta_id,                   # Unique identifier for this route evaluation
    "executed_by": executed_by,          # Who executed the evaluation and from where
    "evaluated_by": "evaluate_risk.py",  # Source module responsible for the analysis
    # List of cities with individual risk scores and classifications
    "cities": [
        {
            "name": city,
            "risk_score": result["city_risks"][city]["score"],
            "risk_level": result["city_risks"][city]["level"],
            "Jurisdiccion_fuerza_militar": result["city_risks"][city]["Jurisdiccion_fuerza_militar"],
            "Jurisdiccion_policia": result["city_risks"][city]["Jurisdiccion_policia"],
        }
        for city in cities
    ],
    # Aggregated summary metrics for the entire route
    "summary": {
        "total_risk": result["total_risk"],
        "average_risk": result["average_risk"],
        "overall_level": result["overall_level"]
    },
    # Initial status of the evaluation; to be updated by the analyst
    "status": "PendingValidation"
}
# Persist the structured result to disk as a JSON file
with open("D:/Github/GestUnifServ/data/output_risk.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=4, ensure_ascii=False)
