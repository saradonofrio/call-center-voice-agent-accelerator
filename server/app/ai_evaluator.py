"""
AI Response Evaluator using Azure OpenAI GPT-4o-mini.

This module automatically evaluates bot responses to identify quality issues
and prioritize conversations that need human review.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from openai import AsyncAzureOpenAI
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential

logger = logging.getLogger(__name__)


class AIEvaluator:
    """
    Evaluates bot responses using GPT-4o-mini to identify quality issues.
    
    Features:
    - Automatic quality assessment of bot responses
    - Categorization of issues (accuracy, tone, context, completeness)
    - Priority scoring for human review
    - Batch evaluation support
    """
    
    # Evaluation categories
    CATEGORIES = {
        "accuracy": "Information accuracy and correctness",
        "tone": "Professional and appropriate tone",
        "context": "Context awareness and relevance",
        "completeness": "Complete and satisfactory answer",
        "clarity": "Clear and understandable response"
    }
    
    # Priority levels
    PRIORITY_CRITICAL = "critical"  # Needs immediate review
    PRIORITY_HIGH = "high"          # Should be reviewed soon
    PRIORITY_MEDIUM = "medium"      # Optional review
    PRIORITY_LOW = "low"            # Likely good quality
    
    def __init__(
        self,
        azure_openai_endpoint: str,
        deployment_name: str = "gpt-4o-mini",
        client_id: Optional[str] = None,
        azure_openai_key: Optional[str] = None
    ):
        """
        Initialize AI evaluator with Managed Identity authentication.
        
        Args:
            azure_openai_endpoint: Azure OpenAI endpoint URL
            deployment_name: Name of GPT-4o-mini deployment
            client_id: Managed identity client ID (optional, for user-assigned identity)
            azure_openai_key: Azure OpenAI API key (optional, fallback if MI not available)
        """
        # Store configuration
        self.azure_openai_endpoint = azure_openai_endpoint
        self.deployment_name = deployment_name
        self.client_id = client_id
        self.azure_openai_key = azure_openai_key
        
        # Determine authentication method
        if client_id:
            self.use_managed_identity = True
            logger.info("Using user-assigned managed identity for authentication")
        elif not azure_openai_key:
            self.use_managed_identity = True
            logger.info("Using default Azure credential (managed identity) for authentication")
        else:
            self.use_managed_identity = False
            logger.info("Using API key for authentication")
            # Initialize client for API key auth
            self.client = AsyncAzureOpenAI(
                azure_endpoint=azure_openai_endpoint,
                api_key=azure_openai_key,
                api_version="2024-08-01-preview"
            )
        
        logger.info(f"AI Evaluator initialized with deployment: {deployment_name}")
    
    async def _get_auth_token(self) -> str:
        """Get authentication token using same pattern as Voice Live."""
        if self.use_managed_identity:
            # Use same authentication pattern as Voice Live handler
            if self.client_id:
                # User-assigned managed identity (same as Voice Live)
                async with ManagedIdentityCredential(client_id=self.client_id) as credential:
                    token = await credential.get_token("https://cognitiveservices.azure.com/.default")
                    return token.token
            else:
                # System-assigned managed identity
                async with DefaultAzureCredential() as credential:
                    token = await credential.get_token("https://cognitiveservices.azure.com/.default")
                    return token.token
        return None
    
    async def _get_client(self) -> AsyncAzureOpenAI:
        """Get OpenAI client with authentication."""
        if self.use_managed_identity:
            # Get fresh token and create client with default_headers
            token = await self._get_auth_token()
            return AsyncAzureOpenAI(
                azure_endpoint=self.azure_openai_endpoint,
                api_key="not-used",  # Required parameter but not used with MI
                api_version="2024-08-01-preview",
                default_headers={"Authorization": f"Bearer {token}"}
            )
        return self.client
    
    async def evaluate_response(
        self,
        user_message: str,
        bot_response: str,
        context: Optional[str] = None
    ) -> Dict:
        """
        Evaluate a single bot response.
        
        Args:
            user_message: User's question or input
            bot_response: Bot's response to evaluate
            context: Optional context about the conversation
            
        Returns:
            Dict with evaluation results:
            {
                "overall_score": 0-10,
                "priority": "critical|high|medium|low",
                "needs_review": bool,
                "issues": ["list of issues"],
                "strengths": ["list of strengths"],
                "categories": {
                    "accuracy": 0-10,
                    "tone": 0-10,
                    "context": 0-10,
                    "completeness": 0-10,
                    "clarity": 0-10
                },
                "evaluation_summary": "Brief summary",
                "timestamp": "ISO timestamp"
            }
        """
        try:
            # Build evaluation prompt
            prompt = self._build_evaluation_prompt(user_message, bot_response, context)
            
            # Get client with fresh auth token
            client = await self._get_client()
            
            # Call GPT-4o-mini
            response = await client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt()
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Lower temperature for consistent evaluation
                response_format={"type": "json_object"}
            )
            
            # Parse response
            evaluation = json.loads(response.choices[0].message.content)
            
            # Calculate priority and needs_review flag
            overall_score = evaluation.get("overall_score", 5)
            priority = self._calculate_priority(overall_score, evaluation.get("issues", []))
            needs_review = priority in [self.PRIORITY_CRITICAL, self.PRIORITY_HIGH]
            
            # Add metadata
            evaluation["priority"] = priority
            evaluation["needs_review"] = needs_review
            evaluation["timestamp"] = datetime.now(timezone.utc).isoformat()
            evaluation["evaluator"] = "GPT-4o-mini"
            
            logger.info(
                f"Evaluated response: score={overall_score}/10, "
                f"priority={priority}, needs_review={needs_review}"
            )
            
            return evaluation
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}", exc_info=True)
            return {
                "overall_score": 5,
                "priority": self.PRIORITY_MEDIUM,
                "needs_review": False,
                "issues": ["AI response parsing failed"],
                "strengths": [],
                "categories": {k: 5 for k in self.CATEGORIES.keys()},
                "evaluation_summary": "Unable to parse AI evaluation response",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "evaluator": "GPT-4o-mini",
                "error": f"JSON parse error: {str(e)}"
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error evaluating response: {error_msg}", exc_info=True)
            
            # More detailed error messages
            if "404" in error_msg or "NotFound" in error_msg:
                error_detail = f"Deployment '{self.deployment_name}' not found in Azure OpenAI"
            elif "PermissionDenied" in error_msg:
                error_detail = "Permission denied - Managed Identity lacks Azure OpenAI access (needs Cognitive Services OpenAI User role)"
            elif "401" in error_msg or "Unauthorized" in error_msg:
                if self.use_managed_identity:
                    error_detail = "Authentication failed with Managed Identity - check Azure RBAC permissions"
                else:
                    error_detail = "Authentication failed - check API key"
            elif "429" in error_msg or "quota" in error_msg.lower():
                error_detail = "Rate limit or quota exceeded"
            elif "timeout" in error_msg.lower():
                error_detail = "Request timeout - Azure OpenAI did not respond"
            else:
                error_detail = f"API error: {error_msg}"
            
            # Return safe default on error
            return {
                "overall_score": 5,
                "priority": self.PRIORITY_MEDIUM,
                "needs_review": False,
                "issues": [error_detail],
                "strengths": [],
                "categories": {k: 5 for k in self.CATEGORIES.keys()},
                "evaluation_summary": "Unable to evaluate response",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "evaluator": "GPT-4o-mini",
                "error": error_detail
            }
    
    async def evaluate_conversation(
        self,
        conversation: Dict
    ) -> Dict:
        """
        Evaluate all turns in a conversation.
        
        Args:
            conversation: Full conversation data with turns
            
        Returns:
            Dict with per-turn evaluations and overall assessment
        """
        try:
            turns = conversation.get("turns", [])
            evaluations = []
            
            # Evaluate each turn
            for turn in turns:
                user_message = turn.get("user_message", "")
                bot_response = turn.get("bot_response", "")
                
                # Build context from previous turns
                context = self._build_conversation_context(turns, turn.get("turn_number", 0))
                
                eval_result = await self.evaluate_response(
                    user_message=user_message,
                    bot_response=bot_response,
                    context=context
                )
                
                evaluations.append({
                    "turn_number": turn.get("turn_number"),
                    "evaluation": eval_result
                })
            
            # Calculate overall conversation score
            avg_score = sum(e["evaluation"]["overall_score"] for e in evaluations) / len(evaluations) if evaluations else 5
            
            # Find critical turns
            critical_turns = [
                e["turn_number"] for e in evaluations 
                if e["evaluation"]["priority"] in [self.PRIORITY_CRITICAL, self.PRIORITY_HIGH]
            ]
            
            return {
                "conversation_id": conversation.get("id"),
                "overall_score": round(avg_score, 1),
                "needs_review": len(critical_turns) > 0,
                "critical_turns": critical_turns,
                "turn_evaluations": evaluations,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error evaluating conversation: {e}", exc_info=True)
            return {
                "conversation_id": conversation.get("id"),
                "overall_score": 5,
                "needs_review": False,
                "critical_turns": [],
                "turn_evaluations": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            }
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for evaluation."""
        return """Sei un esperto valutatore AI di risposte per un sistema di assistente vocale per call center.
Il tuo compito è valutare le risposte del bot per qualità, accuratezza e appropriatezza.

Valuta le risposte secondo queste dimensioni (scala 0-10):
- Accuratezza: Le informazioni sono corrette e fattuali?
- Tono: Il tono è professionale, empatico e appropriato?
- Contesto: La risposta mostra comprensione del contesto e del flusso della conversazione?
- Completezza: La risposta affronta completamente la domanda dell'utente?
- Chiarezza: La risposta è chiara, concisa e facile da capire?

Identifica:
- Problemi: Errori o aree di preoccupazione
- Punti di forza: Cosa fa bene la risposta

Restituisci la tua valutazione come JSON in questo formato esatto:
{
  "overall_score": <numero 0-10>,
  "categories": {
    "accuracy": <numero 0-10>,
    "tone": <numero 0-10>,
    "context": <numero 0-10>,
    "completeness": <numero 0-10>,
    "clarity": <numero 0-10>
  },
  "issues": ["problema1", "problema2"],
  "strengths": ["punto_forza1", "punto_forza2"],
  "evaluation_summary": "Breve riepilogo in 1-2 frasi"
}

Sii critico ma giusto. Segnala risposte con:
- Errori fattuali o disinformazione
- Tono inappropriato o mancanza di empatia
- Contesto mancante o informazioni irrilevanti
- Risposte incomplete
- Linguaggio poco chiaro o confuso

IMPORTANTE: Scrivi TUTTO in italiano, inclusi problemi, punti di forza e riepilogo della valutazione."""

    def _build_evaluation_prompt(
        self,
        user_message: str,
        bot_response: str,
        context: Optional[str] = None
    ) -> str:
        """Build evaluation prompt."""
        prompt = f"""Valuta questa risposta del bot:

MESSAGGIO UTENTE:
{user_message}

RISPOSTA BOT:
{bot_response}"""
        
        if context:
            prompt += f"""

CONTESTO CONVERSAZIONE:
{context}"""
        
        prompt += "\n\nFornisci la tua valutazione in formato JSON. Ricorda: TUTTO deve essere in italiano."
        
        return prompt
    
    def _build_conversation_context(self, turns: List[Dict], current_turn: int) -> str:
        """Build context from previous turns."""
        previous_turns = [t for t in turns if t.get("turn_number", 0) < current_turn]
        
        if not previous_turns:
            return "This is the first turn in the conversation."
        
        context_parts = []
        for turn in previous_turns[-3:]:  # Last 3 turns for context
            context_parts.append(
                f"Turn {turn.get('turn_number')}: "
                f"User: {turn.get('user_message', '')} | "
                f"Bot: {turn.get('bot_response', '')}"
            )
        
        return "\n".join(context_parts)
    
    def _calculate_priority(self, overall_score: float, issues: List[str]) -> str:
        """Calculate priority level based on score and issues."""
        # Critical: Very low score or critical issues
        if overall_score < 4 or any(
            keyword in str(issues).lower() 
            for keyword in ["error", "wrong", "incorrect", "inappropriate", "offensive"]
        ):
            return self.PRIORITY_CRITICAL
        
        # High: Low score or multiple issues
        if overall_score < 6 or len(issues) >= 3:
            return self.PRIORITY_HIGH
        
        # Medium: Moderate score or some issues
        if overall_score < 8 or len(issues) >= 1:
            return self.PRIORITY_MEDIUM
        
        # Low: Good score, no issues
        return self.PRIORITY_LOW


# Singleton instance
_evaluator_instance = None


def get_ai_evaluator(
    azure_openai_endpoint: str,
    deployment_name: str = "gpt-4o-mini",
    client_id: Optional[str] = None,
    azure_openai_key: Optional[str] = None
) -> AIEvaluator:
    """Get or create AI evaluator singleton with Managed Identity support."""
    global _evaluator_instance
    
    if _evaluator_instance is None:
        _evaluator_instance = AIEvaluator(
            azure_openai_endpoint=azure_openai_endpoint,
            deployment_name=deployment_name,
            client_id=client_id,
            azure_openai_key=azure_openai_key
        )
    
    return _evaluator_instance
