#!/usr/bin/env python3
"""Test multilingual PII detection with Presidio"""

import sys
sys.path.insert(0, '/workspaces/call-center-voice-agent-accelerator/server')

from app.pii_anonymizer_presidio import PIIAnonymizerPresidio

# Initialize with Italian + English
anonymizer = PIIAnonymizerPresidio(reversible=True, languages=["it", "en"])

# Test cases
test_cases = [
    ("Ciao, sono Mario Rossi e il mio telefono è 3331234567", "it"),  # Italian
    ("Hello, I'm John Smith and my phone is +1-555-123-4567", "en"),  # English  
    ("Il mio indirizzo email è mario.rossi@example.com", "it"),  # Italian with email
    ("My email address is john.smith@example.com", "en"),  # English with email
]

print("=" * 70)
print("TEST MULTILINGUAL PII DETECTION")
print("=" * 70)

for text, expected_lang in test_cases:
    print(f"\n📝 Input ({expected_lang}): {text}")
    result = anonymizer.anonymize_text(text, "test-session-001", score_threshold=0.6)
    print(f"🔒 Anonymized: {result['anonymized_text']}")
    print(f"🏴 Detected language: {result.get('language', 'N/A')}")
    print(f"🔍 PII found: {', '.join(result['pii_found']) if result['pii_found'] else 'None'}")
    print(f"📊 Entities: {len(result['entities'])} detected")
    
print("\n" + "=" * 70)
print("✅ Multilingual test completed!")
print("=" * 70)
