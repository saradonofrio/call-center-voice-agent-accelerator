# Configurazione Azure AI Search per il Bot Farmacia

## 📋 Panoramica

Il bot può utilizzare Azure AI Search per rispondere basandosi sui tuoi documenti (catalogo prodotti, FAQ, informazioni farmaceutiche, ecc.) invece di usare solo la conoscenza generale del modello.

## 🚀 Setup Passo per Passo

### 1. Crea un Azure AI Search Service

```bash
# Crea il servizio Azure AI Search
az search service create \
  --name farmacia-search \
  --resource-group rg-farmacia-agent \
  --sku basic \
  --location swedencentral
```

### 2. Ottieni le Credenziali

```bash
# Ottieni l'endpoint
az search service show \
  --name farmacia-search \
  --resource-group rg-farmacia-agent \
  --query "endpoint" -o tsv

# Ottieni l'admin key
az search admin-key show \
  --service-name farmacia-search \
  --resource-group rg-farmacia-agent \
  --query "primaryKey" -o tsv
```

### 3. Carica i Tuoi Documenti

Puoi caricare documenti in vari modi:

#### Opzione A: Usa Azure Portal
1. Vai su Azure Portal → Azure AI Search
2. Clicca su "Import data"
3. Seleziona la sorgente (Blob Storage, SQL, ecc.)
4. Configura l'indexer
5. Abilita "Semantic search" (consigliato)

#### Opzione B: Usa Python Script

```python
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

# Configurazione
search_endpoint = "https://farmacia-search.search.windows.net"
admin_key = "YOUR_ADMIN_KEY"
index_name = "rag-1762098848175"

# Crea l'index
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch
)

fields = [
    SearchField(name="id", type=SearchFieldDataType.String, key=True),
    SearchField(name="title", type=SearchFieldDataType.String, searchable=True),
    SearchField(name="content", type=SearchFieldDataType.String, searchable=True),
    SearchField(name="category", type=SearchFieldDataType.String, filterable=True),
]

semantic_config = SemanticConfiguration(
    name="default",
    prioritized_fields=SemanticPrioritizedFields(
        title_field=SemanticField(field_name="title"),
        content_fields=[SemanticField(field_name="content")]
    )
)

semantic_search = SemanticSearch(configurations=[semantic_config])

index = SearchIndex(
    name=index_name,
    fields=fields,
    semantic_search=semantic_search
)

# Crea l'index
index_client = SearchIndexClient(endpoint=search_endpoint, credential=AzureKeyCredential(admin_key))
index_client.create_or_update_index(index)

# Carica documenti
search_client = SearchClient(endpoint=search_endpoint, index_name=index_name, credential=AzureKeyCredential(admin_key))

documents = [
    {
        "id": "1",
        "title": "Paracetamolo 500mg",
        "content": "Il paracetamolo è un analgesico e antipiretico usato per trattare dolore e febbre. Dosaggio: 1-2 compresse ogni 4-6 ore, max 4g/giorno.",
        "category": "farmaci"
    },
    {
        "id": "2",
        "title": "Orari Farmacia",
        "content": "La farmacia è aperta dal lunedì al venerdì dalle 9:00 alle 19:00, sabato dalle 9:00 alle 13:00. Chiusi la domenica.",
        "category": "info"
    }
]

search_client.upload_documents(documents=documents)
```

### 4. Configura le Variabili d'Ambiente

Aggiungi queste variabili alle tue configurazioni Azure Container Apps:

```bash
# Richieste
AZURE_SEARCH_ENDPOINT=https://farmacia-search.search.windows.net
AZURE_SEARCH_INDEX=farmacia-docs

# Opzionali
AZURE_SEARCH_API_KEY=YOUR_ADMIN_KEY
AZURE_SEARCH_SEMANTIC_CONFIG=default
AZURE_SEARCH_TOP_N=5
AZURE_SEARCH_STRICTNESS=3
```

**Nota**: Se usi Managed Identity, puoi omettere `AZURE_SEARCH_API_KEY` e assegnare il ruolo "Search Index Data Reader" alla tua Managed Identity.

### 5. Imposta le Variabili su Azure

```bash
# Imposta le variabili d'ambiente
az containerapp update \
  --name ca-farmacia-agent \
  --resource-group rg-farmacia-agent \
  --set-env-vars \
    AZURE_SEARCH_ENDPOINT=https://farmacia-search.search.windows.net \
    AZURE_SEARCH_INDEX=farmacia-docs \
    AZURE_SEARCH_API_KEY=YOUR_KEY \
    AZURE_SEARCH_SEMANTIC_CONFIG=default \
    AZURE_SEARCH_TOP_N=5 \
    AZURE_SEARCH_STRICTNESS=3
```

## 📊 Parametri di Configurazione

### `AZURE_SEARCH_TOP_N` (default: 5)
Numero di documenti da recuperare per ogni ricerca
- **Consigliato**: 3-5 per risposte veloci
- **Più alto**: Più contesto ma risposte più lente

### `AZURE_SEARCH_STRICTNESS` (1-5, default: 3)
Quanto strettamente il bot deve attenersi ai documenti
- **1-2**: Più creativo, può aggiungere informazioni generali
- **3**: Bilanciato (consigliato)
- **4-5**: Solo informazioni dai documenti

### `AZURE_SEARCH_SEMANTIC_CONFIG`
Nome della configurazione semantica nell'index
- Migliora la rilevanza dei risultati
- Richiede Azure AI Search tier Basic o superiore

## 🧪 Test

Dopo il deploy, testa con domande specifiche sui tuoi documenti:

```
Utente: "Quali sono gli orari della farmacia?"
Bot: "La farmacia è aperta dal lunedì al venerdì dalle 9:00 alle 19:00..."

Utente: "Ho mal di testa, cosa mi consigli?"
Bot: "Per il mal di testa puoi usare il Paracetamolo 500mg..."
```

## ⚠️ Note Importanti

1. **Costi**: Azure AI Search ha costi associati al tier scelto
2. **Semantic Search**: Richiede tier Basic o superiore
3. **Managed Identity**: Consigliata per produzione invece di API key
4. **Aggiornamento Documenti**: Puoi aggiornare l'index senza rideploy del bot

## 🔍 Troubleshooting

### Il bot non usa Azure Search
- Verifica che `AZURE_SEARCH_ENDPOINT` e `AZURE_SEARCH_INDEX` siano impostati
- Controlla i log: dovresti vedere "Azure AI Search enabled with index: ..."

### Errori di autenticazione
- Verifica che l'API key sia corretta
- Se usi Managed Identity, assicurati che abbia i permessi giusti

### Risposte non rilevanti
- Aumenta `AZURE_SEARCH_STRICTNESS` (4 o 5)
- Riduci `AZURE_SEARCH_TOP_N` se ci sono troppi risultati
- Migliora la qualità dei documenti nell'index

## 📚 Risorse

- [Azure AI Search Documentation](https://learn.microsoft.com/azure/search/)
- [Semantic Search](https://learn.microsoft.com/azure/search/semantic-search-overview)
- [Azure OpenAI on Your Data](https://learn.microsoft.com/azure/ai-services/openai/concepts/use-your-data)
