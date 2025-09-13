# Paso 1 — Bot local “Hola Mundo” con Bot Framework Emulator

Objetivo: crear y ejecutar localmente un bot mínimo que responda mensajes, probado con Bot Framework Emulator, sin necesidad de registrarlo aún en Azure.

---

## 0) Requisitos previos

- Python 3.10+ instalado.
- Bot Framework Emulator instalado en tu máquina (Windows/Mac/Linux).
- Repositorio `GestUnifServ` clonado y abierto en tu editor (Visual Studio Code o similar).

---

## 1) Estructura propuesta para el bot local

Creamos una carpeta para el bot dentro del repo:

```
GestUnifServ/
├── bots/
│   └── teams_bot/
│       ├── app.py                 # Servidor aiohttp que expone /api/messages
│       ├── bot.py                 # Lógica del bot (ActivityHandler)
│       └── requirements.txt       # Dependencias del bot
└── ...
```

Puedes ajustar la ruta si prefieres otra organización. Este bot local es independiente de `risk_api.py`; por ahora solo responde mensajes.

---

## 2) requirements.txt

Archivo: `bots/teams_bot/requirements.txt`

```
botbuilder-core
botbuilder-schema
botbuilder-integration-aiohttp
```

---

## 3) Lógica del bot (eco de mensajes)

Archivo: `bots/teams_bot/bot.py`

```python
from botbuilder.core import ActivityHandler, TurnContext

class EchoBot(ActivityHandler):
    async def on_message_activity(self, turn_context: TurnContext):
        text = (turn_context.activity.text or "").strip()
        if not text:
            await turn_context.send_activity("No recibí texto.")
            return
        await turn_context.send_activity(f"Echo: {text}")

    async def on_members_added_activity(self, members_added, turn_context: TurnContext):
        await turn_context.send_activity(
            "Bot listo. Escribe cualquier mensaje y te responderé."
        )
```

---

## 4) Servidor aiohttp del bot

Archivo: `bots/teams_bot/app.py`

```python
import os
import logging
from aiohttp import web

from botbuilder.core import BotFrameworkAdapterSettings
from botbuilder.integration.aiohttp import BotFrameworkAdapter
from botbuilder.schema import Activity

from bot import EchoBot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("teams_bot_step1")

# Para pruebas locales con Emulator NO necesitas credenciales.
APP_ID = os.getenv("MicrosoftAppId", "")
APP_PASSWORD = os.getenv("MicrosoftAppPassword", "")

settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(settings)
bot = EchoBot()

async def messages(req: web.Request) -> web.Response:
    if "application/json" not in req.headers.get("Content-Type", ""):
        return web.Response(status=415, text="Content-Type debe ser application/json")

    body = await req.json()
    activity = Activity().deserialize(body)

    auth_header = req.headers.get("Authorization", "")

    try:
        # El SDK invoca el bot y devuelve (opcionalmente) un InvokeResponse.
        invoke_response = await adapter.process_activity(activity, auth_header, bot.on_turn)
        if invoke_response:
            return web.json_response(data=invoke_response.body, status=invoke_response.status)
        return web.Response(status=201)
    except Exception:
        logger.exception("Error procesando actividad entrante")
        return web.Response(status=500, text="Internal server error")

app = web.Application()
app.router.add_post("/api/messages", messages)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "3978"))
    web.run_app(app, host="0.0.0.0", port=port)
```

---

## 5) Instalación y ejecución

Desde la raíz del repo:

```bash
cd bots/teams_bot
python -m venv .venv
# Activa el entorno:
#   Windows: .venv\Scripts\activate
#   macOS/Linux: source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Ejecuta el bot
python app.py
```

Salida esperada (similar):
```
======== Running on http://0.0.0.0:3978 ========
(Press CTRL+C to quit)
```

---

## 6) Prueba con Bot Framework Emulator

1. Abre el Emulator.
2. Opción “Open Bot”.
3. Endpoint URL: `http://localhost:3978/api/messages`
4. MicrosoftAppId y MicrosoftAppPassword: déjalos vacíos para pruebas locales.
5. Envía un mensaje cualquiera. Deberías recibir: `Echo: <tu texto>`.

Si ves errores:
- Verifica que `app.py` está corriendo en el puerto 3978.
- Revisa la consola del bot y la ventana “Log” del Emulator para mensajes de error.
- Comprueba que el endpoint es exactamente `/api/messages`.

---

## 7) Qué sigue

Con el bot local funcionando, en el siguiente paso haremos:

- Añadir un formulario simple (Adaptive Card) para capturar `employee_id` y las `cities`.
- Escribir una línea en `data/ruta.csv` al recibir la solicitud.
- Llamar al endpoint `POST /evaluate` de `risk_api.py` y devolver el resultado al usuario.

Después de eso:
- Añadiremos un túnel (ngrok/devtunnel) y registraremos el bot en Azure para probarlo dentro de Microsoft Teams.

Este enfoque garantiza que avances de forma incremental: primero un bot funcional local, luego formularios/datos, después integración con tu API, y finalmente Teams.
