# Changelog — GestUnifServ

Todos los cambios notables de este proyecto se documentarán en este archivo.  
El formato está basado en [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),  
y este proyecto sigue [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### Added
- Catálogo de conductores: endpoints opcionales `POST /drivers` y `PUT /drivers` controlados por `ENABLE_DRIVERS_WRITE`; persisten en `DRIVERS_CSV_PATH` y actualizan caché en memoria con bloqueo `asyncio.Lock`.
- Resumen semanal: `GET /summary/week?user_id=...&week_start=YYYY-MM-DD&source=json|db`.
  - `json`: agrega desde respaldos `data/output_*.json` y entrega `records` completos por día (incluye `user`, `segments`, `cities`, `summary`).
  - `db`: agrega desde PostgreSQL y enriquece con JSON si existe.
- Auditoría ligera: archivo `data/audit_log.csv` (NDCSV) con `timestamp,action,user_id,result,json_id,request_id` para acciones `evaluate`, `evaluate_day`, `summary_week`.
- Plantillas → CSV: `rutas.csv` ahora incluye columnas `Jurisdiccion_fuerza_militar` y `Jurisdiccion_policia` por segmento (tomadas desde el municipio destino).
- Scripts de soporte:
  - `scripts/demo_week_summary.py` (genera 5 outputs demo y un `summary_json_*.json`).
  - `scripts/run_full_flow.py` (plantilla→`ruta.csv`→evaluaciones→resúmenes `json|db`).

### Changed
- `POST /evaluate_day`: consolidado a una sola implementación en `src/risk_api.py` (se elimina duplicado).
- `GET /summary/week`: agrega a nivel top‑level por `record` las claves `Jurisdiccion_fuerza_militar` y `Jurisdiccion_policia` (agregadas desde `cities`).

### Fixed
- `load_activos_entries`: detección de delimitador robusta (evita uso de `reader.dialect` sobre una instancia inválida).

### Database
- Nueva columna `planned_date` en `evaluations` (se guarda desde `/evaluate_day`).
  - Inicialización intenta añadirla de forma best‑effort; en SQLite se omite `IF NOT EXISTS` (se registra warning si no aplica) sin bloquear el arranque.

---

## [Unreleased]
- Integración con Microsoft Teams (bot interactivo con Adaptive Card).
- Llamadas del bot al endpoint `/evaluate` de `risk_api.py`.
- Persistencia extendida (viajeros, vehículo, placa).
- Generación y entrega de reportes PDF.

---

## [0.2.0] - 2025-09-13
### Added
- Bot minimo de Microsoft Teams (aiohttp) en `bots/teams_bot`:
  - Endpoint `POST /api/messages` (adapter `BotFrameworkHttpAdapter`).
  - Endpoint `GET /health` para verificacion rapida.
  - Comando simple de prueba: "ping" -> "pong".
- Configuracion de VS Code para desarrollo:
  - `.vscode/launch.json`: ejecutar FastAPI (dev/prod-like), Pytest y el bot.
  - `.vscode/tasks.json`: tarea para correr tests.
  - `.vscode/settings.json`: interprete `venv311`, pytest habilitado.
- Modo desarrollo con SQLite:
  - Soporte via `aiosqlite` y `DATABASE_URL=sqlite+aiosqlite:///./riskdb.sqlite3`.

### Changed
- Dependencias de testing alineadas:
  - `pytest` -> 8.2.0 y `pytest-asyncio` 0.23.6 en `requirements.txt` y `dev-requirements.txt`.
  - `tests/pytest.ini`: `asyncio_mode = auto`.
- `tests/test_api.py`:
  - Asegura import de `src/` en `sys.path`.
  - Reemplaza SQL crudo por `select(...)` de SQLAlchemy 2.x.

### Fixed
- Error en tests por `ModuleNotFoundError: src` y por esquema ausente al usar SQLite.
- Respuesta 400 del Emulator al publicar actividades:
  - Se cambia al adaptador `BotFrameworkHttpAdapter` y el handler devuelve 200 OK.

### Notes
- Bot Framework Emulator recomendado: 4.14.1 (legacy). La serie 4.15.x usa "Live Chat" y puede mostrar 400 en `directline/.../activities` en escenarios locales.
- Para desarrollo local no es necesario ngrok; para pruebas externas/Teams, configurarlo aparte.

---

## [0.1.0] - 2025-09-12
### Added
- `risk_api.py` con endpoint `/evaluate`:
  - Validación de ciudades contra `riesgos.csv`.
  - Clasificación de riesgo por ciudad y riesgo global.
  - Guardado de evaluaciones en PostgreSQL y respaldo JSON.
- `db_handler.py` para conexión asíncrona a PostgreSQL (SQLAlchemy + asyncpg).
- Estructura inicial de carpetas del repositorio (`src/`, `data/`, `tests/`, `docs/`).
- Archivos de configuración:
  - `requirements.txt`, `dev-requirements.txt`.
  - `Dockerfile`, `Dockerfile.dev`, `docker-compose.yml`.
  - `.env` para credenciales y configuración.
- Documentación:
  - `README.md` actualizado con features, arquitectura y uso.
  - `project_structure.md` documentando la organización del repositorio.
  - `roadmap.md` con fases y tareas del proyecto.
- Carpeta `bots/teams_bot` para el desarrollo del bot de MS Teams.
  - `requirements.txt` y `requirements-dev.txt` para dependencias.
  - `.env.example` con variables de entorno básicas.
  - Diagramas ASCII explicando variables de entorno y arquitectura con Docker Compose.

---

## Formato de versión
- **0.x.y**: Etapas iniciales, desarrollo rápido y cambios frecuentes.  
- **1.0.0**: Primera versión estable en producción.  


