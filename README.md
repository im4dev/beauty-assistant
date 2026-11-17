# Beauty Assistant

A WhatsApp assistant that books, reschedules and cancels appointments for beauty salons.
Clients write in plain language; an LLM (**DeepSeek**) extracts the intent, service and
date, and the backend (**FastAPI + PostgreSQL**) checks real availability before
confirming anything.

## Demo

> Recorded on a mock chat UI (not WhatsApp) for the demo salon *Studio Aurora*.
> The bot replies are real output from the backend; the salon and client are made up.

<table>
  <tr>
    <td align="center"><img src="docs/demo/agendar.gif" width="260" alt="Booking a haircut in plain language"></td>
    <td align="center"><img src="docs/demo/reprogramar.gif" width="260" alt="Rescheduling the appointment"></td>
    <td align="center"><img src="docs/demo/cancelar.gif" width="260" alt="Cancelling, with a confirmation step"></td>
  </tr>
  <tr>
    <td align="center"><b>Book</b><br>lists services, proposes the slot, waits for "sí"</td>
    <td align="center"><b>Reschedule</b><br>moves the existing appointment</td>
    <td align="center"><b>Cancel</b><br>asks for confirmation first</td>
  </tr>
</table>

## What it does

- **Booking, rescheduling and cancelling** over WhatsApp, always with an explicit confirmation step.
- **Availability checks** against business hours, active stylists and existing appointments; if the
  requested time is taken it offers the free slots for that day.
- **Waitlist**: when an appointment is cancelled, the freed slot is offered to the next client waiting.
- **Reminders**: 24 h and 1 h before for the client, 30 min before for the stylist.
- **Multi-salon**: each salon is resolved from the WhatsApp phone number that received the message.
- **Dashboard** with login, appointments, stats and live updates (Server-Sent Events).

## How a message flows

```
WhatsApp ──▶ Meta Cloud API ──▶ POST /webhook ──▶ signature check (X-Hub-Signature-256)
                                                  │  dedupe retries, reply 200 at once
                                                  ▼
                                            background task
                                                  │
                         salon (by phone_number_id) + client session
                                                  │
                           DeepSeek: intent + entities (service, datetime)
                                                  │
                     availability check ─▶ create / reschedule / cancel
                                                  │
                                    reply ──▶ Graph API /messages
```

## Stack

Python · FastAPI · SQLAlchemy (async) · PostgreSQL · DeepSeek API · WhatsApp Cloud API · Docker · Caddy

## Running it

Create a `.env` with at least:

```
VERIFY_TOKEN=          # same value as in Meta's webhook settings
APP_SECRET=            # Meta app secret, used to verify webhook signatures
WA_ACCESS_TOKEN=       # permanent System User token
WHATSAPP_PHONE_ID=
DEEPSEEK_API_KEY=
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/beauty
DASHBOARD_USERNAME=
DASHBOARD_PASSWORD=
```

```
docker compose up -d --build                    # local
python -m scratch.seed_demo                     # demo salon, services and stylists
python -m scratch.chat                          # chat with the bot from the terminal, nothing is sent to Meta
```

Point the Meta webhook to `https://<your-domain>/webhook` and subscribe to `messages`.
