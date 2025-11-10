# Test Logs - Salvataggio Automatico su Azure Storage

## Panoramica

Il sistema di test "Simulazione Utenti" ora salva automaticamente i risultati di ogni test eseguito su Azure Blob Storage nel container `testlogs` in formato JSON.

## Come Funziona

### 1. Esecuzione Test
Quando un utente esegue un test dalla pagina `/static/test-bot.html`:
- Configura il numero di dialoghi e turni
- Imposta la distribuzione delle tipologie di utenti (Collaborativo, Fuori Tema, Malevolo)
- Avvia il test

### 2. Salvataggio Automatico
Al termine del test, i risultati vengono automaticamente salvati:
- **Container**: `testlogs` (creato automaticamente se non esiste)
- **Formato file**: `test-YYYY-MM-DDTHH-MM-SS-mmmZ.json`
- **Endpoint API**: `POST /api/test-logs`

### 3. Struttura Dati JSON

Ogni file salvato contiene:

```json
{
  "timestamp": "ISO 8601 timestamp del test",
  "configuration": {
    "dialogCount": "numero di dialoghi simulati",
    "turnsPerDialog": "turni per dialogo",
    "userTypeDistribution": {
      "collaborative": "percentuale utenti collaborativi",
      "offtopic": "percentuale utenti fuori tema", 
      "malicious": "percentuale utenti malevoli"
    }
  },
  "metrics": {
    "accuracy": "percentuale di accuratezza",
    "contextRetention": "percentuale mantenimento contesto",
    "manipulationResistance": "percentuale resistenza attacchi",
    "appropriateResponses": "percentuale risposte appropriate",
    "totalTurns": "numero totale turni",
    "successfulTurns": "numero turni riusciti"
  },
  "dialogs": [
    {
      "number": "numero dialogo",
      "userType": "collaborative|offtopic|malicious",
      "turns": [
        {
          "turn": "numero turno",
          "userMessage": "messaggio utente",
          "botMessage": "risposta bot",
          "evaluation": {
            "appropriate": "true|false",
            "contextBreak": "true|false",
            "critical": "true|false",
            "criticalReason": "descrizione problema critico",
            "score": "punteggio 0-100"
          }
        }
      ],
      "analysis": {
        "successfulTurns": "numero turni riusciti",
        "failedTurns": "numero turni falliti",
        "contextBreaks": "numero perdite contesto",
        "criticalIssue": "descrizione problema critico o null"
      }
    }
  ],
  "criticalIssues": [
    {
      "dialog": "numero dialogo",
      "type": "tipo utente",
      "issue": "descrizione problema"
    }
  ],
  "summary": {
    "totalDialogs": "numero totale dialoghi",
    "totalTurns": "numero totale turni",
    "successRate": "tasso di successo %",
    "criticalIssuesCount": "numero problemi critici"
  }
}
```

## File Modificati

### 1. `/server/server.py`
Aggiunto nuovo endpoint `POST /api/test-logs`:
- Riceve i risultati del test in formato JSON
- Crea il container `testlogs` se non esiste
- Salva il file con timestamp nel nome
- Gestisce errori e logging

### 2. `/server/static/test-bot.html`
Aggiunta funzione `saveTestResults()`:
- Raccoglie tutti i dati del test
- Invia i dati all'endpoint API
- Gestisce errori in console

## Configurazione Richiesta

### Variabili d'Ambiente
Il sistema utilizza la connessione Azure Storage già configurata:

```bash
AZURE_STORAGE_CONNECTION_STRING=<your-connection-string>
```

### Nessuna Configurazione Aggiuntiva Necessaria
Il container `testlogs` viene creato automaticamente alla prima esecuzione.

## Accesso ai Log

### Azure Portal
1. Vai al tuo Storage Account
2. Seleziona "Containers"
3. Apri il container `testlogs`
4. Visualizza o scarica i file JSON

### Azure Storage Explorer
1. Connetti al tuo Storage Account
2. Naviga a `Blob Containers` > `testlogs`
3. Scarica o visualizza i file

