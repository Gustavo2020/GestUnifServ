# Estructura del Proyecto GestUnifServ

```
GestUnifServ/
├── src/
│   ├── risk_api.py          # FastAPI: evaluación, sugerencias, plantillas, resumen semanal
│   ├── db_handler.py        # Conexión a BD (SQLAlchemy async), JSON backups
│   ├── evaluate_risk.py     # Lógica auxiliar de evaluación de riesgo
│   ├── log_config.py        # Configuración de logging centralizado (formato JSON)
│   ├── risk_api_view.py     # Variante/experimentos de vistas (no principal)
│   └── __init__.py          # Marca la carpeta como paquete Python importable
│
├── bots/
│   └── teams_bot/           # Bot de Microsoft Teams → interactúa con risk_api
│       ├── app.py           # Servidor aiohttp que expone /api/messages
│       ├── bot.py           # Lógica del bot (mensajes, etc.)
│       ├── requirements.txt # Dependencias del bot (SDK Bot Framework, aiohttp)
│       ├── requirements-dev.txt
│       └── pytest.ini       # Configuración de pruebas (bot)
│
├── scripts/                 # Utilidades para demo y pruebas de flujo
│   ├── demo_week_summary.py # Genera 5 outputs demo y escribe summary_json_*.json
│   └── run_full_flow.py     # Plantilla → data/ruta.csv → evals → summaries json|db
│
├── data/                    # Datos y artefactos de ejecución (volumen compartido)
│   ├── riesgos.csv          # Mapa oficial de riesgo (puntajes por ciudad)
│   ├── ruta.csv             # Entradas de rutas; incluye Jurisdiccion_* por segmento
│   ├── drivers.csv          # Catálogo de conductores (si se usa `/drivers`)
│   ├── activos.csv          # Catálogo de activos/instalaciones (opcional)
│   ├── audit_log.csv        # Auditoría (timestamp;action;user_id;result;json_id;request_id)
│   ├── output_*.json        # Respaldos JSON de evaluaciones (por ruta_id)
│   ├── summary_json_*.json  # Resúmenes semanales (fuente json)
│   ├── summary_db_*.json    # Resúmenes semanales (fuente DB)
│   └── templates/           # Plantillas personales (JSON) para semanas
│
├── notebooks/               # Notebooks Jupyter para exploración y prototipado
├── tests/                   # Pruebas unitarias de los módulos en src y de la API
├── docs/                    # Documentación del proyecto
│   ├── project_structure.md # Este archivo (estructura actualizada del proyecto)
│   ├── Arquitectura_docker_compose.md
│   ├── changelog.md
│   └── roadmap.md           # Plan de desarrollo y módulos futuros
│
├── requirements.txt         # Dependencias mínimas para ejecución en producción
├── dev-requirements.txt     # Dependencias adicionales para desarrollo y pruebas
├── Dockerfile               # Imagen de producción (FastAPI + Uvicorn)
├── Dockerfile.dev           # Imagen de desarrollo (incluye testing y Jupyter)
├── docker-compose.yml       # Orquestación de contenedores: API + PostgreSQL
├── docker-compose.override.yml # Configuración adicional para entorno local
├── .env                     # Variables de entorno (DB, paths, flags)
├── .dockerignore            # Exclusiones de build docker
├── .gitignore               # Exclusiones de git
├── init_db.py               # Inicialización de tablas (utilitario)
├── test_imports.py          # Verificación de imports del entorno
├── README.md                # Descripción general del proyecto e instrucciones de uso
└── project_structure.md     # Referencia de estructura actualizada (este archivo)
```

---

## Notas

- El bot (bots/teams_bot) se conecta con `risk_api.py` y comparte el volumen `data/`.  
- Endpoints principales: `/evaluate`, `/evaluate_day`, `/templates/*`, `/summary/week`, `/suggest/*`, `/drivers` (opcional).  
- Variables de entorno relevantes:
  - `RISK_CSV_PATH` (riesgos.csv), `DRIVERS_CSV_PATH` (drivers.csv), `ENABLE_DRIVERS_WRITE` (habilita POST/PUT /drivers), `DATABASE_URL` (PostgreSQL/SQLite).  

---

## Resumen de Endpoints Clave

- POST `/evaluate`:
  - Body: `{ user_id, platform, cities: [{ name }] }`
  - Devuelve: riesgo por ciudad, promedio, `ruta_id`, respaldo JSON y guardado en DB.

- POST `/evaluate_day`:
  - Body: `{ date, user: { user_id, ... }, segments: [ { segment_index, origin_municipio, dest_municipio, companions_count, companions_json, activity_type, vehicle_type, vehicle_plate, driver_* , notes } ] }`
  - Devuelve: ciudades (con jurisdicciones), resumen, `ruta_id`; guarda en DB y JSON; setea `planned_date`.

- GET `/summary/week`:
  - Query: `user_id` (opcional), `week_start=YYYY-MM-DD`, `source=json|db`
  - Devuelve: agregados de semana (`days`) y `records` completos por desplazamiento; incluye `Jurisdiccion_*` a nivel top‑level.

- POST `/templates`:
  - Body: `{ user_id, name, days: [{ day_of_week: Lun..Dom, segments: [...] }] }`
  - Crea plantilla personal (JSON en `data/templates/`).

- POST `/templates/{template_id}/apply`:
  - Body: `{ week_start, user: { user_id, ... }, evaluate: bool }`
  - Escribe/actualiza `data/ruta.csv` (incluye `Jurisdiccion_*` por segmento). Si `evaluate=true`, evalúa los días.

- GET `/suggest/municipios`:
  - Query: `q`, `departamento`, `pais`, `limit`
  - Fuente: `riesgos.csv`.

- GET `/suggest/activos`:
  - Query: `q`, `filial`, `limit`
  - Fuente: `data/activos.csv`.

- GET `/suggest/drivers`:
  - Query: `q`, `limit`
  - Fuente: `data/drivers.csv`.

- POST `/drivers` (opcional):
  - Requiere `ENABLE_DRIVERS_WRITE=true`.
  - Body: `{ national_id, first_name?, last_name?, phone? }`
  - Crea en `DRIVERS_CSV_PATH` y actualiza caché.

- PUT `/drivers` (opcional):
  - Requiere `ENABLE_DRIVERS_WRITE=true`.
  - Body: `{ national_id, first_name?, last_name?, phone? }`
  - Actualiza por `national_id` (normalizado dígitos) y persiste CSV + caché.
