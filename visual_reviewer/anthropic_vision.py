"""
anthropic_vision.py — calls Anthropic's API directly, bypassing AWS Bedrock
entirely. Same image-encoding logic as bedrock_vision.py (still fully
testable offline), only the final API call function differs.

Setup, dramatically simpler than Bedrock:
1. Sign up / log in at https://console.anthropic.com
2. Create an API key (Settings -> API Keys)
3. pip install anthropic
4. Add ANTHROPIC_API_KEY=sk-ant-... to .env
No IAM users, no model access requests, no region selection.
"""

import base64
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SUPPORTED_FORMATS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def encode_image_for_anthropic(image_path: str) -> dict:
    """Identical logic to bedrock_vision.encode_image_for_bedrock — the
    request format for images is the same shape across both APIs."""
    path = Path(image_path)
    if not path.exists():
        raise ValueError(f"Image file not found: {image_path}")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported image format '{ext}'. Supported: {list(SUPPORTED_FORMATS)}")

    raw = path.read_bytes()
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image is {len(raw) / 1024 / 1024:.1f}MB, exceeds the {MAX_IMAGE_BYTES / 1024 / 1024:.0f}MB limit."
        )

    return {
        "media_type": SUPPORTED_FORMATS[ext],
        "data": base64.b64encode(raw).decode("utf-8"),
    }


def call_anthropic_vision(image_path: str, prompt: str, max_tokens: int = 2000) -> str:
    """The ONE function that actually calls Anthropic's API. Everything
    above this is offline-testable; only this needs a real API key and
    costs money per call — same design as call_bedrock_vision."""
    import anthropic  # imported here so the rest of the module works without the package installed

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    # Check docs.claude.com for the current model string if this one is out of date
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

    image_b64 = encode_image_for_anthropic(image_path)
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_b64["media_type"],
                            "data": image_b64["data"],
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    return response.content[0].text
