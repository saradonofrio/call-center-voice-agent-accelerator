# Test Logs - Changelog

## 2025-11-10 - Implementazione Salvataggio Test Logs su Azure Storage

### 🎯 Obiettivo
Implementare il salvataggio automatico dei risultati dei test "Simulazione Utenti" su Azure Blob Storage nel container `testlogs` in formato JSON per facilitare l'analisi storica e il monitoraggio delle performance del bot.

### ✅ Modifiche Implementate

#### 1. Backend - `server/server.py`
- **Nuovo endpoint API**: `POST /api/test-logs`
  - Riceve i risultati dei test in formato JSON
  - Crea automaticamente il container `testlogs` se non esiste
  - Salva i file con naming convention: `test-YYYY-MM-DDTHH-MM-SS-mmmZ.json`
  - Gestisce errori con logging appropriato
  - Rate limiting applicato (100 richieste/ora)

#### 2. Frontend - `server/static/test-bot.html`
- **Nuova funzione**: `saveTestResults(results, dialogCount, turnsPerDialog, percentages)`
  - Raccoglie tutti i dati del test
  - Aggiunge timestamp e configurazione
  - Invia i dati all'endpoint `/api/test-logs` via POST
  - Gestisce errori in console senza bloccare l'interfaccia
- **Integrazione**: Chiamata automatica dopo il completamento di ogni test
- **Non invasiva**: L'utente non deve fare nulla, il salvataggio avviene automaticamente

#### 3. Documentazione - `docs/TEST_LOGS_SETUP.md`
Guida completa che include:
- Panoramica del sistema
- Struttura completa dei dati JSON
- Configurazione richiesta
- Metodi di accesso ai log (Portal, CLI, Storage Explorer)
- Script Python di esempio per analisi
- Query comuni per analisi dati
- Troubleshooting
- Best practices per sicurezza

#### 4. Script di Analisi - `server/analyze_test_logs.py`
Script Python completo per analizzare i test logs:
- Calcolo metriche medie
- Analisi per tipo utente
- Identificazione problemi critici
- Analisi trend nel tempo
- Export sommario in JSON
- Report formattato su console

#### 5. Esempio Dati - `docs/test-logs-example.json`
File JSON di esempio che mostra la struttura completa dei dati salvati

#### 6. Aggiornamenti README
- Aggiunta nota in evidenza all'inizio del README
- Nuova sezione "Test Bot - Simulazione Utenti" nella sezione Testing
- Link alla documentazione completa

### 📊 Struttura Dati JSON

Ogni test salvato contiene:
```json
{
  "timestamp": "ISO 8601 timestamp",
  "configuration": { ... },
  "metrics": { ... },
  "dialogs": [ ... ],
  "criticalIssues": [ ... ],
  "summary": { ... }
}
```

### 🔧 Configurazione

**Nessuna configurazione aggiuntiva necessaria!** 
Il sistema utilizza la connessione Azure Storage già configurata tramite `AZURE_STORAGE_CONNECTION_STRING`.

### 🚀 Come Usare

1. **Esegui un test** dalla pagina `/static/test-bot.html`
2. **I risultati vengono salvati automaticamente** su Azure Storage
3. **Accedi ai log**:
   - Azure Portal → Storage Account → Container `testlogs`
   - Azure Storage Explorer
   - Azure CLI
   - Script Python `analyze_test_logs.py`

### 📈 Vantaggi

1. **Tracciabilità**: Ogni test è salvato con timestamp e configurazione completa
2. **Analisi storica**: Confronta performance nel tempo
3. **Debugging**: Dettagli completi per identificare problemi
4. **Reporting**: Dati strutturati per report automatici
5. **Compliance**: Audit trail per test di sicurezza e qualità
6. **Non invasivo**: Salvataggio trasparente senza impatto sull'utente

### 🔐 Sicurezza

- I test logs sono salvati in un container dedicato separato dai documenti
- Accesso controllato tramite permessi Azure Storage
- Possibilità di configurare retention policy
- Container name lowercase per conformità Azure Storage

### 📁 File Creati/Modificati

**Modificati:**
- `/server/server.py` - Aggiunto endpoint `/api/test-logs`
- `/server/static/test-bot.html` - Aggiunta funzione `saveTestResults()`
- `/README.md` - Aggiornata documentazione

**Creati:**
- `/docs/TEST_LOGS_SETUP.md` - Documentazione completa
- `/docs/test-logs-example.json` - Esempio struttura dati
- `/server/analyze_test_logs.py` - Script analisi
- `/docs/TEST_LOGS_CHANGELOG.md` - Questo file

### 🧪 Test Suggeriti

1. Eseguire un test dalla pagina web
2. Verificare che il file appaia nel container `testlogs`
3. Scaricare e verificare la struttura JSON
4. Eseguire lo script `analyze_test_logs.py`
5. Verificare che i dati siano completi e corretti

### 📝 Note Tecniche

- **Container name**: `testlogs` (lowercase per conformità Azure)
- **Formato file**: JSON con indentazione per leggibilità
- **Encoding**: UTF-8 con `ensure_ascii=False` per caratteri internazionali
- **Naming convention**: Timestamp ISO 8601 sanitizzato per filesystem
- **Rate limiting**: Protezione contro abusi (100 req/h)
- **Error handling**: Errori loggati ma non bloccano l'utente

### 🔄 Prossimi Sviluppi Possibili

- Dashboard web per visualizzare statistiche test
- Alert automatici per problemi critici
- Integrazione con Azure Monitor
- Export in altri formati (CSV, Excel)
- Confronto automatico tra test
- Retention policy configurabile
- Compressione automatica file vecchi
