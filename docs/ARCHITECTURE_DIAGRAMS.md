# Feedback System - Complete Architecture with Key Vault

## Infrastructure Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Azure Subscription                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    Resource Group                                 │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │                                                                    │  │
│  │  ┌─────────────────────┐                                         │  │
│  │  │   Azure Key Vault   │                                         │  │
│  │  │   (Auto-created)    │                                         │  │
│  │  ├─────────────────────┤                                         │  │
│  │  │ Secrets:            │                                         │  │
│  │  │ • ACS-CONNECTION-   │◄───┐                                    │  │
│  │  │   STRING            │    │                                    │  │
│  │  │ • AZURE-SEARCH-     │    │                                    │  │
│  │  │   API-KEY           │    │  RBAC: Key Vault Secrets User     │  │
│  │  │ • AZURE-STORAGE-    │    │  (Read-only access)               │  │
│  │  │   CONNECTION-STRING │    │                                    │  │
│  │  │ • AZURE-OPENAI-KEY  │    │                                    │  │
│  │  │ • ANONYMIZATION-    │    │                                    │  │
│  │  │   ENCRYPTION-KEY ✨ │    │                                    │  │
│  │  │   (Auto-generated)  │    │                                    │  │
│  │  └─────────────────────┘    │                                    │  │
│  │                              │                                    │  │
│  │  ┌────────────────────────┐ │  ┌──────────────────────────────┐ │  │
│  │  │  User Assigned         │ │  │  Container App               │ │  │
│  │  │  Managed Identity      ├─┘  │  (Voice Bot + Admin API)     │ │  │
│  │  │  (Auto-created)        │    ├──────────────────────────────┤ │  │
│  │  └────────────────────────┘    │ Configuration:               │ │  │
│  │                                 │  secrets:                    │ │  │
│  │                                 │   - name: anonymization-     │ │  │
│  │                                 │           encryption-key     │ │  │
│  │                                 │     keyVaultUrl: <kv-url>    │ │  │
│  │                                 │     identity: managedId      │ │  │
│  │                                 │                              │ │  │
│  │                                 │  env:                        │ │  │
│  │                                 │   - ANONYMIZATION_ENCRYPTION_│ │  │
│  │                                 │     KEY: secretRef:          │ │  │
│  │                                 │     anonymization-encryption-│ │  │
│  │                                 │     key                      │ │  │
│  │                                 └──────────────────────────────┘ │  │
│  │                                                                    │  │
│  │  ┌──────────────────────────────────────────────────────────┐   │  │
│  │  │           Azure Blob Storage (5 Containers)              │   │  │
│  │  ├──────────────────────────────────────────────────────────┤   │  │
│  │  │ • conversations (anonymized logs)                        │   │  │
│  │  │ • anonymization-maps (encrypted PII mappings)            │   │  │
│  │  │ • feedback (admin ratings/comments)                      │   │  │
│  │  │ • approved-responses (learning data backup)              │   │  │
│  │  │ • audit-logs (GDPR compliance)                           │   │  │
│  │  └──────────────────────────────────────────────────────────┘   │  │
│  │                                                                    │  │
│  │  ┌──────────────────────────────────────────────────────────┐   │  │
│  │  │     Azure AI Search (Vector Search Index)                │   │  │
│  │  ├──────────────────────────────────────────────────────────┤   │  │
│  │  │ Index: feedback-responses                                │   │  │
│  │  │ • user_message (text)                                    │   │  │
│  │  │ • bot_response (text)                                    │   │  │
│  │  │ • corrected_response (text)                              │   │  │
│  │  │ • embedding (1536-dim vector from OpenAI)                │   │  │
│  │  │ • rating, tags, usage_count                              │   │  │
│  │  └──────────────────────────────────────────────────────────┘   │  │
│  │                                                                    │  │
│  │  ┌──────────────────────────────────────────────────────────┐   │  │
│  │  │          Azure OpenAI (Embeddings)                       │   │  │
│  │  ├──────────────────────────────────────────────────────────┤   │  │
│  │  │ Model: text-embedding-ada-002                            │   │  │
│  │  │ Purpose: Generate vectors for RAG learning               │   │  │
│  │  └──────────────────────────────────────────────────────────┘   │  │
│  │                                                                    │  │
│  └────────────────────────────────────────────────────────────────── │  │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

