"""Handles media streaming to Azure Voice Live API via WebSocket."""

import asyncio
import base64
from datetime import datetime
import json
import logging
import os
import uuid

from azure.identity.aio import ManagedIdentityCredential
from websockets.asyncio.client import connect as ws_connect
from websockets.typing import Data

logger = logging.getLogger(__name__)


def session_config(azure_search_config=None):
    """Returns the default session configuration for Voice Live."""
    today = datetime.now().strftime("%d %B %Y")
    
    logger.info("Building session config with azure_search_config: %s", 
                "enabled" if azure_search_config else "disabled")
    
    base_instructions = (
        f"Sei un assistente virtuale farmacista che risponde in modo naturale e con frasi brevi. "
        f"Parla in italiano, a meno che le domande non arrivino in altra lingua. "
        f"Ricordati che oggi è il giorno {today}, usa questa data come riferimento temporale per rispondere alle domande. "
        f"Parla solo di argomenti inerenti la farmacia. "
        f"Inizia la conversazione chiedendo Come posso esserti utile?"
    )
    
    # Add grounding instructions if Azure Search is enabled
    if azure_search_config:
        logger.info("Adding grounding instructions for index: %s", 
                   azure_search_config.get("index_name"))
        base_instructions += (
            "\n\nIMPORTANTE: Quando l'utente fa domande su farmaci, orari, servizi o informazioni della farmacia, "
            "usa SEMPRE la funzione search_pharmacy_database per cercare informazioni accurate. "
            "Basa le tue risposte sui risultati della ricerca. "
            "Se la ricerca non trova risultati rilevanti, dillo chiaramente all'utente."
        )
    
    config = {
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": base_instructions,
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
    
    # Add Azure Search function if configured
    if azure_search_config:
        logger.info("Enabling Azure AI Search function with index: %s", azure_search_config["index_name"])
        
        # Define the search function that Voice Live API can call
        search_function = {
            "type": "function",
            "name": "search_pharmacy_database",
            "description": "Cerca informazioni nel database della farmacia su farmaci, orari, servizi, prezzi e altre informazioni. Usa questa funzione per rispondere a domande specifiche dell'utente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "La query di ricerca basata sulla domanda dell'utente. Esempio: 'paracetamolo', 'orari apertura', 'test covid'"
                    }
                },
                "required": ["query"]
            }
        }
        
        config["session"]["tools"] = [search_function]
        config["session"]["tool_choice"] = "auto"  # Let the model decide when to call the function
        
        logger.info("Added tools to session config. Number of tools: %d", len(config["session"]["tools"]))
        logger.info("Tool name: %s", search_function.get("name"))
        logger.info("Tool type: %s", search_function.get("type"))
        logger.info("Tool choice: %s", config["session"]["tool_choice"])
        
        # Log the full tool definition
        try:
            tools_json = json.dumps(config["session"]["tools"], indent=2)
            logger.info("Full tools definition:\n%s", tools_json)
        except Exception as e:
            logger.error("Failed to serialize tools: %s", e)
            logger.error("Tools object: %s", config["session"]["tools"])
    else:
        logger.info("No tools added to session config - Azure Search not configured")
    
    return config


