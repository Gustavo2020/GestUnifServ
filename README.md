\# GestUnifServ



\*\*Gestor Unificado de Servicios\*\* para servicios administrativos del Grupo Energía Bogotá y sus filiales.



El Gestor contará de varios módulos del cual vamos a realizar el primero que consiste en: 



Evaluación de rutas terrestres en Colombia.  



Este sistema permite a empleados registrar desplazamientos, calcular el riesgo asociado a la ruta, consultar noticias relevantes, y generar reportes automatizados en PDF.



\## Funcionalidades

\- Registro de rutas vía bot en MS Teams

\- Evaluación automática del riesgo por ciudad

\- Revisión manual por analista

\- Consulta de noticias relevantes en la web

\- Generación de PDF y envío por correo



\## Tecnologías

\- Python, FastAPI, PostgreSQL

\- Azure Bot Framework (MS Teams)

\- Scrapy, spaCy, ReportLab



\## Estructura del Proyecto



GestUnifServ/

├── src/              # Código fuente principal (API, lógica de negocio, scraping)

├── data/             # Archivos estáticos (CSV, mapas de riesgo, datos de prueba)

├── notebooks/        # Prototipos y análisis exploratorios en Jupyter

├── tests/            # Pruebas unitarias y de integración

├── docs/             # Diagramas, documentación técnica y flujos del bot

├── README.md         # Documentación principal del proyecto

├── .gitignore        # Exclusiones para Git

└── requirements.txt  # Dependencias del entorno Python

