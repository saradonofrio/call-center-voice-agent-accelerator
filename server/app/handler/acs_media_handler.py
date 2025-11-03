"""Handles media streaming to Azure Voice Live API via WebSocket."""

import asyncio
import base64
from datetime import datetime
import json
import logging
import uuid

from azure.identity.aio import ManagedIdentityCredential
from websockets.asyncio.client import connect as ws_connect
from websockets.typing import Data

logger = logging.getLogger(__name__)


def session_config(azure_search_config=None):
    """Returns the default session configuration for Voice Live."""
    today = datetime.now().strftime("%d %B %Y")
    
    # NOTE: Azure Voice Live API might not support data_sources yet
    # If you're getting errors or no responses, Azure Search integration may not be available
    # For now, we disable it to ensure the bot works
    
    config = {
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": f"Sei un assistente virtuale farmacista che risponde in modo naturale e con frasi brevi. Parla in italiano, a meno che le domande non arrivino in altra lingua. Ricordati che oggi è il giorno {today}, usa questa data come riferimento temporale per rispondere alle domande. Parla solo di argomenti inerenti la farmacia. Inizia la conversazione chiedendo Come posso esserti utile?",
            "turn_detection": {
                "type": "azure_semantic_vad",
                "threshold": 0.3,
                "prefix_padding_ms": 200,
                "silence_duration_ms": 200,
                "remove_filler_words": False,
                "end_of_utterance_detection": {
                    "model": "semantic_detection_v1",
                    "threshold": 0.01,
                    "timeout": 2,
                },
            },
            "input_audio_noise_reduction": {"type": "azure_deep_noise_suppression"},
            "input_audio_echo_cancellation": {"type": "server_echo_cancellation"},
            "voice": {
                "name": "it-IT-IsabellaMultilingualNeural",
                "type": "azure-standard",
                "temperature": 0.8,
            },
        },
    }
    
    # TODO: Azure Search integration currently disabled
    # Azure Voice Live API may not support data_sources parameter yet
    # Monitor Azure Voice Live API updates for grounding support
    if azure_search_config:
        logger.warning("Azure AI Search config provided but integration is currently disabled - Voice Live API may not support it yet")
    
    return config


