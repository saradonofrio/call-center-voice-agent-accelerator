#!/bin/bash

# Rate Limiting Test Script
# Tests the rate limiting implementation on Azure Container App

AZURE_URL="https://ca-farmacia-agent-6fqtj.blacksky-2e64522a.swedencentral.azurecontainerapps.io"

echo "=========================================="
echo "Rate Limiting Test Script"
echo "=========================================="
echo "Testing URL: $AZURE_URL"
echo ""

# Test 1: Test API rate limit (100 per hour)
echo "----------------------------------------"
echo "Test 1: API Rate Limit (100 per hour)"
echo "----------------------------------------"
echo "Making 5 requests to GET /api/documents"
echo "Expected: All should succeed (200 OK)"
echo ""

for i in {1..5}; do
  echo -n "Request $i: "
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$AZURE_URL/api/documents")
  if [ "$HTTP_CODE" == "200" ]; then
    echo "✅ Success (HTTP $HTTP_CODE)"
  elif [ "$HTTP_CODE" == "429" ]; then
    echo "🚫 Rate Limited (HTTP $HTTP_CODE)"
  else
    echo "⚠️  HTTP $HTTP_CODE"
  fi
  sleep 0.5
done

echo ""
echo "----------------------------------------"
echo "Test 2: Upload Rate Limit (10 per hour)"
echo "----------------------------------------"
echo "Creating test file and making 12 upload requests"
echo "Expected: First 10 succeed, 11th and 12th get 429"
echo ""

# Create a small test file
echo "This is a test document for rate limiting." > /tmp/test_document.txt

for i in {1..12}; do
  echo -n "Upload Request $i: "
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$AZURE_URL/api/documents" \
    -F "file=@/tmp/test_document.txt")
  
  if [ "$HTTP_CODE" == "200" ]; then
    echo "✅ Upload Accepted (HTTP $HTTP_CODE)"
  elif [ "$HTTP_CODE" == "429" ]; then
    echo "🚫 RATE LIMITED - Working as expected! (HTTP $HTTP_CODE)"
  elif [ "$HTTP_CODE" == "400" ]; then
    echo "⚠️  Bad Request (HTTP $HTTP_CODE) - might need proper file type"
  elif [ "$HTTP_CODE" == "500" ]; then
    echo "⚠️  Server Error (HTTP $HTTP_CODE) - check app logs"
  else
    echo "⚠️  HTTP $HTTP_CODE"
  fi
  sleep 0.5
done

echo ""
echo "----------------------------------------"
echo "Test 3: Check Current Status"
echo "----------------------------------------"
echo "Testing GET /api/indexer/status (should be under API limit)"
echo ""

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$AZURE_URL/api/indexer/status")
echo -n "Indexer Status: "
if [ "$HTTP_CODE" == "200" ]; then
  echo "✅ Success (HTTP $HTTP_CODE)"
elif [ "$HTTP_CODE" == "429" ]; then
  echo "🚫 Rate Limited (HTTP $HTTP_CODE)"
else
  echo "⚠️  HTTP $HTTP_CODE"
fi

echo ""
echo "=========================================="
echo "Test Complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "- If you saw HTTP 429 on the 11th/12th upload: ✅ Rate limiting is working!"
echo "- If all uploads succeeded: ⚠️  Rate limiting might not be active yet"
echo ""
echo "Next steps:"
echo "1. Check Container App logs in Azure Portal"
echo "2. Verify environment variables are set"
echo "3. Check Application Insights for 429 responses"
echo ""
echo "To check logs:"
echo "  Azure Portal → Your Container App → Logs"
echo "  Look for: 'Rate limiting enabled - ...'"
echo ""

# Cleanup
rm -f /tmp/test_document.txt
