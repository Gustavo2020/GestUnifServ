\# Roadmap — GestUnifServ



Este documento describe las fases, módulos y tareas necesarias para completar el proyecto.  

Se actualiza conforme avanza el desarrollo.  



---



\## Fase 1 — Infraestructura básica

\- \[x] `risk\_api.py`  

&nbsp; - FastAPI con endpoint `/evaluate`.  

&nbsp; - Valida ciudades contra `riesgos.csv`.  

&nbsp; - Clasifica riesgo y guarda resultados.  



\- \[x] `db\_handler.py`  

&nbsp; - Conexión asíncrona a PostgreSQL (SQLAlchemy + asyncpg).  

&nbsp; - Guardado de evaluaciones en BD y respaldo en JSON.  

&nbsp; - Tablas `evaluations` y `city\_results`.  



\- \[x] Configuración inicial del repositorio  

&nbsp; - Estructura de carpetas definida.  

&nbsp; - `requirements.txt` y `dev-requirements.txt`.  

&nbsp; - `Dockerfile`, `Dockerfile.dev` y `docker-compose.yml`.  

&nbsp; - `.env` para credenciales y configuración.  



---



\## Fase 2 — Integraciones iniciales

\- \[ ] Módulo de autenticación MS Teams  

&nbsp; - Validar usuario contra Active Directory corporativo.  

&nbsp; - Asociar `user\_id` con solicitudes de evaluación.  



\- \[ ] Extensión de modelo de datos  

&nbsp; - Campos adicionales:  

&nbsp;   - Viajeros adicionales.  

&nbsp;   - Tipo de vehículo.  

&nbsp;   - Placa.  



\- \[ ] Persistencia extendida en DB  

&nbsp; - Nuevas columnas en `evaluations`.  

&nbsp; - Nueva tabla `travelers` (N:N con `evaluations`).  



---



\## Fase 3 — Enriquecimiento de información

\- \[ ] News fetcher (`news\_fetcher.py`)  

&nbsp; - Consultar noticias en fuentes públicas (ej: RSS, APIs de periódicos).  

&nbsp; - Extraer por palabras clave (ej: nombre de ciudades, “seguridad”, “bloqueos”).  

&nbsp; - Asociar noticias relevantes a una evaluación.  



\- \[ ] Módulo de analista \*(interfaz pendiente)\*  

&nbsp; - Backend para recibir evaluación, adjuntar recomendaciones.  

&nbsp; - Flujo de validación manual.  



---



\## Fase 4 — Reportería

\- \[ ] PDF Generator (`pdf\_generator.py`)  

&nbsp; - Generar informe PDF con:  

&nbsp;   - Datos de ruta y ciudades.  

&nbsp;   - Riesgo por ciudad.  

&nbsp;   - Riesgo global.  

&nbsp;   - Noticias relevantes.  

&nbsp;   - Recomendaciones del analista.  



\- \[ ] Entrega automática al usuario  

&nbsp; - Enviar por MS Teams (bot/connector).  

&nbsp; - Enviar por email como fallback.  



---



\## Fase 5 — Producción y Escalabilidad

\- \[ ] Migrar JSON backups a almacenamiento externo (ej: S3).  

\- \[ ] Monitoreo y logs centralizados (ej: ELK, Grafana + Prometheus).  

\- \[ ] Tests de carga para múltiples solicitudes simultáneas.  



---



Cada fase puede dividirse en \*issues\* dentro de GitHub para mejor trazabilidad.  



- [ ] Integración opcional con SIV (INVÍAS) para capas de accidentalidad (20-21) y estado vial (22-28).
