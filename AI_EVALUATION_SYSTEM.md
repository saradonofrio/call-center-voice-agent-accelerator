# AI Auto-Evaluation System Documentation

## Overview

The AI Auto-Evaluation System uses Azure OpenAI GPT-4o-mini to automatically assess bot responses and prioritize conversations that need human review. This feature helps admin users focus their feedback efforts on the most critical conversations.

## Features

### 1. Automatic Response Evaluation
- **Quality Scoring**: Each bot response receives a score from 0-10
- **Multi-Dimensional Analysis**: Evaluates responses across 5 categories:
  - **Accuracy**: Information correctness and factual accuracy
  - **Tone**: Professional and appropriate communication style
  - **Context**: Understanding of conversation flow and relevance
  - **Completeness**: Whether the answer fully addresses the question
  - **Clarity**: Clear and understandable language

### 2. Priority Classification
The system assigns priority levels based on scores and detected issues:

- **🚨 Critical** (Score < 4): Needs immediate review
  - Likely contains factual errors, inappropriate responses, or major issues
  - Automatically flagged with red badge
  
- **⚠️ High** (Score < 6): Should be reviewed soon
  - Contains multiple issues or low quality
  - Flagged with orange badge
  
- **ℹ️ Medium** (Score < 8): Optional review
  - Moderate quality with some issues
  - Flagged with blue badge
  
- **✅ Low** (Score ≥ 8): Good quality
  - Minimal or no issues detected
  - Flagged with green badge

### 3. Smart Filtering
- **Filter by Priority**: Use "Only AI-flagged for review" checkbox to see only critical/high priority conversations
- **Efficient Workflow**: Focus human review time on conversations that truly need it

## How to Use

### Step 1: Verify Configuration
The AI evaluator uses your existing Azure OpenAI configuration:

```bash
# Already configured in your container
AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com/
AZURE_OPENAI_KEY=your-key-here
```

The system automatically uses the `gpt-4o-mini` deployment from your Azure OpenAI resource.

> ✅ No additional environment variables needed!

### Step 2: Auto-Evaluate Conversations

#### Option A: Evaluate All Conversations
1. Go to the Admin Dashboard at `/static/admin/index.html`
2. Click the **"🤖 Auto-Evaluate All"** button in the Conversations tab
3. Wait for the evaluation to complete (takes a few seconds per conversation)
4. Conversations will be refreshed with AI evaluation badges

#### Option B: Evaluate Single Conversation
1. Click on a conversation to view details
2. If not yet evaluated, click **"🤖 Evaluate with AI"** button
3. The conversation will be evaluated and the view will refresh

### Step 3: Review AI Judgments

#### In Conversation List
Each conversation card shows:
- **Priority Badge**: Color-coded priority level (Critical/High/Medium/Low)
- **AI Score**: Overall score out of 10
- Example: `🚨 Critical (3/10)` or `✅ Good (9/10)`

#### In Conversation Details
For each turn, you can see:
- **Overall AI Analysis**: Score and priority level
- **Evaluation Summary**: Brief description of the assessment
- **Issues**: List of identified problems
- **Strengths**: List of positive aspects
- **Category Scores**: Detailed breakdown by accuracy, tone, context, etc.

### Step 4: Filter Critical Conversations
1. Check the **"🤖 Only AI-flagged for review"** checkbox
2. The list will show only conversations marked as Critical or High priority
3. Focus your human review on these flagged items

### Step 5: Provide Human Feedback
For conversations that need improvement:
1. Review the AI evaluation insights
2. Click **"💬 Feedback"** button on specific turns
3. Add your admin comments and ratings
4. Optionally provide corrected responses
5. Mark excellent responses as **"✅ Approve for Learning"**

## API Endpoints

### Evaluate Entire Conversation
```http
POST /admin/api/evaluate/{conversation_id}
```

Returns evaluation with overall score, priority, and per-turn analysis.

### Evaluate Single Turn
```http
POST /admin/api/evaluate/{conversation_id}/{turn_number}
```

Returns detailed evaluation for a specific turn.

### Get Stored Evaluation
```http
GET /admin/api/evaluations/{conversation_id}
```

Retrieves previously stored evaluation results.

