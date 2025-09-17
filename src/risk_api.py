# ─────────────────────────────────────────────────────────────
# risk_api.py — REST API for Risk Evaluation
#
# Objetivo:
# - Exponer un endpoint POST /evaluate que:
#     1) Valida ciudades contra un mapa oficial de riesgos (CSV).
#     2) Calcula riesgo por ciudad y riesgo general de la ruta.
#     3) Persiste la evaluación en PostgreSQL y genera un respaldo JSON.
# - Preparado para producción:
#     - Manejo de ciclo de vida (lifespan) en FastAPI.
#     - Logging estructurado (a través de src/log_config.setup_logging()).
#     - Middleware que añade un request_id por solicitud para trazabilidad.
#
# Notas sobre el CSV de riesgos:
# - Se carga una sola vez al iniciar la aplicación para eficiencia.
# - El puntaje oficial del CSV SIEMPRE prevalece sobre cualquier valor del cliente.
#
# Nota sobre RISK_CSV_PATH:
# - Ejecución local sin cambios: usará "data/riesgos.csv".
# - En producción, definir la variable de entorno y se usará automáticamente:
#       export RISK_CSV_PATH=/etc/app/config/riesgos.csv
# ─────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from enum import Enum
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import asynccontextmanager
import uuid
import asyncio
import os
import csv
import logging
import json

# ─────────────────────────────────────────────────────────────
# Módulos internos del proyecto
# - db_handler: persistencia en PostgreSQL + respaldo JSON
# - log_config: configuración global de logging (formato JSON por stdout)
# ─────────────────────────────────────────────────────────────
from src.db_handler import save_evaluation_to_db_and_json, init_db, AsyncSessionLocal, Evaluation, CityResult
from sqlalchemy import select
from src.log_config import setup_logging

# Compat loader that supports both legacy and new CSV headers
def load_city_risk_map_compat(filepath: str) -> Dict[str, float]:
    city_risks: Dict[str, float] = {}
    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = [h.strip() for h in (reader.fieldnames or [])]
            col_city = None
            col_risk = None
            for h in headers:
                h_low = h.lower()
                if h_low in ("municipio", "ciudad"):
                    col_city = h
                if h_low in ("riesgo", "risk"):
                    col_risk = h

            for row in reader:
                try:
                    city = (row.get(col_city) or "").strip()
                    score_str = (row.get(col_risk) or "").strip()
                    if not city or not score_str:
                        raise ValueError("missing values")
                    score = float(score_str)
                    city_risks[city] = score
                except (KeyError, AttributeError, ValueError) as row_err:
                    logger.warning(
                        "Fila inválida en CSV de riesgos; fila ignorada | detalle=%s | fila=%s",
                        row_err,
                        row,
                    )
                    continue
    except FileNotFoundError as fnf:
        logger.error(
            "No se encontró el archivo de riesgos en la ruta indicada | path=%s",
            filepath,
            exc_info=True,
        )
        raise RuntimeError(f"Failed to load risk map (file not found): {fnf}") from fnf
    except Exception as e:
        logger.error("Error cargando el mapa de riesgos | path=%s", filepath, exc_info=True)
        raise RuntimeError(f"Failed to load risk map: {e}") from e

    if not city_risks:
        logger.error(
            "El CSV de riesgos fue leído pero no contiene entradas válidas | path=%s",
            filepath,
        )
        raise RuntimeError("Risk map is empty or invalid.")

    logger.info(
        "Mapa de riesgos cargado correctamente | path=%s | ciudades=%d",
        filepath,
        len(city_risks),
    )
    return city_risks

# ─────────────────────────────────────────────────────────────
# Configuración global de logging
# - setup_logging() define formato JSON y nivel según LOG_LEVEL (.env)
# - logger para este módulo: "risk_api"
# ─────────────────────────────────────────────────────────────
setup_logging()
logger = logging.getLogger("risk_api")

# ─────────────────────────────────────────────────────────────
# Carga del mapa oficial de riesgos desde CSV
# - Se espera un archivo con columnas: Ciudad,Riesgo
# - Devuelve un diccionario { "Bogotá": 0.5, "Medellín": 0.3, ... }
# - Incluye robustez frente a filas inválidas (se ignoran con warning)
# ─────────────────────────────────────────────────────────────
def load_city_risk_map(filepath: str) -> Dict[str, float]:
    city_risks: Dict[str, float] = {}
    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    city = row["Ciudad"].strip()
                    score = float(row["Riesgo"])
                    city_risks[city] = score
                except (KeyError, AttributeError, ValueError) as row_err:
                    # Si la fila carece de columnas esperadas o el valor no es convertible a float,
                    # se ignora la fila pero se deja constancia en el log para auditoría.
                    logger.warning(
                        "Fila inválida en CSV de riesgos; fila ignorada | detalle=%s | fila=%s",
                        row_err,
                        row,
                    )
                    continue
    except FileNotFoundError as fnf:
        # Error crítico: no existe el archivo. Se propaga para detener el arranque.
        logger.error(
            "No se encontró el archivo de riesgos en la ruta indicada | path=%s",
            filepath,
            exc_info=True,
        )
        raise RuntimeError(f"Failed to load risk map (file not found): {fnf}") from fnf
    except Exception as e:
        # Cualquier otro error de E/S u otros se consideran críticos en el arranque.
        logger.error("Error cargando el mapa de riesgos | path=%s", filepath, exc_info=True)
        raise RuntimeError(f"Failed to load risk map: {e}") from e

    if not city_risks:
        # Si tras la lectura no hubo entradas válidas, es una situación anómala.
        logger.error(
            "El CSV de riesgos fue leído pero no contiene entradas válidas | path=%s",
            filepath,
        )
        raise RuntimeError("Risk map is empty or invalid.")

    logger.info(
        "Mapa de riesgos cargado correctamente | path=%s | ciudades=%d",
        filepath,
        len(city_risks),
    )
    return city_risks

# ─────────────────────────────────────────────────────────────
# Ruta del CSV configurable por entorno (RISK_CSV_PATH)
# - Local: "data/riesgos.csv"
# - Producción: export RISK_CSV_PATH=/etc/app/config/riesgos.csv
# ─────────────────────────────────────────────────────────────
RISK_CSV_PATH = os.getenv("RISK_CSV_PATH", "data/riesgos.csv")
CITY_RISK_MAP = load_city_risk_map_compat(RISK_CSV_PATH)

