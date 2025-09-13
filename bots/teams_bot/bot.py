from botbuilder.core import ActivityHandler, TurnContext, MessageFactory
from botbuilder.schema import ChannelAccount


class TeamsRiskBot(ActivityHandler):
    async def on_members_added_activity(self, members_added: list[ChannelAccount], turn_context: TurnContext):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    MessageFactory.text("Hola, soy el bot de rutas. Escribe 'ping' para probar.")
                )

    async def on_message_activity(self, turn_context: TurnContext):
        text = (turn_context.activity.text or "").strip().lower()
        if text == "ping":
            await turn_context.send_activity(MessageFactory.text("pong"))
        else:
            # Por ahora comportarse como echo bot
            await turn_context.send_activity(MessageFactory.text(f"Echo: {turn_context.activity.text}"))
