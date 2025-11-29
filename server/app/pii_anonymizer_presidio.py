"""
PII Anonymization Module using Microsoft Presidio.

This module uses Microsoft Presidio for detecting and anonymizing 
Personally Identifiable Information (PII) in conversations, 
ensuring GDPR compliance with enterprise-grade accuracy.

Presidio advantages:
- ML-based NER (Named Entity Recognition)
- Better accuracy than regex-only approaches
- Multilingual support (Italian included)
- Microsoft-maintained and enterprise-ready
- Extensible with custom recognizers
"""

import hashlib
import logging
from typing import Dict, List, Optional
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

logger = logging.getLogger(__name__)


class PIIAnonymizerPresidio:
    """
    Detects and anonymizes PII using Microsoft Presidio.
    
    Features:
    - ML-based entity detection with spaCy NER models
    - Regex-based detection for structured data
    - Italian language support
    - Reversible anonymization with session-based mapping
    - Token replacement ([PERSON_1], [PHONE_1], etc.)
    """
    
    # Mapping from Presidio entity types to our token names
    ENTITY_TYPE_MAP = {
        "PERSON": "PERSON",
        "PHONE_NUMBER": "PHONE",
        "EMAIL_ADDRESS": "EMAIL",
        "IBAN_CODE": "IBAN",
        "CREDIT_CARD": "CARD",
        "CRYPTO": "CRYPTO",
        "LOCATION": "ADDRESS",
        "DATE_TIME": "DATE",
        "NRP": "FISCAL_CODE",  # Italian fiscal code (Numero Registro Persone)
        "IT_FISCAL_CODE": "FISCAL_CODE",
        "IT_DRIVER_LICENSE": "LICENSE",
        "IT_VAT": "VAT",
        "IT_PASSPORT": "PASSPORT",
        "MEDICAL_LICENSE": "MEDICAL",
        "URL": "URL",
        "IP_ADDRESS": "IP"
    }
    
    def __init__(self, reversible: bool = True, language: str = "it"):
        """
        Initialize the Presidio-based PII anonymizer.
        
        Args:
            reversible: If True, maintains mapping for potential de-anonymization
            language: Language code (default: "it" for Italian)
        """
        self.reversible = reversible
        self.language = language
        self.session_maps: Dict[str, Dict[str, str]] = {}
        self.counters: Dict[str, Dict[str, int]] = {}
        
        # Initialize Presidio Analyzer with Italian NLP model
        try:
            # Configure NLP engine for Italian
            nlp_configuration = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "it", "model_name": "it_core_news_lg"}],
            }
            
            provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
            nlp_engine = provider.create_engine()
            
            # Create custom recognizers for Italian context
            italian_phone_patterns = [
                Pattern(name="italian_mobile", 
                       regex=r"\b3\d{8,9}\b", 
                       score=0.7),
                Pattern(name="italian_mobile_formatted", 
                       regex=r"\b3\d{2}[\s\-]?\d{3}[\s\-]?\d{3,4}\b", 
                       score=0.8),
                Pattern(name="italian_landline", 
                       regex=r"\b0\d{1,3}[\s\-]?\d{6,8}\b", 
                       score=0.7),
            ]
            
            italian_phone_recognizer = PatternRecognizer(
                supported_entity="PHONE_NUMBER",
                patterns=italian_phone_patterns,
                supported_language="it",
                name="Italian Phone Recognizer"
            )
            
            # Create analyzer with Italian support and custom recognizers
            self.analyzer = AnalyzerEngine(
                nlp_engine=nlp_engine,
                supported_languages=["it"]
            )
            
            # Add custom Italian phone recognizer
            self.analyzer.registry.add_recognizer(italian_phone_recognizer)
            
            # Create anonymizer
            self.anonymizer = AnonymizerEngine()
            
            logger.info("Presidio PII Anonymizer initialized successfully with Italian support")
            
        except Exception as e:
            logger.error(f"Error initializing Presidio: {e}")
            logger.warning("Falling back to basic functionality")
            raise
    
    def anonymize_text(self, text: str, session_id: str, score_threshold: float = 0.6) -> Dict:
        """
        Anonymize PII in text using Presidio.
        
        Args:
            text: Text to anonymize
            session_id: Session identifier for maintaining consistent replacements
            score_threshold: Minimum confidence score for entity detection (0.0-1.0)
            
        Returns:
            Dictionary with:
            - anonymized_text: Text with PII replaced by tokens
            - pii_found: List of PII types detected
            - anonymization_map: Mapping of tokens to original values (if reversible)
            - entities: List of detected entities with scores
        """
        if not text:
            return {
                "anonymized_text": text,
                "pii_found": [],
                "anonymization_map": {},
                "entities": []
            }
        
        # Initialize session counters if not exists
        if session_id not in self.counters:
            self.counters[session_id] = {}
        if session_id not in self.session_maps:
            self.session_maps[session_id] = {}
        
        try:
            # Analyze text for PII entities
            # Enable all entity types, including medical
            results = self.analyzer.analyze(
                text=text,
                language=self.language,
                score_threshold=score_threshold,
                return_decision_process=False
            )
            
            # Sort results by start position (reverse order for replacement)
            results = sorted(results, key=lambda x: x.start, reverse=True)
            
            anonymized_text = text
            pii_found = []
            entities_info = []
            
            # Replace each detected entity with a token
            for result in results:
                entity_type = result.entity_type
                original_text = text[result.start:result.end]
                score = result.score
                
                # Map Presidio entity type to our token type
                token_type = self.ENTITY_TYPE_MAP.get(entity_type, entity_type)
                
                # Special handling for fiscal codes (hash them)
                if token_type == "FISCAL_CODE":
                    hashed = hashlib.sha256(original_text.encode()).hexdigest()[:8]
                    token = f"[FISCAL_ID_{hashed}]"
                    if self.reversible:
                        self.session_maps[session_id][token] = original_text
                else:
                    # Get or create token for this value
                    token = self._get_or_create_token(original_text, token_type, session_id)
                
                # Replace in text
                anonymized_text = (
                    anonymized_text[:result.start] + 
                    token + 
                    anonymized_text[result.end:]
                )
                
                # Track what we found
                pii_found.append(token_type.lower())
                entities_info.append({
                    "type": entity_type,
                    "token_type": token_type,
                    "score": score,
                    "original": original_text if not token_type == "FISCAL_CODE" else "[REDACTED]",
                    "token": token
                })
            
            result_dict = {
                "anonymized_text": anonymized_text,
                "pii_found": list(set([p.lower() for p in pii_found])),  # Remove duplicates
                "entities": entities_info
            }
            
            if self.reversible:
                result_dict["anonymization_map"] = self.session_maps[session_id].copy()
            
            return result_dict
            
        except Exception as e:
            logger.error(f"Error during PII anonymization: {e}")
            # Return original text on error
            return {
                "anonymized_text": text,
                "pii_found": [],
                "anonymization_map": {},
                "entities": [],
                "error": str(e)
            }
    
    def _get_or_create_token(self, value: str, pii_type: str, session_id: str) -> str:
        """
        Get existing token or create new one for a PII value.
        
        Args:
            value: Original PII value
            pii_type: Type of PII (PHONE, EMAIL, PERSON, etc.)
            session_id: Session identifier
            
        Returns:
            Token string like [PHONE_1], [PERSON_2], etc.
        """
        # Check if we already have a token for this value in this session
        session_map = self.session_maps[session_id]
        for token, original in session_map.items():
            if original == value and pii_type in token:
                return token
        
        # Create new token
        if pii_type not in self.counters[session_id]:
            self.counters[session_id][pii_type] = 0
        
        self.counters[session_id][pii_type] += 1
        counter = self.counters[session_id][pii_type]
        token = f"[{pii_type}_{counter}]"
        
        if self.reversible:
            session_map[token] = value
        
        return token
    
    def get_anonymization_map(self, session_id: str) -> Dict[str, str]:
        """Get the anonymization map for a session."""
        return self.session_maps.get(session_id, {}).copy()
    
    def clear_session(self, session_id: str):
        """Clear session data from memory."""
        if session_id in self.session_maps:
            del self.session_maps[session_id]
        if session_id in self.counters:
            del self.counters[session_id]
    
    @staticmethod
    def hash_phone_number(phone: str) -> str:
        """
        Hash phone number for storage (keep last 4 digits visible).
        
        Args:
            phone: Phone number string
            
        Returns:
            Hashed string like "sha256_***1234"
        """
        import re
        # Remove all non-digit characters
        digits = re.sub(r'\D', '', phone)
        
        if len(digits) >= 4:
            last_four = digits[-4:]
            hashed = hashlib.sha256(phone.encode()).hexdigest()[:8]
            return f"sha256_{hashed}_***{last_four}"
        else:
            hashed = hashlib.sha256(phone.encode()).hexdigest()[:16]
            return f"sha256_{hashed}"
    
    @staticmethod
    def hash_session_id(session_id: str) -> str:
        """
        Hash session ID for storage.
        
        Args:
            session_id: Original session ID
            
        Returns:
            SHA256 hash
        """
        return hashlib.sha256(session_id.encode()).hexdigest()
