# Flujo de variables de entorno en el bot de Teams

┌───────────────────┐
│ Usuario en Teams  │
│  o Emulator       │
└─────────┬─────────┘
          │ Mensaje /evaluar
          ▼
┌──────────────────────────────┐
│  Bot (app.py + bot.py)       │
│  Puerto: PORT=3978           │
│  AppId: MicrosoftAppId       │
│  Secret: MicrosoftAppPassword│
└─────────┬────────────────────┘
          │ Llama a risk_api
          │ Base URL:
          │   RISK_API_BASE_URL
          ▼
┌──────────────────────────────┐
│  risk_api.py (FastAPI)       │
│  Endpoint: /evaluate         │
│  Usa CSV oficial: riesgos.csv│
│  Guarda en DB (PostgreSQL)   │
└─────────┬────────────────────┘
          │ Escribe respaldo
          │ en ruta.csv
          │ (ruta definida en
          │ ROUTE_CSV_PATH)
          ▼
┌──────────────────────────────┐
│   data/                      │
│   ├── riesgos.csv (input)    │
│   └── ruta.csv (output)      │
└──────────────────────────────┘
```

---

### Relación directa:
- **MicrosoftAppId / MicrosoftAppPassword** → Identidad del bot frente a Teams (solo necesarias en Teams, no en Emulator).  
- **PORT=3978** → Dónde escucha el bot localmente (requerido por Emulator).  
- **RISK_API_BASE_URL** → URL para llamar al endpoint `/evaluate` de `risk_api.py`.  
- **ROUTE_CSV_PATH** → Ruta donde se escribe cada solicitud antes/después de invocar la API.  

