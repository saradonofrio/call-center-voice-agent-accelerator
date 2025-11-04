import asyncio
import logging
import sys

import os
from app.handler.acs_event_handler import AcsEventHandler
from app.handler.acs_media_handler import ACSMediaHandler
from app.document_processor import DocumentProcessor
from dotenv import load_dotenv
from quart import Quart, request, websocket, Response, jsonify

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Changed from DEBUG to reduce log verbosity
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

# Azure AI Search configuration (optional - for grounding responses on your data)
app.config["AZURE_SEARCH_ENDPOINT"] = os.environ.get("AZURE_SEARCH_ENDPOINT")
app.config["AZURE_SEARCH_INDEX"] = os.environ.get("AZURE_SEARCH_INDEX")
app.config["AZURE_SEARCH_API_KEY"] = os.environ.get("AZURE_SEARCH_API_KEY")
app.config["AZURE_SEARCH_SEMANTIC_CONFIG"] = os.environ.get("AZURE_SEARCH_SEMANTIC_CONFIG")
app.config["AZURE_SEARCH_TOP_N"] = int(os.environ.get("AZURE_SEARCH_TOP_N", "5"))
app.config["AZURE_SEARCH_STRICTNESS"] = int(os.environ.get("AZURE_SEARCH_STRICTNESS", "3"))

# Azure Storage configuration (for document uploads)
app.config["AZURE_STORAGE_CONNECTION_STRING"] = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
app.config["AZURE_STORAGE_CONTAINER"] = os.environ.get("AZURE_STORAGE_CONTAINER", "documents")

# Azure OpenAI configuration (for embeddings)
app.config["AZURE_OPENAI_ENDPOINT"] = os.environ.get("AZURE_OPENAI_ENDPOINT")
app.config["AZURE_OPENAI_KEY"] = os.environ.get("AZURE_OPENAI_KEY")
app.config["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"] = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")

acs_handler = AcsEventHandler(app.config)

# Initialize document processor
document_processor = DocumentProcessor({
    "azure_storage_connection_string": app.config["AZURE_STORAGE_CONNECTION_STRING"],
    "azure_storage_container": app.config["AZURE_STORAGE_CONTAINER"],
    "azure_search_endpoint": app.config["AZURE_SEARCH_ENDPOINT"],
    "azure_search_index": app.config["AZURE_SEARCH_INDEX"],
    "azure_search_api_key": app.config["AZURE_SEARCH_API_KEY"],
    "azure_openai_endpoint": app.config["AZURE_OPENAI_ENDPOINT"],
    "azure_openai_key": app.config["AZURE_OPENAI_KEY"],
    "azure_openai_embedding_deployment": app.config["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
    "chunk_size": 1000,
    "chunk_overlap": 200
})

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
    message_count = 0
    try:
        while True:
            msg = await websocket.receive()
            message_count += 1
            if isinstance(msg, (bytes, bytearray)):
                logger.debug("Received audio data, message #%d, size: %d bytes", message_count, len(msg))
                await handler.web_to_voicelive(msg)
            else:
                logger.info("Received text message #%d: %s", message_count, msg[:100] if len(msg) > 100 else msg)
                # Assume text message, route to handler
                await handler.handle_websocket_message(msg)
    except Exception:
        logger.exception("Web WebSocket connection closed")


@app.route("/")
async def index():
    """Serves the static index page."""
    return await app.send_static_file("index.html")


@app.route("/api/documents", methods=["POST"])
async def upload_documents():
    """Upload and index documents to Azure Search."""
    logger = logging.getLogger("upload_documents")
    
    try:
        # Get uploaded files
        files = await request.files
        
        if not files:
            return jsonify({"error": "No files provided"}), 400
        
        results = []
        
        # Process each file
        for field_name in files:
            file_list = files.getlist(field_name)
            
            for file in file_list:
                logger.info(f"Processing file: {file.filename}")
                
                # Read file content
                file_content = file.read()
                
                # Validate file size (max 10MB)
                if len(file_content) > 10 * 1024 * 1024:
                    results.append({
                        "filename": file.filename,
                        "status": "error",
                        "error": "File too large (max 10MB)"
                    })
                    continue
                
                # Validate file type
                allowed_extensions = ['.pdf', '.docx', '.doc', '.txt']
                file_ext = os.path.splitext(file.filename)[1].lower()
                
                if file_ext not in allowed_extensions:
                    results.append({
                        "filename": file.filename,
                        "status": "error",
                        "error": f"Unsupported file type: {file_ext}"
                    })
                    continue
                
                # Process and index document
                result = await document_processor.upload_and_index_document(
                    file_content=file_content,
                    filename=file.filename,
                    content_type=file.content_type or "application/octet-stream"
                )
                
                results.append(result)
        
        return jsonify({"results": results}), 200
    
    except Exception as e:
        logger.error(f"Error uploading documents: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/documents", methods=["GET"])
async def list_documents():
    """List all indexed documents."""
    logger = logging.getLogger("list_documents")
    
    try:
        documents = await document_processor.list_documents()
        return jsonify({"documents": documents}), 200
    
    except Exception as e:
        logger.error(f"Error listing documents: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/documents/<path:document_id>", methods=["DELETE"])
async def delete_document(document_id):
    """Delete a document from Azure Search and Blob Storage."""
    logger = logging.getLogger("delete_document")
    
    try:
        success = await document_processor.delete_document(document_id)
        
        if success:
            return jsonify({"message": "Document deleted successfully"}), 200
        else:
            return jsonify({"error": "Failed to delete document"}), 500
    
    except Exception as e:
        logger.error(f"Error deleting document: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/indexer/create", methods=["POST"])
async def create_indexer():
    """Create an Azure Search Indexer for automatic document processing."""
    logger = logging.getLogger("create_indexer")
    
    try:
        result = await document_processor.create_indexer()
        
        if result["status"] == "success":
            return jsonify(result), 200
        else:
            return jsonify(result), 500
    
    except Exception as e:
        logger.error(f"Error creating indexer: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/indexer/run", methods=["POST"])
async def run_indexer():
    """Manually trigger the indexer to process documents."""
    logger = logging.getLogger("run_indexer")
    
    try:
        result = await document_processor.run_indexer()
        
        if result["status"] == "success":
            return jsonify(result), 200
        else:
            return jsonify(result), 500
    
    except Exception as e:
        logger.error(f"Error running indexer: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/indexer/status", methods=["GET"])
async def get_indexer_status():
    """Get the current status of the indexer."""
    logger = logging.getLogger("get_indexer_status")
    
    try:
        result = await document_processor.get_indexer_status()
        
        if result["status"] == "success":
            return jsonify(result), 200
        else:
            return jsonify(result), 404
    
    except Exception as e:
        logger.error(f"Error getting indexer status: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
