# 🤖 AI Auto-Evaluation Quick Start

## What's New?

The Admin Feedback System now includes **automatic AI evaluation** using GPT-4o-mini to assess bot responses and prioritize conversations needing human review.

## Key Features

✅ **Automatic Quality Scoring** - Each response gets a 0-10 score  
✅ **Priority Classification** - Critical/High/Medium/Low badges  
✅ **Smart Filtering** - Show only conversations needing review  
✅ **Detailed Analysis** - Issues, strengths, and category scores  
✅ **Efficient Workflow** - Focus on conversations that matter  

## Quick Setup (1 minute)

### 1. Verify Configuration

The system uses your existing Azure OpenAI configuration:
- `AZURE_OPENAI_ENDPOINT` - Already configured ✅
- `AZURE_OPENAI_KEY` - Already configured ✅
- Deployment: `gpt-4o-mini` - Uses your existing deployment

> No additional configuration needed! The AI evaluator uses the same Azure OpenAI resource.

### 2. Restart Server (if needed)

```bash
cd server
python server.py
```

Look for: `INFO - AI evaluator initialized`

### 3. Use in Admin Dashboard

1. Open: `http://localhost:5000/static/admin/index.html`
2. Click **"🤖 Auto-Evaluate All"** button
3. See priority badges on conversations:
   - 🚨 **Critical** - Needs immediate review
   - ⚠️ **High** - Should review soon
   - ℹ️ **Medium** - Optional review
   - ✅ **Good** - Quality is fine

4. Enable **"🤖 Only AI-flagged for review"** checkbox to filter

## Usage Workflow

```
1. Auto-Evaluate → 2. Filter Critical → 3. Review AI Analysis → 4. Add Human Feedback
```

### Example UI

**Conversation List:**
```
Conv-123  [Web]  🚨 Critical (3/10)  → Click to review
Conv-456  [Phone]  ✅ Good (9/10)   → Skip review
Conv-789  [Web]  ⚠️ High (5/10)     → Should review
```

**Conversation Details:**
```
Turn 1: ✅ Good (9/10)
  ✓ Accurate information
  ✓ Professional tone
  
Turn 2: 🚨 Critical (3/10)
  ✗ Factual error detected
  ✗ Incomplete answer
  → Add human feedback here!
```

## API Endpoints

```bash
# Evaluate entire conversation
POST /admin/api/evaluate/{conversation_id}

# Evaluate single turn
POST /admin/api/evaluate/{conversation_id}/{turn_number}

# Get stored evaluation
GET /admin/api/evaluations/{conversation_id}
```

## Evaluation Criteria

Each response is scored on:

| Category | What's Checked |
|----------|----------------|
| **Accuracy** | Factual correctness |
| **Tone** | Professional & empathetic |
| **Context** | Conversation awareness |
| **Completeness** | Fully answers question |
| **Clarity** | Clear & understandable |

## Cost

- ~$0.0002-0.0005 per conversation
- 1000 evaluations ≈ $0.20-0.50
- Cached for 24 hours (no duplicate costs)

## Full Documentation

📖 See [AI_EVALUATION_SYSTEM.md](./AI_EVALUATION_SYSTEM.md) for complete details  
⚙️ See [AI_EVALUATION_CONFIG.md](./AI_EVALUATION_CONFIG.md) for setup guide

## Troubleshooting

**"AI evaluator not initialized"**  
→ Check `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_KEY` are set  
→ Verify Azure OpenAI resource is accessible

**No priority badges showing**  
→ Click "🤖 Auto-Evaluate All" first

**Evaluation failed**  
→ Verify `gpt-4o-mini` deployment exists in your Azure OpenAI resource  
→ Check Azure OpenAI quota and rate limits

---

**Happy Reviewing! 🎯**
