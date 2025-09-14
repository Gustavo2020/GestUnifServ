import os
import asyncio
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./riskdb.sqlite3")

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db_handler import init_db, save_evaluation_to_db_and_json


async def main():
    await init_db()
    evaluation = {
        "timestamp": datetime.now().isoformat(),
        "ruta_id": "RUTA-TEST-123",
        "executed_by": {"user_id": "tester", "platform": "CLI"},
        "evaluated_by": "unit",
        "cities": [
            {"name": "Bogotá", "risk_score": 0.4, "risk_level": "Medium"},
            {"name": "Medellín", "risk_score": 0.5, "risk_level": "Medium"},
        ],
        "summary": {"total_risk": 0.9, "average_risk": 0.45},
        "overall_level": "Medium",
        "status": "PendingValidation",
    }
    try:
        await save_evaluation_to_db_and_json(evaluation)
        print("OK saved")
    except Exception as e:
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

