import csv
import os
from typing import List, Dict

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
        reader = csv.reader(f)
        next(reader)  # Skip header row
        return [row[0].strip() for row in reader if row and row[0].strip()]


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
        reader = csv.reader(f)
        next(reader, None)  # Skip header row if present

        for row_num, row in enumerate(reader, start=2):
            # Check for missing columns or empty cells
            if len(row) < 2 or not row[0].strip() or not row[1].strip():
                print(f"[Warning] Incomplete row at line {row_num}")
                continue

            city = row[0].strip()
            risk_str = row[1].strip()

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
        reader = csv.reader(f)
        next(reader, None)  # Skip header row if present

        for row_num, row in enumerate(reader, start=2):
            if not row or not row[0].strip():
                print(f"[Warning] Empty row at line {row_num}")
                continue

            city = row[0].strip()

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
def evaluate_risk(cities: List[str], city_risk_map: Dict[str, float]) -> Dict:
    city_risks = {}

    # Assign risk score and classification to each city
    for city in cities:
        risk_score = city_risk_map.get(city, 0.0)
        if risk_score >= 0.7:
            level = "High"
        elif risk_score >= 0.4:
            level = "Medium"
        else:
            level = "Low"
        city_risks[city] = {
            "score": risk_score,
            "level": level
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

    city_risk_map = validate_city_risk_map(riesgos_path)
    cities = validate_route_csv(ruta_path, city_risk_map)
    result = evaluate_risk(cities, city_risk_map)
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
            "risk_level": result["city_risks"][city]["level"]
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