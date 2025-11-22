"""
Document processing module for extracting text and indexing to Azure Search.
Handles PDF, DOCX, and TXT files with chunking and Azure Blob Storage integration.
"""
import logging
import os
import uuid
from typing import List, Dict, Any, Optional
from io import BytesIO

from azure.storage.blob import BlobServiceClient
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchFieldDataType,
    SearchIndexer,
    SearchIndexerDataSourceConnection,
    SearchIndexerDataContainer,
    SearchIndexerSkillset,
    InputFieldMappingEntry,
    OutputFieldMappingEntry,
    FieldMapping,
    SearchField,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
    VectorSearchAlgorithmKind,
    VectorSearchAlgorithmMetric
)
from azure.search.documents.indexes import SearchIndexerClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from openai import AzureOpenAI, OpenAI
import asyncio

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document
except ImportError:
    Document = None

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Processes documents and indexes them to Azure Search."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the document processor.
        
        Args:
            config: Configuration dictionary with Azure credentials
        """
        self.config = config
        
        # Azure Storage configuration
        self.storage_connection_string = config.get("azure_storage_connection_string")
        self.storage_container = config.get("azure_storage_container", "documents")
        self.blob_service_client = None
        
        # Azure Search configuration
        self.search_endpoint = config.get("azure_search_endpoint")
        self.search_index = config.get("azure_search_index")
        self.search_api_key = config.get("azure_search_api_key")
        
        # Azure OpenAI configuration for embeddings
        self.azure_openai_endpoint = config.get("azure_openai_endpoint")
        self.azure_openai_key = config.get("azure_openai_key")
        self.azure_user_assigned_identity_client_id = config.get("azure_user_assigned_identity_client_id")
        self.azure_openai_embedding_deployment = config.get("azure_openai_embedding_deployment", "text-embedding-ada-002")
        self.embedding_dimensions = config.get("embedding_dimensions", 1536)  # 1536 for ada-002, 3072 for ada-003
        
        # Determine if using Managed Identity or API key
        self.use_managed_identity = (self.azure_openai_endpoint and self.azure_user_assigned_identity_client_id and not self.azure_openai_key)
        
        # Document chunking settings
        self.chunk_size = config.get("chunk_size", 1000)  # characters per chunk
        self.chunk_overlap = config.get("chunk_overlap", 200)  # overlap between chunks
        
        # Initialize clients
        self._init_storage_client()
        self._init_search_client()
        self._init_openai_client()
    
    def _init_storage_client(self):
        """Initialize Azure Blob Storage client."""
        if self.storage_connection_string:
            try:
                self.blob_service_client = BlobServiceClient.from_connection_string(
                    self.storage_connection_string
                )
                # Ensure container exists
                container_client = self.blob_service_client.get_container_client(
                    self.storage_container
                )
                if not container_client.exists():
                    container_client.create_container()
                    logger.info(f"Created storage container: {self.storage_container}")
                else:
                    logger.info(f"Using existing storage container: {self.storage_container}")
            except Exception as e:
                logger.error(f"Failed to initialize Azure Storage client: {e}")
                self.blob_service_client = None
        else:
            logger.warning("Azure Storage connection string not configured")
    
    def _init_search_client(self):
        """Initialize Azure Search client (index will be created on first upload if needed)."""
        if not self.search_endpoint or not self.search_index:
            logger.warning("Azure Search not fully configured")
            self.search_client = None
            return
        
        try:
            # Create credential
            if self.search_api_key:
                credential = AzureKeyCredential(self.search_api_key)
            else:
                credential = DefaultAzureCredential()
            
            # Initialize search client for document operations
            self.search_client = SearchClient(
                endpoint=self.search_endpoint,
                index_name=self.search_index,
                credential=credential
            )
            
            logger.info(f"Initialized Azure Search client for index: {self.search_index}")
        except Exception as e:
            logger.error(f"Failed to initialize Azure Search client: {e}")
            self.search_client = None
    
    def _init_openai_client(self):
        """Initialize Azure OpenAI client for embeddings with Managed Identity or API key."""
        if not self.azure_openai_endpoint:
            logger.warning("Azure OpenAI endpoint not configured - vector search will be disabled")
            self.openai_client = None
            return
            
        try:
            if self.use_managed_identity:
                # Use Managed Identity authentication
                credential = ManagedIdentityCredential(client_id=self.azure_user_assigned_identity_client_id)
                # Get token synchronously for sync OpenAI client
                token = credential.get_token("https://cognitiveservices.azure.com/.default")
                
                self.openai_client = AzureOpenAI(
                    azure_endpoint=self.azure_openai_endpoint,
                    azure_ad_token=token.token,
                    api_version="2024-02-01"
                )
                logger.info("Azure OpenAI client initialized for embeddings with Managed Identity")
            elif self.azure_openai_key:
                # Use API key authentication
                self.openai_client = AzureOpenAI(
                    azure_endpoint=self.azure_openai_endpoint,
                    api_key=self.azure_openai_key,
                    api_version="2024-02-01"
                )
                logger.info("Azure OpenAI client initialized for embeddings with API key")
            else:
                logger.warning("Azure OpenAI authentication not configured - vector search will be disabled")
                self.openai_client = None
        except Exception as e:
            logger.error(f"Failed to initialize Azure OpenAI client: {e}")
            self.openai_client = None

    def _generate_embeddings(self, text: str) -> Optional[List[float]]:
        """
        Generate embeddings for the given text using Azure OpenAI.
        
        Args:
            text: The text to generate embeddings for
            
        Returns:
            List of embedding values, or None if generation fails
        """
        if not self.openai_client:
            logger.warning("OpenAI client not initialized, skipping embedding generation")
            return None
            
        try:
            # Truncate text if too long (token limit ~ 8191 for ada-002)
            max_chars = 8000 * 4  # Rough approximation: 1 token ≈ 4 chars
            if len(text) > max_chars:
                text = text[:max_chars]
                logger.debug(f"Truncated text to {max_chars} chars for embedding")
            
            response = self.openai_client.embeddings.create(
                input=text,
                model=self.azure_openai_embedding_deployment
            )
            
            embedding = response.data[0].embedding
            logger.debug(f"Generated embedding with {len(embedding)} dimensions")
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            return None
    
    def _ensure_index_exists(self, index_client: SearchIndexClient):
        """Ensure the search index exists with the correct schema."""
        try:
            # Try to get existing index
            existing_index = index_client.get_index(self.search_index)
            logger.info(f"Using existing search index: {self.search_index}")
            logger.info(f"Index has {len(existing_index.fields)} fields")
            
            # Log existing fields for debugging
            existing_field_names = [f.name for f in existing_index.fields]
            logger.info(f"Existing index fields: {existing_field_names}")
            
            # Check if we need to add missing fields
            required_fields = {"id", "title", "content"}
            if not required_fields.issubset(set(existing_field_names)):
                logger.warning(f"Index is missing required fields. Has: {existing_field_names}, Needs: {required_fields}")
                
        except Exception as e:
            # Create new index if it doesn't exist
            logger.info(f"Index does not exist, creating new index: {self.search_index}")
            logger.debug(f"Error getting index: {e}")
            
            fields = [
                SimpleField(
                    name="id",
                    type=SearchFieldDataType.String,
                    key=True,
                    filterable=True
                ),
                SearchableField(
                    name="title",
                    type=SearchFieldDataType.String,
                    filterable=True,
                    sortable=True
                ),
                SearchableField(
                    name="content",
                    type=SearchFieldDataType.String,
                    analyzer_name="it.microsoft"  # Italian analyzer
                ),
                SimpleField(
                    name="sourceFile",
                    type=SearchFieldDataType.String,
                    filterable=True
                ),
                SimpleField(
                    name="chunkId",
                    type=SearchFieldDataType.Int32,
                    filterable=True
                ),
                SimpleField(
                    name="blobUrl",
                    type=SearchFieldDataType.String,
                    filterable=False
                ),
                # Service-specific fields
                SearchableField(
                    name="serviceName",
                    type=SearchFieldDataType.String,
                    filterable=True,
                    sortable=True
                ),
                SimpleField(
                    name="category",
                    type=SearchFieldDataType.String,
                    filterable=True,
                    facetable=True
                ),
                SearchableField(
                    name="description",
                    type=SearchFieldDataType.String,
                    analyzer_name="it.microsoft"
                ),
                SearchableField(
                    name="duration",
                    type=SearchFieldDataType.String,
                    analyzer_name="it.microsoft"
                ),
                SearchableField(
                    name="preparation",
                    type=SearchFieldDataType.String,
                    analyzer_name="it.microsoft"
                ),
                SearchableField(
                    name="requirements",
                    type=SearchFieldDataType.String,
                    analyzer_name="it.microsoft"
                ),
                SearchableField(
                    name="operators",
                    type=SearchFieldDataType.String,
                    analyzer_name="it.microsoft"
                ),
                SearchableField(
                    name="technicalDetails",
                    type=SearchFieldDataType.String,
                    analyzer_name="it.microsoft"
                ),
                SearchableField(
                    name="fullContent",
                    type=SearchFieldDataType.String,
                    analyzer_name="it.microsoft"
                ),
                # Vector field for semantic search
                SearchField(
                    name="contentVector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=self.embedding_dimensions,
                    vector_search_profile_name="default-vector-profile"
                )
            ]
            
            # Define vector search configuration
            vector_search = VectorSearch(
                algorithms=[
                    HnswAlgorithmConfiguration(
                        name="hnsw-algorithm",
                        kind=VectorSearchAlgorithmKind.HNSW,
                        parameters={
                            "m": 4,
                            "efConstruction": 400,
                            "efSearch": 500,
                            "metric": VectorSearchAlgorithmMetric.COSINE
                        }
                    )
                ],
                profiles=[
                    VectorSearchProfile(
                        name="default-vector-profile",
                        algorithm_configuration_name="hnsw-algorithm"
                    )
                ]
            )
            
            index = SearchIndex(
                name=self.search_index,
                fields=fields,
                vector_search=vector_search
            )
            index_client.create_index(index)
            logger.info(f"Created search index with vector search: {self.search_index}")
    
    async def _ensure_index_exists_async(self):
        """Ensure the search index exists (async wrapper for use during document upload)."""
        if not self.search_endpoint or not self.search_index:
            return
        
        try:
            # Create credential
            if self.search_api_key:
                credential = AzureKeyCredential(self.search_api_key)
            else:
                credential = DefaultAzureCredential()
            
            # Initialize index client
            index_client = SearchIndexClient(
                endpoint=self.search_endpoint,
                credential=credential
            )
            
            # Ensure index exists with proper schema
            self._ensure_index_exists(index_client)
            
        except Exception as e:
            logger.error(f"Failed to ensure index exists: {e}")
            raise
    
    async def upload_and_index_document(
        self,
        file_content: bytes,
        filename: str,
        content_type: str
    ) -> Dict[str, Any]:
        """
        Upload document to Azure Storage and index to Azure Search.
        
        Args:
            file_content: Binary content of the file
            filename: Original filename
            content_type: MIME type of the file
            
        Returns:
            Dictionary with upload status and metadata
        """
        try:
            # Generate unique blob name
            blob_name = f"{uuid.uuid4()}_{filename}"
            
            # Upload to Azure Blob Storage
            blob_url = await self._upload_to_storage(file_content, blob_name)
            
            # Extract text from document
            text_content = self._extract_text(file_content, filename)
            
            if not text_content or not text_content.strip():
                raise ValueError(f"No text content extracted from {filename}")
            
            # Try to parse as structured service document
            service_fields = self._parse_service_document(text_content)
            
            if service_fields:
                # Index as structured service document (single document, no chunking)
                indexed_count = await self._index_service_document(
                    service_fields,
                    filename,
                    blob_name,
                    blob_url,
                    text_content
                )
                return {
                    "status": "success",
                    "filename": filename,
                    "blob_name": blob_name,
                    "blob_url": blob_url,
                    "indexed_as": "service",
                    "service_name": service_fields.get("serviceName", "Unknown"),
                    "chunks_indexed": indexed_count,
                    "text_length": len(text_content)
                }
            else:
                # Index as regular document with chunking
                chunks = self._chunk_text(text_content)
                indexed_count = await self._index_chunks(
                    chunks,
                    filename,
                    blob_name,
                    blob_url
                )
                return {
                    "status": "success",
                    "filename": filename,
                    "blob_name": blob_name,
                    "blob_url": blob_url,
                    "indexed_as": "general",
                    "chunks_indexed": indexed_count,
                    "text_length": len(text_content)
                }
        
        except Exception as e:
            logger.error(f"Failed to process document {filename}: {e}", exc_info=True)
            return {
                "status": "error",
                "filename": filename,
                "error": str(e)
            }
    
    async def _upload_to_storage(self, file_content: bytes, blob_name: str) -> str:
        """Upload file to Azure Blob Storage."""
        if not self.blob_service_client:
            logger.warning("Blob storage not configured, skipping upload")
            return ""
        
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.storage_container,
                blob=blob_name
            )
            
            blob_client.upload_blob(file_content, overwrite=True)
            blob_url = blob_client.url
            
            logger.info(f"Uploaded to blob storage: {blob_name}")
            return blob_url
        
        except Exception as e:
            logger.error(f"Failed to upload to blob storage: {e}")
            raise
    
    def _extract_text(self, file_content: bytes, filename: str) -> str:
        """Extract text content from document."""
        file_ext = os.path.splitext(filename)[1].lower()
        
        if file_ext == '.pdf':
            return self._extract_from_pdf(file_content)
        elif file_ext in ['.docx', '.doc']:
            return self._extract_from_docx(file_content)
        elif file_ext == '.txt':
            return self._extract_from_txt(file_content)
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")
    
    def _extract_from_pdf(self, file_content: bytes) -> str:
        """Extract text from PDF file."""
        if not PdfReader:
            raise ImportError("pypdf not installed. Install with: pip install pypdf")
        
        try:
            pdf_file = BytesIO(file_content)
            reader = PdfReader(pdf_file)
            
            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            
            return "\n\n".join(text_parts)
        
        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            raise
    
    def _extract_from_docx(self, file_content: bytes) -> str:
        """Extract text from DOCX file."""
        if not Document:
            raise ImportError("python-docx not installed. Install with: pip install python-docx")
        
        try:
            docx_file = BytesIO(file_content)
            doc = Document(docx_file)
            
            text_parts = []
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text_parts.append(paragraph.text)
            
            return "\n\n".join(text_parts)
        
        except Exception as e:
            logger.error(f"Failed to extract text from DOCX: {e}")
            raise
    
    def _extract_from_txt(self, file_content: bytes) -> str:
        """Extract text from TXT file."""
        try:
            # Try UTF-8 first, then fallback to latin-1
            try:
                return file_content.decode('utf-8')
            except UnicodeDecodeError:
                return file_content.decode('latin-1')
        
        except Exception as e:
            logger.error(f"Failed to extract text from TXT: {e}")
            raise
    
    def _parse_service_document(self, text: str) -> Dict[str, str]:
        """
        Parse structured service document with fields like:
        Nome servizio: ...
        Categoria: ...
        Descrizione: ...
        etc.
        
        Returns dict with extracted fields, or empty dict if not a service document.
        """
        service_fields = {}
        
        # Field mappings: Italian label -> internal field name
        field_mappings = {
            "Nome servizio": "serviceName",
            "Categoria": "category",
            "Descrizione": "description",
            "Durata": "duration",
            "Preparazione": "preparation",
            "Requisiti": "requirements",
            "Operatori": "operators",
            "Scheda tecnica approfondimento": "technicalDetails",
            "Contenuto completo": "fullContent"
        }
        
        lines = text.split('\n')
        current_field = None
        current_value = []
        
        for line in lines:
            line = line.strip()
            
            # Check if line starts with a field label
            field_found = False
            for label, field_name in field_mappings.items():
                if line.startswith(label + ":"):
                    # Save previous field if exists
                    if current_field and current_value:
                        service_fields[current_field] = '\n'.join(current_value).strip()
                    
                    # Start new field
                    current_field = field_name
                    current_value = [line[len(label)+1:].strip()]
                    field_found = True
                    break
            
            # If not a field label, add to current field value
            if not field_found and current_field and line:
                current_value.append(line)
        
        # Save last field
        if current_field and current_value:
            service_fields[current_field] = '\n'.join(current_value).strip()
        
        # Return parsed fields if we found service-specific fields
        if "serviceName" in service_fields:
            logger.info(f"Parsed service document: {service_fields.get('serviceName')}")
            return service_fields
        
        return {}
    
    def _chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks.
        
        Args:
            text: Full text content
            
        Returns:
            List of text chunks
        """
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = start + self.chunk_size
            
            # If not the last chunk, try to break at sentence boundary
            if end < text_length:
                # Look for period, exclamation, or question mark
                for sep in ['. ', '! ', '? ', '\n\n']:
                    sep_pos = text.rfind(sep, start, end)
                    if sep_pos != -1:
                        end = sep_pos + len(sep)
                        break
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move start position with overlap
            start = end - self.chunk_overlap if end < text_length else text_length
        
        return chunks
    
    async def _index_chunks(
        self,
        chunks: List[str],
        filename: str,
        blob_name: str,
        blob_url: str
    ) -> int:
        """Index text chunks to Azure Search."""
        if not self.search_client:
            logger.warning("Search client not configured, skipping indexing")
            return 0
        
        try:
            # Ensure index exists before indexing documents
            await self._ensure_index_exists_async()
            
            documents = []
            base_id = str(uuid.uuid4())
            
            for idx, chunk in enumerate(chunks):
                # Generate embedding for each chunk
                content_vector = self._generate_embeddings(chunk)
                
                doc = {
                    "id": f"{base_id}_{idx}",
                    "title": filename,
                    "content": chunk,
                    "sourceFile": blob_name,
                    "chunkId": idx,
                    "blobUrl": blob_url or "",
                    # Empty service fields for general documents
                    "serviceName": None,
                    "category": None,
                    "description": None,
                    "duration": None,
                    "preparation": None,
                    "requirements": None,
                    "operators": None,
                    "technicalDetails": None,
                    "fullContent": None
                }
                
                # Add vector field if embeddings were generated
                if content_vector:
                    doc["contentVector"] = content_vector
                
                documents.append(doc)
            
            # Log embedding status
            vectors_count = sum(1 for doc in documents if "contentVector" in doc)
            logger.debug(f"Generated embeddings for {vectors_count}/{len(documents)} chunks")
            
            # Upload to search index
            result = self.search_client.upload_documents(documents=documents)
            
            success_count = sum(1 for r in result if r.succeeded)
            logger.info(f"Indexed {success_count}/{len(chunks)} chunks for {filename}")
            
            return success_count
        
        except Exception as e:
            logger.error(f"Failed to index chunks: {e}")
            raise
    
    async def _index_service_document(
        self,
        service_fields: Dict[str, str],
        filename: str,
        blob_name: str,
        blob_url: str,
        full_text: str
    ) -> int:
        """Index a structured service document to Azure Search."""
        if not self.search_client:
            logger.warning("Search client not configured, skipping indexing")
            return 0
        
        try:
            # Ensure index exists before indexing documents
            await self._ensure_index_exists_async()
            
            # Generate embedding for the full content
            content_vector = self._generate_embeddings(service_fields.get("fullContent", full_text))
            
            # Create single document with all service fields
            doc = {
                "id": str(uuid.uuid4()),
                "title": service_fields.get("serviceName", filename),
                "content": service_fields.get("fullContent", full_text),
                "sourceFile": blob_name,
                "chunkId": 0,
                "blobUrl": blob_url or "",
                "serviceName": service_fields.get("serviceName"),
                "category": service_fields.get("category"),
                "description": service_fields.get("description"),
                "duration": service_fields.get("duration"),
                "preparation": service_fields.get("preparation"),
                "requirements": service_fields.get("requirements"),
                "operators": service_fields.get("operators"),
                "technicalDetails": service_fields.get("technicalDetails"),
                "fullContent": service_fields.get("fullContent")
            }
            
            # Add vector field if embeddings were generated
            if content_vector:
                doc["contentVector"] = content_vector
                logger.debug("Added content vector to service document")
            
            # Upload to search index
            result = self.search_client.upload_documents(documents=[doc])
            
            success_count = sum(1 for r in result if r.succeeded)
            logger.info(f"Indexed service document: {service_fields.get('serviceName')}")
            
            return success_count
        
        except Exception as e:
            logger.error(f"Failed to index service document: {e}")
            raise
    
    async def list_documents(self) -> List[Dict[str, Any]]:
        """List all indexed documents from Azure Search."""
        if not self.search_client:
            return []
        
        try:
            # Get unique documents by sourceFile
            results = self.search_client.search(
                search_text="*",
                select=["sourceFile", "title", "blobUrl"],
                top=1000
            )
            
            # Deduplicate by sourceFile
            seen = set()
            documents = []
            
            for result in results:
                source_file = result.get("sourceFile")
                if source_file and source_file not in seen:
                    seen.add(source_file)
                    documents.append({
                        "id": source_file,
                        "filename": result.get("title", source_file),
                        "blob_url": result.get("blobUrl", "")
                    })
            
            return documents
        
        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            return []
    
    async def delete_document(self, source_file: str) -> bool:
        """
        Delete document from Azure Search and Blob Storage.
        
        Args:
            source_file: Blob name of the document to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Delete from search index (all chunks)
            if self.search_client:
                # Find all chunks for this document
                results = self.search_client.search(
                    search_text="*",
                    filter=f"sourceFile eq '{source_file}'",
                    select=["id"],
                    top=1000
                )
                
                doc_ids = [{"id": r["id"]} for r in results]
                
                if doc_ids:
                    self.search_client.delete_documents(documents=doc_ids)
                    logger.info(f"Deleted {len(doc_ids)} chunks from search index")
            
            # Delete from blob storage
            if self.blob_service_client:
                blob_client = self.blob_service_client.get_blob_client(
                    container=self.storage_container,
                    blob=source_file
                )
                blob_client.delete_blob()
                logger.info(f"Deleted blob: {source_file}")
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to delete document {source_file}: {e}")
            return False
    
    async def create_indexer(self) -> Dict[str, Any]:
        """
        Create an Azure Search Indexer to automatically process documents from Blob Storage.
        
        Returns:
            Dictionary with indexer creation status
        """
        if not all([self.search_endpoint, self.search_index, self.storage_connection_string]):
            return {
                "status": "error",
                "error": "Missing required configuration for indexer"
            }
        
        try:
            # Create credential
            if self.search_api_key:
                credential = AzureKeyCredential(self.search_api_key)
            else:
                credential = DefaultAzureCredential()
            
            # Initialize indexer client
            indexer_client = SearchIndexerClient(
                endpoint=self.search_endpoint,
                credential=credential
            )
            
            # Ensure index exists first
            await self._ensure_index_exists_async()
            
            # Create data source connection name
            datasource_name = f"{self.search_index}-datasource"
            indexer_name = f"{self.search_index}-indexer"
            
            # Create or update data source connection
            datasource = SearchIndexerDataSourceConnection(
                name=datasource_name,
                type="azureblob",
                connection_string=self.storage_connection_string,
                container=SearchIndexerDataContainer(name=self.storage_container)
            )
            
            try:
                indexer_client.create_or_update_data_source_connection(datasource)
                logger.info(f"Created/updated data source: {datasource_name}")
            except Exception as e:
                logger.error(f"Failed to create data source: {e}")
                raise
            
            # Define field mappings (how blob fields map to index fields)
            field_mappings = [
                FieldMapping(source_field_name="metadata_storage_path", target_field_name="id"),
                FieldMapping(source_field_name="metadata_storage_name", target_field_name="title"),
                FieldMapping(source_field_name="content", target_field_name="content"),
                FieldMapping(source_field_name="metadata_storage_path", target_field_name="sourceFile"),
                FieldMapping(source_field_name="metadata_storage_path", target_field_name="blobUrl")
            ]
            
            # Create indexer
            indexer = SearchIndexer(
                name=indexer_name,
                data_source_name=datasource_name,
                target_index_name=self.search_index,
                field_mappings=field_mappings,
                parameters={
                    "batchSize": 10,
                    "maxFailedItems": -1,
                    "maxFailedItemsPerBatch": -1,
                    "configuration": {
                        "dataToExtract": "contentAndMetadata",
                        "parsingMode": "default",
                        "indexedFileNameExtensions": ".pdf,.docx,.txt"
                    }
                }
            )
            
            try:
                result = indexer_client.create_or_update_indexer(indexer)
                logger.info(f"Created/updated indexer: {indexer_name}")
                
                return {
                    "status": "success",
                    "indexer_name": indexer_name,
                    "datasource_name": datasource_name,
                    "message": "Indexer created successfully. It will automatically process new documents uploaded to Blob Storage."
                }
            except Exception as e:
                logger.error(f"Failed to create indexer: {e}")
                raise
        
        except Exception as e:
            logger.error(f"Failed to create indexer: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def run_indexer(self) -> Dict[str, Any]:
        """
        Run the indexer to process documents immediately.
        
        Returns:
            Dictionary with run status
        """
        try:
            # Create credential
            if self.search_api_key:
                credential = AzureKeyCredential(self.search_api_key)
            else:
                credential = DefaultAzureCredential()
            
            # Initialize indexer client
            indexer_client = SearchIndexerClient(
                endpoint=self.search_endpoint,
                credential=credential
            )
            
            indexer_name = f"{self.search_index}-indexer"
            
            # Run the indexer
            indexer_client.run_indexer(indexer_name)
            logger.info(f"Started indexer run: {indexer_name}")
            
            return {
                "status": "success",
                "indexer_name": indexer_name,
                "message": "Indexer run started. Check Azure Portal for progress."
            }
        
        except Exception as e:
            logger.error(f"Failed to run indexer: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def get_indexer_status(self) -> Dict[str, Any]:
        """
        Get the status of the indexer.
        
        Returns:
            Dictionary with indexer status
        """
        try:
            # Create credential
            if self.search_api_key:
                credential = AzureKeyCredential(self.search_api_key)
            else:
                credential = DefaultAzureCredential()
            
            # Initialize indexer client
            indexer_client = SearchIndexerClient(
                endpoint=self.search_endpoint,
                credential=credential
            )
            
            indexer_name = f"{self.search_index}-indexer"
            
            # Get indexer status
            status = indexer_client.get_indexer_status(indexer_name)
            
            return {
                "status": "success",
                "indexer_name": indexer_name,
                "execution_status": status.status,
                "last_result": {
                    "status": status.last_result.status if status.last_result else None,
                    "error_message": status.last_result.error_message if status.last_result else None,
                    "items_processed": status.last_result.items_processed if status.last_result else 0,
                    "items_failed": status.last_result.items_failed if status.last_result else 0
                }
            }
        
        except Exception as e:
            logger.error(f"Failed to get indexer status: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