## Deployment Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Developer Action                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. azd env new test-env                                        │
│     Creates environment configuration                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. azd provision                                               │
│     ├─ Deploys main.bicep                                       │
│     ├─ Creates Resource Group                                   │
│     ├─ Creates User Assigned Managed Identity                   │
│     ├─ Deploys keyvault.bicep                                   │
│     │  ├─ Creates Azure Key Vault                               │
│     │  ├─ Generates Fernet key: base64(guid(...))               │
│     │  └─ Stores in ANONYMIZATION-ENCRYPTION-KEY secret         │
│     ├─ Creates Azure Storage (5 containers)                     │
│     ├─ Creates Azure AI Search                                  │
│     ├─ Creates Azure OpenAI                                     │
│     ├─ Assigns RBAC roles to Managed Identity                   │
│     │  ├─ Key Vault Secrets User                                │
│     │  ├─ Storage Blob Data Contributor                         │
│     │  └─ Cognitive Services User                               │
│     ├─ Deploys containerapp.bicep                               │
│     │  ├─ Creates Container App Environment                     │
│     │  ├─ Configures secrets from Key Vault                     │
│     │  └─ Sets environment variables with secretRef             │
│     └─ Runs postprovision.sh                                    │
│        ├─ Validates encryption key format (Fernet)              │
│        ├─ Regenerates key if invalid (using Python)             │
│        └─ Updates Key Vault with proper key                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. azd deploy                                                  │
│     ├─ Builds Docker image                                      │
│     ├─ Pushes to Azure Container Registry                       │
│     └─ Updates Container App with new image                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ✅ Ready!                                                      │
│     Container App running with Key Vault encryption             │
└─────────────────────────────────────────────────────────────────┘
```

## Runtime Flow - Conversation Logging with Encryption

```
┌─────────────────────────────────────────────────────────────────┐
│  1. User calls bot via ACS or web                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. WebSocket connection established                            │
│     ├─ server.py initializes conversation_logger                │
│     ├─ Generates session_id (UUID)                              │
│     ├─ Captures phone_number (if ACS)                           │
│     └─ Calls media_handler.set_conversation_logger()            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. User speaks: "Ciao, sono Mario Rossi, tel 3201234567"      │
│     ├─ Voice Live API transcribes (ASR)                         │
│     └─ media_handler captures in last_user_message              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. Bot responds with answer                                    │
│     ├─ LLM generates response                                   │
│     ├─ TTS synthesizes audio                                    │
│     ├─ media_handler captures in last_bot_response              │
│     └─ If search used, captures search_query/results            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. Turn completed (response.done event)                        │
│     └─ media_handler.log_turn() called                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. Conversation Logger - PII Anonymization                     │
│     ├─ PIIAnonymizer.anonymize_text()                           │
│     │  ├─ Detects: "Mario Rossi" → [PERSON_1]                  │
│     │  ├─ Detects: "3201234567" → [PHONE_1]                    │
│     │  └─ Creates anonymization_map:                            │
│     │     {"[PERSON_1]": "Mario Rossi",                         │
│     │      "[PHONE_1]": "3201234567"}                           │
│     ├─ EncryptionUtils.encrypt_map()                            │
│     │  ├─ Loads key from Key Vault (via env var)               │
│     │  └─ Encrypts map with Fernet                              │
│     └─ Stores:                                                  │
│        ├─ Anonymized conversation → conversations container     │
│        │  "Ciao, sono [PERSON_1], tel [PHONE_1]"               │
│        └─ Encrypted map → anonymization-maps container          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  7. Call ends                                                   │
│     ├─ conversation_logger.end_conversation()                   │
│     └─ Final save to Azure Blob Storage                         │
└─────────────────────────────────────────────────────────────────┘
```

## Admin Feedback & Learning Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Admin opens dashboard                                       │
│     https://<app>/static/admin/index.html                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Admin.js loads conversations                                │
│     GET /admin/api/conversations?page=1&page_size=20            │
│     ├─ Reads from Azure Blob Storage (conversations container)  │
│     └─ Returns anonymized conversations                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. Admin clicks conversation                                   │
│     GET /admin/api/conversations/<id>                           │
│     ├─ Loads full conversation with all turns                   │
│     └─ Displays: [PERSON_1] asked about [PHONE_1]              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. Admin provides feedback on turn 1                           │
│     POST /admin/api/feedback/<id>                               │
│     Body: {                                                     │
│       "rating": 5,                                              │
│       "tags": ["helpful", "accurate"],                          │
│       "admin_comment": "Great response",                        │
│       "corrected_response": ""                                  │
│     }                                                           │
│     └─ Stores in Azure Blob (feedback container)                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. Admin approves for learning                                 │
│     POST /admin/api/approve/<id>/<turn>                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. FeedbackIndexer.index_approved_response()                   │
│     ├─ Calls Azure OpenAI embeddings API                        │
│     │  Model: text-embedding-ada-002                            │
│     │  Input: user_message + corrected_response                 │
│     │  Output: 1536-dimension vector                            │
│     ├─ Creates search document:                                 │
│     │  {                                                        │
│     │    "id": "uuid",                                          │
│     │    "user_message": "orario farmacia",                     │
│     │    "bot_response": "original response",                   │
│     │    "corrected_response": "corrected",                     │
│     │    "embedding": [0.123, 0.456, ...],                     │
│     │    "rating": 5,                                           │
│     │    "tags": ["helpful"],                                   │
│     │    "usage_count": 0                                       │
│     │  }                                                        │
│     └─ Indexes in Azure AI Search (feedback-responses index)    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ✅ Learning enabled!                                           │
│     Bot will now retrieve this approved response                │
│     when similar questions are asked                            │
└─────────────────────────────────────────────────────────────────┘
```

