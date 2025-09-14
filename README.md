# GestUnifServ

**Unified Service Manager** for administrative services of Grupo Energía Bogotá and its subsidiaries.

GestUnifServ will consist of several modules. The first module focuses on:

**Evaluation of terrestrial routes in Colombia.**

This system allows employees to register travel routes, calculate the associated risk, consult relevant news, and generate automated PDF reports.

---

## Features

- Route registration via bot in MS Teams  
- Automatic risk evaluation by city  
- Manual review by analyst  
- Web-based news retrieval  
- PDF generation and email delivery  

---

## Technologies

- Backend: Python, FastAPI  
- Database: PostgreSQL  
- Integrations: Azure Bot Framework (MS Teams)  
- Data processing: Scrapy, spaCy  
- Reporting: ReportLab  
- Containerization: Docker, Docker Compose  
- Testing: Pytest  

---

## Architecture

The system is deployed using Docker Compose with two main services:

- risk_api → FastAPI microservice exposing REST API endpoints  
- riskdb → PostgreSQL database  

┌────────────┐       ┌──────────────┐       ┌──────────┐
│  MS Teams  │ <---> │   risk_api   │ <---> │  riskdb  │
└────────────┘       └──────────────┘       └──────────┘
       ↑
   Notifications via
   Webhooks / Bot

---

### Shared Data Volume

Both the MS Teams bot and `risk_api` share the `./data` volume. The bot writes weekly plans (`ruta.csv`) and the API reads/writes:

- `riesgos.csv`: authoritative risk map by city (read‑only)
- `ruta.csv`: weekly routes exported from templates (with `Jurisdiccion_*`)
- `output_*.json`: JSON backups for each evaluation
- `audit_log.csv`: append‑only audit for key actions
- `templates/*.json`: personal route templates

## Database Integration

The system uses PostgreSQL to store and manage service data. Initial schema includes:

- `routes`: Employee travel routes and metadata  
- `cities`: Risk scores and contextual information  
- `evaluations`: Analyst reviews and automated assessments  
- `news`: Relevant articles linked to route context  

### Database Setup (Development)

```bash
# Create database and apply schema manually
psql -U your_user -d gestunifserv_db -f db/schema.sql
```

When running with Docker Compose, the database is initialized automatically if empty.

---

## Running with Docker

1. Clone the repository:

```bash
git clone https://github.com/GrupoEnergiaBogota/GestUnifServ.git
cd GestUnifServ
```

2. Build and start the containers:

```bash
docker compose up --build
```

3. Services:  
- API available at: http://localhost:8000  
- PostgreSQL exposed on port 5432  

---

## Running Tests

Run tests locally:

```bash
pytest
```

Run tests inside the container:

```bash
docker compose exec risk_api pytest
```

---

## Integration with Microsoft Teams

GestUnifServ integrates with Microsoft Teams for route registration and risk notifications.

### Incoming Webhooks (basic notifications)

1. Configure an Incoming Webhook in a Teams channel.  
2. Copy the generated URL.  
3. Send notifications from the API:

```python
import requests

webhook_url = "https://outlook.office.com/webhook/..."
message = {
    "text": "New route registered and risk evaluated!"
}
requests.post(webhook_url, json=message)
```

### Bot Framework (conversational interface)

- Register a bot in Azure Active Directory.  
- Connect it to Teams to allow:  
  - Route registration  
  - Requesting reports  
  - Receiving automated risk alerts  

---

## API Usage

Health check:

```bash
curl http://localhost:8000/health
```

Register new route:

```bash
curl -X POST http://localhost:8000/routes \
     -H "Content-Type: application/json" \
     -d '{"employee_id": 123, "origin": "Bogotá", "destination": "Medellín"}'
```

---

## Contribution and Development

1. Fork and clone the repo.  
2. Use Docker Compose for local development.  
3. For manual setup:  

```bash
pip install -r requirements.txt
uvicorn risk_api.main:app --reload
```

4. Make sure PostgreSQL is running and `.env` contains correct DB credentials.  

---

## License

MIT License (or company-specific license, if applicable).

---

## Environment Variables

- `DATABASE_URL`: SQLAlchemy URL (PostgreSQL in prod, `sqlite+aiosqlite:///./riskdb.sqlite3` in dev).  
- `RISK_CSV_PATH`: path to `riesgos.csv` (default `data/riesgos.csv`).  
- `DRIVERS_CSV_PATH`: path to `drivers.csv` (default `data/drivers.csv`).  
- `ENABLE_DRIVERS_WRITE`: enable `POST/PUT /drivers` when `true`.  
- `AUDIT_LOG_PATH`: path to audit CSV (default `data/audit_log.csv`).  
- `LOG_LEVEL`: logging level (`INFO` by default).  

---

## Updated API Usage (Quick Examples)

Evaluate simple route:

```bash
curl -X POST http://localhost:8000/evaluate \
     -H "Content-Type: application/json" \
     -d '{
           "user_id": "user_123",
           "platform": "MS Teams",
           "cities": [{"name": "Bogotá"},{"name": "Medellín"}]
         }'
```

Evaluate a day with segments:

```bash
curl -X POST http://localhost:8000/evaluate_day \
     -H "Content-Type: application/json" \
     -d '{
           "date":"2025-09-15",
           "user": {"user_id":"user_123"},
           "segments": [
             {"segment_index":1,
              "origin_municipio":"Bogotá",
              "dest_tipo":"municipio",
              "dest_municipio":"Medellín",
              "companions_count":0,
              "companions_json":[],
              "activity_type":"Visita de Mantenimiento",
              "vehicle_type":"SUV",
              "vehicle_plate":"ABC123",
              "driver_national_id":"1234567890"}
           ]
         }'
```

Weekly summary (JSON backups or DB):

```bash
curl "http://localhost:8000/summary/week?user_id=user_123&week_start=2025-09-15&source=json"
curl "http://localhost:8000/summary/week?user_id=user_123&week_start=2025-09-15&source=db"
```

Suggestions:

```bash
curl "http://localhost:8000/suggest/municipios?q=Bogo&limit=5"
curl "http://localhost:8000/suggest/activos?q=Subestaci%C3%B3n&limit=5"
curl "http://localhost:8000/suggest/drivers?q=1234&limit=5"
```

Drivers catalog (optional; requires `ENABLE_DRIVERS_WRITE=true`):

```bash
curl -X POST http://localhost:8000/drivers -H "Content-Type: application/json" \
     -d '{"national_id":"1234567890","first_name":"Ana","last_name":"Gómez","phone":"3001234567"}'

curl -X PUT http://localhost:8000/drivers -H "Content-Type: application/json" \
     -d '{"national_id":"1234567890","first_name":"Ana María","last_name":"Gómez","phone":"3000000000"}'
```

---

## Data Folder Cheatsheet

- `data/riesgos.csv`: official city risk map.  
- `data/ruta.csv`: weekly routes exported from templates (includes Jurisdiccion_*).  
- `data/output_*.json`: per‑evaluation backups.  
- `data/summary_json_*.json`: weekly summaries from JSON backups.  
- `data/summary_db_*.json`: weekly summaries from DB.  
- `data/audit_log.csv`: append‑only audit.  

---

## Handy Scripts

- Demo summary from synthetic outputs:

```bash
python scripts/demo_week_summary.py
```

- Full flow (template → ruta.csv → evals → summaries):

```bash
python scripts/run_full_flow.py
```
