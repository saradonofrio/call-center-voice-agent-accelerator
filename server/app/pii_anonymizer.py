"""
PII Anonymization Module for GDPR Compliance.

This module detects and anonymizes Personally Identifiable Information (PII)
in conversations before storage, ensuring GDPR compliance.
"""

import hashlib
import re
import logging
from typing import Dict, List, Tuple
from app.pii_patterns import (
    COMPILED_PHONE_PATTERNS,
    COMPILED_FISCAL_CODE,
    COMPILED_EMAIL,
    COMPILED_CREDIT_CARD,
    COMPILED_ADDRESS_PATTERNS,
    COMPILED_NAME_INDICATORS,
    MEDICAL_TERMS,
    ITALIAN_FIRST_NAMES,
    ITALIAN_LAST_NAMES,
)

logger = logging.getLogger(__name__)


class PIIAnonymizer:
    """
    Detects and anonymizes PII in text for GDPR compliance.
    
    Features:
    - Regex-based detection for structured data (phone, email, fiscal codes)
    - Pattern-based detection for names and addresses
    - Medical term detection
    - Reversible anonymization with session-based mapping
    - Token replacement ([PHONE_1], [PERSON_1], etc.)
    """
    
    def __init__(self, reversible: bool = True):
        """
        Initialize the PII anonymizer.
        
        Args:
            reversible: If True, maintains mapping for potential de-anonymization
        """
        self.reversible = reversible
        self.session_maps: Dict[str, Dict[str, str]] = {}
        self.counters: Dict[str, Dict[str, int]] = {}
    
    def anonymize_text(self, text: str, session_id: str) -> Dict:
        """
        Anonymize PII in text.
        
        Args:
            text: Text to anonymize
            session_id: Session identifier for maintaining consistent replacements
            
        Returns:
            Dictionary with:
            - anonymized_text: Text with PII replaced by tokens
            - pii_found: List of PII types detected
            - anonymization_map: Mapping of tokens to original values (if reversible)
        """
        if not text:
            return {
                "anonymized_text": text,
                "pii_found": [],
                "anonymization_map": {}
            }
        
        # Initialize session counters if not exists
        if session_id not in self.counters:
            self.counters[session_id] = {}
        if session_id not in self.session_maps:
            self.session_maps[session_id] = {}
        
        anonymized = text
        pii_found = []
        
        # Apply anonymization in order (from most specific to least specific)
        
        # 1. Credit cards (before phone numbers to avoid false matches)
        anonymized, found = self._anonymize_credit_cards(anonymized, session_id)
        pii_found.extend(found)
        
        # 2. Fiscal codes (Italian tax codes)
        anonymized, found = self._anonymize_fiscal_codes(anonymized, session_id)
        pii_found.extend(found)
        
        # 3. Email addresses
        anonymized, found = self._anonymize_emails(anonymized, session_id)
        pii_found.extend(found)
        
        # 4. Phone numbers
        anonymized, found = self._anonymize_phone_numbers(anonymized, session_id)
        pii_found.extend(found)
        
        # 5. Addresses
        anonymized, found = self._anonymize_addresses(anonymized, session_id)
        pii_found.extend(found)
        
        # 6. Names (must be after addresses to avoid false positives)
        anonymized, found = self._anonymize_names(anonymized, session_id)
        pii_found.extend(found)
        
        # 7. Medical terms (optional - may be too broad)
        anonymized, found = self._anonymize_medical_terms(anonymized, session_id)
        pii_found.extend(found)
        
        result = {
            "anonymized_text": anonymized,
            "pii_found": list(set(pii_found)),  # Remove duplicates
        }
        
        if self.reversible:
            result["anonymization_map"] = self.session_maps[session_id].copy()
        
        return result
    
    def _anonymize_phone_numbers(self, text: str, session_id: str) -> Tuple[str, List[str]]:
        """Anonymize phone numbers."""
        pii_found = []
        for pattern in COMPILED_PHONE_PATTERNS:
            matches = pattern.finditer(text)
            for match in matches:
                phone = match.group(0)
                token = self._get_or_create_token(phone, "PHONE", session_id)
                text = text.replace(phone, token)
                pii_found.append("phone")
        return text, pii_found
    
    def _anonymize_fiscal_codes(self, text: str, session_id: str) -> Tuple[str, List[str]]:
        """Anonymize Italian fiscal codes."""
        pii_found = []
        matches = COMPILED_FISCAL_CODE.finditer(text)
        for match in matches:
            fiscal_code = match.group(0)
            # Hash fiscal codes (irreversible for security)
            hashed = hashlib.sha256(fiscal_code.encode()).hexdigest()[:8]
            token = f"[FISCAL_ID_{hashed}]"
            
            if self.reversible:
                self.session_maps[session_id][token] = fiscal_code
            
            text = text.replace(fiscal_code, token)
            pii_found.append("fiscal_code")
        return text, pii_found
    
    def _anonymize_emails(self, text: str, session_id: str) -> Tuple[str, List[str]]:
        """Anonymize email addresses."""
        pii_found = []
        matches = COMPILED_EMAIL.finditer(text)
        for match in matches:
            email = match.group(0)
            token = self._get_or_create_token(email, "EMAIL", session_id)
            text = text.replace(email, token)
            pii_found.append("email")
        return text, pii_found
    
    def _anonymize_credit_cards(self, text: str, session_id: str) -> Tuple[str, List[str]]:
        """Anonymize credit card numbers."""
        pii_found = []
        matches = COMPILED_CREDIT_CARD.finditer(text)
        for match in matches:
            card = match.group(0)
            # Additional validation: check if it looks like a real card (Luhn algorithm)
            digits_only = re.sub(r'[\s\-]', '', card)
            if len(digits_only) == 16 and self._is_valid_card(digits_only):
                token = "[CARD]"
                if self.reversible:
                    # Keep last 4 digits
                    last_four = digits_only[-4:]
                    token = f"[CARD_***{last_four}]"
                    self.session_maps[session_id][token] = card
                text = text.replace(card, token)
                pii_found.append("credit_card")
        return text, pii_found
    
    def _anonymize_addresses(self, text: str, session_id: str) -> Tuple[str, List[str]]:
        """Anonymize addresses."""
        pii_found = []
        for pattern in COMPILED_ADDRESS_PATTERNS:
            matches = pattern.finditer(text)
            for match in matches:
                address = match.group(0)
                token = self._get_or_create_token(address, "ADDRESS", session_id)
                text = text.replace(address, token)
                pii_found.append("address")
        return text, pii_found
    
    def _anonymize_names(self, text: str, session_id: str) -> Tuple[str, List[str]]:
        """Anonymize person names."""
        pii_found = []
        
        # 1. Pattern-based detection (e.g., "sono Mario Rossi")
        for pattern in COMPILED_NAME_INDICATORS:
            matches = pattern.finditer(text)
            for match in matches:
                if len(match.groups()) > 0:
                    name = match.group(1)
                    token = self._get_or_create_token(name, "PERSON", session_id)
                    text = text.replace(name, token)
                    pii_found.append("name")
        
        # 2. Common Italian name detection
        words = text.split()
        for i, word in enumerate(words):
            word_lower = word.lower().strip('.,!?;:')
            
            # Check if it's a common Italian first name
            if word_lower in ITALIAN_FIRST_NAMES and word[0].isupper():
                # Check if followed by a last name
                if i + 1 < len(words):
                    next_word = words[i + 1].strip('.,!?;:')
                    next_word_lower = next_word.lower()
                    if next_word_lower in ITALIAN_LAST_NAMES and next_word[0].isupper():
                        full_name = f"{word} {next_word}"
                        token = self._get_or_create_token(full_name, "PERSON", session_id)
                        text = text.replace(full_name, token)
                        pii_found.append("name")
        
        return text, pii_found
    
    def _anonymize_medical_terms(self, text: str, session_id: str) -> Tuple[str, List[str]]:
        """Anonymize medical terms (optional - sensitive health data)."""
        pii_found = []
        text_lower = text.lower()
        
        for term in MEDICAL_TERMS:
            if term in text_lower:
                # Find exact position to preserve case
                pattern = re.compile(re.escape(term), re.IGNORECASE)
                matches = pattern.finditer(text)
                for match in matches:
                    original = match.group(0)
                    token = "[MEDICAL_CONDITION]"
                    if self.reversible:
                        self.session_maps[session_id][token] = original
                    text = text.replace(original, token, 1)
                    pii_found.append("medical")
        
        return text, pii_found
    
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
    
    def _is_valid_card(self, number: str) -> bool:
        """
        Validate credit card using Luhn algorithm.
        
        Args:
            number: Card number as string of digits
            
        Returns:
            True if valid card number
        """
        def luhn_checksum(card_number):
            def digits_of(n):
                return [int(d) for d in str(n)]
            digits = digits_of(card_number)
            odd_digits = digits[-1::-2]
            even_digits = digits[-2::-2]
            checksum = sum(odd_digits)
            for d in even_digits:
                checksum += sum(digits_of(d * 2))
            return checksum % 10
        
        try:
            return luhn_checksum(number) == 0
        except:
            return False
    
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
