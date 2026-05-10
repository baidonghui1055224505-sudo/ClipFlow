from __future__ import annotations
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent / ".env")

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com",
        )
    return _client


SYSTEM_PROMPT = """You are an intelligent video editing assistant. You will receive a transcript with numbered segments, each having an ID, start time, end time, text, and optionally a speaker label.

The user will describe what clips they want to keep, and this may be part of an ongoing conversation where they refine their requirements.

Rules:
- Select segments that MATCH the user's criteria
- If the user says "remove X" or "delete X" or "don't include X", keep everything EXCEPT X
- If the user says "add X" or "also include X", add those segments to the existing selection
- If the user is refining a previous instruction (not starting fresh), modify your previous selection accordingly
- Be inclusive — when in doubt, keep the segment
- For semantic matching, think about what the segment MEANS, not just keyword match
- Consider speaker labels when available (e.g., "SPEAKER_00" or "主持人")

Return a JSON object:
{
  "ids": [0, 3, 5, 7],
  "reasoning": "一句中文解释你为什么选这些片段，比如：'已选出12段关于工厂产能和设备的发言，总时长约3分20秒'"
}

IMPORTANT: Return ONLY a valid JSON object. No markdown, no other text."""


def select_segments(
    transcript: list[dict],
    instruction: str,
    history: list[dict] | None = None,
) -> tuple[list[int], str]:
    """Send transcript + instruction to DeepSeek, return selected IDs and reasoning."""
    segments_for_ai = [
        {"id": s["id"], "start": s["start"], "end": s["end"],
         "text": s["text"], "speaker": s.get("speaker", "")}
        for s in transcript
    ]
    transcript_str = json.dumps(segments_for_ai, ensure_ascii=False, indent=2)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history:
        for msg in history:
            messages.append(msg.copy())

    messages.append({
        "role": "user",
        "content": f"Transcript:\n{transcript_str}\n\nInstruction: {instruction}",
    })

    client = get_client()
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.3,
        max_tokens=4096,
    )

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[:-3]

    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "ids" in data:
            ids = data["ids"]
            reasoning = data.get("reasoning", "")
            if isinstance(ids, list) and all(isinstance(i, int) for i in ids):
                return ids, reasoning
    except json.JSONDecodeError:
        pass

    raise ValueError(f"AI returned invalid response: {raw[:300]}")
