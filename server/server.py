"""
Main server application for the Call Center Voice Agent Accelerator.

This Quart (async Flask) application serves as the central hub for:
- Azure Communication Services (ACS) telephony integration
- Web-based voice chat interface
- Bidirectional audio streaming to Azure Voice Live API
- Document upload and indexing for RAG (Retrieval Augmented Generation)
- Azure AI Search integration for knowledge base grounding

Architecture:
    Phone Calls: PSTN → ACS → EventGrid → /acs/incomingcall → WebSocket → Voice Live
    Web Clients: Browser → /web/ws WebSocket → Voice Live
    Documents: Upload → Azure Blob Storage → Azure AI Search → RAG queries

Endpoints:
    - POST /acs/incomingcall: EventGrid webhook for incoming phone calls
    - POST /acs/callbacks/<id>: ACS lifecycle event callbacks
    - WebSocket /acs/ws: Bidirectional audio for phone calls
    - WebSocket /web/ws: Bidirectional audio for web clients
    - GET /: Serve web chat interface (index.html)
    - POST /api/documents: Upload documents for indexing
    - GET /api/documents: List indexed documents
    - DELETE /api/documents/<id>: Delete a document
    - POST /api/indexer/create: Create Azure Search indexer
    - POST /api/indexer/run: Trigger indexer manually
    - GET /api/indexer/status: Get indexer status
"""

import asyncio
import logging
import sys
import json
import uuid

import os
from datetime import datetime, timezone
from app.handler.acs_event_handler import AcsEventHandler
from app.handler.acs_media_handler import ACSMediaHandler
from app.document_processor import DocumentProcessor
from app.auth import AzureADAuth, require_auth, require_auth_optional
from azure.storage.blob import ContentSettings
from dotenv import load_dotenv
from quart import Quart, request, websocket, Response, jsonify, g
from quart_cors import cors
# from quart_rate_limiter import RateLimiter, rate_limit  # Temporarily disabled due to deployment issues
from app.rate_limiter import rate_limit, get_rate_limiter  # Custom lightweight rate limiter

# Load environment variables from .env file
load_dotenv()

