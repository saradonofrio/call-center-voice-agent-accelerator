import asyncio
import logging
import os

from app.handler.acs_event_handler import AcsEventHandler
from app.handler.acs_media_handler import ACSMediaHandler
from app.handler.aoai_text_handler import AOAITextHandler
from dotenv import load_dotenv
from quart import Quart, request, websocket, Response

load_dotenv()

app = Quart(__name__)
aoai_text_handler = AOAITextHandler(app.config)
@app.websocket("/web/textws")
async def web_text_ws():
    """WebSocket endpoint for web clients to send text and receive bot response via AOAI."""
    logger = logging.getLogger("web_text_ws")
    logger.info("Incoming Web Text WebSocket connection")
    try:
        while True:
            user_text = await websocket.receive()
            logger.info(f"Received user text: {user_text}")
            bot_response = await aoai_text_handler.get_bot_response(user_text)
            await websocket.send(bot_response)
    except Exception:
        logger.exception("Web Text WebSocket connection closed")
app.config["AZURE_VOICE_LIVE_ENDPOINT"] = os.getenv("AZURE_VOICE_LIVE_ENDPOINT")
app.config["AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID"] = os.getenv(
    "AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID", "")
app.config["VOICE_LIVE_MODEL"] = os.getenv("VOICE_LIVE_MODEL", "gpt-4o-mini")
app.config["ACS_CONNECTION_STRING"] = os.getenv("ACS_CONNECTION_STRING")
app.config["ACS_DEV_TUNNEL"] = os.getenv("ACS_DEV_TUNNEL", "")
app.config["AZURE_OPENAI_ENDPOINT"] = os.getenv("AZURE_OPENAI_ENDPOINT")


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s"
)

acs_handler = AcsEventHandler(app.config)


@app.route("/acs/incomingcall", methods=["POST"])
async def incoming_call_handler():
    """Handles initial incoming call event from EventGrid."""
    try:
        events = await request.get_json()
    except Exception as e:
        logging.getLogger("incoming_call_handler").warning(
            "No body was attached to the request or invalid JSON: %s", e
        )
        return Response(response='{"error": "No body attached or invalid JSON"}', status=400, mimetype="application/json")

    if not events:
        logging.getLogger("incoming_call_handler").warning("No body was attached to the request")
        return Response(response='{"error": "No body attached"}', status=400, mimetype="application/json")

    host_url = request.host_url.replace("http://", "https://", 1).rstrip("/")
    return await acs_handler.process_incoming_call(events, host_url, app.config)


@app.route("/acs/callbacks/<context_id>", methods=["POST"])
async def acs_event_callbacks(context_id):
    """Handles ACS event callbacks for call connection and streaming events."""
    try:
        raw_events = await request.get_json()
    except Exception as e:
        logging.getLogger("acs_event_callbacks").warning(
            "No body was attached to the request or invalid JSON: %s", e
        )
        return Response(response='{"error": "No body attached or invalid JSON"}', status=400, mimetype="application/json")

    if not raw_events:
        logging.getLogger("acs_event_callbacks").warning("No body was attached to the request")
        return Response(response='{"error": "No body attached"}', status=400, mimetype="application/json")

    return await acs_handler.process_callback_events(context_id, raw_events, app.config)


@app.websocket("/acs/ws")
async def acs_ws():
    """WebSocket endpoint for ACS to send audio to Voice Live."""
    logger = logging.getLogger("acs_ws")
    logger.info("Incoming ACS WebSocket connection")
    handler = ACSMediaHandler(app.config)
    await handler.init_incoming_websocket(websocket, is_raw_audio=False)
    asyncio.create_task(handler.connect())
    try:
        while True:
            msg = await websocket.receive()
            await handler.acs_to_voicelive(msg)
    except Exception:
        logger.exception("ACS WebSocket connection closed")


@app.websocket("/web/ws")
async def web_ws():
    """WebSocket endpoint for web clients to send audio to Voice Live."""
    logger = logging.getLogger("web_ws")
    logger.info("Incoming Web WebSocket connection")
    handler = ACSMediaHandler(app.config)
    await handler.init_incoming_websocket(websocket, is_raw_audio=True)
    asyncio.create_task(handler.connect())
    try:
        while True:
            msg = await websocket.receive()
            await handler.web_to_voicelive(msg)
    except Exception:
        logger.exception("Web WebSocket connection closed")


@app.route("/")
async def index():
    """Serves the static index page."""
    return await app.send_static_file("index.html")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
