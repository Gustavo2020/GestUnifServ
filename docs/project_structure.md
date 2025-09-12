GestUnifServ/
├── src/
│ ├── risk_api.py # FastAPI app with routes and risk evaluation logic
│ ├── db_handler.py # Database connection and persistence utilities
│ └── ... # Other service modules
│
├── data/
│ ├── ruta.csv # Input route data for evaluations
│ ├── riesgos.csv # Official risk map (city risk scores)
│ └── output_*.json # JSON backups of evaluations
│
├── notebooks/ # Jupyter notebooks for exploration/prototyping
│
├── tests/ # Unit tests for src modules and API
│
├── requirements.txt # Runtime dependencies (production)
├── dev-requirements.txt # Dev/testing dependencies (pytest, Jupyter, pandas)
│
├── Dockerfile # Production container setup (FastAPI + Uvicorn)
├── Dockerfile.dev # Development container setup (adds testing & Jupyter)
├── docker-compose.yml # Orchestration for API + PostgreSQL
├── .env # Environment variables (DB credentials, configs)
│
├── README.md # Project overview and setup instructions
└── project_structure.md # Repository structure reference


