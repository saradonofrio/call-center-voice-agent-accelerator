# Quick Fix: Disable Azure Search

Se il bot non risponde più dopo aver abilitato Azure Search, segui questi passi:

## 🚫 Disabilitare Azure Search Temporaneamente

### Opzione 1: Rimuovi le variabili d'ambiente su Azure

```bash
az containerapp update \
  --name ca-farmacia-agent-6fqtj \
  --resource-group rg-farmacia-agent-6fqtj \
  --remove-env-vars \
    AZURE_SEARCH_ENDPOINT \
    AZURE_SEARCH_INDEX \
    AZURE_SEARCH_API_KEY
```

Poi rideploy:
```bash
azd deploy
```

### Opzione 2: Commenta la configurazione nel codice

Modifica temporaneamente `acs_media_handler.py` per disabilitare Azure Search:

```python
# Temporaneamente disabilita Azure Search
self.azure_search_config = None
# if config.get("AZURE_SEARCH_ENDPOINT") and config.get("AZURE_SEARCH_INDEX"):
#     self.azure_search_config = {
#         ...
#     }
```

## 🔍 Debug del Problema

Dopo il prossimo deploy, controlla i log di Azure per vedere:

### 1. Configurazione inviata
Cerca nel log:
```
Sending session config: {
  "type": "session.update",
  "session": {
    ...
    "data_sources": [ ... ]
  }
}
```

### 2. Errori ricevuti
Cerca nel log:
```
Voice Live Error: {
  "error": {
    "code": "...",
    "message": "..."
  }
}
```

## ⚠️ Problemi Comuni

### 1. Azure Search non configurato correttamente
**Sintomo**: Nessuna risposta dal bot
**Soluzione**: Verifica che l'index esista e contenga dati

### 2. Autenticazione fallita
**Sintomo**: Errore "authentication failed"
**Soluzione**: Verifica che l'API key sia corretta o che Managed Identity abbia i permessi

### 3. Query type non supportato
**Sintomo**: Errore nel log su "query_type"
**Soluzione**: Rimuovi `"query_type"` dalla configurazione se non usi embeddings

### 4. Index vuoto
**Sintomo**: Bot risponde "non ho trovato informazioni"
**Soluzione**: Carica documenti nell'index Azure Search

## ✅ Test Dopo il Fix

Dopo aver disabilitato Azure Search o fixato il problema, testa:

1. **Senza Azure Search**: Il bot dovrebbe rispondere normalmente
2. **Con Azure Search**: Il bot dovrebbe rispondere basandosi sui documenti

## 📝 Prossimi Passi

Una volta che il bot funziona di nuovo senza Azure Search:

1. Crea un index Azure Search di test
2. Carica documenti di esempio
3. Testa la configurazione in locale (se possibile)
4. Riattiva Azure Search con configurazione corretta
