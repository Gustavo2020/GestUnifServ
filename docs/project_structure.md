GestUnifServ/

├── src/

│   ├── risk\_api.py          # REST API service

│   ├── evaluate\_risk.py     # Core evaluation logic (can be imported by API)

│   ├── risk\_validator.py    # Analyst validation module (optional)

│   └── utils/               # Helper functions, input validation, etc.

├── data/

│   ├── ruta.csv             # Input route data

│   ├── riesgos.csv          # Risk map

│   └── output\_\*.json        # Evaluations saved by API

├── notebooks/               # Exploratory analysis or prototyping

├── tests/                   # Unit tests for modules

├── README.md

└── requirements.txt

