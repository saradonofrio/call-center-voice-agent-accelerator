import os
import logging
import aiohttp
from azure.identity.aio import DefaultAzureCredential

class AOAITextHandler:
    def __init__(self, config):
        self.config = config
        self.endpoint = config.get("AZURE_VOICE_LIVE_ENDPOINT")
        self.model = config.get("VOICE_LIVE_MODEL", "gpt-4o-mini")
        self.logger = logging.getLogger("AOAITextHandler")
        self.credential = DefaultAzureCredential()

    async def get_bot_response(self, user_text):
        url = f"{self.endpoint}/openai/deployments/{self.model}/chat/completions?api-version=2024-02-15-preview"
        # Acquire token for Azure OpenAI
        token = await self.credential.get_token("https://ai.azure.com/.default")
        headers = {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messages": [
                {"role": "user", "content": user_text}
            ],
            "max_tokens": 256
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    try:
                        return data["choices"][0]["message"]["content"]
                    except Exception:
                        self.logger.error(f"Malformed AOAI response: {data}")
                        return "Sorry, I couldn't understand the response."
                else:
                    self.logger.error(f"AOAI request failed: {resp.status} {await resp.text()}")
                    return "Sorry, I couldn't get a response from the bot."
