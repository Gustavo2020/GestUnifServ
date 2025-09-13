# Estructura del Proyecto GestUnifServ

```
GestUnifServ/
├── src/
│   ├── risk_api.py          # FastAPI app con rutas y lógica de evaluación de riesgo
│   ├── db_handler.py        # Conexión a base de datos y utilidades de persistencia
│   ├── evaluate_risk.py     # Lógica auxiliar de evaluación de riesgo
│   ├── log_config.py        # Configuración de logging centralizado
│   └── __init__.py          # Marca la carpeta como paquete Python importable
│
├── bots/
│   └── teams_bot/           # Bot de Microsoft Teams para interactuar con risk_api
│       ├── app.py           # Servidor aiohttp que expone /api/messages
│       ├── bot.py           # Lógica del bot (mensajes, Adaptive Cards, etc.)
│       ├── requirements.txt # Dependencias del bot (SDK Bot Framework, requests, etc.)
│       ├── adaptive_card.json # Formulario JSON para captura de rutas (posterior)
│       └── Dockerfile       # Imagen de Docker para desplegar el bot (posterior)
│
├── data/                    # Datos de prueba o respaldo (no usados en producción)
│   ├── ruta.csv             # Datos de entrada de rutas para evaluaciones
│   ├── riesgos.csv          # Mapa oficial de riesgo (puntajes por ciudad)
│   └── output_*.json        # Respaldos JSON de evaluaciones generadas por la API
│
├── notebooks/               # Notebooks Jupyter para exploración y prototipado
│
├── tests/                   # Pruebas unitarias de los módulos en src y de la API
│
├── docs/                    # Documentación del proyecto
│   ├── project_structure.md # Este archivo (estructura actualizada del proyecto)
│   └── roadmap.md           # Plan de desarrollo y módulos futuros
│
├── requirements.txt         # Dependencias mínimas para ejecución en producción
├── dev-requirements.txt     # Dependencias adicionales para desarrollo y pruebas
│
├── Dockerfile               # Imagen de producción (FastAPI + Uvicorn)
├── Dockerfile.dev           # Imagen de desarrollo (incluye testing y Jupyter)
├── docker-compose.yml       # Orquestación de contenedores: API + PostgreSQL
├── docker-compose.override.yml # Configuración adicional para entorno local
├── .env                     # Variables de entorno (credenciales DB, configuraciones)
├── .dockerignore            # Archivos/carpetas a excluir de la build de Docker
├── .gitignore               # Archivos/carpetas a excluir de git
│
├── init_db.py               # Script utilitario para inicializar tablas en PostgreSQL
├── test_imports.py          # Script de verificación de imports en el entorno
│
├── README.md                # Descripción general del proyecto e instrucciones de uso
└── project_structure.md     # Referencia de estructura actualizada (este archivo)
```

---

## Notas

- **bots/teams_bot/** es el nuevo directorio para el desarrollo del bot de Microsoft Teams.  
- Inicialmente contiene `app.py`, `bot.py` y `requirements.txt`; más adelante sumaremos `adaptive_card.json` y `Dockerfile`.  
- El bot se conecta con `risk_api.py` a través del endpoint `/evaluate` y comparte los datos de `data/`.  
- Esta separación facilita desplegar la API y el bot como contenedores independientes dentro del mismo `docker-compose.yml`.  
