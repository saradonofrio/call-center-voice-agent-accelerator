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

import os
from app.handler.acs_event_handler import AcsEventHandler
from app.handler.acs_media_handler import ACSMediaHandler
from app.document_processor import DocumentProcessor
from app.auth import AzureADAuth, require_auth, require_auth_optional
from dotenv import load_dotenv
from quart import Quart, request, websocket, Response, jsonify, g

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
app = Quart(__name__)

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
# Azure OpenAI configuration (for embeddings in document indexing)
app.config["AZURE_OPENAI_ENDPOINT"] = os.environ.get("AZURE_OPENAI_ENDPOINT")
app.config["AZURE_OPENAI_KEY"] = os.environ.get("AZURE_OPENAI_KEY")
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
document_processor = DocumentProcessor({
    "azure_storage_connection_string": app.config["AZURE_STORAGE_CONNECTION_STRING"],
    "azure_storage_container": app.config["AZURE_STORAGE_CONTAINER"],
    "azure_search_endpoint": app.config["AZURE_SEARCH_ENDPOINT"],
    "azure_search_index": app.config["AZURE_SEARCH_INDEX"],
    "azure_search_api_key": app.config["AZURE_SEARCH_API_KEY"],
    "azure_openai_endpoint": app.config["AZURE_OPENAI_ENDPOINT"],
    "azure_openai_key": app.config["AZURE_OPENAI_KEY"],
    "azure_openai_embedding_deployment": app.config["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
    "chunk_size": 1000,  # Size of text chunks for indexing
    "chunk_overlap": 200  # Overlap between chunks to preserve context
})

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
    
    # Connect to Voice Live API in background
    asyncio.create_task(handler.connect())
    
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
                # Forward raw audio to Voice Live API
                await handler.web_to_voicelive(msg)
            # Handle text messages (e.g., configuration, commands)
            else:
                logger.info("Received text message #%d: %s", message_count, msg[:100] if len(msg) > 100 else msg)
                # Route text message to appropriate handler
                await handler.handle_websocket_message(msg)
    except Exception:
        logger.exception("Web WebSocket connection closed")


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


# ============================================================
# DOCUMENT MANAGEMENT API
# ============================================================

@app.route("/api/documents", methods=["POST"])
# Public for testing - no authentication required
async def upload_documents():
    """
    Upload and index documents to Azure Search for RAG.
    
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


@app.route("/api/indexer/run", methods=["POST"])
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
# APPLICATION ENTRY POINT
# ============================================================

if __name__ == "__main__":
    # Run the Quart application
    # debug=True enables auto-reload and detailed error messages
    # host="0.0.0.0" allows external connections (not just localhost)
    # port=8000 is the default port for this application
    debug_mode = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode, host="0.0.0.0", port=8000)