### Azure CLI
```bash
# Lista tutti i test logs
az storage blob list \
  --account-name <storage-account-name> \
  --container-name testlogs \
  --output table

# Scarica un file specifico
az storage blob download \
  --account-name <storage-account-name> \
  --container-name testlogs \
  --name test-2025-11-10T14-30-00-000Z.json \
  --file ./test-results.json
```

### Python Script per Analisi
```python
from azure.storage.blob import BlobServiceClient
import json

# Connetti a Azure Storage
connection_string = "your-connection-string"
blob_service_client = BlobServiceClient.from_connection_string(connection_string)
container_client = blob_service_client.get_container_client("testlogs")

# Lista tutti i test
blobs = container_client.list_blobs()
for blob in blobs:
    print(f"Test: {blob.name}")
    
    # Scarica e analizza
    blob_client = container_client.get_blob_client(blob.name)
    data = json.loads(blob_client.download_blob().readall())
    
    print(f"  Accuracy: {data['metrics']['accuracy']}%")
    print(f"  Critical Issues: {data['summary']['criticalIssuesCount']}")
    print()
```

## Analisi dei Dati

### Query Comuni

**Calcolare l'accuratezza media di tutti i test:**
```python
import json
from azure.storage.blob import BlobServiceClient

def calculate_average_accuracy(connection_string):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client("testlogs")
    
    accuracies = []
    for blob in container_client.list_blobs():
        blob_client = container_client.get_blob_client(blob.name)
        data = json.loads(blob_client.download_blob().readall())
        accuracies.append(data['metrics']['accuracy'])
    
    return sum(accuracies) / len(accuracies) if accuracies else 0
```

**Trovare test con problemi critici:**
```python
def find_critical_issues(connection_string):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client("testlogs")
    
    tests_with_issues = []
    for blob in container_client.list_blobs():
        blob_client = container_client.get_blob_client(blob.name)
        data = json.loads(blob_client.download_blob().readall())
        
        if data['summary']['criticalIssuesCount'] > 0:
            tests_with_issues.append({
                'timestamp': data['timestamp'],
                'issues': data['criticalIssues']
            })
    
    return tests_with_issues
```

**Confrontare performance per tipo utente:**
```python
def analyze_by_user_type(connection_string):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client("testlogs")
    
    stats = {
        'collaborative': [],
        'offtopic': [],
        'malicious': []
    }
    
    for blob in container_client.list_blobs():
        blob_client = container_client.get_blob_client(blob.name)
        data = json.loads(blob_client.download_blob().readall())
        
        for dialog in data['dialogs']:
            success_rate = dialog['analysis']['successfulTurns'] / len(dialog['turns'])
            stats[dialog['userType']].append(success_rate)
    
    return {
        user_type: sum(rates) / len(rates) if rates else 0
        for user_type, rates in stats.items()
    }
```

## Esempio di Output

Vedi il file `docs/test-logs-example.json` per un esempio completo della struttura dati salvata.

## Vantaggi

1. **Tracciabilità**: Ogni test è salvato con timestamp e configurazione completa
2. **Analisi storica**: Possibilità di confrontare test nel tempo
3. **Debugging**: Dettagli completi per identificare problemi
4. **Reporting**: Dati strutturati per generare report automatici
5. **Compliance**: Audit trail per test di sicurezza e qualità

## Troubleshooting

### Errore: "Azure Storage not configured"
Verifica che `AZURE_STORAGE_CONNECTION_STRING` sia impostata nel file `.env` o nelle variabili d'ambiente.

### I file non vengono salvati
Controlla i log del server per errori. Verifica anche i permessi dello Storage Account.

### Container non creato automaticamente
Crea manualmente il container:
```bash
az storage container create \
  --name testlogs \
  --account-name <storage-account-name>
```

## Sicurezza

- I test logs possono contenere informazioni sensibili sui test di sicurezza
- Limita l'accesso al container `testlogs` solo agli utenti autorizzati
- Considera l'uso di SAS tokens con scadenza per l'accesso programmatico
- Configura policy di retention per eliminare log vecchi automaticamente
