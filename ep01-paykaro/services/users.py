"""PayKaro's customers. Not part of the system under test, and not instrumented.

Each user logs in, then watches their phone (the carrier's inbox) for the OTP. If it hasn't come
within PATIENCE_S, they ask the support bot, up to MAX_COMPLAINTS times, then give up.
CHAT_BUDGET_PER_MIN caps how many chats reach the bot, which keeps the LLM bill to cents.
Every 10s it prints what the users experienced.
"""
import asyncio
import os
import random
import statistics
import time

import httpx

APP_URL = os.environ["APP_URL"]
BOT_URL = os.environ["BOT_URL"]
PHONE_URL = os.environ["PHONE_URL"]
RATE = float(os.environ.get("LOGINS_PER_SEC", "1.3"))
PATIENCE = float(os.environ.get("PATIENCE_S", "15"))
MAX_COMPLAINTS = int(os.environ.get("MAX_COMPLAINTS", "2"))
GIVE_UP_S = float(os.environ.get("GIVE_UP_S", "120"))
BOT_ON = os.environ.get("BOT_ENABLED", "true") == "true"
CHAT_BUDGET = int(os.environ.get("CHAT_BUDGET_PER_MIN", "30"))

stats = {"logins": 0, "got_otp": [], "gave_up": 0, "errors": 0, "chats": 0, "resends": 0}
chat_window = {"minute": 0, "used": 0}
COMPLAINTS = ["Hi, I didn't get my OTP.", "Still nothing. Can you send it again?", "Nothing again!! Please help"]


def chat_allowed() -> bool:
    minute = int(time.time() // 60)
    if chat_window["minute"] != minute:
        chat_window.update(minute=minute, used=0)
    if chat_window["used"] >= CHAT_BUDGET:
        return False
    chat_window["used"] += 1
    return True


async def wait_for_otp(client: httpx.AsyncClient, phone: str, since: float, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        r = await client.get(f"{PHONE_URL}/inbox/{phone}", params={"since": since})
        if r.json():
            return True
        await asyncio.sleep(1)
    return False


async def user(client: httpx.AsyncClient, n: int) -> None:
    phone = f"+9198{n:08d}"
    start = time.time()
    stats["logins"] += 1
    try:
        await client.post(f"{APP_URL}/login", json={"phone": phone})
        messages: list[dict] = []
        for complaint in COMPLAINTS[:MAX_COMPLAINTS] + [None]:
            if await wait_for_otp(client, phone, start, PATIENCE if complaint else GIVE_UP_S):
                stats["got_otp"].append(time.time() - start)
                return
            if complaint is None or not BOT_ON or not chat_allowed():
                continue
            messages.append({"role": "user", "content": complaint})
            r = await client.post(f"{BOT_URL}/chat", json={"phone": phone, "messages": messages}, timeout=60)
            reply = r.json()
            stats["chats"] += 1
            stats["resends"] += reply.get("resends", 0)
            messages.append({"role": "assistant", "content": reply.get("reply") or ""})
        stats["gave_up"] += 1
    except httpx.HTTPError:
        stats["errors"] += 1


async def report() -> None:
    while True:
        await asyncio.sleep(10)
        got = sorted(stats["got_otp"][-200:])
        p50 = statistics.median(got) if got else 0
        p95 = got[int(len(got) * 0.95) - 1] if len(got) >= 20 else (got[-1] if got else 0)
        print(f"logins={stats['logins']} got_otp={len(stats['got_otp'])} gave_up={stats['gave_up']} errors={stats['errors']} "
              f"otp_wait_p50={p50:.1f}s p95={p95:.1f}s chats={stats['chats']} bot_resends={stats['resends']}",
              flush=True)


async def main() -> None:
    asyncio.create_task(report())
    async with httpx.AsyncClient(timeout=10) as client:
        n = random.randint(0, 10_000_000)
        while True:
            n += 1
            asyncio.create_task(user(client, n))
            await asyncio.sleep(random.expovariate(RATE))


asyncio.run(main())
