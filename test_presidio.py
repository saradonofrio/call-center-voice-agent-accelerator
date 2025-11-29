#!/usr/bin/env python3
"""Test PII anonymization with Microsoft Presidio."""

import sys
sys.path.insert(0, '/workspaces/call-center-voice-agent-accelerator/server')

from app.pii_anonymizer_presidio import PIIAnonymizerPresidio

def test_presidio_detection():
    """Test Presidio PII detection."""
    
    print("Initializing Presidio...")
    anonymizer = PIIAnonymizerPresidio(reversible=True, language="it")
    print("✅ Presidio initialized\n")
    
    test_cases = [
        # Phone numbers
        ("Il mio numero è 3401234567", "phone"),
        ("Chiamami al +39 340 123 4567", "phone"),
        
        # Names
        ("Mi chiamo Mario Rossi", "person"),
        ("Sono Francesco D'Angelo", "person"),
        ("Dott. Bianchi mi ha prescritto", "person"),
        
        # Addresses/Locations
        ("Abito a Milano", "address"),
        ("Vivo in Via Roma 123", "address"),
        
        # Email
        ("La mia email è mario.rossi@gmail.com", "email"),
        
        # Complex test
        ("Mi chiamo Mario Rossi, telefono 340 1234567, email mario@test.it", "multiple"),
    ]
    
    print("=" * 80)
    print("TEST PRESIDIO PII ANONYMIZATION")
    print("=" * 80)
    
    for i, (text, expected_pii) in enumerate(test_cases, 1):
        result = anonymizer.anonymize_text(text, f"test-session-{i}", score_threshold=0.3)
        
        print(f"\n{i}. Test: {expected_pii.upper()}")
        print(f"   Input:      '{text}'")
        print(f"   Output:     '{result['anonymized_text']}'")
        print(f"   PII Found:  {result['pii_found']}")
        
        if result.get('entities'):
            print(f"   Entities detected:")
            for entity in result['entities']:
                print(f"      - {entity['type']} (score: {entity['score']:.2f}): {entity['token']}")
        
        # Check if expected PII was found
        if expected_pii == "multiple" or any(expected_pii in pii for pii in result['pii_found']):
            print(f"   Status:     ✅ PASS")
        else:
            print(f"   Status:     ⚠️  Expected {expected_pii}, found: {result['pii_found']}")
    
    # Complex test
    print("\n" + "=" * 80)
    print("COMPLEX TEST - Full conversation")
    print("=" * 80)
    
    complex_text = """
    Buongiorno, mi chiamo Mario Rossi e abito a Milano in Via Garibaldi 15.
    Il mio numero di telefono è 340 123 4567 e la mia email è mario.rossi@gmail.com.
    Ho bisogno di farmaci per il diabete.
    """
    
    result = anonymizer.anonymize_text(complex_text.strip(), "test-complex", score_threshold=0.3)
    
    print(f"\nInput:\n{complex_text}")
    print(f"\nOutput:\n{result['anonymized_text']}")
    print(f"\nPII Found: {result['pii_found']}")
    print(f"\nEntities detected: {len(result.get('entities', []))}")
    for entity in result.get('entities', []):
        print(f"  - {entity['type']} (confidence: {entity['score']:.2%}): {entity['token']}")
    
    print(f"\nAnonymization Map:")
    for token, value in result.get('anonymization_map', {}).items():
        print(f"  {token} -> {value}")

if __name__ == "__main__":
    try:
        test_presidio_detection()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