# ============================================================
# LOGGING CONFIGURATION
# ============================================================
# Configure logging to stdout with INFO level
# Format includes timestamp, logger name, level, and message
logging.basicConfig(
    level=logging.INFO,  # Changed from DEBUG to reduce log verbosity
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# ============================================================
# APPLICATION INITIALIZATION
# ============================================================
# Initialize Quart app (async-capable Flask alternative)
# Configure static folder for serving admin dashboard and other static assets
app = Quart(__name__, static_folder='static', static_url_path='/static')

# ============================================================
# CORS CONFIGURATION
# ============================================================
# Configure Cross-Origin Resource Sharing for security
# For testing: Allow all origins
# For production: Restrict to specific domains
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")  # Use "*" for testing, specific domains for production

# Apply CORS to the app
# Note: allow_credentials cannot be True when allow_origin is "*"
# For wildcard origins, set allow_credentials to False
app = cors(
    app,
    allow_origin=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=False if ALLOWED_ORIGINS == "*" else True,
    max_age=3600  # Cache preflight requests for 1 hour
)

logger = logging.getLogger(__name__)
logger.info(f"CORS enabled with allowed origins: {ALLOWED_ORIGINS}")

# ============================================================
# RATE LIMITING CONFIGURATION
# ============================================================
# Protect against DoS attacks and API abuse using custom lightweight rate limiter
# No external dependencies required - works with single-instance deployments

# Rate limit settings in seconds (can be customized via environment variables)
RATE_LIMIT_UPLOADS_COUNT = int(os.environ.get("RATE_LIMIT_UPLOADS_COUNT", "10"))
RATE_LIMIT_UPLOADS_WINDOW = int(os.environ.get("RATE_LIMIT_UPLOADS_WINDOW", "3600"))  # 1 hour

RATE_LIMIT_API_COUNT = int(os.environ.get("RATE_LIMIT_API_COUNT", "100"))
RATE_LIMIT_API_WINDOW = int(os.environ.get("RATE_LIMIT_API_WINDOW", "3600"))  # 1 hour

RATE_LIMIT_ADMIN_COUNT = int(os.environ.get("RATE_LIMIT_ADMIN_COUNT", "50"))
RATE_LIMIT_ADMIN_WINDOW = int(os.environ.get("RATE_LIMIT_ADMIN_WINDOW", "3600"))  # 1 hour

logger.info(f"Rate limiting enabled - Uploads: {RATE_LIMIT_UPLOADS_COUNT}/{RATE_LIMIT_UPLOADS_WINDOW}s, "
            f"API: {RATE_LIMIT_API_COUNT}/{RATE_LIMIT_API_WINDOW}s, "
            f"Admin: {RATE_LIMIT_ADMIN_COUNT}/{RATE_LIMIT_ADMIN_WINDOW}s")

# Schedule periodic cleanup to prevent memory growth
async def cleanup_rate_limiter():
    """Background task to cleanup old rate limiter entries."""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        get_rate_limiter().cleanup_old_entries()
        logger.debug("Rate limiter cleanup completed")

# Start cleanup task
@app.before_serving
async def start_cleanup_task():
    app.add_background_task(cleanup_rate_limiter)


# ============================================================
# AZURE COMMUNICATION SERVICES CONFIGURATION
# ============================================================
# Load required environment variables into app.config
# ACS connection string for telephony integration
app.config["ACS_CONNECTION_STRING"] = os.environ.get("ACS_CONNECTION_STRING")

# ============================================================
# AZURE VOICE LIVE API CONFIGURATION
# ============================================================
# Voice Live endpoint and model for conversational AI
app.config["AZURE_VOICE_LIVE_ENDPOINT"] = os.environ.get("AZURE_VOICE_LIVE_ENDPOINT")
app.config["VOICE_LIVE_MODEL"] = os.environ.get("VOICE_LIVE_MODEL")

# Authentication: Managed Identity (preferred) or API Key
app.config["AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID"] = os.environ.get("AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID")
app.config["VOICE_LIVE_API_KEY"] = os.environ.get("VOICE_LIVE_API_KEY")

# ============================================================
# AZURE AI SEARCH CONFIGURATION
# ============================================================
# Azure AI Search configuration (optional - for grounding responses on your data)
app.config["AZURE_SEARCH_ENDPOINT"] = os.environ.get("AZURE_SEARCH_ENDPOINT")
app.config["AZURE_SEARCH_INDEX"] = os.environ.get("AZURE_SEARCH_INDEX")
app.config["AZURE_SEARCH_API_KEY"] = os.environ.get("AZURE_SEARCH_API_KEY")
app.config["AZURE_SEARCH_SEMANTIC_CONFIG"] = os.environ.get("AZURE_SEARCH_SEMANTIC_CONFIG")
app.config["AZURE_SEARCH_TOP_N"] = int(os.environ.get("AZURE_SEARCH_TOP_N", "5"))  # Number of search results
app.config["AZURE_SEARCH_STRICTNESS"] = int(os.environ.get("AZURE_SEARCH_STRICTNESS", "3"))  # Relevance threshold

# ============================================================
# AZURE STORAGE CONFIGURATION
# ============================================================
# Azure Storage configuration (for document uploads)
app.config["AZURE_STORAGE_CONNECTION_STRING"] = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
app.config["AZURE_STORAGE_CONTAINER"] = os.environ.get("AZURE_STORAGE_CONTAINER", "documents")

# ============================================================
# AZURE OPENAI CONFIGURATION
# ============================================================
# Azure OpenAI configuration (for embeddings in document indexing and AI evaluation)
# Falls back to Voice Live endpoint if not separately configured
# Uses Managed Identity for authentication (no API key required in container)
app.config["AZURE_OPENAI_ENDPOINT"] = os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("AZURE_VOICE_LIVE_ENDPOINT")
app.config["AZURE_OPENAI_KEY"] = os.environ.get("AZURE_OPENAI_KEY")  # Optional: only for local development
app.config["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"] = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")

# ============================================================
# AZURE AD / ENTRA ID AUTHENTICATION CONFIGURATION
# ============================================================
# Azure AD configuration for API authentication
# These values come from your App Registration in Azure Portal
AZURE_AD_TENANT_ID = os.environ.get("AZURE_AD_TENANT_ID")
AZURE_AD_CLIENT_ID = os.environ.get("AZURE_AD_CLIENT_ID")
AZURE_AD_AUDIENCE = os.environ.get("AZURE_AD_AUDIENCE")  # Optional, defaults to api://{client_id}

# Initialize Azure AD authentication handler
# Set to None if not configured (allows running without auth in dev)
azure_ad_auth = None
if AZURE_AD_TENANT_ID and AZURE_AD_CLIENT_ID:
    azure_ad_auth = AzureADAuth(
        tenant_id=AZURE_AD_TENANT_ID,
        client_id=AZURE_AD_CLIENT_ID,
        audience=AZURE_AD_AUDIENCE
    )
    logging.info("Azure AD authentication enabled")
else:
    logging.warning("Azure AD authentication NOT configured - API endpoints are UNPROTECTED!")

# ============================================================
# INITIALIZE HANDLERS
# ============================================================
# Initialize ACS event handler for telephony integration
acs_handler = AcsEventHandler(app.config)

# Initialize document processor for upload, chunking, and indexing
# Uses Voice Live endpoint with Managed Identity for embeddings
document_processor = DocumentProcessor({
    "azure_storage_connection_string": app.config["AZURE_STORAGE_CONNECTION_STRING"],
    "azure_storage_container": app.config["AZURE_STORAGE_CONTAINER"],
    "azure_search_endpoint": app.config["AZURE_SEARCH_ENDPOINT"],
    "azure_search_index": app.config["AZURE_SEARCH_INDEX"],
    "azure_search_api_key": app.config["AZURE_SEARCH_API_KEY"],
    "azure_openai_endpoint": app.config["AZURE_VOICE_LIVE_ENDPOINT"],  # Use Voice Live endpoint
    "azure_openai_key": None,  # Managed Identity - no API key needed
    "azure_openai_embedding_deployment": app.config["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
    "azure_user_assigned_identity_client_id": app.config.get("AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID"),  # For Managed Identity
    "chunk_size": 1000,  # Size of text chunks for indexing
    "chunk_overlap": 200  # Overlap between chunks to preserve context
})

# ============================================================
# INITIALIZE CONVERSATION LOGGING & FEEDBACK SYSTEM
# ============================================================
from app.conversation_logger import get_conversation_logger
from app.gdpr_compliance import get_gdpr_compliance
from app.feedback_indexer import get_feedback_indexer
from app.analytics import get_analytics
from app.ai_evaluator import get_ai_evaluator

# Initialize conversation logger with PII anonymization
conversation_logger = None
gdpr_compliance = None
feedback_indexer = None
analytics = None
ai_evaluator = None

# Initialize at startup
@app.before_serving
async def initialize_feedback_system():
    """Initialize conversation logging and feedback system."""
    global conversation_logger, gdpr_compliance, feedback_indexer, analytics, ai_evaluator
    
    storage_conn = app.config["AZURE_STORAGE_CONNECTION_STRING"]
    
    if storage_conn:
        try:
            # Initialize conversation logger
            conversation_logger = get_conversation_logger(storage_conn)
            await conversation_logger.initialize()
            logger.info("Conversation logger initialized")
            
            # Initialize GDPR compliance
            gdpr_compliance = get_gdpr_compliance(storage_conn)
            await gdpr_compliance.initialize()
            logger.info("GDPR compliance initialized")
            
            # Initialize analytics
            analytics = get_analytics(storage_conn)
            await analytics.initialize()
            logger.info("Analytics initialized")
            
            # Initialize feedback indexer if search is configured
            # Uses Voice Live endpoint with Managed Identity for embeddings
            if (app.config.get("AZURE_SEARCH_ENDPOINT") and 
                app.config.get("AZURE_SEARCH_API_KEY") and
                app.config.get("AZURE_VOICE_LIVE_ENDPOINT")):
                
                feedback_indexer = get_feedback_indexer(
                    search_endpoint=app.config["AZURE_SEARCH_ENDPOINT"],
                    search_api_key=app.config["AZURE_SEARCH_API_KEY"],
                    storage_connection_string=storage_conn,
                    openai_endpoint=app.config["AZURE_VOICE_LIVE_ENDPOINT"],  # Use Voice Live endpoint
                    openai_api_key=None,  # Managed Identity - no API key needed
                    embedding_model=app.config.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"),
                    client_id=app.config.get("AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID")  # For Managed Identity
                )
                await feedback_indexer.initialize()
                logger.info("Feedback indexer initialized with Managed Identity")
            
            # Initialize AI evaluator for automatic response evaluation
            # Uses Azure Voice Live endpoint with Managed Identity authentication
            if app.config.get("AZURE_VOICE_LIVE_ENDPOINT"):
                
                # Use Voice Live model for evaluation
                # Use VOICE_LIVE_MODEL
                model_name = (
                    app.config.get("VOICE_LIVE_MODEL")
                ).strip()  # Remove any whitespace including leading/trailing spaces
                
                # Additional cleanup: remove any internal extra spaces
                model_name = " ".join(model_name.split())
                
                try:
                    # Use Managed Identity for authentication (same as Voice Live)
                    ai_evaluator = get_ai_evaluator(
                        azure_openai_endpoint=app.config["AZURE_VOICE_LIVE_ENDPOINT"],
                        deployment_name=model_name,
                        client_id=app.config.get("AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID"),
                    )
                    logger.info(f"AI evaluator initialized with deployment: '{model_name}' using Managed Identity")
                except Exception as e:
                    logger.error(f"Failed to initialize AI evaluator with deployment '{model_name}': {e}")
                    logger.warning("AI evaluation features will not be available")
        except Exception as e:
            logger.error(f"Error initializing feedback system: {e}")

@app.after_serving
async def cleanup_feedback_system():
    """Cleanup feedback system on shutdown."""
    if conversation_logger:
        await conversation_logger.close()
    if gdpr_compliance:
        await gdpr_compliance.close()
    if feedback_indexer:
        await feedback_indexer.close()
    if analytics:
        await analytics.close()

# ============================================================
# ACS TELEPHONY ENDPOINTS
# ============================================================

@app.route("/acs/incomingcall", methods=["POST"])
async def incoming_call_handler():
    """
    Handle initial incoming call event from EventGrid.
    
    This endpoint receives EventGrid events when someone calls the ACS phone number.
    It validates the subscription and processes incoming call events.
    
    Flow:
        1. Receive EventGrid event (subscription validation or incoming call)
        2. Parse and validate JSON body
        3. Forward to ACS handler for processing
        4. ACS handler answers call with WebSocket streaming
    
    Returns:
        Response: 200 OK with validation code or call answer confirmation
                 400 Bad Request if body is missing or invalid JSON
    """
    # Parse JSON body from EventGrid event
    try:
        events = await request.get_json()
    except Exception as e:
        logging.getLogger("incoming_call_handler").warning(
            "No body was attached to the request or invalid JSON: %s", e
        )
        return Response(response='{"error": "No body attached or invalid JSON"}', status=400, mimetype="application/json")

    # Validate that events were provided
    if not events:
        logging.getLogger("incoming_call_handler").warning("No body was attached to the request")
        return Response(response='{"error": "No body attached"}', status=400, mimetype="application/json")

    # Construct host URL for callbacks (ensure HTTPS)
    host_url = request.host_url.replace("http://", "https://", 1).rstrip("/")
    
    # Forward to ACS handler to answer the call
    return await acs_handler.process_incoming_call(events, host_url, app.config)


@app.route("/acs/callbacks/<context_id>", methods=["POST"])
async def acs_event_callbacks(context_id):
    """
    Handle ACS event callbacks for call connection and streaming events.
    
    This endpoint receives lifecycle events from ACS during an active call:
    - CallConnected: Call successfully established
    - MediaStreamingStarted: Audio streaming has begun
    - MediaStreamingStopped: Audio streaming has stopped
    - MediaStreamingFailed: Audio streaming encountered an error
    - CallDisconnected: Call has ended
    
    Args:
        context_id (str): Unique identifier for the call context (GUID)
    
    Returns:
        Response: 200 OK after processing events
                 400 Bad Request if body is missing or invalid JSON
    """
    # Parse JSON body containing ACS callback events
    try:
        raw_events = await request.get_json()
    except Exception as e:
        logging.getLogger("acs_event_callbacks").warning(
            "No body was attached to the request or invalid JSON: %s", e
        )
        return Response(response='{"error": "No body attached or invalid JSON"}', status=400, mimetype="application/json")

    # Validate that events were provided
    if not raw_events:
        logging.getLogger("acs_event_callbacks").warning("No body was attached to the request")
        return Response(response='{"error": "No body attached"}', status=400, mimetype="application/json")

    # Forward to ACS handler for logging and processing
    return await acs_handler.process_callback_events(context_id, raw_events, app.config)


# ============================================================
# WEBSOCKET ENDPOINTS - Audio Streaming
# ============================================================
# Note: Rate limiting not applied to WebSockets (not supported by quart-rate-limiter)
# WebSocket connection limits should be configured at the infrastructure level

@app.websocket("/acs/ws")
async def acs_ws():
    """
    WebSocket endpoint for ACS to send audio to Voice Live.
    
    This WebSocket handles bidirectional audio streaming for phone calls:
    - Receives caller audio from ACS in JSON format with Base64-encoded PCM
    - Forwards audio to Voice Live API
    - Receives AI responses from Voice Live
    - Sends AI audio back to ACS for playback to caller
    
    Flow:
        Phone Call → ACS → WebSocket (JSON+Base64) → Voice Live API →
        AI Response → WebSocket → ACS → Phone Call
    
    Connection Lifecycle:
        1. WebSocket connection established by ACS
        2. Handler initializes and connects to Voice Live
        3. Continuous message loop processes audio chunks
        4. Connection closed on exception or call end
    """
    logger = logging.getLogger("acs_ws")
    logger.info("Incoming ACS WebSocket connection")
    
    # Initialize media handler for this connection
    handler = ACSMediaHandler(app.config)
    
    # Set up incoming WebSocket (ACS sends JSON messages)
    await handler.init_incoming_websocket(websocket, is_raw_audio=False)
    
    # Set up conversation logging for phone channel
    if conversation_logger:
        session_id = f"acs-{uuid.uuid4()}"
        phone_number = request.args.get("phone")  # Get phone from query params if available
        handler.set_conversation_logger(conversation_logger, session_id, "phone", phone_number)
    
    # Connect to Voice Live API in background
    asyncio.create_task(handler.connect())
    
    # Main message loop - process ACS audio messages
    try:
        while True:
            # Receive message from ACS (JSON with Base64 audio)
            msg = await websocket.receive()
            # Forward to Voice Live API
            await handler.acs_to_voicelive(msg)
    except Exception:
        logger.exception("ACS WebSocket connection closed")
    finally:
        # End conversation logging
        if conversation_logger and handler.session_id:
            try:
                await conversation_logger.end_conversation(handler.session_id)
                logger.info("Conversation logging ended")
            except Exception as e:
                logger.error(f"Error ending conversation: {e}")


@app.websocket("/web/ws")
async def web_ws():
    """
    WebSocket endpoint for web clients to send audio to Voice Live.
    
    This WebSocket handles bidirectional audio streaming for browser-based chat:
    - Receives user audio from browser in raw binary PCM format
    - Forwards audio to Voice Live API
    - Receives AI responses from Voice Live
    - Sends AI audio back to browser for playback
    
    Flow:
        Browser Microphone → WebSocket (Raw PCM) → Voice Live API →
        AI Response → WebSocket → Browser Audio Output
    
    Connection Lifecycle:
        1. WebSocket connection established by browser (index.html)
        2. Handler initializes and connects to Voice Live
        3. Continuous message loop processes audio/text messages
        4. Connection closed on exception or user disconnect
    """
    logger = logging.getLogger("web_ws")
    logger.info("Incoming Web WebSocket connection")
    
    # Initialize media handler for this connection
    handler = ACSMediaHandler(app.config)
    
    # Set up incoming WebSocket (browser sends raw audio bytes)
    await handler.init_incoming_websocket(websocket, is_raw_audio=True)
    
    # Set up conversation logging for web channel
    if conversation_logger:
        session_id = f"web-{uuid.uuid4()}"
        handler.set_conversation_logger(conversation_logger, session_id, "web")
    
    # DON'T connect to Voice Live immediately - wait for custom instructions or first message
    # This allows the frontend to send custom instructions first
    voice_live_task = None
    
    # Track message count for debugging
    message_count = 0
    
    # Main message loop - process browser messages
    try:
        while True:
            # Receive message from browser (raw audio bytes or text)
            msg = await websocket.receive()
            message_count += 1
            
            # Handle binary audio data
            if isinstance(msg, (bytes, bytearray)):
                logger.debug("Received audio data, message #%d, size: %d bytes", message_count, len(msg))
                
                # Connect to Voice Live on first audio if not connected yet
                if not handler.voice_live_connected and voice_live_task is None:
                    logger.info("First audio received - connecting to Voice Live API")
                    voice_live_task = asyncio.create_task(handler.connect())
                    # Wait for connection to complete so custom instructions are used
                    await voice_live_task
                
                # Forward raw audio to Voice Live API
                await handler.web_to_voicelive(msg)
            # Handle text messages (e.g., configuration, commands)
            else:
                logger.info("Received text message #%d: %s", message_count, msg[:100] if len(msg) > 100 else msg)
                
                # Parse message to check if it's custom instructions
                try:
                    msg_data = json.loads(msg) if isinstance(msg, str) else {}
                    msg_type = msg_data.get("type")
                except:
                    msg_type = None
                
                # Connect to Voice Live on first non-instructions message if not connected yet
                if not handler.voice_live_connected and voice_live_task is None:
                    # Don't connect yet if this is the instructions message
                    if msg_type != "session.update_instructions":
                        logger.info("First user message received - connecting to Voice Live API")
                        voice_live_task = asyncio.create_task(handler.connect())
                        # Wait for connection to complete so custom instructions are used
                        await voice_live_task
                
                # Route text message to appropriate handler
                await handler.handle_websocket_message(msg)
    except Exception:
        logger.exception("Web WebSocket connection closed")
    finally:
        # End conversation logging
        if conversation_logger and handler.session_id:
            try:
                await conversation_logger.end_conversation(handler.session_id)
                logger.info("Conversation logging ended")
            except Exception as e:
                logger.error(f"Error ending conversation: {e}")


# ============================================================
# STATIC FILE SERVING
# ============================================================

@app.route("/")
async def index():
    """
    Serve the static index page (web chat interface).
    
    Returns:
        HTML: The main chat interface (index.html) with audio streaming capabilities
    """
    return await app.send_static_file("index.html")


@app.route("/static/<path:filename>")
async def serve_static(filename):
    """
    Serve static files from the static directory.
    
    This route handles all static assets including the admin dashboard,
    JavaScript files, CSS files, and images.
    
    Args:
        filename: Path to the file within the static directory
        
    Returns:
        File: The requested static file
    """
    from quart import send_from_directory
    import os
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    return await send_from_directory(static_dir, filename)


# ============================================================
# AI INSTRUCTIONS API
# ============================================================

@app.route("/api/instructions", methods=["GET"])
async def get_instructions():
    """
    Get the default AI system instructions.
    
    Returns the default instructions with placeholder examples.
    Placeholders are processed by the frontend before sending to Voice Live API.
    
    Returns:
        JSON: Object containing the default base_instructions with placeholders
    """
    # Return default instructions WITH PLACEHOLDERS as examples
    # Frontend will replace {{TODAY_IT}}, {{DAY_IT}}, etc. with actual values
    base_instructions = (
        "Sei un assistente virtuale farmacista che risponde in modo naturale e con frasi brevi. "
        "Parla in italiano, a meno che le domande non arrivino in altra lingua. "
        "Ricordati che oggi è {{TODAY_IT}}, {{DAY_IT}}, usa questa data come riferimento temporale per rispondere alle domande. "
        "Parla solo di argomenti inerenti la farmacia, se la ricerca non trova risultati rilevanti, rispondi 'Ti consiglio di contattare la farmacia.' "
        "Inizia la conversazione chiedendo 'Come posso esserti utile?'\n\n"
        "IMPORTANTE: Quando rispondi via testo (non voce), usa formattazione per migliorare la leggibilità:\n"
        "- Usa **grassetto** per evidenziare parole importanti\n"
        "- Usa elenchi puntati (- o •) per liste di farmaci, orari, o servizi\n"
        "- Vai a capo per separare concetti diversi\n"
        "- Usa elenchi numerati (1. 2. 3.) per istruzioni in sequenza\n"
        "Esempio: 'Ecco gli orari:\n- Lunedì: 9:00-19:00\n- Martedì: 9:00-19:00'"
    )
    
    return jsonify({"instructions": base_instructions}), 200


@app.route("/api/instructions", methods=["POST"])
async def save_instructions():
    """
    Save custom AI instructions (stored in session for next WebSocket connection).
    
    Note: This is a placeholder endpoint. The actual instructions are sent
    via WebSocket when the connection is established.
    
    Returns:
        JSON: Success message
    """
    try:
        data = await request.get_json()
        instructions = data.get("instructions")
        
        if not instructions:
            return jsonify({"error": "Instructions cannot be empty"}), 400
        
        # In a real implementation, you might store this in Redis or a database
        # For now, we just acknowledge receipt since the client will send
        # the instructions via WebSocket on connection
        logger.info("Received custom instructions (will be applied on next WebSocket connection)")
        
        return jsonify({"message": "Instructions received"}), 200
    
    except Exception as e:
        logger.exception("Error saving instructions")
        return jsonify({"error": str(e)}), 500


# ============================================================
# DOCUMENT MANAGEMENT API
# ============================================================

@app.route("/api/documents", methods=["POST"])
@rate_limit(max_requests=RATE_LIMIT_UPLOADS_COUNT, window_seconds=RATE_LIMIT_UPLOADS_WINDOW)
# Public for testing - no authentication required
async def upload_documents():
    """
    Upload and index documents to Azure Search for RAG.
    
```
    
    **Authentication**: None required (public endpoint for testing)
    
    This endpoint handles document uploads and processes them for knowledge base:
    1. Validate file size (max 10MB) and type (pdf, docx, doc, txt)
    2. Upload to Azure Blob Storage
    3. Extract text content
    4. Chunk text into smaller segments
    5. Generate embeddings using Azure OpenAI
    6. Index in Azure AI Search for retrieval
    
    Supported file types: .pdf, .docx, .doc, .txt
    
    Returns:
        JSON: Results for each uploaded file with status (success/error)
        200 OK: All files processed (check individual results for errors)
        400 Bad Request: No files provided
        401 Unauthorized: Missing or invalid authentication
        403 Forbidden: Insufficient permissions
        500 Internal Server Error: Processing failure
    """
    logger = logging.getLogger("upload_documents")
    
    # Log authenticated user if available
    if hasattr(g, 'user'):
        logger.info("Document upload by user: %s (%s)", 
                   g.user.get('username'), g.user.get('roles'))
    
    try:
        # Get uploaded files from multipart form data
        files = await request.files
        
        # Validate that files were provided
        if not files:
            return jsonify({"error": "No files provided"}), 400
        
        # Track results for each file
        results = []
        
        # ============================================================
        # PROCESS EACH UPLOADED FILE
        # ============================================================
        for field_name in files:
            file_list = files.getlist(field_name)
            
            for file in file_list:
                logger.info(f"Processing file: {file.filename}")
                
                # Read file content into memory
                file_content = file.read()
                
                # ============================================================
                # VALIDATE FILE SIZE
                # ============================================================
                # Validate file size (max 10MB)
                if len(file_content) > 10 * 1024 * 1024:
                    results.append({
                        "filename": file.filename,
                        "status": "error",
                        "error": "File too large (max 10MB)"
                    })
                    continue
                
                # ============================================================
                # VALIDATE FILE TYPE
                # ============================================================
                # Validate file type by extension
                allowed_extensions = ['.pdf', '.docx', '.doc', '.txt']
                file_ext = os.path.splitext(file.filename)[1].lower()
                
                if file_ext not in allowed_extensions:
                    results.append({
                        "filename": file.filename,
                        "status": "error",
                        "error": f"Unsupported file type: {file_ext}"
                    })
                    continue
                
                # ============================================================
                # PROCESS AND INDEX DOCUMENT
                # ============================================================
                # Upload to Blob Storage, extract text, chunk, embed, and index
                result = await document_processor.upload_and_index_document(
                    file_content=file_content,
                    filename=file.filename,
                    content_type=file.content_type or "application/octet-stream"
                )
                
                results.append(result)
        
        # Return results for all uploaded files
        return jsonify({"results": results}), 200
    
    except Exception as e:
        logger.error(f"Error uploading documents: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/documents", methods=["GET"])
@rate_limit(max_requests=RATE_LIMIT_API_COUNT, window_seconds=RATE_LIMIT_API_WINDOW)
# GET documents is public - no authentication required for viewing
async def list_documents():
    """
    List all indexed documents in Azure Search.
    
    **Authentication**: None required (public endpoint)
    
    Retrieves metadata for all documents currently indexed in the knowledge base.
    Useful for displaying available documents to users or administrators.
    
    Returns:
        JSON: List of documents with metadata (id, filename, upload date, etc.)
        200 OK: Documents retrieved successfully
        401 Unauthorized: Missing or invalid authentication
        403 Forbidden: Insufficient permissions
        500 Internal Server Error: Query failure
    """
    logger = logging.getLogger("list_documents")
    
    try:
        # Query Azure Search for all indexed documents
        documents = await document_processor.list_documents()
        return jsonify({"documents": documents}), 200
    
    except Exception as e:
        logger.error(f"Error listing documents: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/documents/<path:document_id>", methods=["DELETE"])
@rate_limit(max_requests=RATE_LIMIT_API_COUNT, window_seconds=RATE_LIMIT_API_WINDOW)
# Public for testing - no authentication required
async def delete_document(document_id):
    """
    Delete a document from Azure Search and Blob Storage.
    
    **Authentication**: None required (public endpoint for testing)
    
    Removes a document from the knowledge base:
    1. Delete from Azure AI Search index
    2. Delete from Azure Blob Storage
    
    Args:
        document_id (str): Unique identifier of the document to delete
    
    Returns:
        JSON: Success or error message
        200 OK: Document deleted successfully
        500 Internal Server Error: Deletion failure
    """
    logger = logging.getLogger("delete_document")
    
    try:
        # Delete from both Search and Storage
        success = await document_processor.delete_document(document_id)
        
        if success:
            return jsonify({"message": "Document deleted successfully"}), 200
        else:
            return jsonify({"error": "Failed to delete document"}), 500
    
    except Exception as e:
        logger.error(f"Error deleting document: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================================
# AZURE SEARCH INDEXER MANAGEMENT API
# ============================================================

@app.route("/api/indexer/create", methods=["POST"])
@rate_limit(max_requests=RATE_LIMIT_ADMIN_COUNT, window_seconds=RATE_LIMIT_ADMIN_WINDOW)
# Public for testing - no authentication required
async def create_indexer():
    """
    Create an Azure Search Indexer for automatic document processing.
    
    **Authentication**: None required (public endpoint for testing)
    
    Sets up an automated pipeline that:
    1. Monitors Azure Blob Storage container for new documents
    2. Automatically extracts text from uploaded files
    3. Generates embeddings and indexes content
    4. Keeps search index synchronized with storage
    
    This enables "drop files in blob storage and they get indexed automatically"
    workflow instead of manual API uploads.
    
    Returns:
        JSON: Indexer creation result with status and details
        200 OK: Indexer created successfully
        401 Unauthorized: Missing or invalid authentication
        403 Forbidden: Insufficient permissions (requires Admin role)
        500 Internal Server Error: Creation failure
    """
    logger = logging.getLogger("create_indexer")
    
    try:
        # Create indexer, data source, and skillset
        result = await document_processor.create_indexer()
        
        if result["status"] == "success":
            return jsonify(result), 200
        else:
            return jsonify(result), 500
    
    except Exception as e:
        logger.error(f"Error creating indexer: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/test-logs", methods=["POST"])
@rate_limit(max_requests=RATE_LIMIT_API_COUNT, window_seconds=RATE_LIMIT_API_WINDOW)
async def save_test_logs():
    """
    Save user simulation test results to Azure Blob Storage.
    
    **Authentication**: None required (public endpoint for testing)
    
    Receives test results from the test-bot.html page and saves them 
    to Azure Blob Storage in the 'TestLogs' container as JSON files.
    
    Request Body:
        JSON object with test results containing:
        - timestamp: Test execution timestamp
        - configuration: Test configuration (dialog count, turns, percentages)
        - metrics: Test metrics (accuracy, context retention, etc.)
        - dialogs: Array of dialog results
        - criticalIssues: Array of critical issues found
    
    Returns:
        JSON: Save result with status and blob name
        200 OK: Test logs saved successfully
        400 Bad Request: Invalid request body
        500 Internal Server Error: Save failure
    """
    logger = logging.getLogger("save_test_logs")
    
    try:
        # Get JSON body from request
        test_data = await request.get_json()
        
        if not test_data:
            return jsonify({"error": "No test data provided"}), 400
        
        # Add server-side timestamp if not present
        if 'timestamp' not in test_data:
            from datetime import datetime
            test_data['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        
        # Generate blob name based on timestamp
        from datetime import datetime
        timestamp_str = test_data.get('timestamp', datetime.utcnow().isoformat() + 'Z')
        # Clean timestamp for filename (remove special chars)
        clean_timestamp = timestamp_str.replace(':', '-').replace('.', '-')
        blob_name = f"test-{clean_timestamp}.json"
        
        # Import Azure Storage Blob client
        from azure.storage.blob import BlobServiceClient, ContentSettings
        import asyncio
        
        # Get connection string from config
        connection_string = app.config["AZURE_STORAGE_CONNECTION_STRING"]
        if not connection_string:
            logger.error("AZURE_STORAGE_CONNECTION_STRING not configured")
            return jsonify({"error": "Azure Storage not configured"}), 500
        
        # Function to upload blob (sync operation wrapped for async)
        def upload_to_blob():
            # Create blob service client
            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
            
            # Get or create TestLogs container
            container_name = "testlogs"
            container_client = blob_service_client.get_container_client(container_name)
            
            # Create container if it doesn't exist
            try:
                container_client.create_container()
                logger.info(f"Created container: {container_name}")
            except Exception as e:
                # Container might already exist, which is fine
                if "ContainerAlreadyExists" not in str(e):
                    logger.warning(f"Container creation note: {e}")
            
            # Upload test data as JSON blob
            blob_client = container_client.get_blob_client(blob_name)
            test_json = json.dumps(test_data, indent=2, ensure_ascii=False)
            blob_client.upload_blob(test_json, overwrite=True)
            
            return container_name
        
        # Run sync operation in executor
        loop = asyncio.get_event_loop()
        container_name = await loop.run_in_executor(None, upload_to_blob)
        
        logger.info(f"Test logs saved successfully: {blob_name}")
        
        return jsonify({
            "status": "success",
            "message": "Test logs saved successfully",
            "blob_name": blob_name,
            "container": container_name
        }), 200
    
    except Exception as e:
        logger.error(f"Error saving test logs: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/test-logs", methods=["GET"])
@rate_limit(max_requests=RATE_LIMIT_API_COUNT, window_seconds=RATE_LIMIT_API_WINDOW)
async def get_test_logs():
    """
    Retrieve all test logs from Azure Blob Storage.
    
    **Authentication**: None required (public endpoint for testing)
    
    Returns a list of all test results saved in the 'testlogs' container.
    Each test includes metadata and full results.
    
    Returns:
        JSON: List of test results
        200 OK: Tests retrieved successfully
        500 Internal Server Error: Retrieval failure
    """
    logger = logging.getLogger("get_test_logs")
    
    try:
        from azure.storage.blob import BlobServiceClient
        import asyncio
        
        # Get connection string from config
        connection_string = app.config["AZURE_STORAGE_CONNECTION_STRING"]
        if not connection_string:
            logger.error("AZURE_STORAGE_CONNECTION_STRING not configured")
            return jsonify({"error": "Azure Storage not configured"}), 500
        
        # Function to retrieve all test logs (sync operation wrapped for async)
        def get_all_tests():
            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
            container_client = blob_service_client.get_container_client("testlogs")
            
            tests = []
            
            try:
                # List all blobs in container
                blobs = container_client.list_blobs()
                
                for blob in blobs:
                    # Download and parse each blob
                    blob_client = container_client.get_blob_client(blob.name)
                    content = blob_client.download_blob().readall()
                    test_data = json.loads(content)
                    test_data['blob_name'] = blob.name
                    tests.append(test_data)
                    
            except Exception as e:
                # Container might not exist yet
                if "ContainerNotFound" in str(e) or "The specified container does not exist" in str(e):
                    logger.info("Container 'testlogs' does not exist yet - returning empty list")
                    return []
                raise
            
            return tests
        
        # Run sync operation in executor
        loop = asyncio.get_event_loop()
        tests = await loop.run_in_executor(None, get_all_tests)
        
        logger.info(f"Retrieved {len(tests)} test logs")
        
        return jsonify({"tests": tests, "count": len(tests)}), 200
    
    except Exception as e:
        logger.error(f"Error retrieving test logs: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/indexer/run", methods=["POST"])
@rate_limit(max_requests=RATE_LIMIT_ADMIN_COUNT, window_seconds=RATE_LIMIT_ADMIN_WINDOW)
# Public for testing - no authentication required
async def run_indexer():
    """
    Manually trigger the indexer to process documents.
    
    **Authentication**: None required (public endpoint for testing)
    
    Forces the indexer to run immediately instead of waiting for its schedule.
    Useful for:
    - Processing newly uploaded documents right away
    - Re-indexing after configuration changes
    - Testing indexer functionality
    
    Returns:
        JSON: Indexer run result with status
        200 OK: Indexer triggered successfully
        401 Unauthorized: Missing or invalid authentication
        403 Forbidden: Insufficient permissions (requires Admin role)
        500 Internal Server Error: Trigger failure
    """
    logger = logging.getLogger("run_indexer")
    
    try:
        # Trigger indexer execution
        result = await document_processor.run_indexer()
        
        if result["status"] == "success":
            return jsonify(result), 200
        else:
            return jsonify(result), 500
    
    except Exception as e:
        logger.error(f"Error running indexer: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/indexer/status", methods=["GET"])
@rate_limit(max_requests=RATE_LIMIT_API_COUNT, window_seconds=RATE_LIMIT_API_WINDOW)
# GET status is public - no authentication required for viewing
async def get_indexer_status():
    """
    Get the current status of the indexer.
    
    **Authentication**: None required (public endpoint)
    
    Returns information about:
    - Indexer execution history
    - Last run timestamp
    - Success/failure status
    - Number of documents processed
    - Any errors encountered
    
    Useful for monitoring and troubleshooting automated indexing.
    
    Returns:
        JSON: Indexer status details
        200 OK: Status retrieved successfully
        401 Unauthorized: Missing or invalid authentication
        403 Forbidden: Insufficient permissions
        404 Not Found: Indexer doesn't exist
        500 Internal Server Error: Query failure
    """
    logger = logging.getLogger("get_indexer_status")
    
    try:
        # Query indexer status from Azure Search
        result = await document_processor.get_indexer_status()
        
        if result["status"] == "success":
            return jsonify(result), 200
        else:
            return jsonify(result), 404
    
    except Exception as e:
        logger.error(f"Error getting indexer status: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================================
# ADMIN API ENDPOINTS - CONVERSATION REVIEW & FEEDBACK
# ============================================================

@app.route("/admin/api/conversations", methods=["GET"])
@rate_limit(max_requests=RATE_LIMIT_API_COUNT, window_seconds=RATE_LIMIT_API_WINDOW)
@require_auth_optional(azure_ad_auth)
async def get_conversations():
    """
    List all conversations with optional filters.
    
    Query parameters:
        - page: Page number (default: 1)
        - page_size: Items per page (default: 50)
        - channel: Filter by channel (web|phone)
        - start_date: Filter from date (ISO format)
        - end_date: Filter until date (ISO format)
    
    Returns:
        JSON: List of conversations with metadata
    """
    logger_endpoint = logging.getLogger("get_conversations")
    
    try:
        # Parse query parameters
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 50))
        channel_filter = request.args.get("channel")
        start_date_str = request.args.get("start_date")
        end_date_str = request.args.get("end_date")
        
        # Parse dates
        start_date = datetime.fromisoformat(start_date_str) if start_date_str else None
        end_date = datetime.fromisoformat(end_date_str) if end_date_str else None
        
        # Get conversations from storage
        conversations_list = []
        container_client = conversation_logger.blob_service_client.get_container_client("conversations")
        
        async for blob in container_client.list_blobs():
            # Apply date filter
            if start_date and blob.creation_time and blob.creation_time.replace(tzinfo=timezone.utc) < start_date:
                continue
            if end_date and blob.creation_time and blob.creation_time.replace(tzinfo=timezone.utc) > end_date:
                continue
            
            # Download conversation
            blob_client = container_client.get_blob_client(blob.name)
            content = await blob_client.download_blob()
            conv = json.loads(await content.readall())
            
            # Apply channel filter
            if channel_filter and conv.get("channel") != channel_filter:
                continue
            
            # Add to list
            conversations_list.append({
                "id": conv.get("id"),
                "timestamp": conv.get("timestamp"),
                "channel": conv.get("channel"),
                "total_turns": len(conv.get("turns", [])),
                "duration_seconds": conv.get("metadata", {}).get("duration_seconds", 0),
                "pii_detected": bool(conv.get("pii_detected_types")),
            })
        
        # Sort by timestamp (newest first)
        conversations_list.sort(key=lambda x: x["timestamp"], reverse=True)
        
        # Paginate
        total_count = len(conversations_list)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated = conversations_list[start_idx:end_idx]
        
        return jsonify({
            "conversations": paginated,
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": (total_count + page_size - 1) // page_size
        }), 200
        
    except Exception as e:
        logger_endpoint.error(f"Error getting conversations: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/admin/api/conversations/<conversation_id>", methods=["GET"])
@rate_limit(max_requests=RATE_LIMIT_API_COUNT, window_seconds=RATE_LIMIT_API_WINDOW)
@require_auth_optional(azure_ad_auth)
async def get_conversation_detail(conversation_id: str):
    """
    Get detailed conversation data.
    
    Returns:
        JSON: Full conversation with all turns
    """
    logger_endpoint = logging.getLogger("get_conversation_detail")
    
    try:
        container_client = conversation_logger.blob_service_client.get_container_client("conversations")
        
        # Find conversation by ID
        async for blob in container_client.list_blobs():
            if conversation_id in blob.name:
                blob_client = container_client.get_blob_client(blob.name)
                content = await blob_client.download_blob()
                conv = json.loads(await content.readall())
                return jsonify(conv), 200
        
        return jsonify({"error": "Conversation not found"}), 404
        
    except Exception as e:
        logger_endpoint.error(f"Error getting conversation detail: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/admin/api/feedback/<conversation_id>", methods=["POST"])
@rate_limit(max_requests=RATE_LIMIT_API_COUNT, window_seconds=RATE_LIMIT_API_WINDOW)
@require_auth_optional(azure_ad_auth)
async def submit_feedback():
    """
    Submit feedback for a conversation turn.
    
    Request body:
        {
            "conversation_id": "conv-...",
            "turn_number": 2,
            "rating": 4,
            "tags": ["helpful", "accurate"],
            "admin_comment": "Good response",
            "corrected_response": "..."
        }
    
    Returns:
        JSON: Feedback ID
    """
    logger_endpoint = logging.getLogger("submit_feedback")
    
    try:
        data = await request.get_json()
        
        conversation_id = data.get("conversation_id")
        turn_number = data.get("turn_number")
        rating = data.get("rating", 3)
        tags = data.get("tags", [])
        admin_comment = data.get("admin_comment", "")
        corrected_response = data.get("corrected_response", "")
        
        # Create feedback entry
        feedback_id = f"fb-{conversation_id}-turn{turn_number}"
        feedback = {
            "feedback_id": feedback_id,
            "conversation_id": conversation_id,
            "turn_number": turn_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "admin_user": g.get("user_email", "admin@pharmacy.com"),
            "rating": rating,
            "tags": tags,
            "admin_comment": admin_comment,
            "corrected_response": corrected_response,
            "approved": False
        }
        
        # Save to storage
        feedback_container = conversation_logger.blob_service_client.get_container_client("feedback")
        
        # Ensure container exists
        try:
            await feedback_container.get_container_properties()
        except:
            await feedback_container.create_container()
        
        blob_name = f"{feedback_id}.json"
        blob_client = feedback_container.get_blob_client(blob_name)
        await blob_client.upload_blob(
            json.dumps(feedback, indent=2, ensure_ascii=False),
            overwrite=True,
            content_settings=ContentSettings(content_type="application/json")
        )
        
        logger_endpoint.info(f"Feedback submitted: {feedback_id}")
        
        return jsonify({"feedback_id": feedback_id, "status": "success"}), 201
        
    except Exception as e:
        logger_endpoint.error(f"Error submitting feedback: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/admin/api/approve/<conversation_id>/<int:turn_number>", methods=["POST"])
@rate_limit(max_requests=RATE_LIMIT_API_COUNT, window_seconds=RATE_LIMIT_API_WINDOW)
@require_auth_optional(azure_ad_auth)
async def approve_response(conversation_id: str, turn_number: int):
    """
    Approve a response for learning (index in Azure AI Search).
    
    Returns:
        JSON: Approval status
    """
    logger_endpoint = logging.getLogger("approve_response")
    
    try:
        if not feedback_indexer:
            return jsonify({"error": "Feedback indexer not configured"}), 503
        
        # Get conversation
        container_client = conversation_logger.blob_service_client.get_container_client("conversations")
        
        conv = None
        async for blob in container_client.list_blobs():
            if conversation_id in blob.name:
                blob_client = container_client.get_blob_client(blob.name)
                content = await blob_client.download_blob()
                conv = json.loads(await content.readall())
                break
        
        if not conv:
            return jsonify({"error": "Conversation not found"}), 404
        
        # Find the turn
        turn = next((t for t in conv.get("turns", []) if t["turn_number"] == turn_number), None)
        if not turn:
            return jsonify({"error": "Turn not found"}), 404
        
        # Get feedback if exists
        feedback_id = f"fb-{conversation_id}-turn{turn_number}"
        feedback_container = conversation_logger.blob_service_client.get_container_client("feedback")
        
        corrected_response = None
        rating = 5
        tags = ["approved"]
        admin_comment = ""
        
        try:
            feedback_blob = feedback_container.get_blob_client(f"{feedback_id}.json")
            feedback_content = await feedback_blob.download_blob()
            feedback_data = json.loads(await feedback_content.readall())
            
            corrected_response = feedback_data.get("corrected_response")
            rating = feedback_data.get("rating", 5)
            tags = feedback_data.get("tags", ["approved"])
            admin_comment = feedback_data.get("admin_comment", "")
            
            # Mark as approved
            feedback_data["approved"] = True
            await feedback_blob.upload_blob(
                json.dumps(feedback_data, indent=2, ensure_ascii=False),
                overwrite=True
            )
        except:
            pass  # No feedback exists
        
        # Build context from previous turns
        context = ""
        if turn_number > 1:
            prev_turns = [t for t in conv.get("turns", []) if t["turn_number"] < turn_number][-2:]
            context = " ".join([f"U: {t['user_message']} B: {t['bot_response']}" for t in prev_turns])
        
        # Index in Azure AI Search
        doc_id = await feedback_indexer.index_approved_response(
            conversation_id=conversation_id,
            turn_number=turn_number,
            user_query=turn["user_message"],
            approved_response=corrected_response or turn["bot_response"],
            original_response=turn["bot_response"],
            admin_comment=admin_comment,
            rating=rating,
            tags=tags,
            context=context
        )
        
        logger_endpoint.info(f"Approved and indexed response: {doc_id}")
        
        return jsonify({"doc_id": doc_id, "status": "approved"}), 200
        
    except Exception as e:
        logger_endpoint.error(f"Error approving response: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/admin/api/analytics/dashboard", methods=["GET"])
@rate_limit(max_requests=RATE_LIMIT_API_COUNT, window_seconds=RATE_LIMIT_API_WINDOW)
@require_auth_optional(azure_ad_auth)
async def get_analytics_dashboard():
    """
    Get comprehensive analytics dashboard data.
    
    Returns:
        JSON: Dashboard metrics and trends
    """
    logger_endpoint = logging.getLogger("get_analytics_dashboard")
    
    try:
        if not analytics:
            return jsonify({"error": "Analytics not initialized"}), 503
        
        dashboard_data = await analytics.get_dashboard_data()
        return jsonify(dashboard_data), 200
        
    except Exception as e:
        logger_endpoint.error(f"Error getting analytics: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================================
# AI EVALUATION ENDPOINTS
# ============================================================

@app.route("/admin/api/evaluate/<conversation_id>", methods=["POST"])
@rate_limit(max_requests=RATE_LIMIT_API_COUNT, window_seconds=RATE_LIMIT_API_WINDOW)
@require_auth_optional(azure_ad_auth)
async def evaluate_conversation(conversation_id: str):
    """
    Valuta tutte le risposte della conversazione.
    
    Ritorna:
        JSON: Risultati della valutazione con punteggi e priorità
    """
    logger_endpoint = logging.getLogger("evaluate_conversation")
    
    try:
        if not ai_evaluator:
            logger_endpoint.error("AI evaluator not initialized - check Azure OpenAI configuration")
            return jsonify({"error": "AI evaluator not initialized - check Azure OpenAI configuration"}), 503
        
        if not conversation_logger:
            logger_endpoint.error("Conversation logger not initialized")
            return jsonify({"error": "Conversation logger not initialized"}), 503
        
        # Get conversation
        logger_endpoint.info(f"Fetching conversation {conversation_id}")
        container_client = conversation_logger.blob_service_client.get_container_client("conversations")
        
        conversation = None
        async for blob in container_client.list_blobs():
            if conversation_id in blob.name:
                blob_client = container_client.get_blob_client(blob.name)
                content = await blob_client.download_blob()
                conversation = json.loads(await content.readall())
                break
        
        if not conversation:
            logger_endpoint.error(f"Conversation {conversation_id} not found in storage")
            return jsonify({"error": "Conversation not found"}), 404
        
        # Evaluate conversation
        logger_endpoint.info(f"Starting AI evaluation for conversation {conversation_id}")
        evaluation = await ai_evaluator.evaluate_conversation(conversation)
        logger_endpoint.info(f"AI evaluation completed for {conversation_id}")
        
        # Store evaluation in blob storage
        evaluations_container = conversation_logger.blob_service_client.get_container_client("evaluations")
        try:
            await evaluations_container.get_container_properties()
        except:
            await evaluations_container.create_container()
        
        eval_blob_name = f"eval-{conversation_id}.json"
        eval_blob_client = evaluations_container.get_blob_client(eval_blob_name)
        await eval_blob_client.upload_blob(
            json.dumps(evaluation, indent=2, ensure_ascii=False),
            overwrite=True,
            content_settings=ContentSettings(content_type="application/json")
        )
        
        logger_endpoint.info(
            f"Evaluated conversation {conversation_id}: "
            f"score={evaluation['overall_score']}, needs_review={evaluation['needs_review']}"
        )
        
        return jsonify(evaluation), 200
        
    except Exception as e:
        logger_endpoint.error(f"Error evaluating conversation: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/admin/api/evaluate/<conversation_id>/<int:turn_number>", methods=["POST"])
@rate_limit(max_requests=RATE_LIMIT_API_COUNT, window_seconds=RATE_LIMIT_API_WINDOW)
@require_auth_optional(azure_ad_auth)
async def evaluate_turn(conversation_id: str, turn_number: int):
    """
    Valuta una singola risposta della conversazione.
    
    Ritorna:
        JSON: Risultati della valutazione per la risposta
    """
    logger_endpoint = logging.getLogger("evaluate_turn")
    
    try:
        if not ai_evaluator:
            return jsonify({"error": "AI evaluator not initialized"}), 503
        
        # Get conversation
        container_client = conversation_logger.blob_service_client.get_container_client("conversations")
        
        conversation = None
        async for blob in container_client.list_blobs():
            if conversation_id in blob.name:
                blob_client = container_client.get_blob_client(blob.name)
                content = await blob_client.download_blob()
                conversation = json.loads(await content.readall())
                break
        
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404
        
        # Find the specific turn
        turns = conversation.get("turns", [])
        turn = next((t for t in turns if t.get("turn_number") == turn_number), None)
        
        if not turn:
            return jsonify({"error": "Turn not found"}), 404
        
        # Build context from previous turns
        context = ""
        previous_turns = [t for t in turns if t.get("turn_number", 0) < turn_number]
        if previous_turns:
            context_parts = []
            for prev_turn in previous_turns[-3:]:  # Last 3 turns
                context_parts.append(
                    f"Turn {prev_turn.get('turn_number')}: "
                    f"User: {prev_turn.get('user_message')} | "
                    f"Bot: {prev_turn.get('bot_response')}"
                )
            context = "\n".join(context_parts)
        
        # Evaluate the turn
        evaluation = await ai_evaluator.evaluate_response(
            user_message=turn.get("user_message", ""),
            bot_response=turn.get("bot_response", ""),
            context=context if context else None
        )
        
        logger_endpoint.info(
            f"Evaluated turn {turn_number} in {conversation_id}: "
            f"score={evaluation['overall_score']}, priority={evaluation['priority']}"
        )
        
        return jsonify(evaluation), 200
        
    except Exception as e:
        logger_endpoint.error(f"Error evaluating turn: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/admin/api/evaluations/<conversation_id>", methods=["GET"])
@rate_limit(max_requests=RATE_LIMIT_API_COUNT, window_seconds=RATE_LIMIT_API_WINDOW)
@require_auth_optional(azure_ad_auth)
async def get_evaluation(conversation_id: str):
    """
    Get stored evaluation for a conversation.
    
    Returns:
        JSON: Evaluation results if available
    """
    logger_endpoint = logging.getLogger("get_evaluation")
    
    try:
        evaluations_container = conversation_logger.blob_service_client.get_container_client("evaluations")
        
        eval_blob_name = f"eval-{conversation_id}.json"
        
        try:
            eval_blob_client = evaluations_container.get_blob_client(eval_blob_name)
            content = await eval_blob_client.download_blob()
            evaluation = json.loads(await content.readall())
            return jsonify(evaluation), 200
        except:
            return jsonify({"message": "No evaluation found"}), 404
        
    except Exception as e:
        logger_endpoint.error(f"Error getting evaluation: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================================
# GDPR COMPLIANCE ENDPOINTS
# ============================================================

@app.route("/api/gdpr/data-access", methods=["POST"])
@rate_limit(max_requests=10, window_seconds=3600)
async def gdpr_data_access():
    """
    Handle GDPR data access request (Right to Access).
    
    Request body:
        {
            "session_id": "..." OR "phone_number": "+39..."
        }
    
    Returns:
        JSON: User's conversation data (anonymized)
    """
    logger_endpoint = logging.getLogger("gdpr_data_access")
    
    try:
        data = await request.get_json()
        session_id = data.get("session_id")
        phone_number = data.get("phone_number")
        
        if not gdpr_compliance:
            return jsonify({"error": "GDPR compliance not initialized"}), 503
        
        result = await gdpr_compliance.handle_data_access_request(
            session_id=session_id,
            phone_number=phone_number
        )
        
        if result:
            return jsonify(result), 200
        else:
            return jsonify({"message": "No data found"}), 404
            
    except Exception as e:
        logger_endpoint.error(f"Error handling data access request: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/gdpr/data-erasure", methods=["DELETE"])
@rate_limit(max_requests=10, window_seconds=3600)
async def gdpr_data_erasure():
    """
    Handle GDPR data erasure request (Right to be Forgotten).
    
    Request body:
        {
            "session_id": "..." OR "phone_number": "+39..."
        }
    
    Returns:
        JSON: Deletion summary
    """
    logger_endpoint = logging.getLogger("gdpr_data_erasure")
    
    try:
        data = await request.get_json()
        session_id = data.get("session_id")
        phone_number = data.get("phone_number")
        
        if not gdpr_compliance:
            return jsonify({"error": "GDPR compliance not initialized"}), 503
        
        result = await gdpr_compliance.handle_data_erasure_request(
            session_id=session_id,
            phone_number=phone_number,
            requester_info={"ip": request.remote_addr}
        )
        
        return jsonify(result), 200
            
    except Exception as e:
        logger_endpoint.error(f"Error handling data erasure request: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================================
# APPLICATION ENTRY POINT
# ============================================================

if __name__ == "__main__":
    # Run the Quart application
    # debug=True enables auto-reload and detailed error messages
    # host="0.0.0.0" allows external connections (not just localhost)
    # port=8000 is the default port for this application
    debug_mode = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode, host="0.0.0.0", port=8000)
