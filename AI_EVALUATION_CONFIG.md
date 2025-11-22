# AI Evaluation Configuration Guide

## Quick Setup

Add the following environment variable to enable AI auto-evaluation:

```bash
# AI Evaluation Configuration (Optional but Recommended)
# Uses GPT-4o-mini for automatic response evaluation
AZURE_OPENAI_EVAL_DEPLOYMENT=gpt-4o-mini
```

## Complete Configuration

The AI evaluation system requires Azure OpenAI credentials. If you already have Azure OpenAI configured for embeddings, the same credentials will be used.

### Required Variables (Shared with Document Indexing)

```bash
# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=your-azure-openai-api-key-here
```

### Optional Variables

```bash
# AI Evaluation Deployment (defaults to gpt-4o-mini if not set)
AZURE_OPENAI_EVAL_DEPLOYMENT=gpt-4o-mini

# Embedding Deployment (for document search)
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-ada-002
```

## Step-by-Step Setup

### 1. Create Azure OpenAI Resource (if not exists)

If you don't have Azure OpenAI configured yet:

```bash
# Using Azure CLI
az cognitiveservices account create \
  --name your-openai-resource \
  --resource-group your-rg \
  --kind OpenAI \
  --sku S0 \
  --location eastus2

# Get the endpoint and key
az cognitiveservices account show \
  --name your-openai-resource \
  --resource-group your-rg \
  --query "properties.endpoint" -o tsv

az cognitiveservices account keys list \
  --name your-openai-resource \
  --resource-group your-rg \
  --query "key1" -o tsv
```

### 2. Deploy GPT-4o-mini Model

```bash
# Deploy GPT-4o-mini model
az cognitiveservices account deployment create \
  --name your-openai-resource \
  --resource-group your-rg \
  --deployment-name gpt-4o-mini \
  --model-name gpt-4o-mini \
  --model-version "2024-07-18" \
  --model-format OpenAI \
  --sku-capacity 10 \
  --sku-name "Standard"
```

