# Setup Automatizzato Ambiente

Questo progetto è configurato per un **deployment completamente automatizzato**. Tutti i passaggi di configurazione vengono eseguiti automaticamente dopo `azd provision`.

## 🚀 Quick Start

### Setup Nuovo Ambiente (Completamente Automatizzato)

```bash
# 1. Crea e seleziona l'ambiente
azd env new <nome-ambiente>
azd env select <nome-ambiente>

# 2. Effettua login (se non già loggato)
az login --tenant 3c2f8fc7-162c-4bfa-b056-595e813f4f40

# 3. Provisioning (include configurazione automatica)
azd provision

# 4. Deploy dell'applicazione
azd deploy
```

**Fatto!** L'ambiente è completamente configurato e pronto all'uso.

---

## 🔧 Cosa Viene Automatizzato

### Durante `azd provision`

Il hook `infra/hooks/postprovision.sh` esegue automaticamente:

#### ✅ 1. Azure AD App Registration
- Crea (o trova) l'App Registration automaticamente
- Nome: `Call Center Voice Agent API - <nome-ambiente>`
- Configura `AZURE_AD_TENANT_ID` e `AZURE_AD_CLIENT_ID`

#### ✅ 2. Configurazione Search Index
- Imposta `AZURE_SEARCH_INDEX` = `pharmacy-knowledge-base`
- Nome predefinito configurabile in `infra/main.bicep`

#### ✅ 3. Aggiornamento Container App
- Ri-esegue `azd provision` per applicare le nuove variabili
- Tutte le env vars vengono iniettate automaticamente nel container

### Nell'Applicazione

#### ✅ 4. Creazione Automatica Indice
- L'app crea l'indice al primo avvio (funzione `_ensure_index_exists`)
- Schema con vector search configurato automaticamente
- Non serve intervento manuale

#### ✅ 5. Configurazione CORS
- CORS automaticamente configurato in base a `ALLOWED_ORIGINS`
- Gestione sicura credentials con wildcard origins

---

## 📋 Configurazioni Predefinite

Tutte le configurazioni hanno valori di default in `infra/main.bicep`:

```bicep
// Automatiche - Non serve configurare
param azureSearchIndex string = 'pharmacy-knowledge-base'
param azureSearchSemanticConfig string = 'default'
param azureSearchTopN string = '5'
param azureSearchStrictness string = '3'

// Configurate automaticamente dal post-provision hook
param azureAdTenantId string = ''  // ← Impostato automaticamente
param azureAdClientId string = ''  // ← Impostato automaticamente
```

---

## 🔄 Copia Dati da Produzione (Opzionale)

Per copiare documenti da produzione a un ambiente di test:

```bash
# Dopo azd provision, esegui:
./copy_search_data.sh
```

Questo copia:
- Schema dell'indice
- Tutti i documenti indicizzati
- File blob dello storage

**Nota**: La copia dati NON è automatica per evitare sovrascritture accidentali.

---

## 🎯 Ambienti Multipli

Puoi creare ambienti illimitati, tutti configurati automaticamente:

```bash
# Ambiente di sviluppo
azd env new dev
azd provision
azd deploy

# Ambiente di staging
azd env new staging
azd provision
azd deploy

# Ambiente di test
azd env new test
azd provision
azd deploy
```

Ogni ambiente avrà:
- ✅ Propria App Registration Azure AD
- ✅ Proprio indice di ricerca
- ✅ Proprie risorse Azure isolate
- ✅ Configurazione automatica completa

---

## 🛠️ Personalizzazione

### Modificare Nome Indice Predefinito

Modifica `infra/main.bicep`:

```bicep
param azureSearchIndex string = 'il-tuo-nome-indice'
```

### Modificare Configurazione Azure AD

Il post-provision hook può essere personalizzato in `infra/hooks/postprovision.sh`:

```bash
# Esempio: usare un'App Registration esistente
azd env set AZURE_AD_CLIENT_ID "<tuo-client-id>"
```

### Saltare Configurazione Automatica

Per disabilitare l'automazione, commenta in `azure.yaml`:

```yaml
hooks:
  postprovision:
    posix:
      shell: sh
      # run: ./infra/hooks/postprovision.sh  # ← Commenta questa riga
```

---

## 📝 Variabili d'Ambiente

### Configurate Automaticamente

Queste variabili vengono impostate automaticamente:

