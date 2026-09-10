"""
pipeline/ollama_client.py
────────────────────────────
Local LLM Integration for CPI Pipeline via Ollama.
Provides structured JSON output for classification and auditing tasks.
"""

from __future__ import annotations

import json
import logging
import os
import requests
from typing import Any

log = logging.getLogger(__name__)

class OllamaClient:
    """Client for interacting with a local Ollama server."""

    def __init__(
        self,
        model: str = os.getenv("OLLAMA_MODEL", "llama3.1"),
        base_url: str = os.getenv("OLLAMA_BASE_URL", "http://172.27.128.1:11434")
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.endpoint = f"{self.base_url}/api/generate"

    def generate(self, prompt: str, system_prompt: str = "", format_json: bool = True) -> Any:
        """
        Generates a response from the local Ollama model.
        """
        try:
            chat_endpoint = f"{self.base_url}/api/chat"
            chat_payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json" if format_json else None,
                "options": {
                    "temperature": 0.1,
                }
            }

            response = requests.post(chat_endpoint, json=chat_payload, timeout=300)
            response.raise_for_status()

            data = response.json()
            content = data.get("message", {}).get("content", "")

            if not format_json:
                return content

            try:
                return json.loads(content)
            except json.JSONDecodeError:
                log.error("Ollama returned invalid JSON: %s", content)
                return None
        except requests.exceptions.RequestException as e:
            log.error("Ollama API request failed: %s", e)
            return None

    def check_health(self) -> bool:
        """Verifies if the Ollama server is reachable."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