Or use the Azure Portal:
1. Go to Azure OpenAI Studio (https://oai.azure.com/)
2. Navigate to Deployments
3. Click "Create new deployment"
4. Select model: **gpt-4o-mini**
5. Name: **gpt-4o-mini** (recommended)
6. Click "Create"

### 3. Update .env File

Add to your `server/.env` file:

```bash
# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=your-key-from-step-1
AZURE_OPENAI_EVAL_DEPLOYMENT=gpt-4o-mini
```

### 4. Restart Server

```bash
cd server
python server.py
```

Check logs for confirmation:
```
INFO - AI evaluator initialized
```

## Verification

### Test the API Endpoint

```bash
# Get a conversation ID from your admin dashboard
CONV_ID="conv-xxx-xxx"

# Evaluate a conversation
curl -X POST http://localhost:5000/admin/api/evaluate/$CONV_ID

# Expected response:
# {
#   "conversation_id": "conv-xxx",
#   "overall_score": 7.5,
#   "needs_review": false,
#   "priority": "medium",
#   "turn_evaluations": [...]
# }
```

### Check UI

1. Open admin dashboard: `http://localhost:5000/static/admin/index.html`
2. Load conversations
3. Click "🤖 Auto-Evaluate All"
4. Check for priority badges on conversations

## Configuration Options

### Model Selection

You can use different GPT models:

```bash
# GPT-4o-mini (Recommended - Fast & Cost-effective)
AZURE_OPENAI_EVAL_DEPLOYMENT=gpt-4o-mini

# GPT-4o (More accurate but slower and more expensive)
AZURE_OPENAI_EVAL_DEPLOYMENT=gpt-4o

# GPT-4 (Legacy, not recommended)
AZURE_OPENAI_EVAL_DEPLOYMENT=gpt-4
```

**Recommendation**: Use `gpt-4o-mini` for best balance of speed, cost, and quality.

### Model Comparison

| Model | Speed | Cost | Accuracy | Best For |
|-------|-------|------|----------|----------|
| gpt-4o-mini | ⚡⚡⚡ | 💰 | ⭐⭐⭐ | Production use |
| gpt-4o | ⚡⚡ | 💰💰 | ⭐⭐⭐⭐ | High-accuracy needs |
| gpt-4 | ⚡ | 💰💰💰 | ⭐⭐⭐⭐ | Legacy systems |

## Troubleshooting

### Issue: "AI evaluator not initialized"

**Solution**: Check environment variables are set correctly

```bash
# Verify variables are loaded
python -c "import os; print(os.environ.get('AZURE_OPENAI_ENDPOINT'))"
python -c "import os; print(os.environ.get('AZURE_OPENAI_KEY'))"
```

### Issue: "Deployment not found"

**Solution**: Verify deployment name matches

```bash
# List deployments
az cognitiveservices account deployment list \
  --name your-openai-resource \
  --resource-group your-rg \
  --query "[].name" -o tsv
```

Make sure `AZURE_OPENAI_EVAL_DEPLOYMENT` matches one of the listed deployments.

### Issue: Rate limit errors

**Solution**: Increase deployment capacity or add retry logic

```bash
# Increase deployment capacity (TPM)
az cognitiveservices account deployment update \
  --name your-openai-resource \
  --resource-group your-rg \
  --deployment-name gpt-4o-mini \
  --sku-capacity 50
```

### Issue: High costs

**Solution**: Reduce evaluation frequency

- Don't evaluate the same conversation multiple times
- Use the 24-hour cache (default behavior)
- Evaluate only flagged conversations manually

**Cost Estimates** (approximate):
- GPT-4o-mini: ~$0.15 per 1M input tokens, ~$0.60 per 1M output tokens
- Average conversation evaluation: ~500 tokens total
- Cost per evaluation: ~$0.0002-0.0005
- 1000 evaluations: ~$0.20-0.50

## Environment Variable Reference

### Complete .env Example

```bash
# ===========================================
# AZURE VOICE LIVE API (Required)
# ===========================================
AZURE_VOICE_LIVE_API_KEY=your-voice-live-key
AZURE_VOICE_LIVE_ENDPOINT=https://your-endpoint.cognitiveservices.azure.com/
VOICE_LIVE_MODEL=gpt-4o-mini

# ===========================================
# AZURE COMMUNICATION SERVICES (Required for Phone)
# ===========================================
ACS_CONNECTION_STRING=your-acs-connection-string

# ===========================================
# AZURE STORAGE (Required for Feedback System)
# ===========================================
AZURE_STORAGE_CONNECTION_STRING=your-storage-connection-string
AZURE_STORAGE_CONTAINER=documents

# ===========================================
# AZURE OPENAI (Required for AI Evaluation & Embeddings)
# ===========================================
AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com/
AZURE_OPENAI_KEY=your-openai-api-key

# Model deployments
AZURE_OPENAI_EVAL_DEPLOYMENT=gpt-4o-mini         # For AI evaluation
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-ada-002  # For document search

# ===========================================
# AZURE AI SEARCH (Optional - for RAG)
# ===========================================
AZURE_SEARCH_ENDPOINT=https://your-search.search.windows.net
AZURE_SEARCH_INDEX=documents
AZURE_SEARCH_API_KEY=your-search-api-key

# ===========================================
# AZURE AD AUTH (Optional - for API security)
# ===========================================
AZURE_AD_TENANT_ID=your-tenant-id
AZURE_AD_CLIENT_ID=your-client-id
AZURE_AD_AUDIENCE=api://your-client-id

# ===========================================
# RATE LIMITING (Optional)
# ===========================================
RATE_LIMIT_ENABLED=true
RATE_LIMIT_API_COUNT=100
RATE_LIMIT_API_WINDOW=60
```

## Next Steps

After configuration:

1. ✅ Test evaluation with a single conversation
2. ✅ Use "Auto-Evaluate All" in admin dashboard
3. ✅ Enable "Only AI-flagged for review" filter
4. ✅ Review critical conversations and provide feedback
5. ✅ Monitor Azure OpenAI costs in Azure Portal

## Support

For issues:
- Check server logs: `tail -f server.log`
- Review Azure OpenAI metrics in Azure Portal
- Verify deployment status in Azure OpenAI Studio
- Contact admin if problems persist

---

**Documentation Version**: 1.0  
**Last Updated**: November 2025
