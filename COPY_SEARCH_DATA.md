# Copia Dati Azure Search: Produzione → Test

Questo documento spiega come copiare l'indice di Azure Search e i documenti dall'ambiente di produzione all'ambiente di test.

## 📋 Panoramica

Lo script automatizza:
1. ✅ Copia dello schema dell'indice (campi, configurazione vettoriale, analyzer)
2. ✅ Copia di tutti i documenti indicizzati
3. ✅ Copia dei file blob dallo storage di produzione a quello di test

## 🚀 Utilizzo Rapido

### Opzione 1: Script Bash Automatico (Consigliato)

```bash
# Assicurati di essere loggato in Azure
az login --tenant 3c2f8fc7-162c-4bfa-b056-595e813f4f40

# Esegui lo script
./copy_search_data.sh
```

Lo script:
- ✓ Recupera automaticamente tutti i nomi delle risorse
- ✓ Ottiene le credenziali necessarie da Azure
- ✓ Esegue la copia completa

### Opzione 2: Script Python Manuale

Se preferisci controllare manualmente le variabili d'ambiente:

```bash
# Imposta variabili d'ambiente di produzione
export PROD_SEARCH_ENDPOINT="https://search-farmacia-agent-6fqtj.search.windows.net"
export PROD_SEARCH_KEY="<chiave-admin-produzione>"
export PROD_SEARCH_INDEX="pharmacy-knowledge-base"
export PROD_STORAGE_CONNECTION_STRING="<connection-string-produzione>"
export PROD_STORAGE_CONTAINER="documents"

# Imposta variabili d'ambiente di test
export TEST_SEARCH_ENDPOINT="https://search-test-f4c3w.search.windows.net"
export TEST_SEARCH_KEY="<chiave-admin-test>"
export TEST_SEARCH_INDEX="pharmacy-knowledge-base"
export TEST_STORAGE_CONNECTION_STRING="<connection-string-test>"
export TEST_STORAGE_CONTAINER="documents"

# Esegui lo script Python
python3 copy_search_data.py
```

## 📦 Prerequisiti

### Pacchetti Python

Installa i pacchetti necessari:

```bash
pip install azure-search-documents azure-storage-blob
```

Oppure se usi l'ambiente virtuale del progetto:

```bash
cd server
source .venv/bin/activate
pip install azure-search-documents azure-storage-blob
```

### Permessi Azure

L'utente Azure deve avere i seguenti ruoli:
- **Produzione**: Reader + Search Service Contributor + Storage Blob Data Reader
- **Test**: Search Service Contributor + Storage Blob Data Contributor

## 🔄 Quando Eseguire la Copia

### Durante il Setup Iniziale

Dopo aver provisionato l'ambiente di test per la prima volta:

```bash
azd env select test
azd provision
./copy_search_data.sh
azd deploy
```

### Aggiornamenti Periodici

Quando i documenti in produzione cambiano e vuoi sincronizzare il test:

```bash
./copy_search_data.sh
```

### Dopo Modifiche allo Schema

Se modifichi lo schema dell'indice in produzione:

```bash
./copy_search_data.sh
```

Lo script cancellerà l'indice esistente in test e lo ricreerà con il nuovo schema.

## 🔧 Configurazione Ambienti

### Ambiente di Produzione
- **Resource Group**: `rg-farmacia-agent-6fqtj`
- **Search Service**: `search-farmacia-agent-6fqtj`
- **Storage Account**: `stfarmaciaagent6fqtj`
- **Search Index**: `pharmacy-knowledge-base`

### Ambiente di Test
- **Resource Group**: `rg-test-f4c3w`
- **Search Service**: `search-test-f4c3w`
- **Storage Account**: `stf4c3w`
- **Search Index**: `pharmacy-knowledge-base`

## 🎯 Creazione Automatica Indice

L'applicazione è già configurata per creare automaticamente l'indice se non esiste:

```python
# In document_processor.py
def _ensure_index_exists(self, index_client):
    """Ensure the search index exists with proper schema."""
    # Crea l'indice se non esiste
```

Questo significa che:
- ✓ Al primo upload di documenti, l'indice viene creato automaticamente
- ✓ L'API `/api/documents` può essere usata per caricare i primi documenti
- ✓ Non è strettamente necessario copiare l'indice se vuoi iniziare da zero

## 📊 Output dello Script

Lo script mostra:
```
==========================================
Azure Search Data Copy: Production → Test
==========================================

ℹ Copying search index schema from production to test...
✓ Index created successfully: pharmacy-knowledge-base

------------------------------------------------------------

ℹ Copying documents from production to test...
✓ Found 45 documents in production
ℹ Uploading 45 documents to test index...
✓ Successfully uploaded 45 documents to test index

------------------------------------------------------------

ℹ Copying blobs from production to test storage...
✓ Found 45 blobs in production
✓ Successfully copied 45 blobs to test storage

==========================================
✓ Data copy process completed!
==========================================
```

## 🛠️ Troubleshooting

### Errore: "Missing required environment variable"

Assicurati di eseguire lo script bash che imposta automaticamente le variabili:
```bash
./copy_search_data.sh
```

### Errore: "Index already exists"

Lo script cancella automaticamente l'indice esistente in test. Se non vuoi questo comportamento, commenta la sezione di eliminazione nello script Python.

### Errore: "Authentication failed"

Verifica di essere loggato in Azure:
```bash
az login --tenant 3c2f8fc7-162c-4bfa-b056-595e813f4f40
az account show
```

### Errore: "Resource not found"

Verifica che i nomi delle risorse siano corretti nello script bash:
```bash
az search service show --name search-test-f4c3w --resource-group rg-test-f4c3w
```

## 🔐 Sicurezza

⚠️ **Importante**: 
- Le chiavi API sono sensibili - non committarle mai nel repository
- Lo script recupera le chiavi dinamicamente da Azure
- Le variabili d'ambiente sono temporanee e valide solo per la sessione corrente

## 📝 Alternative

### Opzione 1: Copia Manuale tramite Azure Portal

Puoi copiare i documenti manualmente:
1. Vai al Search Service di produzione nel portale Azure
2. Apri "Search Explorer" e esporta i risultati
3. Importali nel Search Service di test

### Opzione 2: Indexer automatico da Blob Storage

Configura un indexer che legge automaticamente dallo storage:
```bash
# Chiama l'API per creare l'indexer
curl -X POST https://ca-test-f4c3w.azurecontainerapps.io/api/indexer/create
```

### Opzione 3: Upload via API

Usa l'API dell'applicazione per caricare i documenti:
```bash
# Upload di un documento
curl -X POST https://ca-test-f4c3w.azurecontainerapps.io/api/documents \
  -F "file=@documento.pdf"
```

## 📚 Risorse Aggiuntive

- [Azure AI Search Documentation](https://learn.microsoft.com/en-us/azure/search/)
- [Azure Storage Blob Documentation](https://learn.microsoft.com/en-us/azure/storage/blobs/)
- [Azure SDK for Python](https://learn.microsoft.com/en-us/python/api/overview/azure/)
