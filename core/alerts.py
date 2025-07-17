"""
Alerts via n8n Webhook integration.

Requires environment variable:
  - N8N_WEBHOOK_URL: the target webhook URL for n8n.
"""
import os

import aiohttp

# Configuration
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
if not N8N_WEBHOOK_URL:
    raise RuntimeError("N8N_WEBHOOK_URL env var is required for core.alerts")


async def notify(event_type: str, payload: dict) -> bool:
    """
    Send a notification to the configured n8n webhook.

    Args:
        event_type: a string identifying the event type.
        payload: a dict of event-specific data.

    Returns:
        True if the HTTP response status is 2xx, False otherwise.
    """
    data = {"event_type": event_type, "payload": payload}
    headers = {"Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(N8N_WEBHOOK_URL, json=data, headers=headers) as resp:
            return 200 <= resp.status < 300
