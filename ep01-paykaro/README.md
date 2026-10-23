# PayKaro: the customer's system for FDE Field Kit Ep 01

PayKaro is a fictional Indian fintech. Its login OTPs are late, sometimes never arrive, and it got
worse after an AI support bot launched. Nobody owns the bot. This lab is that system, plus the tools
a forward deployed engineer brings on day one.

The app services have **no OpenTelemetry SDK or code**. OBI (OpenTelemetry eBPF Instrumentation)
traces them from the kernel; the Collector turns the spans into a service graph.

```
login → auth → otp-service → egress-proxy (the bank's, TLS-inspecting) → sms-vendor → carrier → phones
support-bot (LLM agent: check_account, resend_otp) → auth, otp-service, openrouter.ai
users: simulated customers who log in, wait, and ask the bot when the OTP is late (not instrumented)
```

| Service | What it is |
|---|---|
| `login`, `auth` | PayKaro's login path |
| `otp-service` | Queues login codes for 2 sender threads. Resends from the bot skip the queue ("instant resend"). |
| `egress-proxy` | The bank's proxy. Terminates TLS; the inspection delay is **simulated** (`HANDSHAKE_DELAY_S`, default 1.7 s ± 0.3 s before answering the ClientHello). |
| `sms-vendor` | A mock vendor with one shared quota for the account (`SMS_QUOTA_PER_MIN`, default 90). Past it, everything gets 429. |
| `carrier` | The telecom network; holds each phone's inbox. Outside OBI's view. |
| `support-bot` | A real LLM agent (OpenRouter, `openai/gpt-4o-mini` by default) with two tools and no limit on resends. |
| `users` | Customers: 1.3 logins/s, ask the bot after 15 s without an OTP, at most 2 complaints each, chats capped at 30/min to keep the LLM bill to cents. |

The OBI, Collector, Jaeger, Prometheus and Grafana containers are the FDE's own tools. Nothing above them changes.

## Run it

Needs Docker and a Linux kernel with eBPF (OBI runs privileged with `pid: host`).

```sh
export LLM_API_KEY=...   # any OpenAI-compatible key; OpenRouter by default. Without it the bot is scripted.
make up                  # PayKaro + OBI + Collector + Jaeger + Prometheus + Grafana
make users               # what customers experience, every 10 s
make bot-off             # "before the bot launched": customers just wait
make bot-on              # the bot is live again
make vendor              # SMS quota: accepted / rejected
make knock               # one HTTPS send through the proxy: connect / TLS handshake / request
make down
```

- Jaeger: <http://localhost:16686> (System Architecture shows the map; search `support-bot` for one chat)
- Grafana: <http://localhost:3000/d/paykaro> (edges incl. the LLM provider, quota, bot activity, send time)
- Prometheus: <http://localhost:9090>

## What you should see

`./measure.sh` runs each scenario from a clean start for 7 minutes and prints what customers saw at
4 and 7 minutes. The fixes are switches: `HANDSHAKE_DELAY_S=0.05` (the bank allow-lists the SMS vendor,
no inspection), `RESEND_COOLDOWN_S=120` (one resend per phone per 2 min), `SMS_RESEND_QUOTA_PER_MIN=20`
(resends get their own bucket at the vendor).

Measured 2026-10-21:

| Scenario | p50 @4 / @7 min | p95 @4 / @7 min | SMS rejected @7 min |
|---|---|---|---|
| bot off | 18 s / 41 s | 24 s / 54 s | 0 |
| bot on | 23 s / 45 s | 53 s / 64 s | 50 (11 users gave up) |
| bot limited only | 7 s / 13 s | 42 s / 52 s | 32 |
| proxy bypassed only (bot on) | 1.1 s | 1.1 s | 0 (88 of 90 quota used in a minute) |
| all three fixes | 1.0 s | 1.1 s | 0 |

`make knock`: connect ~1 ms, TLS handshake 1.3–2.0 s, request ~20 ms.

## Known limits

- **Secure Boot / kernel lockdown** blocks the eBPF helper OBI uses to inject trace headers, so OBI
  logs "context propagation is disabled". Per-service spans, the service graph and in-process trees
  (one bot chat → LLM → tools) still work; one login is not one end-to-end trace.
- The bot runs as `async def` with 4 workers so each chat stays on one thread, which lets OBI nest the
  chat's LLM and tool calls under it without header propagation.
- OBI's metrics export about once a minute, so dashboard rates use 3–5 minute windows.
