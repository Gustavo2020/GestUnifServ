import os
import json
import logging
from aiohttp import web
from botbuilder.core import BotFrameworkAdapterSettings
from botbuilder.core.integration import aiohttp_error_middleware
from botbuilder.integration.aiohttp.bot_framework_http_adapter import (
    BotFrameworkHttpAdapter,
)
from botbuilder.schema import Activity

from bot import TeamsRiskBot


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("teams_bot.app")


APP_ID = os.getenv("MicrosoftAppId", "")
APP_PASSWORD = os.getenv("MicrosoftAppPassword", "")

adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkHttpAdapter(adapter_settings)
bot = TeamsRiskBot()


async def on_error(context, error: Exception):
    logger.exception("Bot error: %s", error)
    await context.send_activity("Lo siento, ocurrió un error en el bot.")


adapter.on_turn_error = on_error


async def messages(request: web.Request) -> web.Response:
    # Accept only JSON payloads
    content_type = request.headers.get("Content-Type", "")
    if "application/json" not in content_type:
        return web.Response(status=415, text="Unsupported Media Type")

    # Authorization header for Bot Framework (used by channel/emulator)
    auth_header = request.headers.get("Authorization", "")
    try:
        body = await request.json()
    except Exception:
        logger.exception("Invalid JSON payload received at /api/messages")
        return web.Response(status=400, text="Invalid JSON")

    activity = Activity().deserialize(body)
    logger.info(
        "Incoming activity type=%s | channelId=%s | serviceUrl=%s | convId=%s",
        getattr(activity, "type", None),
        getattr(activity, "channel_id", None),
        getattr(activity, "service_url", None),
        getattr(getattr(activity, "conversation", None), "id", None),
    )

    try:
        invoke_response = await adapter.process_activity(
            activity, auth_header, bot.on_turn
        )
        if invoke_response:
            return web.Response(status=invoke_response.status, text=invoke_response.body)
        # For non-invoke activities, returning 200 indicates the activity was accepted
        return web.Response(status=200)
    except Exception:
        logger.exception("Failed processing activity")
        return web.Response(status=500, text="Error processing activity")


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_app() -> web.Application:
    app = web.Application(middlewares=[aiohttp_error_middleware])
    app.add_routes(
        [
            web.get("/health", health),
            web.post("/api/messages", messages),
        ]
    )
    return app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "3978"))
    web.run_app(create_app(), host="127.0.0.1", port=port)