# Enriched loader: riesgo + jurisdicciones
def load_city_meta_map(filepath: str) -> Dict[str, Dict[str, object]]:
    meta: Dict[str, Dict[str, object]] = {}
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = [h.strip() for h in (reader.fieldnames or [])]
        col_city = None
        col_risk = None
        col_jfm = None
        col_jpol = None
        for h in headers:
            low = h.lower()
            if low in ("municipio", "ciudad"):
                col_city = h
            elif low in ("riesgo", "risk"):
                col_risk = h
            elif low == "jurisdiccion_fuerza_militar":
                col_jfm = h
            elif low == "jurisdiccion_policia":
                col_jpol = h
        for row in reader:
            city = (row.get(col_city) or "").strip() if col_city else ""
            rs = (row.get(col_risk) or "").strip() if col_risk else ""
            if not city or not rs:
                continue
            try:
                score = float(rs)
            except ValueError:
                continue
            meta[city] = {
                "risk": score,
                "Jurisdiccion_fuerza_militar": (row.get(col_jfm) or "").strip() if col_jfm else "",
                "Jurisdiccion_policia": (row.get(col_jpol) or "").strip() if col_jpol else "",
            }
    if not meta:
        raise RuntimeError("Risk meta map empty")
    return meta

CITY_META_MAP = load_city_meta_map(RISK_CSV_PATH)

# Build municipality entries (Departamento, Municipio, País) for suggestions
def load_municipality_entries(filepath: str) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = {k.lower(): k for k in (reader.fieldnames or [])}
        c_dep = cols.get("departamento")
        c_mun = cols.get("municipio") or cols.get("ciudad")
        c_pais = cols.get("país") or cols.get("pais")
        for row in reader:
            d = (row.get(c_dep) or "").strip() if c_dep else ""
            m = (row.get(c_mun) or "").strip() if c_mun else ""
            p = (row.get(c_pais) or "").strip() if c_pais else ""
            if d and m:
                entries.append({"departamento": d, "municipio": m, "pais": p})
    # de-duplicate
    seen = set()
    uniq: List[Dict[str, str]] = []
    for e in entries:
        key = (e["departamento"], e["municipio"], e.get("pais", ""))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    return uniq

MUNI_ENTRIES = load_municipality_entries(RISK_CSV_PATH)

def load_activos_entries(filepath: str) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    act_path = Path("data/activos.csv")
    if not act_path.exists():
        return entries
    with act_path.open("r", encoding="utf-8", newline="") as f:
        # Robust delimiter detection without relying on DictReader internals
        first = f.readline()
        delim = ';' if first.count(';') > first.count(',') else ','
        f.seek(0)
        reader = csv.DictReader(f, delimiter=delim)
        cols = {k.lower(): k for k in (reader.fieldnames or [])}
        c_name = cols.get("name")
        c_filial = cols.get("filial")
        c_dep = cols.get("departamento")
        c_mun = cols.get("municipio") or cols.get("ciudad")
        for row in reader:
            name = (row.get(c_name) or "").strip() if c_name else ""
            filial = (row.get(c_filial) or "").strip() if c_filial else ""
            d = (row.get(c_dep) or "").strip() if c_dep else ""
            m = (row.get(c_mun) or "").strip() if c_mun else ""
            if name:
                entries.append({
                    "name": name,
                    "filial": filial,
                    "departamento": d,
                    "municipio": m,
                })
    return entries

ACTIVOS_ENTRIES = load_activos_entries("data/activos.csv")

def load_drivers_entries(filepath: str) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    drv_path = Path(filepath)
    if not drv_path.exists():
        return entries
    with drv_path.open("r", encoding="utf-8", newline="") as f:
        # detect delimiter
        first = f.readline()
        delim = ';' if first.count(';') > first.count(',') else ','
        f.seek(0)
        reader = csv.DictReader(f, delimiter=delim)
        cols = {k.lower(): k for k in (reader.fieldnames or [])}
        c_id = cols.get("national_id") or cols.get("id_number") or cols.get("cedula")
        c_fn = cols.get("first_name") or cols.get("nombres")
        c_ln = cols.get("last_name") or cols.get("apellidos")
        c_ph = cols.get("phone") or cols.get("celular") or cols.get("telefono")
        for row in reader:
            nid = (row.get(c_id) or '').strip() if c_id else ''
            if not nid:
                continue
            entries.append({
                'national_id': nid,
                'first_name': (row.get(c_fn) or '').strip() if c_fn else '',
                'last_name': (row.get(c_ln) or '').strip() if c_ln else '',
                'phone': (row.get(c_ph) or '').strip() if c_ph else '',
            })
    return entries

DRIVERS_CSV_PATH = os.getenv("DRIVERS_CSV_PATH", "data/drivers.csv")
DRIVERS_ENTRIES = load_drivers_entries(DRIVERS_CSV_PATH)
ENABLE_DRIVERS_WRITE = os.getenv("ENABLE_DRIVERS_WRITE", "false").lower() in ("1", "true", "yes", "on")
_DRIVERS_LOCK: "asyncio.Lock" = asyncio.Lock()

def _save_drivers_entries(filepath: str, entries: List[Dict[str, str]]) -> None:
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    # try to preserve original delimiter if file exists
    delim = ","
    try:
        if path.exists() and path.stat().st_size > 0:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                first = f.readline()
            if first.count(";") > first.count(","):
                delim = ";"
    except Exception:
        # fallback to comma if any issue reading current file
        delim = ","

    fieldnames = ["national_id", "first_name", "last_name", "phone"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delim)
        w.writeheader()
        for e in entries:
            w.writerow({
                "national_id": (e.get("national_id") or "").strip(),
                "first_name": (e.get("first_name") or "").strip(),
                "last_name": (e.get("last_name") or "").strip(),
                "phone": (e.get("phone") or "").strip(),
            })

# ===== Auditoría: resumen ligero en archivo (no prioritario) =====
AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "data/audit_log.csv")
_AUDIT_LOCK: "asyncio.Lock" = asyncio.Lock()