class ACSMediaHandler:
    """Manages audio streaming between client and Azure Voice Live API."""

    def __init__(self, config):
        self.endpoint = config["AZURE_VOICE_LIVE_ENDPOINT"]
        self.model = config["VOICE_LIVE_MODEL"]
        self.client_id = config.get("AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID")
        self.api_key = config.get("VOICE_LIVE_API_KEY")
        
        # Azure AI Search configuration (optional)
        self.azure_search_config = None
        if config.get("AZURE_SEARCH_ENDPOINT") and config.get("AZURE_SEARCH_INDEX"):
            self.azure_search_config = {
                "endpoint": config["AZURE_SEARCH_ENDPOINT"],
                "index_name": config["AZURE_SEARCH_INDEX"],
                "api_key": config.get("AZURE_SEARCH_API_KEY"),
                "auth_type": "api_key" if config.get("AZURE_SEARCH_API_KEY") else "system_assigned_managed_identity",
                "semantic_configuration": config.get("AZURE_SEARCH_SEMANTIC_CONFIG"),
                "top_n": config.get("AZURE_SEARCH_TOP_N", 5),
                "strictness": config.get("AZURE_SEARCH_STRICTNESS", 3)
            }
            logger.info("Azure AI Search enabled with index: %s", self.azure_search_config["index_name"])
        
        self.send_queue = asyncio.Queue()
        self.ws = None
        self.send_task = None
        self.incoming_websocket = None
        self.is_raw_audio = True

    def _generate_guid(self):
        return str(uuid.uuid4())

    def _handle_task_exception(self, task):
        try:
            exc = task.exception()
            if exc:
                logger.error("Async task failed: %s", exc)
        except Exception as e:
            logger.error("Error checking task exception: %s", e)

    async def connect(self):
        """Connects to Azure Voice Live API via WebSocket."""
        endpoint = self.endpoint.rstrip("/")
        model = self.model.strip()
        url = f"{endpoint}/voice-live/realtime?api-version=2025-05-01-preview&model={model}"
        url = url.replace("https://", "wss://")

        headers = {"x-ms-client-request-id": self._generate_guid()}

        if self.client_id:
        # Use async context manager to auto-close the credential
            async with ManagedIdentityCredential(client_id=self.client_id) as credential:
                token = await credential.get_token(
                    "https://ai.azure.com/.default"
                )
                headers["Authorization"] = f"Bearer {token.token}"
        else:
            headers["api-key"] = self.api_key

        self.ws = await ws_connect(url, additional_headers=headers)

        # Send session configuration with Azure Search if enabled
        session_cfg = session_config(self.azure_search_config)
        logger.info("Sending session config: %s", json.dumps(session_cfg, indent=2))
        await self._send_json(session_cfg)
        await self._send_json({"type": "response.create"})

        receiver_task = asyncio.create_task(self._receiver_loop())
        receiver_task.add_done_callback(self._handle_task_exception)
        self.send_task = asyncio.create_task(self._sender_loop())
        self.send_task.add_done_callback(self._handle_task_exception)

    async def init_incoming_websocket(self, socket, is_raw_audio=True):
        """Sets up incoming ACS WebSocket."""
        self.incoming_websocket = socket
        self.is_raw_audio = is_raw_audio

    async def audio_to_voicelive(self, audio_b64: str):
        """Queues audio data to be sent to Voice Live API."""
        await self.send_queue.put(
            json.dumps({"type": "input_audio_buffer.append", "audio": audio_b64})
        )

    async def _send_json(self, obj):
        """Sends a JSON object over WebSocket."""
        if self.ws:
            await self.ws.send(json.dumps(obj))

    async def _sender_loop(self):
        """Continuously sends messages from the queue to the Voice Live WebSocket."""
        try:
            while True:
                msg = await self.send_queue.get()
                if self.ws:
                    await self.ws.send(msg)
        except Exception:
            logger.exception("[ACSMediaHandler] Sender loop error")

    async def _receiver_loop(self):
        """Handles incoming events from the Voice Live WebSocket."""
        try:
            async for message in self.ws:
                event = json.loads(message)
                event_type = event.get("type")
                
                logger.debug("[_receiver_loop] Received event type: %s", event_type)

                match event_type:
                    case "session.created":
                        session_id = event.get("session", {}).get("id")
                        logger.info("[ACSMediaHandler] Session ID: %s", session_id)

                    case "input_audio_buffer.cleared":
                        logger.info("Input Audio Buffer Cleared Message")

                    case "input_audio_buffer.speech_started":
                        logger.info(
                            "Voice activity detection started at %s ms",
                            event.get("audio_start_ms"),
                        )
                        await self.stop_audio()

                    case "input_audio_buffer.speech_stopped":
                        logger.info("Speech stopped")

                    case "conversation.item.input_audio_transcription.completed":
                        transcript = event.get("transcript")
                        logger.info("User: %s", transcript)
                        # Send user voice transcription to frontend
                        if self.is_raw_audio:
                            await self.send_message(
                                json.dumps({"Kind": "UserVoiceTranscription", "Text": transcript})
                            )

                    case "conversation.item.input_audio_transcription.failed":
                        error_msg = event.get("error")
                        logger.warning("Transcription Error: %s", error_msg)

                    case "response.done":
                        response = event.get("response", {})
                        logger.info("Response Done: Id=%s", response.get("id"))
                        if response.get("status_details"):
                            logger.info(
                                "Status Details: %s",
                                json.dumps(response["status_details"], indent=2),
                            )

                    case "response.audio_transcript.done":
                        transcript = event.get("transcript")
                        logger.info("AI: %s", transcript)
                        # Send bot audio transcription to frontend
                        if self.is_raw_audio:
                            await self.send_message(
                                json.dumps({"Kind": "BotVoiceTranscription", "Text": transcript})
                            )

                    case "response.audio.delta":
                        delta = event.get("delta")
                        if self.is_raw_audio:
                            audio_bytes = base64.b64decode(delta)
                            await self.send_message(audio_bytes)
                        else:
                            await self.voicelive_to_acs(delta)

                    case "conversation.item.completed":
                        # Text response from Azure Voice Live API
                        item = event.get("item", {})
                        if item.get("type") == "message" and item.get("role") == "assistant":
                            content_list = item.get("content", [])
                            for content in content_list:
                                if content.get("type") == "text":
                                    text = content.get("text")
                                    logger.info("Bot (text): %s", text)
                                    if text and not self.is_raw_audio:
                                        # Send text response to ACS client
                                        await self.send_message(json.dumps({
                                            "Kind": "BotResponse",
                                            "Text": text
                                        }))
                                    elif text and self.is_raw_audio:
                                        # Send text response to web client
                                        await self.send_message(json.dumps({
                                            "Kind": "BotResponse",
                                            "Text": text
                                        }))

                    case "error":
                        logger.error("Voice Live Error: %s", json.dumps(event, indent=2))
                        # Send error notification to client if needed
                        error_msg = event.get("error", {})
                        logger.error("Error details - Code: %s, Message: %s", 
                                   error_msg.get("code"), 
                                   error_msg.get("message"))

                    case _:
                        logger.debug(
                            "[ACSMediaHandler] Other event: %s", event_type
                        )
        except Exception:
            logger.exception("[ACSMediaHandler] Receiver loop error")

    async def send_message(self, message: Data):
        """Sends data back to client WebSocket."""
        try:
            await self.incoming_websocket.send(message)
        except Exception:
            logger.exception("[ACSMediaHandler] Failed to send message")

    async def voicelive_to_acs(self, base64_data):
        """Converts Voice Live audio delta to ACS audio message."""
        try:
            data = {
                "Kind": "AudioData",
                "AudioData": {"Data": base64_data},
                "StopAudio": None,
            }
            await self.send_message(json.dumps(data))
        except Exception:
            logger.exception("[ACSMediaHandler] Error in voicelive_to_acs")

    async def stop_audio(self):
        """Sends a StopAudio signal to ACS."""
        stop_audio_data = {"Kind": "StopAudio", "AudioData": None, "StopAudio": {}}
        await self.send_message(json.dumps(stop_audio_data))

    async def acs_to_voicelive(self, stream_data):
        """Processes audio from ACS and forwards to Voice Live if not silent."""
        try:
            data = json.loads(stream_data)
            if data.get("kind") == "AudioData":
                audio_data = data.get("audioData", {})
                if not audio_data.get("silent", True):
                    await self.audio_to_voicelive(audio_data.get("data"))
        except Exception:
            logger.exception("[ACSMediaHandler] Error processing ACS audio")

    async def handle_websocket_message(self, message):
        """Handles incoming messages from frontend WebSocket and routes text/audio to Voice Live."""
        try:
            if isinstance(message, (bytes, bytearray)):
                # Assume raw audio bytes from web client
                await self.web_to_voicelive(message)
                return
            
            logger.info("[handle_websocket_message] Received text message: %s", message[:200])
            data = json.loads(message)
            msg_type = data.get("type")
            logger.info("[handle_websocket_message] Message type: %s", msg_type)
            
            if msg_type == "input_audio_buffer.append" and "audio" in data:
                await self.audio_to_voicelive(data["audio"])
            elif msg_type == "conversation.item.create":
                item = data.get("item", {})
                logger.info("[handle_websocket_message] Item: %s", item)
                # Check for old format (input field)
                input_obj = data.get("input", {})
                if input_obj.get("type") == "input_text" and "text" in input_obj:
                    logger.info("[handle_websocket_message] Text from old format: %s", input_obj["text"])
                    await self.text_to_voicelive(input_obj["text"])
                # Check for new format (item field)
                elif item.get("type") == "message":
                    content_list = item.get("content", [])
                    for content in content_list:
                        if content.get("type") == "input_text" and "text" in content:
                            logger.info("[handle_websocket_message] Text from new format: %s", content["text"])
                            await self.text_to_voicelive(content["text"])
        except Exception:
            logger.exception("[ACSMediaHandler] Error handling frontend websocket message")

    async def text_to_voicelive(self, text: str):
        """Queues text data to be sent to Voice Live API as input_text and commits it."""
        logger.info("[text_to_voicelive] Sending text to Voice Live: %s", text)
        payload = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": text
                    }
                ]
            }
        }
        logger.info("[text_to_voicelive] Payload: %s", json.dumps(payload, indent=2))
        await self.send_queue.put(json.dumps(payload))
        # Send commit event immediately after
        await self.send_queue.put(json.dumps({"type": "response.create"}))
        logger.info("[text_to_voicelive] Sent response.create")

    async def web_to_voicelive(self, audio_bytes):
        """Encodes raw audio bytes and sends to Voice Live API."""
        if not isinstance(audio_bytes, (bytes, bytearray)):
            logger.warning("web_to_voicelive called with non-bytes input, skipping. Type: %s", type(audio_bytes))
            return
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        await self.audio_to_voicelive(audio_b64)
