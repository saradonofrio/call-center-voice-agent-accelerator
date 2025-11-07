"""
Handles media streaming to Azure Voice Live API via WebSocket.

This module manages bidirectional audio/text streaming between clients and Azure Voice Live API,
including Azure AI Search integration for grounding (RAG - Retrieval Augmented Generation).
"""

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
    """
    Returns the default session configuration for Voice Live API.
    
    This configuration defines:
    - Conversation modalities (text and audio)
    - AI personality and instructions in Italian
    - Voice activity detection (VAD) settings
    - Noise reduction and echo cancellation
    - Voice selection (Italian neural voice)
    - Azure AI Search integration for grounding (if enabled)
    
    Args:
        azure_search_config (dict, optional): Azure AI Search configuration for document grounding.
            If provided, adds function calling capability to search the pharmacy database.
    
    Returns:
        dict: Session configuration object to be sent to Voice Live API
    """
    # Get current date for temporal context in responses
    today = datetime.now().strftime("%d %B %Y")
    
    logger.info("Building session config with azure_search_config: %s", 
                "enabled" if azure_search_config else "disabled")
    
    # Base system instructions for the AI assistant (in Italian)
    base_instructions = (
        f"Sei un assistente virtuale farmacista che risponde in modo naturale e con frasi brevi. "
        f"Parla in italiano, a meno che le domande non arrivino in altra lingua. "
        f"Ricordati che oggi è il giorno {today}, usa questa data come riferimento temporale per rispondere alle domande. "
        f"Parla solo di argomenti inerenti la farmacia, se la ricerca non trova risultati rilevanti, rispondi 'Ti consiglio di contattare la farmacia.'"
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
            "Se la ricerca non trova risultati rilevanti, rispondi 'Ti consiglio di contattare la farmacia.'"
        )
    
    # Build session configuration object
    config = {
        "type": "session.update",
        "session": {
            # Enable both text and audio modalities
            "modalities": ["text", "audio"],
            
            # AI system instructions (personality and behavior)
            "instructions": base_instructions,
            
            # Voice Activity Detection (VAD) configuration
            "turn_detection": {
                "type": "azure_semantic_vad",  # Azure's semantic VAD model
                "threshold": 0.3,               # Sensitivity threshold
                "prefix_padding_ms": 200,       # Audio before speech detection
                "silence_duration_ms": 200,     # Silence duration to detect end of speech
                "remove_filler_words": False,   # Keep "um", "uh", etc.
                "end_of_utterance_detection": {
                    "model": "semantic_detection_v1",
                    "threshold": 0.01,
                    "timeout": 2,
                },
            },
            
            # Audio processing settings
            "input_audio_noise_reduction": {"type": "azure_deep_noise_suppression"},
            "input_audio_echo_cancellation": {"type": "server_echo_cancellation"},
            
            # Voice configuration - Italian neural voice
            "voice": {
                "name": "it-IT-IsabellaMultilingualNeural",  # Italian female voice
                "type": "azure-standard",
                "temperature": 0.8,  # Response creativity (0.0-1.0)
            },
        },
    }
    
    # Add Azure Search function calling if configured
    if azure_search_config:
        logger.info("Enabling Azure AI Search function with index: %s", azure_search_config["index_name"])
        
        # Define the search function that Voice Live API can call
        # This enables the AI to retrieve information from the pharmacy database
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
        
        # Add function to session configuration
        config["session"]["tools"] = [search_function]
        config["session"]["tool_choice"] = "auto"  # Let the model decide when to call the function
        
        # Log function configuration for debugging
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
    """
    Manages audio streaming between client and Azure Voice Live API.
    
    This class handles:
    - WebSocket connection to Azure Voice Live API
    - Bidirectional audio/text streaming
    - Azure AI Search integration for document grounding
    - Function calling for database queries
    - Audio format conversion (Int16 PCM ↔ Base64)
    
    Architecture:
        Client (Web/ACS) ←→ WebSocket ←→ ACSMediaHandler ←→ WebSocket ←→ Voice Live API
                                              ↓
                                        Azure AI Search
    """

    def __init__(self, config):
        """
        Initialize the media handler with configuration.
        
        Args:
            config (dict): Configuration dictionary containing:
                - AZURE_VOICE_LIVE_ENDPOINT: Voice Live API endpoint URL
                - VOICE_LIVE_MODEL: Model deployment name
                - AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID: Managed identity client ID (optional)
                - VOICE_LIVE_API_KEY: API key for authentication (optional)
                - AZURE_SEARCH_ENDPOINT: Azure AI Search endpoint (optional)
                - AZURE_SEARCH_INDEX: Search index name (optional)
                - AZURE_SEARCH_API_KEY: Search API key (optional)
        """
        # Voice Live API configuration
        self.endpoint = config["AZURE_VOICE_LIVE_ENDPOINT"]
        self.model = config["VOICE_LIVE_MODEL"]
        self.client_id = config.get("AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID")
        self.api_key = config.get("VOICE_LIVE_API_KEY")
        
        # Azure AI Search configuration - only enable if endpoint and index are provided
        self.azure_search_config = None
        search_endpoint = config.get("AZURE_SEARCH_ENDPOINT")
        search_index = config.get("AZURE_SEARCH_INDEX")
        
        logger.info("Azure Search config - Endpoint: %s, Index: %s", search_endpoint, search_index)
        
        # Configure Azure AI Search if both endpoint and index are provided
        if search_endpoint and search_index:
            self.azure_search_config = {
                "endpoint": search_endpoint,
                "index_name": search_index,
                "api_key": config.get("AZURE_SEARCH_API_KEY"),
                "auth_type": "api_key" if config.get("AZURE_SEARCH_API_KEY") else "system_assigned_managed_identity",
                "semantic_configuration": config.get("AZURE_SEARCH_SEMANTIC_CONFIG"),
                "top_n": config.get("AZURE_SEARCH_TOP_N", 5),          # Number of results to return
                "strictness": config.get("AZURE_SEARCH_STRICTNESS", 3)  # Relevance threshold (1-5)
            }
            logger.info("Azure AI Search enabled with index: %s", self.azure_search_config["index_name"])
        else:
            logger.warning("Azure AI Search NOT enabled - missing endpoint or index configuration")

        # Async communication queues and WebSocket connections
        self.send_queue = asyncio.Queue()        # Queue for messages to send to Voice Live API
        self.ws = None                           # WebSocket connection to Voice Live API
        self.send_task = None                    # Async task for sending messages
        self.incoming_websocket = None           # WebSocket connection from client
        self.is_raw_audio = True                 # Flag for audio format (raw vs ACS format)
        self.response_in_progress = False        # Track if AI is generating a response
        self.custom_instructions = None          # Store custom instructions from frontend
        self.voice_live_connected = False        # Track if Voice Live connection is established

    def _generate_guid(self):
        """Generate a unique GUID for request tracking."""
        return str(uuid.uuid4())

    def _handle_task_exception(self, task):
        """
        Handle exceptions from async tasks.
        
        Args:
            task: The asyncio task that completed
        """
        try:
            exc = task.exception()
            if exc:
                logger.error("Async task failed: %s", exc)
        except Exception as e:
            logger.error("Error checking task exception: %s", e)

    async def connect(self):
        """
        Connects to Azure Voice Live API via WebSocket.
        
        Process:
        1. Constructs WebSocket URL with model parameter
        2. Authenticates using Managed Identity or API key
        3. Establishes WebSocket connection
        4. Sends session configuration (including Azure Search tools if enabled)
        5. Starts async receiver and sender loops
        
        Raises:
            Exception: If connection or authentication fails
        """
        # Build WebSocket URL (convert https:// to wss://)
        endpoint = self.endpoint.rstrip("/")
        model = self.model.strip()
        url = f"{endpoint}/voice-live/realtime?api-version=2025-05-01-preview&model={model}"
        url = url.replace("https://", "wss://")

        # Prepare request headers
        headers = {"x-ms-client-request-id": self._generate_guid()}

        # Authenticate using Managed Identity or API key
        if self.client_id:
            # Use async context manager to auto-close the credential
            async with ManagedIdentityCredential(client_id=self.client_id) as credential:
                token = await credential.get_token(
                    "https://ai.azure.com/.default"
                )
                headers["Authorization"] = f"Bearer {token.token}"
        else:
            headers["api-key"] = self.api_key

        # Establish WebSocket connection
        self.ws = await ws_connect(url, additional_headers=headers)

        # Send session configuration with Azure Search if enabled
        # Use custom instructions if available, otherwise use defaults from session_config
        if self.custom_instructions:
            logger.info("Using custom instructions provided by user")
            session_cfg = session_config(self.azure_search_config)
            session_cfg["session"]["instructions"] = self.custom_instructions
        else:
            logger.info("Using default instructions")
            session_cfg = session_config(self.azure_search_config)
        
        logger.info("Session config type: %s", type(session_cfg))
        logger.info("Session config keys: %s", list(session_cfg.keys()) if isinstance(session_cfg, dict) else "NOT A DICT")
        
        # Verify tools are included in configuration
        if "session" in session_cfg and "tools" in session_cfg["session"]:
            logger.info("Tools found in session config! Number of tools: %d", len(session_cfg["session"]["tools"]))
        else:
            logger.warning("NO TOOLS in session config!")
        
        # Log full configuration for debugging
        try:
            config_json = json.dumps(session_cfg, indent=2)
            logger.info("Full session config being sent:\n%s", config_json)
        except Exception as e:
            logger.error("Failed to serialize session config: %s", e)
            logger.error("Session config value: %s", session_cfg)
            raise
            
        await self._send_json(session_cfg)
        # Note: Don't send response.create here - let first user input trigger it
        
        # Mark Voice Live as connected
        self.voice_live_connected = True
        logger.info("Voice Live API connection established")

        # Start async message processing loops
        receiver_task = asyncio.create_task(self._receiver_loop())
        receiver_task.add_done_callback(self._handle_task_exception)
        self.send_task = asyncio.create_task(self._sender_loop())
        self.send_task.add_done_callback(self._handle_task_exception)

    async def init_incoming_websocket(self, socket, is_raw_audio=True):
        """
        Sets up incoming WebSocket connection from client.
        
        Args:
            socket: WebSocket connection from client (web or ACS)
            is_raw_audio (bool): True for raw PCM audio, False for ACS JSON format
        """
        self.incoming_websocket = socket
        self.is_raw_audio = is_raw_audio

    async def audio_to_voicelive(self, audio_b64: str):
        """
        Queues base64-encoded audio data to be sent to Voice Live API.
        
        Args:
            audio_b64 (str): Base64-encoded PCM audio data
        """
        await self.send_queue.put(
            json.dumps({"type": "input_audio_buffer.append", "audio": audio_b64})
        )

    async def _send_json(self, obj):
        """
        Sends a JSON object over WebSocket to Voice Live API.
        
        Args:
            obj (dict): Object to serialize and send
        """
        if self.ws:
            await self.ws.send(json.dumps(obj))

    async def _sender_loop(self):
        """
        Continuously sends messages from the queue to the Voice Live WebSocket.
        
        This runs as an async task, processing messages from send_queue
        and forwarding them to the Voice Live API.
        """
        try:
            while True:
                msg = await self.send_queue.get()
                if self.ws:
                    await self.ws.send(msg)
        except Exception:
            logger.exception("[ACSMediaHandler] Sender loop error")

    async def _receiver_loop(self):
        """
        Handles incoming events from the Voice Live WebSocket.
        
        This is the main event processing loop that handles all messages from Voice Live API:
        - Session management events
        - Audio transcriptions (user and bot)
        - Audio data for playback
        - Function calling events (Azure Search integration)
        - Error events
        
        Events are processed using pattern matching (match/case) based on event type.
        """
        try:
            async for message in self.ws:
                event = json.loads(message)
                event_type = event.get("type")
                
                logger.debug("[_receiver_loop] Received event type: %s", event_type)

                match event_type:
                    # ================================================================
                    # SESSION MANAGEMENT EVENTS
                    # ================================================================
                    
                    case "session.created":
                        # Voice Live session established
                        session_id = event.get("session", {}).get("id")
                        logger.info("[ACSMediaHandler] Session ID: %s", session_id)

                    case "response.created":
                        # AI started generating a response
                        logger.info("Response created - setting response_in_progress = True")
                        self.response_in_progress = True

                    # ================================================================
                    # AUDIO BUFFER EVENTS
                    # ================================================================

                    case "input_audio_buffer.cleared":
                        # Audio buffer was cleared
                        logger.info("Input Audio Buffer Cleared Message")

                    case "input_audio_buffer.speech_started":
                        # Voice Activity Detection (VAD) detected speech start
                        logger.info(
                            "Voice activity detection started at %s ms",
                            event.get("audio_start_ms"),
                        )
                        # Stop any ongoing audio playback when user starts speaking
                        await self.stop_audio()

                    case "input_audio_buffer.speech_stopped":
                        # VAD detected end of speech
                        logger.info("Speech stopped")

                    # ================================================================
                    # TRANSCRIPTION EVENTS
                    # ================================================================

                    case "conversation.item.input_audio_transcription.completed":
                        # User speech transcription completed
                        transcript = event.get("transcript")
                        logger.info("User: %s", transcript)
                        # Send user voice transcription to frontend
                        if self.is_raw_audio:
                            await self.send_message(
                                json.dumps({"Kind": "UserVoiceTranscription", "Text": transcript})
                            )

                    case "conversation.item.input_audio_transcription.failed":
                        # Transcription failed
                        error_msg = event.get("error")
                        logger.warning("Transcription Error: %s", error_msg)

                    case "response.audio_transcript.done":
                        # Bot audio response transcription completed
                        transcript = event.get("transcript")
                        logger.info("AI: %s", transcript)
                        # Send bot audio transcription to frontend
                        if self.is_raw_audio:
                            await self.send_message(
                                json.dumps({"Kind": "BotVoiceTranscription", "Text": transcript})
                            )

                    # ================================================================
                    # RESPONSE COMPLETION EVENTS
                    # ================================================================

                    case "response.done":
                        # AI finished generating response
                        response = event.get("response", {})
                        logger.info("Response Done: Id=%s", response.get("id"))
                        self.response_in_progress = False  # Response completed
                        if response.get("status_details"):
                            logger.info(
                                "Status Details: %s",
                                json.dumps(response["status_details"], indent=2),
                            )

                    # ================================================================
                    # AUDIO PLAYBACK EVENTS
                    # ================================================================

                    case "response.audio.delta":
                        # Received audio chunk from AI response
                        delta = event.get("delta")
                        if self.is_raw_audio:
                            # Send raw audio bytes to web client
                            audio_bytes = base64.b64decode(delta)
                            await self.send_message(audio_bytes)
                        else:
                            # Send ACS-formatted audio to ACS client
                            await self.voicelive_to_acs(delta)

                    # ================================================================
                    # TEXT RESPONSE EVENTS
                    # ================================================================

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

                    # ================================================================
                    # FUNCTION CALLING EVENTS (Azure Search Integration)
                    # ================================================================

                    case "response.function_call_arguments.done":
                        # Voice Live API is calling our search function
                        call_id = event.get("call_id")
                        function_name = event.get("name")
                        arguments_str = event.get("arguments")
                        
                        logger.info("Function call: %s with args: %s", function_name, arguments_str)
                        
                        if function_name == "search_pharmacy_database":
                            try:
                                # Parse function arguments
                                arguments = json.loads(arguments_str)
                                query = arguments.get("query", "")
                                
                                # Execute the Azure AI Search
                                search_results = await self._execute_azure_search(query)
                                
                                # Send results back to Voice Live API
                                # The API will automatically continue the response after receiving the result
                                await self._send_function_result(call_id, search_results)
                                
                            except Exception as e:
                                logger.error("Error executing search function: %s", e)
                                await self._send_function_error(call_id, str(e))

                    # ================================================================
                    # ERROR EVENTS
                    # ================================================================

                    case "error":
                        # Error from Voice Live API
                        logger.error("Voice Live Error: %s", json.dumps(event, indent=2))
                        # Send error notification to client if needed
                        error_msg = event.get("error", {})
                        logger.error("Error details - Code: %s, Message: %s", 
                                   error_msg.get("code"), 
                                   error_msg.get("message"))

                    # ================================================================
                    # OTHER/UNKNOWN EVENTS
                    # ================================================================

                    case _:
                        # Log any other event types for debugging
                        logger.debug(
                            "[ACSMediaHandler] Other event: %s", event_type
                        )
        except Exception:
            logger.exception("[ACSMediaHandler] Receiver loop error")

    async def send_message(self, message: Data):
        """
        Sends data back to client WebSocket.
        
        Args:
            message (Data): Message data to send (can be text or binary)
        """
        try:
            await self.incoming_websocket.send(message)
        except Exception:
            logger.exception("[ACSMediaHandler] Failed to send message")

    async def voicelive_to_acs(self, base64_data):
        """
        Converts Voice Live audio delta to ACS audio message format.
        
        This is used when the client is an Azure Communication Services (ACS) endpoint
        rather than a web browser.
        
        Args:
            base64_data (str): Base64-encoded audio data from Voice Live
        """
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
        """
        Sends a StopAudio signal to client.
        
        This is typically sent when user starts speaking, to interrupt any ongoing
        AI audio playback (barge-in behavior).
        """
        stop_audio_data = {"Kind": "StopAudio", "AudioData": None, "StopAudio": {}}
        await self.send_message(json.dumps(stop_audio_data))

    async def acs_to_voicelive(self, stream_data):
        """
        Processes audio from ACS and forwards to Voice Live if not silent.
        
        Args:
            stream_data (str): JSON string containing ACS audio data
        """
        try:
            data = json.loads(stream_data)
            if data.get("kind") == "AudioData":
                audio_data = data.get("audioData", {})
                # Only forward non-silent audio
                if not audio_data.get("silent", True):
                    await self.audio_to_voicelive(audio_data.get("data"))
        except Exception:
            logger.exception("[ACSMediaHandler] Error processing ACS audio")

    async def handle_websocket_message(self, message):
        """
        Handles incoming messages from frontend WebSocket and routes text/audio to Voice Live.
        
        This method processes messages from web clients and forwards them appropriately:
        - Binary data (bytes/bytearray) → treated as raw audio
        - JSON with type "input_audio_buffer.append" → base64 audio
        - JSON with type "conversation.item.create" → text message
        
        Args:
            message: WebSocket message (can be bytes for audio or str for JSON)
        """
        try:
            # Handle raw audio bytes from web client microphone
            if isinstance(message, (bytes, bytearray)):
                await self.web_to_voicelive(message)
                return
            
            logger.info("[handle_websocket_message] Received text message: %s", message[:200])
            data = json.loads(message)
            msg_type = data.get("type")
            logger.info("[handle_websocket_message] Message type: %s", msg_type)
            
            # Handle custom instructions update from frontend
            if msg_type == "session.update_instructions":
                custom_instructions = data.get("instructions")
                if custom_instructions:
                    logger.info("[handle_websocket_message] Received custom instructions: %s", custom_instructions[:100])
                    
                    # Store custom instructions for when we connect to Voice Live
                    self.custom_instructions = custom_instructions
                    
                    # If already connected to Voice Live, send update
                    if self.voice_live_connected:
                        await self._send_json({
                            "type": "session.update",
                            "session": {
                                "instructions": custom_instructions
                            }
                        })
                        logger.info("[handle_websocket_message] Sent custom instructions update to Voice Live API")
                    else:
                        logger.info("[handle_websocket_message] Stored custom instructions for initial connection")
                return
            
            # Handle base64-encoded audio
            if msg_type == "input_audio_buffer.append" and "audio" in data:
                await self.audio_to_voicelive(data["audio"])
                
            # Handle text messages (supports both old and new format)
            elif msg_type == "conversation.item.create":
                item = data.get("item", {})
                logger.info("[handle_websocket_message] Item: %s", item)
                
                # Check for old format (input field at top level)
                input_obj = data.get("input", {})
                if input_obj.get("type") == "input_text" and "text" in input_obj:
                    logger.info("[handle_websocket_message] Text from old format: %s", input_obj["text"])
                    await self.text_to_voicelive(input_obj["text"])
                    
                # Check for new format (item.content structure)
                elif item.get("type") == "message":
                    content_list = item.get("content", [])
                    for content in content_list:
                        if content.get("type") == "input_text" and "text" in content:
                            logger.info("[handle_websocket_message] Text from new format: %s", content["text"])
                            await self.text_to_voicelive(content["text"])
        except Exception:
            logger.exception("[ACSMediaHandler] Error handling frontend websocket message")

    async def text_to_voicelive(self, text: str):
        """
        Sends text input to Voice Live API and triggers a response.
        
        This method:
        1. Creates a conversation item with the user's text
        2. Immediately sends a response.create to trigger AI response
        
        Args:
            text (str): User's text message
        """
        logger.info("[text_to_voicelive] Sending text to Voice Live: %s", text)
        
        # Create conversation item with user message
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
        
        # Trigger AI response generation
        await self.send_queue.put(json.dumps({"type": "response.create"}))
        logger.info("[text_to_voicelive] Sent response.create")

    async def web_to_voicelive(self, audio_bytes):
        """
        Encodes raw audio bytes from web client and sends to Voice Live API.
        
        Args:
            audio_bytes (bytes): Raw PCM audio data from browser
        """
        if not isinstance(audio_bytes, (bytes, bytearray)):
            logger.warning("web_to_voicelive called with non-bytes input, skipping. Type: %s", type(audio_bytes))
            return
            
        # Convert to base64 for JSON transmission
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        await self.audio_to_voicelive(audio_b64)

    async def _execute_azure_search(self, query: str) -> str:
        """
        Execute Azure AI Search and return formatted results.
        
        This method is called when the Voice Live API invokes the search_pharmacy_database function.
        It queries the Azure AI Search index and returns formatted results for the AI to use
        in generating its response.
        
        Args:
            query (str): Search query from the AI (e.g., "paracetamolo", "orari apertura")
            
        Returns:
            str: Formatted search results in Italian, or error message if search fails
        """
        if not self.azure_search_config:
            return "Ricerca non disponibile al momento."
        
        try:
            from azure.search.documents.aio import SearchClient
            from azure.core.credentials import AzureKeyCredential
            
            logger.info("Executing Azure Search for query: %s", query)
            
            # Create async search client
            credential = AzureKeyCredential(self.azure_search_config["api_key"])
            async with SearchClient(
                endpoint=self.azure_search_config["endpoint"],
                index_name=self.azure_search_config["index_name"],
                credential=credential
            ) as search_client:
                
                # Execute search with configured parameters
                results = await search_client.search(
                    search_text=query,
                    top=self.azure_search_config.get("top_n", 5)  # Return top N results
                )
                
                # Format results for AI consumption
                formatted_results = []
                result_count = 0
                async for result in results:
                    result_count += 1
                    title = result.get("title", "")
                    content = result.get("content", "")
                    score = result.get("@search.score", 0)
                    
                    # Format each result with title, content, and relevance score
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
        """
        Send function call result back to Voice Live API.
        
        After executing a function (like Azure Search), this method sends the results
        back to Voice Live API. The API then uses these results to generate its response
        to the user.
        
        Args:
            call_id (str): Unique identifier for the function call
            result (str): Search results or function output
        """
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
        
        # After sending function output, trigger a new response
        # This tells Voice Live to continue generating the response with the search results
        logger.info("Triggering response.create after function result")
        await self.send_queue.put(json.dumps({"type": "response.create"}))
    
    async def _send_function_error(self, call_id: str, error: str):
        """
        Send function call error back to Voice Live API.
        
        If a function execution fails, this method sends the error information
        back to Voice Live API so it can inform the user appropriately.
        
        Args:
            call_id (str): Unique identifier for the function call
            error (str): Error message describing what went wrong
        """
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
        
        # After sending function error, trigger a new response
        # Voice Live will use the error information to generate an appropriate response
        logger.info("Triggering response.create after function error")
        await self.send_queue.put(json.dumps({"type": "response.create"}))
