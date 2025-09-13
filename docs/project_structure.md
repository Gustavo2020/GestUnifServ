# Estructura del Proyecto GestUnifServ

GestUnifServ/
├── src/
│   ├── risk_api.py          # FastAPI app con rutas y lógica de evaluación de riesgo
│   ├── db_handler.py        # Conexión a base de datos y utilidades de persistencia
│   ├── evaluate_risk.py     # (opcional) lógica auxiliar de evaluación de riesgo si se separa
│   └── __init__.py          # Marca la carpeta como paquete Python importable
│
├── data/
│   ├── ruta.csv             # Datos de entrada de rutas para evaluaciones
│   ├── riesgos.csv          # Mapa oficial de riesgo (puntajes por ciudad)
│   └── output_*.json        # Respaldos JSON de evaluaciones generadas por la API
│
├── notebooks/               # Notebooks Jupyter para exploración y prototipado
│
├── tests/                   # Pruebas unitarias de los módulos en src y de la API
│
├── requirements.txt         # Dependencias mínimas para ejecución en producción
├── dev-requirements.txt     # Dependencias adicionales para desarrollo y pruebas (pytest, Jupyter, pandas)
│
├── Dockerfile               # Imagen de producción (FastAPI + Uvicorn)
├── Dockerfile.dev           # Imagen de desarrollo (incluye testing y Jupyter)
├── docker-compose.yml       # Orquestación de contenedores: API + PostgreSQL
├── .env                     # Variables de entorno (credenciales DB, configuraciones)
│
├── init_db.py               # Script utilitario para inicializar tablas en PostgreSQL
│                            # Ejecuta src/db_handler.init_db() y crea evaluations y city_results
│
├── README.md                # Descripción general del proyecto e instrucciones de uso
└── project_structure.md     # Este archivo (referencia de estructura actualizada)



