# Changelog — GestUnifServ

Todos los cambios notables de este proyecto se documentarán en este archivo.  
El formato está basado en [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),  
y este proyecto sigue [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
