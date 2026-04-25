import os
from collections.abc import AsyncGenerator
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """You are an expert bike advisor who helps users find the perfect bicycle for their needs.

You guide users through a friendly conversation to understand:
- Primary use case (commuting, mountain biking, road cycling, gravel, casual rides, etc.)
- Budget range
- Fitness level and riding experience
- Terrain and typical routes
- Ride distance and frequency
- Physical considerations (height, fit preferences)

Based on their answers, you recommend specific bike categories and models with clear reasoning.

Guidelines:
- Ask one or two focused questions at a time — don't overwhelm with a long form
- Be conversational and encouraging
- When you have enough information (usually after 2-4 exchanges), give a concrete recommendation
- Include approximate price ranges and where to buy when recommending
- If the user already knows what they want, skip straight to the recommendation"""


class BikeChooserAgent:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    async def stream(self, query: str) -> AsyncGenerator[dict[str, Any], None]:
        try:
            async with self.client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                thinking={"type": "adaptive"},
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": query}],
            ) as stream:
                async for text in stream.text_stream:
                    yield {"content": text, "done": False}
            yield {"content": "", "done": True}
        except Exception as e:
            yield {"content": f"Sorry, an error occurred: {e}", "done": True}
