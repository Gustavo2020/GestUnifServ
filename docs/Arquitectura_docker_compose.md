# Arquitectura en Docker Compose: Bot + API + DB

┌───────────────────┐
│ Usuario en Teams  │
│  o Emulator       │
└─────────┬─────────┘
          │ Mensaje (HTTP POST /api/messages)
          ▼
┌───────────────────────────────┐
│  Contenedor: teams_bot        │
│  Puerto expuesto: 3978        │
│                               │
│  Variables:                   │
│   - MicrosoftAppId            │
│   - MicrosoftAppPassword      │
│   - RISK_API_BASE_URL=http://risk_api:8000
│   - ROUTE_CSV_PATH=/app/data/ruta.csv
│                               │
│  Acción:                      │
│   - Recibe mensaje             │
│   - Escribe línea en ruta.csv │
│   - POST → risk_api:/evaluate │
└─────────┬─────────────────────┘
          │
          ▼
┌───────────────────────────────┐
│  Contenedor: risk_api         │
│  Puerto expuesto: 8000        │
│                               │
│  Función:                     │
│   - Lee riesgos.csv           │
│   - Valida y calcula riesgo   │
│   - Persiste en DB            │
│   - Escribe respaldo JSON     │
└─────────┬─────────────────────┘
          │
          ▼
┌───────────────────────────────┐
│  Contenedor: riskdb           │
│  Puerto expuesto: 5432        │
│                               │
│  Base de datos PostgreSQL     │
│   - Tablas: routes, cities,   │
│     evaluations, news         │
└─────────┬─────────────────────┘
          │
          ▼
┌───────────────────────────────┐
│  Volumen compartido: ./data   │
│                               │
│  Archivos:                    │
│   - riesgos.csv (input oficial)
│   - ruta.csv (salida de bot)  │
│   - output_*.json (respaldo)  │
└───────────────────────────────┘
```

---

### Puntos clave
- **teams_bot** y **risk_api** comparten el volumen `./data` → ambos leen/escriben los mismos CSV.  
- **risk_api** persiste resultados en **riskdb (PostgreSQL)**.  
- **Usuario** interactúa con el bot en Teams (o Emulator).  
- Toda la comunicación entre contenedores usa los nombres de servicio (`http://risk_api:8000`, `riskdb:5432`).  
