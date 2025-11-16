"""
GDPR Compliance Utilities.

This module provides utilities for GDPR compliance including:
- Data access requests (right to access)
- Data erasure requests (right to be forgotten)
- Data retention policies
- Audit logging
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import ContentSettings

logger = logging.getLogger(__name__)


class GDPRCompliance:
    """
    Handles GDPR compliance operations.
    
    Features:
    - Right to access: Retrieve user's conversation data
    - Right to erasure: Delete user's data
    - Data retention: Auto-delete old conversations
    - Audit logging: Track data access
    """
    
    def __init__(self, storage_connection_string: str):
        """
        Initialize GDPR compliance utilities.
        
        Args:
            storage_connection_string: Azure Storage connection string
        """
        self.storage_connection_string = storage_connection_string
        self.blob_service_client = None
        
        # Default retention periods (days)
        self.conversation_retention_days = 90
        self.anonymization_map_retention_days = 365  # Keep longer for legal requirements
        self.audit_log_retention_days = 730  # 2 years
    
    async def initialize(self):
        """Initialize Azure Storage client."""
        self.blob_service_client = BlobServiceClient.from_connection_string(
            self.storage_connection_string
        )
        logger.info("GDPR compliance module initialized")
    
    async def handle_data_access_request(
        self,
        session_id: str = None,
        phone_number: str = None
    ) -> Optional[Dict]:
        """
        Handle GDPR data access request (Right to Access).
        
        User can request their conversation data using either:
        - session_id: For web users
        - phone_number: For phone users (will be hashed and matched)
        
        Args:
            session_id: Session identifier
            phone_number: Phone number (will be hashed)
            
        Returns:
            Dictionary with conversation data (anonymized) or None if not found
        """
        try:
            from app.pii_anonymizer import PIIAnonymizer
            
            conversations_container = self.blob_service_client.get_container_client("conversations")
            
            # Determine search criteria
            if session_id:
                session_hash = PIIAnonymizer.hash_session_id(session_id)
                search_field = "session_id_hash"
                search_value = session_hash
            elif phone_number:
                phone_hash = PIIAnonymizer.hash_phone_number(phone_number)
                search_field = "phone_number_hash"
                search_value = phone_hash
            else:
                raise ValueError("Either session_id or phone_number must be provided")
            
            # Search for matching conversations
            matching_conversations = []
            
            async for blob in conversations_container.list_blobs():
                blob_client = conversations_container.get_blob_client(blob.name)
                content = await blob_client.download_blob()
                data = json.loads(await content.readall())
                
                if data.get(search_field) == search_value:
                    matching_conversations.append(data)
            
            if not matching_conversations:
                logger.info(f"No conversations found for data access request: {search_field}={search_value}")
                return None
            
            # Log access
            await self._log_audit_event(
                event_type="data_access_request",
                details={
                    search_field: search_value,
                    "conversations_found": len(matching_conversations)
                }
            )
            
            return {
                "request_date": datetime.now(timezone.utc).isoformat(),
                "conversations": matching_conversations,
                "total_conversations": len(matching_conversations)
            }
            
        except Exception as e:
            logger.error(f"Error handling data access request: {e}")
            raise
    
    async def handle_data_erasure_request(
        self,
        session_id: str = None,
        phone_number: str = None,
        requester_info: Optional[Dict] = None
    ) -> Dict:
        """
        Handle GDPR data erasure request (Right to be Forgotten).
        
        Deletes all data associated with the user:
        - Conversations
        - Anonymization maps
        - Feedback
        
        Args:
            session_id: Session identifier
            phone_number: Phone number (will be hashed)
            requester_info: Information about who requested erasure
            
        Returns:
            Dictionary with deletion summary
        """
        try:
            from app.pii_anonymizer import PIIAnonymizer
            
            # Determine search criteria
            if session_id:
                session_hash = PIIAnonymizer.hash_session_id(session_id)
                search_field = "session_id_hash"
                search_value = session_hash
            elif phone_number:
                phone_hash = PIIAnonymizer.hash_phone_number(phone_number)
                search_field = "phone_number_hash"
                search_value = phone_hash
            else:
                raise ValueError("Either session_id or phone_number must be provided")
            
            deleted_items = {
                "conversations": 0,
                "anonymization_maps": 0,
                "feedback": 0
            }
            
            # Delete conversations
            conversations_container = self.blob_service_client.get_container_client("conversations")
            async for blob in conversations_container.list_blobs():
                blob_client = conversations_container.get_blob_client(blob.name)
                content = await blob_client.download_blob()
                data = json.loads(await content.readall())
                
                if data.get(search_field) == search_value:
                    await blob_client.delete_blob()
                    deleted_items["conversations"] += 1
                    logger.info(f"Deleted conversation: {blob.name}")
            
            # Delete anonymization maps
            maps_container = self.blob_service_client.get_container_client("anonymization-maps")
            map_blob_name = f"map-{session_hash[:16]}.json.encrypted"
            try:
                map_blob_client = maps_container.get_blob_client(map_blob_name)
                await map_blob_client.delete_blob()
                deleted_items["anonymization_maps"] += 1
                logger.info(f"Deleted anonymization map: {map_blob_name}")
            except:
                pass  # Map might not exist
            
            # Delete feedback
            feedback_container = self.blob_service_client.get_container_client("feedback")
            async for blob in feedback_container.list_blobs():
                if search_value in blob.name or (session_id and session_id[:8] in blob.name):
                    blob_client = feedback_container.get_blob_client(blob.name)
                    await blob_client.delete_blob()
                    deleted_items["feedback"] += 1
                    logger.info(f"Deleted feedback: {blob.name}")
            
            # Log erasure event
            await self._log_audit_event(
                event_type="data_erasure_request",
                details={
                    search_field: search_value,
                    "deleted_items": deleted_items,
                    "requester_info": requester_info or {}
                }
            )
            
            logger.info(f"Completed data erasure: {deleted_items}")
            
            return {
                "request_date": datetime.now(timezone.utc).isoformat(),
                "deleted_items": deleted_items,
                "status": "completed"
            }
            
        except Exception as e:
            logger.error(f"Error handling data erasure request: {e}")
            raise
    
    async def cleanup_old_data(self) -> Dict:
        """
        Clean up data older than retention period.
        
        Returns:
            Dictionary with cleanup summary
        """
        try:
            cutoff_conversations = datetime.now(timezone.utc) - timedelta(days=self.conversation_retention_days)
            cutoff_maps = datetime.now(timezone.utc) - timedelta(days=self.anonymization_map_retention_days)
            
            deleted_items = {
                "conversations": 0,
                "anonymization_maps": 0
            }
            
            # Clean up old conversations
            conversations_container = self.blob_service_client.get_container_client("conversations")
            async for blob in conversations_container.list_blobs():
                # Check blob creation time
                if blob.creation_time and blob.creation_time.replace(tzinfo=timezone.utc) < cutoff_conversations:
                    blob_client = conversations_container.get_blob_client(blob.name)
                    await blob_client.delete_blob()
                    deleted_items["conversations"] += 1
                    logger.info(f"Deleted old conversation: {blob.name}")
            
            # Clean up old anonymization maps
            maps_container = self.blob_service_client.get_container_client("anonymization-maps")
            async for blob in maps_container.list_blobs():
                if blob.creation_time and blob.creation_time.replace(tzinfo=timezone.utc) < cutoff_maps:
                    blob_client = maps_container.get_blob_client(blob.name)
                    await blob_client.delete_blob()
                    deleted_items["anonymization_maps"] += 1
                    logger.info(f"Deleted old anonymization map: {blob.name}")
            
            # Log cleanup
            await self._log_audit_event(
                event_type="data_retention_cleanup",
                details={
                    "deleted_items": deleted_items,
                    "retention_days": {
                        "conversations": self.conversation_retention_days,
                        "anonymization_maps": self.anonymization_map_retention_days
                    }
                }
            )
            
            logger.info(f"Data retention cleanup completed: {deleted_items}")
            
            return {
                "cleanup_date": datetime.now(timezone.utc).isoformat(),
                "deleted_items": deleted_items,
                "status": "completed"
            }
            
        except Exception as e:
            logger.error(f"Error during data cleanup: {e}")
            raise
    
    async def _log_audit_event(self, event_type: str, details: Dict):
        """
        Log audit event to Azure Storage.
        
        Args:
            event_type: Type of event (data_access_request, data_erasure_request, etc.)
            details: Event details
        """
        try:
            # Create audit log entry
            audit_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "details": details
            }
            
            # Save to audit logs container
            audit_container = self.blob_service_client.get_container_client("audit-logs")
            
            # Create container if not exists
            try:
                await audit_container.get_container_properties()
            except:
                await audit_container.create_container()
            
            # Create blob name with timestamp
            blob_name = f"audit-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}.json"
            blob_client = audit_container.get_blob_client(blob_name)
            
            # Upload audit log
            await blob_client.upload_blob(
                json.dumps(audit_entry, indent=2, ensure_ascii=False),
                overwrite=True,
                content_settings=ContentSettings(content_type="application/json")
            )
            
        except Exception as e:
            logger.error(f"Error logging audit event: {e}")
            # Don't raise - audit logging failure shouldn't break main operation
    
    async def get_audit_logs(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        event_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve audit logs with optional filters.
        
        Args:
            start_date: Filter logs from this date
            end_date: Filter logs until this date
            event_type: Filter by event type
            
        Returns:
            List of audit log entries
        """
        try:
            audit_container = self.blob_service_client.get_container_client("audit-logs")
            audit_logs = []
            
            async for blob in audit_container.list_blobs():
                # Filter by creation time if specified
                if start_date and blob.creation_time and blob.creation_time.replace(tzinfo=timezone.utc) < start_date:
                    continue
                if end_date and blob.creation_time and blob.creation_time.replace(tzinfo=timezone.utc) > end_date:
                    continue
                
                # Download and parse log
                blob_client = audit_container.get_blob_client(blob.name)
                content = await blob_client.download_blob()
                log_entry = json.loads(await content.readall())
                
                # Filter by event type if specified
                if event_type and log_entry.get("event_type") != event_type:
                    continue
                
                audit_logs.append(log_entry)
            
            return audit_logs
            
        except Exception as e:
            logger.error(f"Error retrieving audit logs: {e}")
            return []
    
    async def close(self):
        """Close storage client."""
        if self.blob_service_client:
            await self.blob_service_client.close()


# Singleton instance
_gdpr_compliance = None


def get_gdpr_compliance(storage_connection_string: str = None) -> GDPRCompliance:
    """
    Get singleton instance of GDPRCompliance.
    
    Args:
        storage_connection_string: Azure Storage connection string (required on first call)
        
    Returns:
        GDPRCompliance instance
    """
    global _gdpr_compliance
    if _gdpr_compliance is None:
        if storage_connection_string is None:
            raise ValueError("storage_connection_string required for first initialization")
        _gdpr_compliance = GDPRCompliance(storage_connection_string)
    return _gdpr_compliance
