# Vector Search Setup Guide

This document explains the vector search (semantic search) implementation for the call center voice agent's document grounding system.

## Overview

Vector search enables **semantic/hybrid search** by generating embeddings for document content and comparing them with query embeddings. This improves search relevance beyond simple keyword matching.

### Benefits
- **Better semantic matching**: Find documents based on meaning, not just keywords
- **Hybrid search**: Combine keyword matching with vector similarity for best results
- **Italian language support**: Works well with Italian content alongside the Italian analyzer
- **Improved grounding**: Voice agent gets more relevant context for better responses

## Architecture

### Components
1. **Azure OpenAI Embeddings**: Generates vector representations of text
2. **Azure AI Search**: Stores vectors and performs hybrid search
3. **HNSW Algorithm**: Efficient approximate nearest neighbor search
4. **Cosine Similarity**: Measures vector similarity

### Index Schema
The search index includes a `contentVector` field with:
- **Type**: Collection(Edm.Single) - array of floating point numbers
- **Dimensions**: 1536 (for text-embedding-ada-002) or 3072 (for text-embedding-3-large)
- **Algorithm**: HNSW (Hierarchical Navigable Small World)
- **Metric**: Cosine similarity
- **Profile**: default-vector-profile

### Document Processing Flow
1. **Text extraction** from PDF/DOCX/TXT files
2. **Chunking** (1000 chars with 200 char overlap) for general documents
3. **Embedding generation** via Azure OpenAI for each chunk/document
4. **Index upload** with both text content and vectors
5. **Hybrid search** uses both text and vector fields

## Required Environment Variables

Add these to your Azure Container App environment variables or local `.env` file:

```bash
# Azure OpenAI Configuration (for embeddings)
AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/
AZURE_OPENAI_KEY=your-azure-openai-key
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-ada-002  # or text-embedding-3-large
```

### How to Get These Values

#### Via Azure Portal:
1. Navigate to your **Azure OpenAI Service** resource
2. Go to **Keys and Endpoint**
3. Copy:
   - **Endpoint**: `AZURE_OPENAI_ENDPOINT`
   - **Key 1** or **Key 2**: `AZURE_OPENAI_KEY`
4. Go to **Model deployments** → Click **Manage Deployments**
5. Note your embedding model deployment name: `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`

#### Via Azure CLI:
```bash
# Get OpenAI endpoint
az cognitiveservices account show \
  --name your-openai-resource \
  --resource-group your-rg \
  --query properties.endpoint \
  --output tsv

# Get OpenAI key
az cognitiveservices account keys list \
  --name your-openai-resource \
  --resource-group your-rg \
  --query key1 \
  --output tsv

# List deployments
az cognitiveservices account deployment list \
  --name your-openai-resource \
  --resource-group your-rg
```

## Deployment Models

### text-embedding-ada-002
- **Dimensions**: 1536
- **Context length**: 8,191 tokens
- **Cost**: Lower
- **Performance**: Good for most use cases
- **Recommended**: For general semantic search

### text-embedding-3-large
- **Dimensions**: 3072 (can be reduced)
- **Context length**: 8,191 tokens
- **Cost**: Higher
- **Performance**: Better accuracy
- **Recommended**: For high-accuracy requirements

**Note**: If using `text-embedding-3-large`, update `embedding_dimensions` in `DocumentProcessor` initialization:
```python
document_processor = DocumentProcessor({
    # ... other config ...
    "embedding_dimensions": 3072  # for text-embedding-3-large
})
```

## How It Works

### 1. Index Creation
When the first document is uploaded, the code creates an Azure AI Search index with:
```python
# Vector field
SearchField(
    name="contentVector",
    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
    searchable=True,
    vector_search_dimensions=1536,  # or 3072
    vector_search_profile_name="default-vector-profile"
)

# Vector search configuration
VectorSearch(
    algorithms=[
        HnswAlgorithmConfiguration(
            name="hnsw-algorithm",
            kind=VectorSearchAlgorithmKind.HNSW,
            parameters={
                "m": 4,                      # Max connections per node
                "efConstruction": 400,       # Construction quality
                "efSearch": 500,             # Search quality
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
```

### 2. Embedding Generation
For each document chunk or service document:
```python
def _generate_embeddings(self, text: str) -> Optional[List[float]]:
    # Truncate if needed (8000 chars ≈ 2000 tokens)
    if len(text) > 32000:
        text = text[:32000]
    
    # Call Azure OpenAI
    response = self.openai_client.embeddings.create(
        input=text,
        model=self.azure_openai_embedding_deployment
    )
    
    return response.data[0].embedding  # List of 1536 or 3072 floats
```

### 3. Document Indexing
Documents are indexed with both text and vectors:
```python
doc = {
    "id": "...",
    "content": "actual text content",
    "contentVector": [0.123, -0.456, ...],  # 1536 or 3072 dimensions
    # ... other fields
}
```

### 4. Search (Future Enhancement)
To perform hybrid search (not yet implemented in voice agent):
```python
from azure.search.documents.models import VectorizedQuery

results = search_client.search(
    search_text="query text",  # Keyword search
    vector_queries=[
        VectorizedQuery(
            vector=query_embedding,
            k_nearest_neighbors=5,
            fields="contentVector"
        )
    ],
    top=10
)
```

## Troubleshooting

### No embeddings generated
**Symptom**: Logs show "OpenAI client not initialized, skipping embedding generation"
**Solution**: Ensure `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_KEY` are set

### Wrong dimensions error
**Symptom**: "Index field 'contentVector' expects vectors of size 1536, but received 3072"
**Solution**: Match `embedding_dimensions` parameter to your deployment model:
- text-embedding-ada-002 → 1536
- text-embedding-3-large → 3072

### Rate limit errors
**Symptom**: "Rate limit exceeded" from Azure OpenAI
**Solution**: 
- Reduce upload batch size
- Increase Azure OpenAI quota
- Add retry logic with exponential backoff

### Deployment not found
**Symptom**: "The API deployment for this resource does not exist"
**Solution**: Verify `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` matches your actual deployment name in Azure Portal

## Verification

After deployment, check logs for:
```
Azure OpenAI client initialized for embeddings
Generated embedding with 1536 dimensions
Added content vector to service document
Generated embeddings for 5/5 chunks
```

## Performance Considerations

### Token Limits
- Maximum input: ~8,191 tokens per embedding call
- Code truncates at 32,000 chars (safe limit)
- Large documents are chunked automatically

### Indexing Speed
- Embeddings generation adds ~200-500ms per chunk
- Batch processing happens in parallel where possible
- Total time depends on document size and chunk count

### Cost Optimization
- Use text-embedding-ada-002 for cost efficiency
- Chunk size of 1000 chars balances granularity vs. API calls
- Only regenerate embeddings when content changes

## Next Steps

1. **Set environment variables** in Azure Container App
2. **Deploy the updated code** via `azd deploy`
3. **Upload test documents** via the configuration UI
4. **Verify embeddings** in logs
5. **Test search quality** (future: implement voice agent search integration)

## References

- [Azure OpenAI Embeddings](https://learn.microsoft.com/azure/ai-services/openai/concepts/understand-embeddings)
- [Azure AI Search Vector Search](https://learn.microsoft.com/azure/search/vector-search-overview)
- [HNSW Algorithm](https://arxiv.org/abs/1603.09320)