| Variabile | Valore | Origine |
|-----------|--------|---------|
| `AZURE_AD_TENANT_ID` | Tenant ID Azure | Auto-detect da `az account` |
| `AZURE_AD_CLIENT_ID` | App Registration ID | Creata automaticamente |
| `AZURE_SEARCH_INDEX` | `pharmacy-knowledge-base` | Default in `main.bicep` |
| `AZURE_SEARCH_SEMANTIC_CONFIG` | `default` | Default in `main.bicep` |
| `AZURE_SEARCH_ENDPOINT` | URL servizio Search | Da deployment Bicep |
| `AZURE_SEARCH_API_KEY` | Chiave Search | Da Key Vault (auto) |
| `AZURE_STORAGE_CONNECTION_STRING` | Connection string Storage | Da Key Vault (auto) |
| `AZURE_OPENAI_KEY` | Chiave OpenAI | Da Key Vault (auto) |

### Personalizzabili (Opzionali)

```bash
# Cambiare nome indice
azd env set AZURE_SEARCH_INDEX "nome-personalizzato"

# Cambiare configurazione CORS
azd env set ALLOWED_ORIGINS "https://miodominio.com"

# Rate limiting
azd env set RATE_LIMIT_API_COUNT "200"
azd env set RATE_LIMIT_API_WINDOW "3600"
```

Dopo modifiche alle variabili:
```bash
azd provision  # Applica le modifiche
```

---

## 🔍 Verifica Configurazione

Visualizza tutte le variabili configurate:

```bash
azd env get-values
```

Verifica Container App:

```bash
# Lista variabili d'ambiente nel container
az containerapp show \
  --name ca-<env>-<suffix> \
  --resource-group rg-<env>-<suffix> \
  --query "properties.template.containers[0].env" \
  --output table
```

Verifica indice Search:

```bash
# Conta documenti nell'indice
SEARCH_KEY=$(az search admin-key show \
  --service-name search-<env>-<suffix> \
  --resource-group rg-<env>-<suffix> \
  --query primaryKey -o tsv)

curl -s "https://search-<env>-<suffix>.search.windows.net/indexes/pharmacy-knowledge-base/docs/\$count?api-version=2021-04-30-Preview" \
  -H "api-key: $SEARCH_KEY"
```

---

## 🐛 Troubleshooting

### Post-provision Hook Fallisce

Se il post-provision hook fallisce, puoi eseguire manualmente:

```bash
./infra/hooks/postprovision.sh
```

### App Registration Non Creata

Crea manualmente:

```bash
TENANT_ID=$(az account show --query tenantId -o tsv)
CLIENT_ID=$(az ad app create \
  --display-name "Call Center Voice Agent API - <env>" \
  --sign-in-audience AzureADMyOrg \
  --query appId -o tsv)

azd env set AZURE_AD_TENANT_ID "$TENANT_ID"
azd env set AZURE_AD_CLIENT_ID "$CLIENT_ID"
azd provision
```

### Indice Non Creato

L'indice viene creato al primo utilizzo. Puoi forzare la creazione chiamando l'API:

```bash
curl -X POST https://ca-<env>.azurecontainerapps.io/api/indexer/create
```

### Variabili Non Applicate

Dopo modifiche a variabili d'ambiente:

```bash
azd provision  # Riapplica configurazione
azd deploy     # Rideploya se necessario
```

---

## 📚 File Chiave

| File | Scopo |
|------|-------|
| `azure.yaml` | Configurazione azd con hook post-provision |
| `infra/hooks/postprovision.sh` | Script automazione post-deploy |
| `infra/main.bicep` | Configurazioni predefinite e parametri |
| `copy_search_data.sh` | Copia dati da produzione (opzionale) |
| `server/app/document_processor.py` | Creazione automatica indice |

---

## ✅ Checklist Setup Nuovo Ambiente

- [ ] `azd env new <nome>`
- [ ] `az login --tenant <tenant-id>`
- [ ] `azd provision` (include configurazione automatica)
- [ ] Verifica: `azd env get-values | grep AZURE_AD`
- [ ] Verifica: Container App accessibile
- [ ] (Opzionale) `./copy_search_data.sh` per dati produzione
- [ ] `azd deploy`
- [ ] Test applicazione funzionante

**Tempo stimato**: 5-10 minuti per ambiente completo