## Evaluation Criteria

The AI evaluator uses the following system prompt:

- **Accuracy**: Checks for factual correctness and misinformation
- **Tone**: Assesses professionalism, empathy, and appropriateness
- **Context**: Evaluates conversation flow understanding
- **Completeness**: Verifies the answer fully addresses the question
- **Clarity**: Measures response clarity and conciseness

### Critical Issues Flagged
- Factual errors or misinformation
- Inappropriate tone or lack of empathy
- Missing context or irrelevant information
- Incomplete answers
- Unclear or confusing language

## Best Practices

### 1. Regular Evaluation
- Run **"Auto-Evaluate All"** periodically (e.g., daily or weekly)
- Evaluations are cached for 24 hours to avoid redundant processing

### 2. Review Prioritization
- Start with Critical priority conversations
- Move to High priority when time permits
- Use Medium/Low priority for quality audits

### 3. Combine AI + Human Judgment
- AI evaluation provides initial triage
- Human review validates and provides context-specific feedback
- Use AI insights to guide your feedback comments

### 4. Monitor Trends
- Track the distribution of priority levels over time
- Look for patterns in common issues
- Use approved responses to improve the bot

## Implementation Details

### Components Created

1. **Backend Module**: `server/app/ai_evaluator.py`
   - `AIEvaluator` class for GPT-4o-mini integration
   - Async evaluation methods
   - Priority calculation logic

2. **API Endpoints**: Added to `server/server.py`
   - `/admin/api/evaluate/<conversation_id>` - Evaluate full conversation
   - `/admin/api/evaluate/<conversation_id>/<turn>` - Evaluate single turn
   - `/admin/api/evaluations/<conversation_id>` - Get stored evaluation

3. **Frontend Updates**:
   - `server/static/admin/admin.js` - Evaluation functions and UI logic
   - `server/static/admin/index.html` - Filter checkbox and buttons
   - `server/static/admin/admin.css` - Styling for badges and evaluation displays

### Storage
- Evaluations are stored in Azure Blob Storage container `evaluations`
- Format: `eval-{conversation_id}.json`
- Cached for 24 hours before re-evaluation

### Performance
- Single conversation evaluation: ~2-5 seconds
- Batch evaluation: Processes conversations sequentially
- Rate limits apply based on Azure OpenAI quotas

## Troubleshooting

### Evaluation Not Working
1. Check environment variables are set correctly
2. Verify Azure OpenAI deployment name matches `AZURE_OPENAI_EVAL_DEPLOYMENT`
3. Check Azure OpenAI API quotas and rate limits
4. Review server logs for error messages

### Missing Evaluation Data
- Evaluations are stored separately from conversations
- Click "🤖 Evaluate with AI" if data is missing
- Check Azure Blob Storage for `evaluations` container

### Slow Evaluation
- GPT-4o-mini typically responds in 2-5 seconds per conversation
- For many conversations, use batch evaluation during off-peak hours
- Consider increasing Azure OpenAI quota if needed

## Future Enhancements

Potential improvements for future releases:

1. **Batch Processing**: Asynchronous background evaluation of multiple conversations
2. **Custom Evaluation Criteria**: Admin-configurable evaluation dimensions
3. **Trend Analysis**: Dashboard showing evaluation trends over time
4. **Auto-Feedback**: Automatically submit low-priority feedback
5. **Integration with Training**: Use evaluations to automatically fine-tune the bot

## Security Notes

- AI evaluations may contain PII from conversations (already anonymized)
- Evaluation data follows same GDPR compliance as conversation data
- Admin authentication required for all evaluation endpoints
- Rate limiting protects against abuse

## Cost Considerations

- Each evaluation makes 1 API call to Azure OpenAI (GPT-4o-mini)
- Typical cost: ~$0.0001-0.0005 per conversation evaluation
- Consider caching strategy (24h default) to minimize costs
- Monitor Azure OpenAI usage in Azure Portal

## Support

For issues or questions:
1. Check server logs in Application Insights
2. Review Azure OpenAI deployment status
3. Verify all configuration values
4. Contact system administrator

---

**Version**: 1.0  
**Last Updated**: November 2025  
**Author**: Call Center Voice Agent Team