class ACSMediaHandler:
    """Manages audio streaming between client and Azure Voice Live API."""

    def __init__(self, config):
        self.endpoint = config["AZURE_VOICE_LIVE_ENDPOINT"]
        self.model = config["VOICE_LIVE_MODEL"]
        self.client_id = config.get("AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID")
        self.api_key = config.get("VOICE_LIVE_API_KEY")
        
        # Azure AI Search configuration - only enable if endpoint and index are provided
        self.azure_search_config = None
        search_endpoint = config.get("AZURE_SEARCH_ENDPOINT")
        search_index = config.get("AZURE_SEARCH_INDEX")
        
        logger.info("Azure Search config - Endpoint: %s, Index: %s", search_endpoint, search_index)
        
        if search_endpoint and search_index:
            self.azure_search_config = {
                "endpoint": search_endpoint,
                "index_name": search_index,
                "api_key": config.get("AZURE_SEARCH_API_KEY"),
                "auth_type": "api_key" if config.get("AZURE_SEARCH_API_KEY") else "system_assigned_managed_identity",
                "semantic_configuration": config.get("AZURE_SEARCH_SEMANTIC_CONFIG"),
                "top_n": config.get("AZURE_SEARCH_TOP_N", 5),
                "strictness": config.get("AZURE_SEARCH_STRICTNESS", 3)
            }
            logger.info("Azure AI Search enabled with index: %s", self.azure_search_config["index_name"])
        else:
            logger.warning("Azure AI Search NOT enabled - missing endpoint or index configuration")


        self.send_queue = asyncio.Queue()
        self.ws = None
        self.send_task = None
        self.incoming_websocket = None
        self.is_raw_audio = True
        self.response_in_progress = False  # Track if a response is being generated

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
        logger.info("Session config type: %s", type(session_cfg))
        logger.info("Session config keys: %s", list(session_cfg.keys()) if isinstance(session_cfg, dict) else "NOT A DICT")
        
        # Check if tools are in the session
        if "session" in session_cfg and "tools" in session_cfg["session"]:
            logger.info("Tools found in session config! Number of tools: %d", len(session_cfg["session"]["tools"]))
        else:
            logger.warning("NO TOOLS in session config!")
        
        try:
            config_json = json.dumps(session_cfg, indent=2)
            logger.info("Full session config being sent:\n%s", config_json)
        except Exception as e:
            logger.error("Failed to serialize session config: %s", e)
            logger.error("Session config value: %s", session_cfg)
            raise
            
        await self._send_json(session_cfg)
        # Don't send response.create here - let the first user input trigger it

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

                    case "response.created":
                        logger.info("Response created - setting response_in_progress = True")
                        self.response_in_progress = True

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
                        self.response_in_progress = False  # Response completed
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

                    case "response.function_call_arguments.done":
                        # Voice Live API is calling our search function
                        call_id = event.get("call_id")
                        function_name = event.get("name")
                        arguments_str = event.get("arguments")
                        
                        logger.info("Function call: %s with args: %s", function_name, arguments_str)
                        
                        if function_name == "search_pharmacy_database":
                            try:
                                arguments = json.loads(arguments_str)
                                query = arguments.get("query", "")
                                
                                # Execute the search
                                search_results = await self._execute_azure_search(query)
                                
                                # Send results back to Voice Live API
                                # The API will automatically continue the response after receiving the result
                                await self._send_function_result(call_id, search_results)
                                
                            except Exception as e:
                                logger.error("Error executing search function: %s", e)
                                await self._send_function_error(call_id, str(e))

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

    async def _execute_azure_search(self, query: str) -> str:
        """Execute Azure AI Search and return formatted results."""
        if not self.azure_search_config:
            return "Ricerca non disponibile al momento."
        
        try:
            from azure.search.documents.aio import SearchClient
            from azure.core.credentials import AzureKeyCredential
            
            logger.info("Executing Azure Search for query: %s", query)
            
            # Create search client
            credential = AzureKeyCredential(self.azure_search_config["api_key"])
            async with SearchClient(
                endpoint=self.azure_search_config["endpoint"],
                index_name=self.azure_search_config["index_name"],
                credential=credential
            ) as search_client:
                
                # Execute search
                results = await search_client.search(
                    search_text=query,
                    top=self.azure_search_config.get("top_n", 5)
                )
                
                # Format results
                formatted_results = []
                result_count = 0
                async for result in results:
                    result_count += 1
                    title = result.get("title", "")
                    content = result.get("content", "")
                    score = result.get("@search.score", 0)
                    
                    formatted_results.append(
                        f"[{result_count}] {title}\n{content}\n(Rilevanza: {score:.2f})"
                    )
                
                if formatted_results:
                    logger.info("Found %d results for query: %s", result_count, query)
                    return "Informazioni trovate nel database della farmacia:\n\n" + "\n\n".join(formatted_results)
                else:
                    logger.info("No results found for query: %s", query)
                    return "Non ho trovato informazioni specifiche su questo argomento nel database della farmacia."
                    
        except Exception as e:
            logger.error("Error executing Azure Search: %s", e)
            return f"Si è verificato un errore durante la ricerca: {str(e)}"
    
    async def _send_function_result(self, call_id: str, result: str):
        """Send function call result back to Voice Live API."""
        message = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result
            }
        }
        logger.info("Sending function result for call_id: %s", call_id)
        await self.send_queue.put(json.dumps(message))
        
        # After sending function output, we need to trigger a new response
        logger.info("Triggering response.create after function result")
        await self.send_queue.put(json.dumps({"type": "response.create"}))
    
    async def _send_function_error(self, call_id: str, error: str):
        """Send function call error back to Voice Live API."""
        message = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": f"Errore durante la ricerca: {error}"
            }
        }
        logger.error("Sending function error for call_id: %s - %s", call_id, error)
        await self.send_queue.put(json.dumps(message))
        
        # After sending function error, we need to trigger a new response
        logger.info("Triggering response.create after function error")
        await self.send_queue.put(json.dumps({"type": "response.create"}))
