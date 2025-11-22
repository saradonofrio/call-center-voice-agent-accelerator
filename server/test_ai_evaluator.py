"""
Test script to verify AI Evaluator configuration and initialization.
Run this to check if the AI evaluator can connect to Azure OpenAI.
"""

import os
import asyncio
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_ai_evaluator():
    """Test AI evaluator initialization and basic functionality."""
    
    print("=" * 60)
    print("AI Evaluator Configuration Test")
    print("=" * 60)
    
    # Check environment variables
    print("\n1. Checking Environment Variables:")
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("AZURE_VOICE_LIVE_ENDPOINT")
    key = os.environ.get("AZURE_OPENAI_KEY") or os.environ.get("VOICE_LIVE_API_KEY")
    model = os.environ.get("VOICE_LIVE_MODEL", "gpt-4o-mini")
    
    print(f"   Endpoint: {'✓ SET' if endpoint else '✗ NOT SET'}")
    if endpoint:
        print(f"            {endpoint}")
    print(f"   API Key:  {'✓ SET' if key else '✗ NOT SET'}")
    print(f"   Model:    {model}")
    
    if not endpoint or not key:
        print("\n✗ ERROR: Azure OpenAI endpoint or key not configured!")
        print("\nMake sure these environment variables are set:")
        print("  - AZURE_OPENAI_ENDPOINT (or AZURE_VOICE_LIVE_ENDPOINT)")
        print("  - AZURE_OPENAI_KEY (or VOICE_LIVE_API_KEY)")
        return False
    
    # Try to initialize evaluator
    print("\n2. Initializing AI Evaluator:")
    try:
        from app.ai_evaluator import get_ai_evaluator
        
        evaluator = get_ai_evaluator(
            azure_openai_endpoint=endpoint,
            azure_openai_key=key,
            deployment_name=model
        )
        print(f"   ✓ AI Evaluator initialized successfully")
        print(f"   Using deployment: {model}")
        
    except Exception as e:
        print(f"   ✗ Failed to initialize: {e}")
        return False
    
    # Test evaluation
    print("\n3. Testing Evaluation:")
    try:
        test_user_msg = "What are your opening hours?"
        test_bot_response = "We are open Monday to Friday, 9 AM to 5 PM."
        
        print(f"   User: {test_user_msg}")
        print(f"   Bot:  {test_bot_response}")
        print(f"   Evaluating...")
        
        result = await evaluator.evaluate_response(
            user_message=test_user_msg,
            bot_response=test_bot_response
        )
        
        print(f"\n   ✓ Evaluation completed!")
        print(f"   Overall Score: {result['overall_score']}/10")
        print(f"   Priority: {result['priority']}")
        print(f"   Needs Review: {result['needs_review']}")
        if result.get('evaluation_summary'):
            print(f"   Summary: {result['evaluation_summary']}")
        
        # Check if there was an error
        if result.get('error'):
            print(f"\n   ⚠️  Warning: {result['error']}")
            print("\n   Common fixes:")
            print("   - Check that the deployment name matches your Azure OpenAI deployment")
            print("   - Verify the deployment supports chat completions")
            print("   - Check Azure OpenAI quota and rate limits")
            return False
        
        return True
        
    except Exception as e:
        print(f"   ✗ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\nStarting AI Evaluator test...\n")
    
    success = asyncio.run(test_ai_evaluator())
    
    print("\n" + "=" * 60)
    if success:
        print("✓ ALL TESTS PASSED - AI Evaluator is working correctly!")
    else:
        print("✗ TESTS FAILED - Please check the errors above")
    print("=" * 60 + "\n")
    
    sys.exit(0 if success else 1)
