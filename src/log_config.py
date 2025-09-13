# ─────────────────────────────────────────────────────────────
# log_config.py — Configuración centralizada de logging
#
# - Usa logging estándar con salida JSON.
# - Nivel configurable vía variable de entorno LOG_LEVEL.
# - Se integra fácilmente con FastAPI y otros módulos.
# ─────────────────────────────────────────────────────────────

import logging
import json
import os
from datetime import datetime

class JsonFormatter(logging.Formatter):
    """
    Formatea logs como JSON para fácil ingestión en sistemas de monitoreo.
    """
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Si hay excepción, agregar traceback
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)

def setup_logging():
    """
    Configura logging global:
    - Nivel según LOG_LEVEL (default INFO).
    - Formato JSON en stdout.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = [handler]

    # Evitar logs duplicados de Uvicorn
    logging.getLogger("uvicorn").propagate = False
    logging.getLogger("uvicorn.error").propagate = False
    logging.getLogger("uvicorn.access").propagate = False