async def append_audit_entry(action: str, user_id: str, result: str, json_id: str = "", request_id: Optional[str] = None) -> None:
    try:
        path = Path(AUDIT_LOG_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with _AUDIT_LOCK:
            first_write = (not path.exists()) or (path.stat().st_size == 0)
            with path.open("a", encoding="utf-8", newline="") as f:
                w = csv.writer(f, delimiter=';')
                if first_write:
                    w.writerow(["timestamp", "action", "user_id", "result", "json_id", "request_id"])
                w.writerow([
                    datetime.now().isoformat(),
                    action,
                    (user_id or "").strip(),
                    (result or "").strip(),
                    (json_id or "").strip(),
                    (request_id or "").strip(),
                ])
    except Exception:
        # Nunca interferir con el flujo principal por auditoría
        logger.error("No se pudo escribir en el audit log", exc_info=True)

def _slug(s: str) -> str:
    import unicodedata
    s = (s or "").strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch == ' ':
            out.append(ch)
        else:
            out.append(' ')
    return ' '.join(''.join(out).split())

def _digits(s: str) -> str:
    return ''.join(ch for ch in (s or '') if ch.isdigit())

# ─────────────────────────────────────────────────────────────
# Esquemas de entrada/salida (Pydantic)
# - CityRisk.risk_score es opcional para tolerar payloads incompletos.
#   De todos modos, el servicio utilizará SIEMPRE el valor oficial del CSV.
# ─────────────────────────────────────────────────────────────
class CityRisk(BaseModel):
    name: str
    risk_score: Optional[float] = None  # Ignorado. Se usa puntaje oficial del CSV.

class EvaluationRequest(BaseModel):
    user_id: str
    platform: str
    cities: List[CityRisk]

class CityResult(BaseModel):
    name: str
    risk_score: float
    risk_level: str

class CityResultExt(CityResult):
    Jurisdiccion_fuerza_militar: str = ""
    Jurisdiccion_policia: str = ""

class EvaluationResponse(BaseModel):
    timestamp: str
    ruta_id: str
    executed_by: Dict[str, str]
    evaluated_by: str
    cities: List[CityResult]
    summary: Dict[str, float]
    overall_level: str
    status: str

# V2 models (evaluate_day)
class DestTipo(str, Enum):
    municipio = "municipio"
    activo = "activo"

class ActivityType(str, Enum):
    visita_mantenimiento = "Visita de Mantenimiento"
    visita_inspeccion = "Visita de Inspección"
    gestion_social = "Gestión Social"
    emergencia = "Emergencia"

class VehicleType(str, Enum):
    camioneta_platon = "Camioneta con platón"
    suv = "SUV"
    automovil = "Automóvil"
    bus = "Bus"
    minivan = "Minivan"

class Companion(BaseModel):
    id_number: str
    first_name: str
    last_name: str

class ItinerarySegment(BaseModel):
    segment_index: int
    origin_departamento: str
    origin_municipio: str
    dest_tipo: DestTipo
    dest_id: Optional[str] = None
    dest_departamento: str
    dest_municipio: str
    companions_count: int = 0
    companions_json: List[Companion] = Field(default_factory=list)
    activity_type: ActivityType
    vehicle_type: VehicleType
    vehicle_plate: str
    driver_national_id: str
    driver_first_name: Optional[str] = None
    driver_last_name: Optional[str] = None
    driver_phone: Optional[str] = None
    notes: Optional[str] = None

class UserInfo(BaseModel):
    user_id: str
    user_national_id: Optional[str] = None
    user_first_name: Optional[str] = None
    user_last_name: Optional[str] = None
    user_phone: Optional[str] = None
    filial: Optional[str] = None

class EvaluateDayRequest(BaseModel):
    date: str
    user: UserInfo
    segments: List[ItinerarySegment]

class EvaluateDayResponse(BaseModel):
    timestamp: str
    date: str
    ruta_id: str
    executed_by: Dict[str, str]
    evaluated_by: str
    user: UserInfo
    segments: List[ItinerarySegment]
    cities: List[CityResultExt]
    summary: Dict[str, float]
    overall_level: str
    status: str

# ─────────────────────────────────────────────────────────────
# Clasificación de riesgo
# - Tramos ajustables según política de negocio.
# ─────────────────────────────────────────────────────────────
def classify_risk(score: float) -> str:
    if score >= 0.7:
        return "High"
    elif score >= 0.4:
        return "Medium"
    else:
        return "Low"

def _cities_from_segments(segments: List[ItinerarySegment]) -> List[str]:
    ordered: List[str] = []
    seen = set()
    for seg in sorted(segments, key=lambda s: s.segment_index):
        for nm in (seg.origin_municipio, seg.dest_municipio):
            if nm and nm not in seen:
                ordered.append(nm)
                seen.add(nm)
    return ordered

# ─────────────────────────────────────────────────────────────
# Manejo del ciclo de vida (lifespan) — reemplaza @app.on_event("startup")
# - init_db(): crea tablas si no existen.
# - Se registran eventos de inicio y fin de la app.
# ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        logger.info("Base de datos inicializada correctamente.")
        yield
    except Exception:
        # Si algo falla en el arranque, se deja traza completa y se propaga.
        logger.error("Error durante la inicialización de la aplicación.", exc_info=True)
        raise
    finally:
        logger.info("Aplicación finalizada; liberación de recursos completada.")

# ─────────────────────────────────────────────────────────────
# Inicialización de la aplicación FastAPI
# ─────────────────────────────────────────────────────────────
app = FastAPI(lifespan=lifespan)

# ─────────────────────────────────────────────────────────────
# Middleware de trazabilidad
# - Añade un X-Request-ID a cada respuesta.
# - Loggea inicio y fin de cada request con ruta y método.
# - request.state.request_id queda disponible para otros componentes.
# ─────────────────────────────────────────────────────────────
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    logger.info(
        "Solicitud entrante | request_id=%s | method=%s | path=%s",
        request_id,
        request.method,
        request.url.path,
    )

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id

    logger.info(
        "Solicitud procesada | request_id=%s | method=%s | path=%s | status=%s",
        request_id,
        request.method,
        request.url.path,
        getattr(response, "status_code", "unknown"),
    )
    return response

# ─────────────────────────────────────────────────────────────
# Endpoint principal /evaluate
# - Validaciones:
#     * Lista de ciudades no vacía.
#     * Cada ciudad debe existir en el mapa oficial.
# - Cálculo:
#     * Suma y promedio del riesgo.
#     * Clasificación por ciudad y global.
# - Persistencia:
#     * Guardado en DB (SQLAlchemy/async) y respaldo JSON (db_handler).
# - Manejo de errores:
#     * 400: errores de entrada (ciudad inválida, lista vacía).
#     * 500: errores internos (persistencia u otros).
# ─────────────────────────────────────────────────────────────
@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_risk(request: EvaluationRequest, req: Request):
    # Log de alto nivel con datos críticos de la solicitud (sin PII sensible).
    logger.info(
        "Nueva solicitud /evaluate | user_id=%s | platform=%s | ciudades=%s",
        request.user_id,
        request.platform,
        [c.name for c in request.cities],
    )

    if not request.cities:
        logger.warning("Solicitud inválida: lista de ciudades vacía.")
        raise HTTPException(status_code=400, detail="City list is empty.")

    now = datetime.now()
    timestamp = now.isoformat()
    ruta_id = f"RUTA-{uuid.uuid4()}"

    city_results: List[Dict[str, str | float]] = []
    total_risk = 0.0

    for city in request.cities:
        city_name = city.name.strip()

        # Validación estricta: la ciudad debe existir en el CSV oficial.
        if city_name not in CITY_RISK_MAP:
            logger.error(
                "Ciudad no encontrada en el mapa oficial | ruta_id=%s | city=%s",
                ruta_id,
                city_name,
            )
            raise HTTPException(
                status_code=400,
                detail=f"City '{city_name}' not found in official risk map.",
            )

        # Se usa SIEMPRE el puntaje oficial del CSV.
        official_score = CITY_RISK_MAP[city_name]
        level = classify_risk(official_score)

        city_results.append(
            {
                "name": city_name,
                "risk_score": official_score,
                "risk_level": level,
            }
        )
        total_risk += official_score

        logger.debug(
            "Ciudad evaluada | ruta_id=%s | city=%s | score=%.2f | level=%s",
            ruta_id,
            city_name,
            official_score,
            level,
        )

    average_risk = total_risk / len(city_results)
    overall_level = classify_risk(average_risk)

    # Ensamblado de la respuesta
    output: Dict[str, object] = {
        "timestamp": timestamp,
        "ruta_id": ruta_id,
        "executed_by": {
            "user_id": request.user_id,
            "platform": request.platform,
        },
        "evaluated_by": "risk_api.py",
        "cities": city_results,
        "summary": {
            "total_risk": round(total_risk, 2),
            "average_risk": round(average_risk, 2),
        },
        "overall_level": overall_level,
        "status": "PendingValidation",
    }

    # Persistencia y respaldo con manejo de errores granular.
    try:
        await save_evaluation_to_db_and_json(output)
        try:
            await append_audit_entry(
                action="evaluate_day",
                user_id=request.user_id,
                result="OK",
                json_id=ruta_id,
                request_id=None,
            )
        except Exception:
            pass
        try:
            await append_audit_entry(
                action="evaluate",
                user_id=request.user_id,
                result="OK",
                json_id=ruta_id,
                request_id=getattr(getattr(req, 'state', None), 'request_id', None),
            )
        except Exception:
            pass
        logger.info(
            "Evaluación guardada correctamente | ruta_id=%s | overall_level=%s | total=%.2f | average=%.2f",
            ruta_id,
            overall_level,
            total_risk,
            average_risk,
        )
    except HTTPException as e:
        # Si alguna capa levantó HTTPException, se respeta su código.
        logger.error(
            "Error HTTP durante guardado | ruta_id=%s", ruta_id, exc_info=True
        )
        try:
            await append_audit_entry(
                action="evaluate",
                user_id=request.user_id,
                result=f"HTTP_{getattr(e, 'status_code', 'ERR')}",
                json_id=ruta_id,
                request_id=getattr(getattr(req, 'state', None), 'request_id', None),
            )
        except Exception:
            pass
        raise
    except Exception:
        # Errores inesperados en persistencia se devuelven como 500.
        logger.error(
            "Error interno al guardar evaluación | ruta_id=%s", ruta_id, exc_info=True
        )
        raise HTTPException(
            status_code=500, detail="Internal error while saving evaluation."
        )

    return output

# ─────────────────────────────────────────────────────────────
# Sugerencias para autocompletado
# ─────────────────────────────────────────────────────────────
@app.get("/suggest/municipios")
async def suggest_municipios(q: Optional[str] = None, departamento: Optional[str] = None, pais: Optional[str] = None, limit: int = 10):
    qslug = _slug(q or "")
    dslug = _slug(departamento or "")
    pslug = _slug(pais or "")
    results = []
    for e in MUNI_ENTRIES:
        if dslug and _slug(e.get("departamento", "")) != dslug:
            continue
        if pslug and _slug(e.get("pais", "")) != pslug:
            continue
        if qslug:
            # match on municipio or departamento
            if qslug not in _slug(e.get("municipio", "")) and qslug not in _slug(e.get("departamento", "")):
                continue
        title = f"{e.get('municipio')} — {e.get('departamento')}" + (f" ({e.get('pais')})" if e.get('pais') else "")
        value = f"{e.get('departamento')}|{e.get('municipio')}"
        results.append({
            "title": title,
            "value": value,
            "departamento": e.get('departamento'),
            "municipio": e.get('municipio'),
            "pais": e.get('pais') or "",
        })
        if len(results) >= limit:
            break
    return {"items": results}


@app.get("/suggest/activos")
async def suggest_activos(q: Optional[str] = None, filial: Optional[str] = None, limit: int = 10):
    qslug = _slug(q or "")
    fslug = _slug(filial or "")
    results = []
    for a in ACTIVOS_ENTRIES:
        if fslug and _slug(a.get("filial", "")) != fslug:
            continue
        if qslug:
            if qslug not in _slug(a.get("name", "")) and qslug not in _slug(a.get("municipio", "")) and qslug not in _slug(a.get("departamento", "")):
                continue
        title = f"{a.get('name')} — {a.get('municipio')}, {a.get('departamento')}" + (f" ({a.get('filial')})" if a.get('filial') else "")
        value = a.get('name')
        results.append({
            "title": title,
            "value": value,
            "name": a.get('name'),
            "filial": a.get('filial') or "",
            "departamento": a.get('departamento') or "",
            "municipio": a.get('municipio') or "",
        })
        if len(results) >= limit:
            break
    return {"items": results}


@app.get("/suggest/drivers")
async def suggest_drivers(q: Optional[str] = None, limit: int = 10):
    """
    Sugerir conductores por cédula o nombre.
    - q con dígitos: coincide en national_id por subcadena
    - q texto: coincide en first_name/last_name normalizados
    Devuelve items con title (para UI) y value = national_id, más campos para autocompletar.
    """
    q = (q or '').strip()
    qd = _digits(q)
    qs = _slug(q)
    results = []
    for d in DRIVERS_ENTRIES:
        nid = d.get('national_id', '')
        fn = d.get('first_name', '')
        ln = d.get('last_name', '')
        ph = d.get('phone', '')
        match = False
        if qd and qd in _digits(nid):
            match = True
        elif qs and (qs in _slug(fn) or qs in _slug(ln) or qs in _slug(f"{fn} {ln}")):
            match = True
        elif not qs and not qd:
            match = True  # no query → primeros N
        if not match:
            continue
        title = f"{nid} — {fn} {ln} ({ph})".strip()
        results.append({
            'title': title,
            'value': nid,
            'national_id': nid,
            'first_name': fn,
            'last_name': ln,
            'phone': ph,
        })
        if len(results) >= limit:
            break
    return { 'items': results }

# ===== Drivers catalog: optional POST/PUT endpoints =====
class DriverRecord(BaseModel):
    national_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


@app.post("/drivers", response_model=DriverRecord, status_code=201)
async def create_driver(driver: DriverRecord):
    if not ENABLE_DRIVERS_WRITE:
        raise HTTPException(status_code=403, detail="Drivers write API is disabled. Set ENABLE_DRIVERS_WRITE=true to enable.")

    nid_raw = (driver.national_id or "").strip()
    if not nid_raw:
        raise HTTPException(status_code=400, detail="national_id is required")

    nid_digits = _digits(nid_raw)
    async with _DRIVERS_LOCK:
        # check duplicates by digits to avoid format variants
        exists = any(_digits(d.get('national_id', '')) == nid_digits for d in DRIVERS_ENTRIES)
        if exists:
            raise HTTPException(status_code=409, detail="Driver already exists")

        record = {
            'national_id': nid_raw,
            'first_name': (driver.first_name or '').strip(),
            'last_name': (driver.last_name or '').strip(),
            'phone': (driver.phone or '').strip(),
        }
        DRIVERS_ENTRIES.append(record)
        try:
            _save_drivers_entries(DRIVERS_CSV_PATH, DRIVERS_ENTRIES)
            logger.info("Driver created | national_id=%s", nid_raw)
        except Exception:
            # rollback in-memory if disk write fails
            DRIVERS_ENTRIES.pop()
            logger.error("Failed saving drivers CSV after create | id=%s", nid_raw, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to persist driver")

        return DriverRecord(**record)


@app.put("/drivers", response_model=DriverRecord)
async def update_driver(driver: DriverRecord):
    if not ENABLE_DRIVERS_WRITE:
        raise HTTPException(status_code=403, detail="Drivers write API is disabled. Set ENABLE_DRIVERS_WRITE=true to enable.")

    nid_raw = (driver.national_id or "").strip()
    if not nid_raw:
        raise HTTPException(status_code=400, detail="national_id is required")

    nid_digits = _digits(nid_raw)
    async with _DRIVERS_LOCK:
        idx = -1
        for i, d in enumerate(DRIVERS_ENTRIES):
            if _digits(d.get('national_id', '')) == nid_digits:
                idx = i
                break
        if idx < 0:
            raise HTTPException(status_code=404, detail="Driver not found")

        # update fields; keep id as provided (allows formatting refresh)
        DRIVERS_ENTRIES[idx] = {
            'national_id': nid_raw,
            'first_name': (driver.first_name or '').strip(),
            'last_name': (driver.last_name or '').strip(),
            'phone': (driver.phone or '').strip(),
        }
        try:
            _save_drivers_entries(DRIVERS_CSV_PATH, DRIVERS_ENTRIES)
            logger.info("Driver updated | national_id=%s", nid_raw)
        except Exception:
            logger.error("Failed saving drivers CSV after update | id=%s", nid_raw, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to persist driver")

        return DriverRecord(**DRIVERS_ENTRIES[idx])

# ======== V2: evaluar día con segmentos y devolver datos completos ========
class EvaluateDayRequest(BaseModel):
    date: str
    user: 'UserInfo'
    segments: List['ItinerarySegment']

class UserInfo(BaseModel):
    user_id: str
    user_national_id: Optional[str] = None
    user_first_name: Optional[str] = None
    user_last_name: Optional[str] = None
    user_phone: Optional[str] = None
    filial: Optional[str] = None

class EvaluateDayResponse(BaseModel):
    timestamp: str
    date: str
    ruta_id: str
    executed_by: Dict[str, str]
    evaluated_by: str
    user: UserInfo
    segments: List['ItinerarySegment']
    cities: List[CityResultExt]
    summary: Dict[str, float]
    overall_level: str
    status: str

class ItinerarySegment(BaseModel):
    segment_index: int
    origin_departamento: str
    origin_municipio: str
    dest_tipo: str
    dest_id: Optional[str] = None
    dest_departamento: str
    dest_municipio: str
    companions_count: int = 0
    companions_json: List[Dict[str, str]] = Field(default_factory=list)
    activity_type: str
    vehicle_type: str
    vehicle_plate: str
    driver_national_id: str
    driver_first_name: Optional[str] = None
    driver_last_name: Optional[str] = None
    driver_phone: Optional[str] = None
    notes: Optional[str] = None

def _cities_from_segments(segments: List[ItinerarySegment]) -> List[str]:
    ordered: List[str] = []
    seen = set()
    for seg in sorted(segments, key=lambda s: s.segment_index):
        for nm in (seg.origin_municipio, seg.dest_municipio):
            if nm and nm not in seen:
                ordered.append(nm)
                seen.add(nm)
    return ordered

# ===== Templates (personal routes) minimal CRUD + apply-to-week =====
TEMPLATES_DIR = Path("data/templates")
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

class TemplateDay(BaseModel):
    day_of_week: str  # Mon..Sun or Lun..Dom
    segments: List[ItinerarySegment]

class TemplateCreate(BaseModel):
    user_id: str
    name: str
    description: Optional[str] = None
    days: List[TemplateDay]

class TemplateMeta(BaseModel):
    template_id: str
    user_id: str
    name: str
    description: Optional[str] = None
    days_count: int
    created_at: str

def _weekday_index(dw: str) -> int:
    mapping = {
        'Mon': 0, 'Tue': 1, 'Wed': 2, 'Thu': 3, 'Fri': 4, 'Sat': 5, 'Sun': 6,
        'Lun': 0, 'Mar': 1, 'Mie': 2, 'Mié': 2, 'Jue': 3, 'Vie': 4, 'Sab': 5, 'Sáb': 5, 'Dom': 6,
    }
    key = (dw or '').strip()
    if key not in mapping:
        raise ValueError(f"Invalid day_of_week: {dw}")
    return mapping[key]

def _template_path(tid: str) -> Path:
    return TEMPLATES_DIR / f"{tid}.json"

@app.post("/templates", response_model=TemplateMeta)
async def create_template(tpl: TemplateCreate):
    # basic validation of cities present in risk map
    for day in tpl.days:
        for seg in day.segments:
            for nm in (seg.origin_municipio, seg.dest_municipio):
                if nm not in CITY_RISK_MAP:
                    raise HTTPException(status_code=400, detail=f"City '{nm}' not found in official risk map.")

    tid = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    data = {
        "template_id": tid,
        "user_id": tpl.user_id,
        "name": tpl.name,
        "description": tpl.description,
        "days": [d.model_dump() for d in tpl.days],
        "created_at": created_at,
    }
    _template_path(tid).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return TemplateMeta(template_id=tid, user_id=tpl.user_id, name=tpl.name, description=tpl.description, days_count=len(tpl.days), created_at=created_at)

@app.get("/templates", response_model=List[TemplateMeta])
async def list_templates(user_id: Optional[str] = None):
    metas: List[TemplateMeta] = []
    for fp in TEMPLATES_DIR.glob("*.json"):
        try:
            obj = json.loads(fp.read_text(encoding="utf-8"))
            if user_id and obj.get("user_id") != user_id:
                continue
            metas.append(TemplateMeta(
                template_id=obj.get("template_id"),
                user_id=obj.get("user_id"),
                name=obj.get("name"),
                description=obj.get("description"),
                days_count=len(obj.get("days", [])),
                created_at=obj.get("created_at", ""),
            ))
        except Exception:
            continue
    return metas

@app.get("/templates/{template_id}")
async def get_template(template_id: str):
    fp = _template_path(template_id)
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    return json.loads(fp.read_text(encoding="utf-8"))

@app.delete("/templates/{template_id}")
async def delete_template(template_id: str, user_id: Optional[str] = None):
    fp = _template_path(template_id)
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    obj = json.loads(fp.read_text(encoding="utf-8"))
    if user_id and obj.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    fp.unlink(missing_ok=True)
    return {"deleted": True}

class ApplyTemplateRequest(BaseModel):
    week_start: str  # YYYY-MM-DD (Monday)
    user: UserInfo
    evaluate: Optional[bool] = False

ROUTE_CSV = Path("data/ruta.csv")
ROUTE_HEADER = [
    'date','user_id','user_national_id','user_first_name','user_last_name','user_phone','filial','segment_index',
    'origin_departamento','origin_municipio','dest_tipo','dest_id','dest_departamento','dest_municipio',
    'companions_count','companions_json','activity_type','vehicle_type','vehicle_plate','driver_national_id',
    'driver_first_name','driver_last_name','driver_phone','notes',
    'Jurisdiccion_fuerza_militar','Jurisdiccion_policia'
]

def _week_dates(week_start: str) -> List[str]:
    base = datetime.fromisoformat(week_start)
    return [(base + timedelta(days=i)).date().isoformat() for i in range(7)]

@app.post("/templates/{template_id}/apply")
async def apply_template(template_id: str, req: ApplyTemplateRequest):
    fp = _template_path(template_id)
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    obj = json.loads(fp.read_text(encoding="utf-8"))
    days = obj.get("days", [])
    dates = _week_dates(req.week_start)

    # Read existing and filter out current user's week
    existing: List[Dict[str, str]] = []
    if ROUTE_CSV.exists():
        with ROUTE_CSV.open('r', encoding='utf-8', errors='replace', newline='') as f:
            r = csv.DictReader(f, delimiter=';')
            for row in r:
                if row.get('user_id') == req.user.user_id and row.get('date') in dates:
                    continue
                existing.append(row)

    expanded: List[Dict[str, str]] = []
    for day in days:
        dw = day.get('day_of_week')
        try:
            idx = _weekday_index(dw)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        date = dates[idx]
        for seg in day.get('segments', []):
            for nm in (seg.get('origin_municipio'), seg.get('dest_municipio')):
                if nm not in CITY_RISK_MAP:
                    raise HTTPException(status_code=400, detail=f"City '{nm}' not found in official risk map.")
            # Jurisdicciones para el destino (si existe en meta)
            dest_city = seg.get('dest_municipio','')
            meta = CITY_META_MAP.get(dest_city, {})
            jfm = str(meta.get('Jurisdiccion_fuerza_militar',''))
            jpol = str(meta.get('Jurisdiccion_policia',''))
            row = {
                'date': date,
                'user_id': req.user.user_id,
                'user_national_id': req.user.user_national_id or '',
                'user_first_name': req.user.user_first_name or '',
                'user_last_name': req.user.user_last_name or '',
                'user_phone': req.user.user_phone or '',
                'filial': req.user.filial or '',
                'segment_index': str(seg.get('segment_index')),
                'origin_departamento': seg.get('origin_departamento',''),
                'origin_municipio': seg.get('origin_municipio',''),
                'dest_tipo': seg.get('dest_tipo','municipio'),
                'dest_id': seg.get('dest_id') or '',
                'dest_departamento': seg.get('dest_departamento',''),
                'dest_municipio': seg.get('dest_municipio',''),
                'companions_count': str(seg.get('companions_count', 0)),
                'companions_json': json.dumps(seg.get('companions_json', []), ensure_ascii=False),
                'activity_type': seg.get('activity_type','Visita de Mantenimiento'),
                'vehicle_type': seg.get('vehicle_type','SUV'),
                'vehicle_plate': seg.get('vehicle_plate',''),
                'driver_national_id': seg.get('driver_national_id',''),
                'driver_first_name': seg.get('driver_first_name','') or '',
                'driver_last_name': seg.get('driver_last_name','') or '',
                'driver_phone': seg.get('driver_phone','') or '',
                'notes': seg.get('notes','') or '',
                'Jurisdiccion_fuerza_militar': jfm,
                'Jurisdiccion_policia': jpol,
            }
            expanded.append(row)

    # Write combined file
    with ROUTE_CSV.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=ROUTE_HEADER, delimiter=';')
        w.writeheader()
        for r in existing + expanded:
            w.writerow(r)

    # Optional evaluation
    if req.evaluate:
        results = []
        grouped: Dict[str, List[Dict[str, str]]] = {}
        for r in expanded:
            grouped.setdefault(r['date'], []).append(r)
        for date, rows in grouped.items():
            segs = []
            for r in rows:
                comp = json.loads(r.get('companions_json') or '[]')
                segs.append(ItinerarySegment(
                    segment_index=int(r['segment_index']),
                    origin_departamento=r['origin_departamento'],
                    origin_municipio=r['origin_municipio'],
                    dest_tipo=r['dest_tipo'],
                    dest_id=r['dest_id'] or None,
                    dest_departamento=r['dest_departamento'],
                    dest_municipio=r['dest_municipio'],
                    companions_count=int(r['companions_count'] or 0),
                    companions_json=comp,  # type: ignore
                    activity_type=r['activity_type'],
                    vehicle_type=r['vehicle_type'],
                    vehicle_plate=r['vehicle_plate'],
                    driver_national_id=r['driver_national_id'],
                    driver_first_name=r.get('driver_first_name') or None,
                    driver_last_name=r.get('driver_last_name') or None,
                    driver_phone=r.get('driver_phone') or None,
                    notes=r.get('notes') or None,
                ))
            req_body = EvaluateDayRequest(date=date, user=req.user, segments=segs)
            await evaluate_day(req_body)
        return {"applied_rows": len(expanded), "evaluated_days": len(grouped)}

    return {"applied_rows": len(expanded)}

@app.post("/evaluate_day", response_model=EvaluateDayResponse)
async def evaluate_day(request: EvaluateDayRequest):
    logger.info(
        "Nueva solicitud /evaluate_day | user_id=%s | date=%s | segments=%d",
        request.user.user_id,
        request.date,
        len(request.segments),
    )
    if not request.segments:
        raise HTTPException(status_code=400, detail="No segments provided.")

    # Validate municipalities exist
    for seg in request.segments:
        for nm in (seg.origin_municipio, seg.dest_municipio):
            if nm not in CITY_META_MAP:
                raise HTTPException(status_code=400, detail=f"City '{nm}' not found in official risk map.")

    day_cities = _cities_from_segments(request.segments)

    city_results: List[CityResultExt] = []
    total = 0.0
    for cname in day_cities:
        meta = CITY_META_MAP.get(cname, {})
        score = float(meta.get("risk", 0.0))
        level = classify_risk(score)
        city_results.append(
            CityResultExt(
                name=cname,
                risk_score=score,
                risk_level=level,
                Jurisdiccion_fuerza_militar=str(meta.get("Jurisdiccion_fuerza_militar", "")),
                Jurisdiccion_policia=str(meta.get("Jurisdiccion_policia", "")),
            )
        )
        total += score

    avg = total / len(day_cities) if day_cities else 0.0
    overall = classify_risk(avg)

    timestamp = datetime.now().isoformat()
    ruta_id = f"RUTA-{uuid.uuid4()}"

    output: Dict[str, object] = {
        "timestamp": timestamp,
        "date": request.date,
        "ruta_id": ruta_id,
        "executed_by": {"user_id": request.user.user_id or "", "platform": "MS Teams"},
        "evaluated_by": "risk_api.py",
        "user": request.user.model_dump(),
        "segments": [s.model_dump() for s in sorted(request.segments, key=lambda x: x.segment_index)],
        "cities": [c.model_dump() for c in city_results],
        "summary": {"total_risk": round(total, 2), "average_risk": round(avg, 2)},
        "overall_level": overall,
        "status": "PendingValidation",
    }

    try:
        await save_evaluation_to_db_and_json(output)
    except Exception:
        logger.error("Error guardando evaluación día | ruta_id=%s", ruta_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error while saving evaluation.")

    return output

# ===== Weekly summary =====
class WeeklyDaySummary(BaseModel):
    date: str
    ruta_id: str
    overall_level: str
    average_risk: float
    cities_count: int
    status: str

class WeeklySummaryResponse(BaseModel):
    week_start: str
    week_end: str
    user_id: Optional[str] = None
    evaluations_count: int
    average_risk_week: float
    max_risk_week: float
    unique_cities: List[str]
    status_counts: Dict[str, int]
    days: List[WeeklyDaySummary]
    records: List[Dict[str, object]]

@app.get("/summary/week", response_model=WeeklySummaryResponse)
async def summary_week(user_id: Optional[str] = None, week_start: str = "", req: Request = None, source: str = "json"):
    try:
        dates = _week_dates(week_start)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid week_start (expected YYYY-MM-DD, Monday)")

    # DB-backed summary (uses Evaluation.timestamp as day proxy)
    if (source or "").lower() == "db":
        try:
            start_dt = datetime.fromisoformat(week_start)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid week_start (expected YYYY-MM-DD, Monday)")
        end_dt = start_dt + timedelta(days=7)
        async with AsyncSessionLocal() as session:
            q = select(Evaluation).where(
                Evaluation.timestamp >= start_dt,
                Evaluation.timestamp < end_dt,
            )
            if user_id:
                q = q.where(Evaluation.user_id == user_id)
            evs = (await session.execute(q)).scalars().all()

            if not evs:
                return WeeklySummaryResponse(
                    week_start=week_start,
                    week_end=(start_dt + timedelta(days=6)).date().isoformat(),
                    user_id=user_id,
                    evaluations_count=0,
                    average_risk_week=0.0,
                    max_risk_week=0.0,
                    unique_cities=[],
                    status_counts={},
                    days=[],
                    records=[],
                )

            ids = [e.id for e in evs]
            city_rows = (
                await session.execute(
                    select(CityResult.evaluation_id, CityResult.name).where(
                        CityResult.evaluation_id.in_(ids)
                    )
                )
            ).all()

            cities_by_eval: Dict[str, List[str]] = {}
            unique_cities_set = set()
            for eid, name in city_rows:
                if not name:
                    continue
                cities_by_eval.setdefault(eid, []).append(name)
                unique_cities_set.add(name)

            status_counts: Dict[str, int] = {}
            days_items: List[WeeklyDaySummary] = []
            for e in evs:
                st = e.status or ""
                status_counts[st] = status_counts.get(st, 0) + 1
                days_items.append(
                    WeeklyDaySummary(
                        date=e.timestamp.date().isoformat(),
                        ruta_id=e.id,
                        overall_level=e.overall_level,
                        average_risk=round(float(e.average_risk or 0.0), 2),
                        cities_count=len(cities_by_eval.get(e.id, [])),
                        status=st,
                    )
                )

            # Build full records using JSON backups when available, fallback to DB-only info
            records: List[Dict[str, object]] = []
            data_dir = Path("data")
            for e in evs:
                try:
                    date_iso = (e.planned_date.isoformat() if getattr(e, 'planned_date', None) else e.timestamp.date().isoformat())
                    fp = data_dir / f"output_{e.id}.json"
                    if fp.exists():
                        obj = json.loads(fp.read_text(encoding="utf-8"))
                        # Aggregate top-level jurisdictions from cities if present
                        try:
                            jfm_vals = []
                            jpol_vals = []
                            for c in obj.get("cities", []) or []:
                                if isinstance(c, dict):
                                    v1 = str(c.get("Jurisdiccion_fuerza_militar", "")).strip()
                                    v2 = str(c.get("Jurisdiccion_policia", "")).strip()
                                    if v1:
                                        jfm_vals.append(v1)
                                    if v2:
                                        jpol_vals.append(v2)
                            jfm_top = " | ".join(sorted({*jfm_vals}))
                            jpol_top = " | ".join(sorted({*jpol_vals}))
                        except Exception:
                            jfm_top = ""
                            jpol_top = ""
                        records.append({
                            "timestamp": obj.get("timestamp", e.timestamp.isoformat()),
                            "date": obj.get("date") or date_iso,
                            "ruta_id": e.id,
                            "executed_by": obj.get("executed_by", {"user_id": e.user_id, "platform": e.platform}),
                            "evaluated_by": obj.get("evaluated_by", "risk_api.py"),
                            "user": obj.get("user", {}),
                            "segments": obj.get("segments", []),
                            "cities": obj.get("cities", []),
                            "summary": obj.get("summary", {"total_risk": e.total_risk, "average_risk": e.average_risk}),
                            "overall_level": obj.get("overall_level", e.overall_level),
                            "status": obj.get("status", st),
                            "Jurisdiccion_fuerza_militar": jfm_top,
                            "Jurisdiccion_policia": jpol_top,
                        })
                    else:
                        # Build minimal record and aggregate jurisdictions from CITY_META_MAP
                        jfm_top = " | ".join(sorted({
                            str(CITY_META_MAP.get(n, {}).get("Jurisdiccion_fuerza_militar", "")).strip()
                            for n in cities_by_eval.get(e.id, []) if n
                        } - {""}))
                        jpol_top = " | ".join(sorted({
                            str(CITY_META_MAP.get(n, {}).get("Jurisdiccion_policia", "")).strip()
                            for n in cities_by_eval.get(e.id, []) if n
                        } - {""}))
                        records.append({
                            "timestamp": e.timestamp.isoformat(),
                            "date": date_iso,
                            "ruta_id": e.id,
                            "executed_by": {"user_id": e.user_id, "platform": e.platform},
                            "evaluated_by": "risk_api.py",
                            "user": {},
                            "segments": [],
                            "cities": [
                                {
                                    "name": n,
                                    "Jurisdiccion_fuerza_militar": str(CITY_META_MAP.get(n, {}).get("Jurisdiccion_fuerza_militar", "")),
                                    "Jurisdiccion_policia": str(CITY_META_MAP.get(n, {}).get("Jurisdiccion_policia", "")),
                                }
                                for n in cities_by_eval.get(e.id, [])
                            ],
                            "summary": {"total_risk": float(e.total_risk or 0.0), "average_risk": float(e.average_risk or 0.0)},
                            "overall_level": e.overall_level,
                            "status": st,
                            "Jurisdiccion_fuerza_militar": jfm_top,
                            "Jurisdiccion_policia": jpol_top,
                        })
                except Exception:
                    continue

            days_sorted = sorted(days_items, key=lambda d: d.date)
            cnt = len(days_sorted)
            avg_week = round(sum(d.average_risk for d in days_sorted) / cnt, 2) if cnt else 0.0
            max_week = round(max((d.average_risk for d in days_sorted), default=0.0), 2)

            resp = WeeklySummaryResponse(
                week_start=week_start,
                week_end=(start_dt + timedelta(days=6)).date().isoformat(),
                user_id=user_id,
                evaluations_count=cnt,
                average_risk_week=avg_week,
                max_risk_week=max_week,
                unique_cities=sorted(unique_cities_set),
                status_counts=status_counts,
                days=days_sorted,
                records=records,
            )

            try:
                await append_audit_entry(
                    action="summary_week",
                    user_id=user_id,
                    result="OK",
                    json_id="",
                    request_id=getattr(getattr(req, 'state', None), 'request_id', None),
                )
            except Exception:
                pass

            return resp

    data_dir = Path("data")
    if not data_dir.exists():
        return WeeklySummaryResponse(
            week_start=week_start,
            week_end=(datetime.fromisoformat(week_start) + timedelta(days=6)).date().isoformat(),
            user_id=user_id,
            evaluations_count=0,
            average_risk_week=0.0,
            max_risk_week=0.0,
            unique_cities=[],
            status_counts={},
            days=[],
            records=[],
        )

    days: List[WeeklyDaySummary] = []
    records: List[Dict[str, object]] = []
    unique_cities_set = set()
    status_counts: Dict[str, int] = {}
    for fp in data_dir.glob("output_*.json"):
        try:
            obj = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if user_id and obj.get("executed_by", {}).get("user_id") != user_id:
            continue
        date = obj.get("date")
        if not date or date not in dates:
            continue
        ruta_id = obj.get("ruta_id", "")
        overall = obj.get("overall_level", "")
        avg = float(obj.get("summary", {}).get("average_risk", 0.0))
        st = obj.get("status", "") or ""
        cities = obj.get("cities", [])
        for c in cities:
            name = (c.get("name") if isinstance(c, dict) else None) or ""
            if name:
                unique_cities_set.add(name)
        status_counts[st] = status_counts.get(st, 0) + 1
        days.append(WeeklyDaySummary(
            date=date,
            ruta_id=ruta_id,
            overall_level=overall,
            average_risk=round(avg, 2),
            cities_count=len(cities),
            status=st,
        ))
        # Full record for later evaluation pipelines
        try:
            # Keep only known fields to avoid excessive payload
            # Aggregate jurisdictions at top-level (unique, pipe-joined)
            try:
                jfm_vals = []
                jpol_vals = []
                for c in (cities or []):
                    if isinstance(c, dict):
                        v1 = str(c.get("Jurisdiccion_fuerza_militar", "")).strip()
                        v2 = str(c.get("Jurisdiccion_policia", "")).strip()
                        if v1:
                            jfm_vals.append(v1)
                        if v2:
                            jpol_vals.append(v2)
                jfm_top = " | ".join(sorted({*jfm_vals}))
                jpol_top = " | ".join(sorted({*jpol_vals}))
            except Exception:
                jfm_top = ""
                jpol_top = ""
            record = {
                "timestamp": obj.get("timestamp"),
                "date": obj.get("date"),
                "ruta_id": ruta_id,
                "executed_by": obj.get("executed_by", {}),
                "evaluated_by": obj.get("evaluated_by"),
                "user": obj.get("user", {}),
                "segments": obj.get("segments", []),
                "cities": cities,
                "summary": obj.get("summary", {}),
                "overall_level": overall,
                "status": st,
                "Jurisdiccion_fuerza_militar": jfm_top,
                "Jurisdiccion_policia": jpol_top,
            }
            records.append(record)
        except Exception:
            pass

    days_sorted = sorted(days, key=lambda d: d.date)
    cnt = len(days_sorted)
    avg_week = round(sum(d.average_risk for d in days_sorted) / cnt, 2) if cnt else 0.0
    max_week = round(max((d.average_risk for d in days_sorted), default=0.0), 2)

    resp = WeeklySummaryResponse(
        week_start=week_start,
        week_end=(datetime.fromisoformat(week_start) + timedelta(days=6)).date().isoformat(),
        user_id=user_id,
        evaluations_count=cnt,
        average_risk_week=avg_week,
        max_risk_week=max_week,
        unique_cities=sorted(unique_cities_set),
        status_counts=status_counts,
        days=days_sorted,
        records=records,
    )

    # Non-blocking audit (best-effort)
    try:
        await append_audit_entry(
            action="summary_week",
            user_id=user_id,
            result="OK",
            json_id="",
            request_id=getattr(getattr(req, 'state', None), 'request_id', None),
        )
    except Exception:
        pass

    return resp
