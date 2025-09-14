# init_db.py — Script para inicializar la base de datos PostgreSQL
#
# Este script ejecuta la función init_db() definida en src/db_handler.py
# para crear las tablas necesarias en la base de datos (evaluations y city_results).
#
# Uso:
#   python init_db.py
#
# Requisitos:
# - PostgreSQL en ejecución (ej: contenedor Docker riskdb)
# - Variables de entorno configuradas (DATABASE_URL) o valores por defecto en db_handler.py
# - Entorno virtual activado (venv311)
#
# Resultado:
# - Tablas creadas si no existían previamente.
# - Mensaje de confirmación en consola.

import asyncio
from src.db_handler import init_db

if __name__ == "__main__":
    try:
        asyncio.run(init_db())
        print("Tablas creadas correctamente en la base de datos.")
    except Exception as e:
        print("Error al crear tablas:", e)
