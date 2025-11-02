import asyncio
import logging
import sys

import os
from app.handler.acs_event_handler import AcsEventHandler
from app.handler.acs_media_handler import ACSMediaHandler
from dotenv import load_dotenv
from quart import Quart, request, websocket, Response

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

app = Quart(__name__)

# Load required environment variables into app.config
app.config["ACS_CONNECTION_STRING"] = os.environ.get("ACS_CONNECTION_STRING")
app.config["AZURE_VOICE_LIVE_ENDPOINT"] = os.environ.get("AZURE_VOICE_LIVE_ENDPOINT")
app.config["VOICE_LIVE_MODEL"] = os.environ.get("VOICE_LIVE_MODEL")
app.config["AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID"] = os.environ.get("AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID")
app.config["VOICE_LIVE_API_KEY"] = os.environ.get("VOICE_LIVE_API_KEY")

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
            if isinstance(msg, (bytes, bytearray)):
                await handler.web_to_voicelive(msg)
            else:
                # Assume text message, route to handler
                await handler.handle_websocket_message(msg)
    except Exception:
        logger.exception("Web WebSocket connection closed")


@app.route("/")
async def index():
    """Serves the static index page."""
    return await app.send_static_file("index.html")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
