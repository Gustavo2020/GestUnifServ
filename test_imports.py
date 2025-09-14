# test_imports.py — Verifica que los módulos del proyecto cargan bien

try:
    # Importamos directamente desde el paquete src
    from src import risk_api
    from src import db_handler

    print("Importación exitosa: risk_api y db_handler están accesibles.")

    # Probamos que las funciones críticas existen
    assert hasattr(db_handler, "save_evaluation_to_db_and_json"), "Falta save_evaluation_to_db_and_json"
    assert hasattr(db_handler, "init_db"), "Falta init_db"
    assert hasattr(risk_api, "app"), "Falta app en risk_api (FastAPI app)"

    print("Todas las funciones y objetos clave están presentes.")

except Exception as e:
    print("Error al importar módulos:", e)
