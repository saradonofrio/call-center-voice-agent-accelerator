"""
Feedback Indexer for Azure AI Search.

This module manages indexing of admin-approved responses into Azure AI Search
for bot learning through RAG (Retrieval Augmented Generation).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
)
from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import ContentSettings
import openai

logger = logging.getLogger(__name__)


class FeedbackIndexer:
    """
    Manages Azure AI Search index for admin-approved feedback responses.
    
    Features:
    - Create and manage 'feedback-responses' search index
    - Index approved responses with embeddings
    - Search for similar situations for bot learning
    - Track usage statistics
    """
    
    INDEX_NAME = "feedback-responses"
    
    def __init__(
        self,
        search_endpoint: str,
        search_api_key: str,
        storage_connection_string: str,
        openai_endpoint: str = None,
        openai_api_key: str = None,
        embedding_model: str = "text-embedding-ada-002"
    ):
        """
        Initialize feedback indexer.
        
        Args:
            search_endpoint: Azure AI Search endpoint
            search_api_key: Azure AI Search API key
            storage_connection_string: Azure Storage connection string
            openai_endpoint: Azure OpenAI endpoint for embeddings
            openai_api_key: Azure OpenAI API key
            embedding_model: Embedding model deployment name
        """
        self.search_endpoint = search_endpoint
        self.search_credential = AzureKeyCredential(search_api_key)
        self.storage_connection_string = storage_connection_string
        self.embedding_model = embedding_model
        
        # Azure OpenAI for embeddings
        if openai_endpoint and openai_api_key:
            openai.api_type = "azure"
            openai.api_base = openai_endpoint
            openai.api_key = openai_api_key
            openai.api_version = "2023-05-15"
        
        self.index_client = None
        self.search_client = None
        self.blob_service_client = None
    
    async def initialize(self):
        """Initialize Azure clients and ensure index exists."""
        try:
            # Initialize search clients
            self.index_client = SearchIndexClient(
                endpoint=self.search_endpoint,
                credential=self.search_credential
            )
            
            self.search_client = SearchClient(
                endpoint=self.search_endpoint,
                index_name=self.INDEX_NAME,
                credential=self.search_credential
            )
            
            # Initialize storage client
            self.blob_service_client = BlobServiceClient.from_connection_string(
                self.storage_connection_string
            )
            
            # Ensure index exists
            await self._ensure_index_exists()
            
            logger.info("Feedback indexer initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing feedback indexer: {e}")
            raise
    
    async def _ensure_index_exists(self):
        """Create feedback-responses index if it doesn't exist."""
        try:
            # Check if index exists
            try:
                await self.index_client.get_index(self.INDEX_NAME)
                logger.info(f"Index '{self.INDEX_NAME}' already exists")
                return
            except:
                pass  # Index doesn't exist, create it
            
            # Define index schema
            fields = [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                SearchableField(name="user_query", type=SearchFieldDataType.String),
                SearchableField(name="context", type=SearchFieldDataType.String),
                SearchableField(name="approved_response", type=SearchFieldDataType.String),
                SearchableField(name="original_response", type=SearchFieldDataType.String),
                SearchableField(name="admin_comment", type=SearchFieldDataType.String),
                SimpleField(name="rating", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
                SimpleField(name="tags", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True),
                SimpleField(name="conversation_id", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="timestamp", type=SearchFieldDataType.DateTimeOffset, sortable=True, filterable=True),
                SimpleField(name="usage_count", type=SearchFieldDataType.Int32, sortable=True),
                # Vector field for semantic search
                SearchField(
                    name="embedding",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=1536,
                    vector_search_profile_name="vector-profile"
                )
            ]
            
            # Vector search configuration
            vector_search = VectorSearch(
                profiles=[
                    VectorSearchProfile(
                        name="vector-profile",
                        algorithm_configuration_name="hnsw-config"
                    )
                ],
                algorithms=[
                    HnswAlgorithmConfiguration(name="hnsw-config")
                ]
            )
            
            # Create index
            index = SearchIndex(
                name=self.INDEX_NAME,
                fields=fields,
                vector_search=vector_search
            )
            
            await self.index_client.create_index(index)
            logger.info(f"Created index '{self.INDEX_NAME}'")
            
        except Exception as e:
            logger.error(f"Error ensuring index exists: {e}")
            raise
    
    async def index_approved_response(
        self,
        conversation_id: str,
        turn_number: int,
        user_query: str,
        approved_response: str,
        original_response: str = "",
        admin_comment: str = "",
        rating: int = 5,
        tags: List[str] = None,
        context: str = ""
    ) -> str:
        """
        Index an admin-approved response for bot learning.
        
        Args:
            conversation_id: Source conversation ID
            turn_number: Turn number in conversation
            user_query: User's original query
            approved_response: Admin-approved response
            original_response: Bot's original response
            admin_comment: Admin's comment
            rating: Rating (1-5)
            tags: Tags (e.g., ["excellent", "helpful"])
            context: Conversation context
            
        Returns:
            Document ID
        """
        try:
            # Generate document ID
            doc_id = f"approved-{conversation_id}-turn{turn_number}"
            
            # Generate embedding for semantic search
            embedding = await self._generate_embedding(f"{user_query} {context}")
            
            # Create document
            document = {
                "id": doc_id,
                "user_query": user_query,
                "context": context,
                "approved_response": approved_response,
                "original_response": original_response,
                "admin_comment": admin_comment or "",
                "rating": rating,
                "tags": tags or [],
                "conversation_id": conversation_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "usage_count": 0,
                "embedding": embedding
            }
            
            # Upload to index
            result = await self.search_client.upload_documents(documents=[document])
            
            logger.info(f"Indexed approved response: {doc_id}")
            
            # Save to approved-responses container for backup
            await self._save_to_storage(doc_id, document)
            
            return doc_id
            
        except Exception as e:
            logger.error(f"Error indexing approved response: {e}")
            raise
    
    async def search_similar_situations(
        self,
        query: str,
        context: str = "",
        top: int = 3,
        min_rating: int = 4
    ) -> List[Dict]:
        """
        Search for similar approved responses for bot learning.
        
        Args:
            query: User query to match
            context: Conversation context
            top: Number of results to return
            min_rating: Minimum rating filter
            
        Returns:
            List of similar approved responses
        """
        try:
            # Generate query embedding
            query_embedding = await self._generate_embedding(f"{query} {context}")
            
            # Perform vector search
            results = await self.search_client.search(
                search_text=query,
                vector_queries=[{
                    "vector": query_embedding,
                    "k_nearest_neighbors": top,
                    "fields": "embedding"
                }],
                filter=f"rating ge {min_rating}",
                select=["id", "user_query", "approved_response", "admin_comment", "rating", "tags", "usage_count"],
                top=top
            )
            
            similar_responses = []
            async for result in results:
                similar_responses.append({
                    "id": result["id"],
                    "user_query": result["user_query"],
                    "approved_response": result["approved_response"],
                    "admin_comment": result.get("admin_comment", ""),
                    "rating": result["rating"],
                    "tags": result.get("tags", []),
                    "relevance_score": result.get("@search.score", 0)
                })
                
                # Increment usage count
                await self._increment_usage_count(result["id"])
            
            logger.info(f"Found {len(similar_responses)} similar approved responses")
            return similar_responses
            
        except Exception as e:
            logger.error(f"Error searching similar situations: {e}")
            return []
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using Azure OpenAI."""
        try:
            response = await openai.Embedding.acreate(
                input=text,
                engine=self.embedding_model
            )
            return response['data'][0]['embedding']
            
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            # Return zero vector as fallback
            return [0.0] * 1536
    
    async def _increment_usage_count(self, doc_id: str):
        """Increment usage count for a document."""
        try:
            # Get current document
            result = await self.search_client.get_document(key=doc_id)
            
            # Update usage count
            result["usage_count"] = result.get("usage_count", 0) + 1
            
            # Merge update
            await self.search_client.merge_documents(documents=[result])
            
        except Exception as e:
            logger.error(f"Error incrementing usage count: {e}")
            # Non-critical error, don't raise
    
    async def _save_to_storage(self, doc_id: str, document: Dict):
        """Save approved response to Azure Storage for backup."""
        try:
            container_client = self.blob_service_client.get_container_client("approved-responses")
            
            # Ensure container exists
            try:
                await container_client.get_container_properties()
            except:
                await container_client.create_container()
            
            # Save document
            blob_name = f"{doc_id}.json"
            blob_client = container_client.get_blob_client(blob_name)
            
            # Remove embedding to save space
            doc_copy = document.copy()
            if "embedding" in doc_copy:
                del doc_copy["embedding"]
            
            await blob_client.upload_blob(
                json.dumps(doc_copy, indent=2, ensure_ascii=False),
                overwrite=True,
                content_settings=ContentSettings(content_type="application/json")
            )
            
        except Exception as e:
            logger.error(f"Error saving to storage: {e}")
            # Non-critical error, don't raise
    
    async def delete_approved_response(self, doc_id: str):
        """Delete an approved response from the index."""
        try:
            await self.search_client.delete_documents(documents=[{"id": doc_id}])
            logger.info(f"Deleted approved response: {doc_id}")
            
        except Exception as e:
            logger.error(f"Error deleting approved response: {e}")
            raise
    
    async def get_statistics(self) -> Dict:
        """Get indexer statistics."""
        try:
            # Count total documents
            results = await self.search_client.search(
                search_text="*",
                select=["id", "rating", "usage_count"],
                include_total_count=True
            )
            
            total_count = 0
            total_rating = 0
            total_usage = 0
            rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            
            async for result in results:
                total_count += 1
                rating = result.get("rating", 0)
                total_rating += rating
                total_usage += result.get("usage_count", 0)
                if rating in rating_distribution:
                    rating_distribution[rating] += 1
            
            return {
                "total_approved_responses": total_count,
                "average_rating": total_rating / total_count if total_count > 0 else 0,
                "total_usage": total_usage,
                "rating_distribution": rating_distribution
            }
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}
    
    async def close(self):
        """Close clients."""
        if self.index_client:
            await self.index_client.close()
        if self.search_client:
            await self.search_client.close()
        if self.blob_service_client:
            await self.blob_service_client.close()


# Singleton instance
_feedback_indexer = None


def get_feedback_indexer(**kwargs) -> FeedbackIndexer:
    """Get singleton instance of FeedbackIndexer."""
    global _feedback_indexer
    if _feedback_indexer is None:
        _feedback_indexer = FeedbackIndexer(**kwargs)
    return _feedback_indexer