## RAG Learning - Bot Retrieval Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. New user asks similar question                              │
│     "quando siete aperti?"                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Bot function call for search                                │
│     search_similar_situations("quando siete aperti?")           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. FeedbackIndexer.search_similar_situations()                 │
│     ├─ Generate embedding for query                             │
│     │  Azure OpenAI: text-embedding-ada-002                     │
│     │  "quando siete aperti?" → [0.789, 0.234, ...]            │
│     ├─ Vector search in Azure AI Search                         │
│     │  Index: feedback-responses                                │
│     │  Algorithm: Cosine similarity (HNSW)                      │
│     │  Top K: 3 results                                         │
│     └─ Returns similar approved responses:                      │
│        [                                                        │
│          {                                                      │
│            "user_message": "orario farmacia",                   │
│            "corrected_response": "Approved answer",             │
│            "score": 0.92,                                       │
│            "rating": 5                                          │
│          },                                                     │
│          { ... },                                               │
│          { ... }                                                │
│        ]                                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. Bot context enhanced with approved responses                │
│     LLM Prompt:                                                 │
│     "User asks: quando siete aperti?                            │
│      Here are similar approved responses:                       │
│      1. For 'orario farmacia': [Approved answer]                │
│      2. ...                                                     │
│      Use these as guidance for your response."                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. Bot generates improved response                             │
│     ├─ Uses learned knowledge from approved responses           │
│     └─ Provides consistent, high-quality answer                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. Usage tracking                                              │
│     FeedbackIndexer._increment_usage_count()                    │
│     └─ Updates usage_count in Azure AI Search                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ✅ Bot learned from admin feedback!                            │
│     Better responses over time through continuous learning      │
└─────────────────────────────────────────────────────────────────┘
```

## GDPR Data Request Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  User requests data access (Right to Access - Article 15)      │
│  POST /api/gdpr/data-access                                     │
│  Body: {"identifier": "+39123456789", "identifier_type": "phone"}│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  GDPRCompliance.handle_data_access_request()                    │
│  ├─ Hash phone number: sha256("+39123456789")                  │
│  ├─ Search Azure Blob Storage:                                  │
│  │  ├─ conversations container (by phone_hash)                  │
│  │  └─ anonymization-maps container (by phone_hash)             │
│  ├─ Load encrypted anonymization map                            │
│  ├─ EncryptionUtils.decrypt_map()                               │
│  │  └─ Uses key from Key Vault (ANONYMIZATION_ENCRYPTION_KEY)   │
│  ├─ De-anonymize conversations:                                 │
│  │  "[PERSON_1]" → "Mario Rossi"                               │
│  │  "[PHONE_1]" → "3201234567"                                 │
│  ├─ Package all data:                                           │
│  │  {                                                           │
│  │    "conversations": [...],                                   │
│  │    "feedback": [...],                                        │
│  │    "pii_detected": ["phone", "person_name"]                 │
│  │  }                                                           │
│  └─ Log audit event                                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  User requests data erasure (Right to be Forgotten - Art. 17)  │
│  DELETE /api/gdpr/data-erasure                                  │
│  Body: {"identifier": "+39123456789", "identifier_type": "phone"}│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  GDPRCompliance.handle_data_erasure_request()                   │
│  ├─ Hash phone number                                           │
│  ├─ Delete from Azure Blob Storage:                             │
│  │  ├─ All conversations with phone_hash                        │
│  │  ├─ Anonymization map with phone_hash                        │
│  │  └─ All related feedback                                     │
│  ├─ Verify deletion complete                                    │
│  ├─ Log audit event                                             │
│  └─ Return confirmation                                         │
└─────────────────────────────────────────────────────────────────┘
```

---
**Version**: 1.0  
**Date**: November 16, 2025  
**Status**: Production Ready ✅
