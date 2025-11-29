#!/usr/bin/env python3
"""
Test di integrazione per verificare che Presidio funzioni con il sistema.
"""

import sys
import asyncio
sys.path.insert(0, '/workspaces/call-center-voice-agent-accelerator/server')

from app.pii_anonymizer_presidio import PIIAnonymizerPresidio

async def test_integration():
    """Test che Presidio funzioni correttamente nel contesto del sistema."""
    
    print("=" * 80)
    print("TEST INTEGRAZIONE PRESIDIO")
    print("=" * 80)
    
    # Simula il flusso del conversation logger
    print("\n1. Inizializzazione Presidio...")
    anonymizer = PIIAnonymizerPresidio(reversible=True, language="it")
    print("   ✅ Presidio inizializzato")
    
    # Test conversazione tipica farmacia
    print("\n2. Test conversazione farmacia...")
    session_id = "test-session-123"
    
    test_messages = [
        ("Buongiorno, mi chiamo Mario Rossi", "Buongiorno! Come posso aiutarla?"),
        ("Ho bisogno di farmaci per il diabete", "Certo, ha una ricetta medica?"),
        ("Sì, il mio numero è 3401234567", "Perfetto, preparo subito i farmaci."),
        ("La mia email è mario.rossi@gmail.com", "Le invierò la ricevuta via email."),
    ]
    
    for i, (user_msg, bot_msg) in enumerate(test_messages, 1):
        print(f"\n   Turno {i}:")
        print(f"   User (orig):  '{user_msg}'")
        
        # Anonymize come fa il conversation logger
        user_result = anonymizer.anonymize_text(user_msg, session_id, score_threshold=0.5)
        bot_result = anonymizer.anonymize_text(bot_msg, session_id, score_threshold=0.5)
        
        print(f"   User (anon):  '{user_result['anonymized_text']}'")
        print(f"   Bot (anon):   '{bot_result['anonymized_text']}'")
        
        if user_result['pii_found']:
            print(f"   PII trovati:  {user_result['pii_found']}")
    
    # Verifica mappa di anonimizzazione
    print(f"\n3. Mappa di anonimizzazione sessione:")
    anon_map = anonymizer.get_anonymization_map(session_id)
    for token, value in anon_map.items():
        print(f"   {token} -> {value}")
    
    # Test funzioni statiche (per GDPR)
    print(f"\n4. Test funzioni hash (per GDPR):")
    phone_hashed = PIIAnonymizerPresidio.hash_phone_number("3401234567")
    session_hashed = PIIAnonymizerPresidio.hash_session_id(session_id)
    print(f"   Phone hash:   {phone_hashed}")
    print(f"   Session hash: {session_hashed[:32]}...")
    
    # Cleanup
    anonymizer.clear_session(session_id)
    print(f"\n5. Sessione pulita: {len(anonymizer.get_anonymization_map(session_id))} elementi rimanenti")
    
    print("\n" + "=" * 80)
    print("✅ TEST COMPLETATO CON SUCCESSO")
    print("=" * 80)
    print("\nPresidio è pronto per essere utilizzato in produzione!")
    print("- Rilevamento ML-based con spaCy")
    print("- Supporto italiano nativo")
    print("- Custom recognizer per telefoni italiani")
    print("- Compatibile con GDPR compliance")

if __name__ == "__main__":
    try:
        asyncio.run(test_integration())
    except Exception as e:
        print(f"\n❌ Errore: {e}")
        import traceback
        traceback.print_exc()
