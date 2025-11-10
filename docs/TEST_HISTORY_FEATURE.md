# Storico Test - Nuove Funzionalità

## 📊 Panoramica

La pagina `test-bot.html` ora include una sezione completa per visualizzare e analizzare lo storico di tutti i test eseguiti.

## ✨ Nuove Funzionalità

### 1. **Statistiche Aggregate**
Visualizza metriche aggregate di tutti i test:
- 📊 Numero totale di test eseguiti
- ✅ Accuratezza media
- 🧠 Mantenimento contesto medio
- 🛡️ Resistenza agli attacchi media
- ⚠️ Totale problemi critici riscontrati
- 💬 Totale dialoghi simulati

### 2. **Filtri Avanzati**
Filtra i test per:
- **Data**: Seleziona intervallo temporale (da/a)
- **Accuratezza**: Min/Max percentuale
- **Numero Dialoghi**: Filtra per configurazione specifica
- **Problemi Critici**: 
  - Tutti i test
  - Solo test con problemi
  - Solo test senza problemi

### 3. **Visualizzazione Dettagliata**
Per ogni test puoi vedere:
- 📅 Data e ora esecuzione
- ⚙️ Configurazione (dialoghi, turni, distribuzione utenti)
- 📊 Metriche complete
- 🚨 Problemi critici (se presenti)
- 💬 **Tutti i dialoghi** con:
  - Messaggi completi utente/bot
  - Score di valutazione per ogni turno
  - Indicatori di contesto e problemi critici
  - Analisi per dialogo

## 🎨 Interfaccia

### Tab Navigation
La pagina è divisa in due tab:
1. **🚀 Nuovo Test** - Esegui un nuovo test (interfaccia esistente)
2. **📊 Storico Test** - Visualizza test passati (nuova funzionalità)

### Card Test Espandibili
Ogni test è visualizzato in una card che mostra:
- **Header**: Data, configurazione, accuratezza
- **Metriche rapide**: Contesto, resistenza, risposte OK
- **Click per espandere**: Mostra tutti i dettagli e dialoghi

## 🔧 Implementazione Tecnica

### Frontend (`test-bot.html`)

**Nuovi Stili CSS:**
- Tab navigation system
- Filter section
- Test cards con expand/collapse
- Aggregate statistics cards
- Responsive grid layouts

**Nuove Funzioni JavaScript:**
- `switchTab(tabName)` - Gestisce navigazione tra tab
- `loadTestHistory()` - Carica tutti i test da API
- `displayAggregateStats(tests)` - Calcola e mostra statistiche aggregate
- `displayTestList(tests)` - Renderizza lista test
- `renderTestDetails(test)` - Renderizza dettagli dialoghi
- `toggleTestDetails(index)` - Expand/collapse dettagli
- `applyFilters()` - Applica filtri selezionati
- `resetFilters()` - Reset tutti i filtri
- `refreshHistory()` - Ricarica dati da server

### Backend (`server.py`)

**Nuovo Endpoint: `GET /api/test-logs`**
```python
GET /api/test-logs
```

**Funzionalità:**
- Connessione a Azure Blob Storage
- Lista tutti i blob nel container `testlogs`
- Download e parsing di ogni file JSON
- Ritorna array completo di test

**Response:**
```json
{
  "tests": [...],
  "count": 10
}
```

## 📖 Come Usare

### Visualizzare lo Storico
1. Vai su `/static/test-bot.html`
2. Clicca sul tab **"📊 Storico Test"**
3. La pagina carica automaticamente tutti i test

### Filtrare i Test
1. Nella sezione "🔍 Filtra Test":
   - Imposta i criteri desiderati
   - Clicca **"🔍 Applica Filtri"**
2. Le statistiche e la lista si aggiornano automaticamente
3. Clicca **"🔄 Reset"** per rimuovere i filtri

### Visualizzare Dettagli Dialoghi
1. Trova il test di interesse nella lista
2. **Clicca sulla card** del test
3. La card si espande mostrando:
   - Problemi critici (se presenti)
   - Tutti i dialoghi completi
   - Ogni turno con messaggi e valutazioni

### Aggiornare i Dati
- Clicca **"⟳ Aggiorna"** per ricaricare i dati dal server

## 🎯 Vantaggi

1. **Analisi Storica**: Vedi come performano i tuoi bot nel tempo
2. **Identificazione Pattern**: Trova problemi ricorrenti
3. **Comparazione**: Confronta diversi test e configurazioni
4. **Debug Facilitato**: Visualizza conversazioni complete per debugging
5. **Reporting**: Dati pronti per creare report

## 🔄 Aggiornamenti Automatici

- **Nuovo test completato**: I risultati vengono salvati automaticamente
- **Caricamento lazy**: I dati vengono caricati solo quando apri il tab Storico
- **Performance**: Lista ottimizzata anche con molti test

## 📊 Esempi di Utilizzo

### Trovare test con bassa accuratezza
1. Imposta "Accuratezza Max" a 70%
2. Applica filtri
3. Esamina i dialoghi per capire le cause

### Analizzare evoluzione nel tempo
1. Ordina i test per data (automatico)
2. Confronta metriche tra test recenti e vecchi
3. Identifica miglioramenti o regressioni

### Verificare resistenza attacchi
1. Filtra per "Solo con problemi"
2. Espandi i test per vedere tentativi di attacco
3. Analizza come il bot ha risposto

## 🐛 Troubleshooting

### "Nessun test trovato"
- Verifica di aver eseguito almeno un test
- Controlla che Azure Storage sia configurato correttamente
- Prova a cliccare "⟳ Aggiorna"

### "Errore nel caricamento"
- Verifica la connessione a Azure Storage
- Controlla i log del server per dettagli
- Assicurati che `AZURE_STORAGE_CONNECTION_STRING` sia configurata

### Filtri non funzionano
- Clicca "🔄 Reset" e riprova
- Verifica che i valori inseriti siano validi
- Controlla la console JavaScript per errori

## 📝 Note Tecniche

- **Formato dati**: JSON conforme alla struttura definita in `TEST_LOGS_SETUP.md`
- **Sorting**: Test ordinati per data decrescente (più recente prima)
- **Performance**: Rendering ottimizzato per liste lunghe
- **Responsive**: Interfaccia adattiva per mobile/desktop
- **Accessibilità**: Colori e icone per indicare stati

## 🚀 Sviluppi Futuri

Possibili miglioramenti:
- [ ] Export CSV/Excel per analisi esterna
- [ ] Grafici trend nel tempo
- [ ] Comparazione side-by-side di due test
- [ ] Download singolo test in JSON
- [ ] Delete test dalla UI
- [ ] Search full-text nei dialoghi
- [ ] Notifiche per nuovi test critici
