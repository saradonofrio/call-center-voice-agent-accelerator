"""
Conversation Logger with PII Removal and GDPR Compliance.

This module tracks all user-bot conversations, anonymizes PII,
and stores them in Azure Blob Storage for admin review and learning.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from azure.storage.blob.aio import BlobServiceClient, ContainerClient
from azure.storage.blob import ContentSettings
from app.pii_anonymizer import PIIAnonymizer
from app.encryption_utils import get_encryption_utils

logger = logging.getLogger(__name__)


class ConversationLogger:
    """
    Logs conversations with PII anonymization for GDPR compliance.
    
    Features:
    - Track all conversation turns (user messages + bot responses)
    - Anonymize PII before storage
    - Store anonymization maps separately (encrypted)
    - Support both web and phone channels
    - Azure Blob Storage integration
    """
    
    # Container names
    CONVERSATIONS_CONTAINER = "conversations"
    ANONYMIZATION_MAPS_CONTAINER = "anonymization-maps"
    FEEDBACK_CONTAINER = "feedback"
    APPROVED_RESPONSES_CONTAINER = "approved-responses"
    
    def __init__(self, storage_connection_string: str):
        """
        Initialize conversation logger.
        
        Args:
            storage_connection_string: Azure Storage connection string
        """
        self.storage_connection_string = storage_connection_string
        self.blob_service_client = None
        self.pii_anonymizer = PIIAnonymizer(reversible=True)
        self.encryption_utils = get_encryption_utils()
        
        # Active conversations (session_id -> conversation data)
        self.active_conversations: Dict[str, Dict] = {}
        
        # Container clients
        self.conversations_container = None
        self.maps_container = None
    
    async def initialize(self):
        """Initialize Azure Storage containers."""
        try:
            self.blob_service_client = BlobServiceClient.from_connection_string(
                self.storage_connection_string
            )
            
            # Create containers if they don't exist
            await self._ensure_container_exists(self.CONVERSATIONS_CONTAINER)
            await self._ensure_container_exists(self.ANONYMIZATION_MAPS_CONTAINER)
            await self._ensure_container_exists(self.FEEDBACK_CONTAINER)
            await self._ensure_container_exists(self.APPROVED_RESPONSES_CONTAINER)
            
            # Get container clients
            self.conversations_container = self.blob_service_client.get_container_client(
                self.CONVERSATIONS_CONTAINER
            )
            self.maps_container = self.blob_service_client.get_container_client(
                self.ANONYMIZATION_MAPS_CONTAINER
            )
            
            logger.info("Conversation logger initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing conversation logger: {e}")
            raise
    
    async def _ensure_container_exists(self, container_name: str):
        """Create container if it doesn't exist."""
        try:
            container_client = self.blob_service_client.get_container_client(container_name)
            
            # Check if container exists
            exists = False
            try:
                await container_client.get_container_properties()
                exists = True
            except:
                pass
            
            if not exists:
                await container_client.create_container()
                logger.info(f"Created container: {container_name}")
            
        except Exception as e:
            logger.error(f"Error ensuring container {container_name} exists: {e}")
            # Don't raise - container might exist already
    
    def start_conversation(
        self,
        session_id: str,
        channel: str,
        phone_number: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Start tracking a new conversation.
        
        Args:
            session_id: Unique session identifier
            channel: 'web' or 'phone'
            phone_number: Phone number for phone channel (will be hashed)
            metadata: Additional metadata (model, voice, etc.)
        """
        conversation = {
            "id": f"conv-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{session_id[:8]}",
            "session_id": session_id,
            "session_id_hash": PIIAnonymizer.hash_session_id(session_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "channel": channel,
            "turns": [],
            "metadata": metadata or {},
            "pii_detected_types": set(),
        }
        
        if phone_number:
            conversation["phone_number_hash"] = PIIAnonymizer.hash_phone_number(phone_number)
        
        self.active_conversations[session_id] = conversation
        logger.info(f"Started conversation: {conversation['id']} (channel: {channel})")
    
    async def log_turn(
        self,
        session_id: str,
        user_message: str,
        bot_response: str,
        search_used: bool = False,
        search_query: Optional[str] = None,
        search_results: Optional[List] = None,
        response_time_ms: Optional[int] = None
    ):
        """
        Log a conversation turn with PII anonymization.
        
        Args:
            session_id: Session identifier
            user_message: User's message (will be anonymized)
            bot_response: Bot's response (will be anonymized)
            search_used: Whether Azure AI Search was used
            search_query: Search query if used
            search_results: Search results if used
            response_time_ms: Response time in milliseconds
        """
        if session_id not in self.active_conversations:
            logger.warning(f"Attempting to log turn for unknown session: {session_id}")
            # Start conversation if not exists
            self.start_conversation(session_id, "unknown")
        
        conversation = self.active_conversations[session_id]
        
        # Anonymize user message
        user_anonymized = self.pii_anonymizer.anonymize_text(user_message, session_id)
        
        # Anonymize bot response (in case it echoed PII)
        bot_anonymized = self.pii_anonymizer.anonymize_text(bot_response, session_id)
        
        # Create turn data
        turn = {
            "turn_number": len(conversation["turns"]) + 1,
            "user_message": user_anonymized["anonymized_text"],
            "bot_response": bot_anonymized["anonymized_text"],
            "search_used": search_used,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        if search_query:
            turn["search_query"] = search_query
        
        if search_results:
            # Limit search results to save space
            turn["search_results_count"] = len(search_results)
            turn["search_results_preview"] = search_results[:2] if len(search_results) > 0 else []
        
        if response_time_ms:
            turn["response_time_ms"] = response_time_ms
        
        # Track PII types detected
        pii_types = set(user_anonymized["pii_found"] + bot_anonymized["pii_found"])
        conversation["pii_detected_types"].update(pii_types)
        
        # Add turn to conversation
        conversation["turns"].append(turn)
        
        logger.debug(f"Logged turn {turn['turn_number']} for session {session_id}")
    
    async def end_conversation(self, session_id: str):
        """
        End conversation and save to storage.
        
        Args:
            session_id: Session identifier
        """
        if session_id not in self.active_conversations:
            logger.warning(f"Attempting to end unknown session: {session_id}")
            return
        
        conversation = self.active_conversations[session_id]
        
        # Finalize metadata
        conversation["metadata"]["total_turns"] = len(conversation["turns"])
        conversation["metadata"]["duration_seconds"] = self._calculate_duration(conversation)
        conversation["metadata"]["ended_at"] = datetime.now(timezone.utc).isoformat()
        conversation["pii_detected_types"] = list(conversation["pii_detected_types"])
        
        # Mark as anonymized
        conversation["anonymized"] = True
        conversation["anonymization_version"] = "1.0"
        
        # Save conversation (anonymized)
        await self._save_conversation(conversation)
        
        # Save anonymization map (encrypted, separate storage)
        anonymization_map = self.pii_anonymizer.get_anonymization_map(session_id)
        if anonymization_map:
            await self._save_anonymization_map(session_id, conversation["id"], anonymization_map)
        
        # Clear from memory
        del self.active_conversations[session_id]
        self.pii_anonymizer.clear_session(session_id)
        
        logger.info(f"Ended and saved conversation: {conversation['id']}")
    
    async def _save_conversation(self, conversation: Dict):
        """Save anonymized conversation to Azure Storage."""
        try:
            blob_name = f"{conversation['id']}.json"
            
            # Convert to JSON
            json_data = json.dumps(conversation, indent=2, ensure_ascii=False)
            
            # Upload to blob storage
            blob_client = self.conversations_container.get_blob_client(blob_name)
            await blob_client.upload_blob(
                json_data,
                overwrite=True,
                content_settings=ContentSettings(content_type="application/json")
            )
            
            logger.info(f"Saved conversation: {blob_name}")
            
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            raise
    
    async def _save_anonymization_map(
        self,
        session_id: str,
        conversation_id: str,
        anonymization_map: Dict[str, str]
    ):
        """Save encrypted anonymization map to Azure Storage."""
        try:
            # Create map data with metadata
            map_data = {
                "session_id_hash": PIIAnonymizer.hash_session_id(session_id),
                "conversation_id": conversation_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "encryption_version": "1.0",
                "mappings": anonymization_map,
                "access_log": []
            }
            
            # Encrypt the map
            encrypted_data = self.encryption_utils.encrypt_map(map_data)
            
            # Save to blob storage
            blob_name = f"map-{PIIAnonymizer.hash_session_id(session_id)[:16]}.json.encrypted"
            blob_client = self.maps_container.get_blob_client(blob_name)
            
            await blob_client.upload_blob(
                encrypted_data,
                overwrite=True,
                content_settings=ContentSettings(content_type="application/octet-stream")
            )
            
            logger.info(f"Saved encrypted anonymization map: {blob_name}")
            
        except Exception as e:
            logger.error(f"Error saving anonymization map: {e}")
            # Don't raise - conversation is already saved
    
    def _calculate_duration(self, conversation: Dict) -> int:
        """Calculate conversation duration in seconds."""
        if len(conversation["turns"]) < 2:
            return 0
        
        try:
            start_time = datetime.fromisoformat(conversation["timestamp"])
            end_time = datetime.fromisoformat(conversation["turns"][-1]["timestamp"])
            duration = (end_time - start_time).total_seconds()
            return int(duration)
        except:
            return 0
    
    async def close(self):
        """Close storage clients."""
        if self.blob_service_client:
            await self.blob_service_client.close()


# Singleton instance
_conversation_logger = None


def get_conversation_logger(storage_connection_string: str = None) -> ConversationLogger:
    """
    Get singleton instance of ConversationLogger.
    
    Args:
        storage_connection_string: Azure Storage connection string (required on first call)
        
    Returns:
        ConversationLogger instance
    """
    global _conversation_logger
    if _conversation_logger is None:
        if storage_connection_string is None:
            raise ValueError("storage_connection_string required for first initialization")
        _conversation_logger = ConversationLogger(storage_connection_string)
    return _conversation_logger
