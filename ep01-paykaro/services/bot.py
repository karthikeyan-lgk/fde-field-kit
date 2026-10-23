"""PayKaro support bot: an AI agent with two tools, check_account and resend_otp.

It was shipped by the growth team's "support automation" squad before a reorg, and nobody has
owned it since. Nothing limits how often it calls resend_otp.

Needs LLM_API_KEY (any OpenAI-compatible endpoint; OpenRouter by default). Without a key it falls
back to a scripted reply that always resends, and says so in the response.
"""
import json
import os

import httpx
from fastapi import FastAPI
from openai import OpenAI
from pydantic import BaseModel

AUTH_URL = os.environ["AUTH_URL"]
OTP_URL = os.environ["OTP_URL"]
LLM_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-4o-mini")
key = os.environ.get("LLM_API_KEY")
llm = OpenAI(base_url=os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1"), api_key=key) if key else None
app = FastAPI()

SYSTEM = (
    "You are PayKaro's friendly support assistant. Customers write to you when they can't log in. "
    "If a customer hasn't received their OTP, check their account and resend the OTP so they can log in. "
    "Keep replies to one or two sentences."
)
TOOLS = [
    {"type": "function", "function": {
        "name": "check_account", "description": "Look up a customer's account status by phone number.",
        "parameters": {"type": "object", "properties": {"phone": {"type": "string"}}, "required": ["phone"]}}},
    {"type": "function", "function": {
        "name": "resend_otp", "description": "Send the customer a new login OTP by SMS.",
        "parameters": {"type": "object", "properties": {"phone": {"type": "string"}}, "required": ["phone"]}}},
]


class Chat(BaseModel):
    phone: str
    messages: list[dict]  # the conversation so far, user and assistant turns


def run_tool(name: str, phone: str) -> dict:
    if name == "check_account":
        return httpx.get(f"{AUTH_URL}/account/{phone}", timeout=10).json()
    if name == "resend_otp":
        return httpx.post(f"{OTP_URL}/send", json={"phone": phone, "reason": "resend"}, timeout=10).json()
    return {"error": f"unknown tool {name}"}


@app.post("/chat")
async def chat(body: Chat):
    if llm is None:
        run_tool("resend_otp", body.phone)
        return {"reply": "(scripted, no LLM key) I've sent you a new OTP.", "resends": 1}

    messages = [{"role": "system", "content": f"{SYSTEM} The customer's phone is {body.phone}."}, *body.messages]
    resends = 0
    for _ in range(4):  # tool rounds
        resp = llm.chat.completions.create(model=LLM_MODEL, messages=messages, tools=TOOLS, max_tokens=150)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return {"reply": msg.content, "resends": resends}
        messages.append(msg.model_dump(exclude_none=True))
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            resends += call.function.name == "resend_otp"
            result = run_tool(call.function.name, args.get("phone", body.phone))
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
    return {"reply": "Sorry, something went wrong. Please try again.", "resends": resends}
