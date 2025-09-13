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
