# Project Luvcraft

## An internal AI-powered fandom intelligence platform by Project Pluto

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![Supabase](https://img.shields.io/badge/Supabase-3FCF8E?style=flat-square&logo=supabase&logoColor=white)](https://supabase.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?style=flat-square&logo=rabbitmq&logoColor=white)](https://www.rabbitmq.com/)

---

## Overview

**Project Luvcraft** is developed with **Project Pluto** as the industry partner. The platform aggregates public market signals, tracks hype cycles, measures sentiment across social platforms, and uses Large Language Models (LLMs) to generate multi-dimensional brand collaboration insights for strategic fandom research.

## Key Features

* **Signal Aggregation:** Collects real-time data from social and community platforms.
* **Hype Tracking:** Measures velocity and volume of market trends.
* **AI-Powered Insights:** Uses LangChain and LLMs to generate actionable reports.
* **Asynchronous Processing:** Uses a PostgreSQL transactional outbox, Celery Beat, workers, and RabbitMQ for durable background tasks.
* **Interactive Dashboard:** Provides a researcher portal built with Next.js and Tailwind CSS.

## Tech Stack

**Frontend:**

* Next.js 16 & React 19
* Tailwind CSS
* Recharts

**Backend:**

* Python 3.12 & FastAPI
* Celery & RabbitMQ (Task Queues)
* Supabase PostgreSQL (Managed Persistence)
* SQLAlchemy (Data Models)
* LangChain & LiteLLM (AI Orchestration)
* Gemini 2.5 Flash-Lite & GPT o4-mini (AI Models)

**AI Model Routing:**

* **Gemini 2.5 Flash-Lite:** Critical tasks that require deeper reasoning, higher confidence, or more careful synthesis.
* **GPT o4-mini:** Simple tasks such as lightweight summarization, formatting, classification, and low-risk helper responses.

**Infrastructure & Data:**

* Docker Compose for local development
* RabbitMQ persistent task queue volume
* Supabase-managed PostgreSQL for deployed persistence
* Local PostgreSQL-compatible container for development fallback

## Architecture & Structure

The repository follows a clean, modular, cloud-ready monorepo structure:

```text
project-luvcraft/
|-- backend/                 # Core API and worker services
|   |-- app/collectors/      # Modular scrapers and public data collectors
|   |-- app/services/        # LLM intelligence and reporting modules
|   `-- app/db/              # PostgreSQL-compatible data models
|-- frontend/                # Researcher dashboard UI
|   `-- components/          # Internal dashboard components
|-- docs/                    # Technical documentation
|   `-- collector.md         # YouTube Collector MVP documentation
|-- compose.yaml             # Local Postgres, RabbitMQ, Celery, Backend, Frontend
`-- CONTRIBUTING.md          # Mandatory Git conventions and team rules
```

## Running The Project

### Prerequisites

Install the following tools before running the project locally:

* [Docker Desktop](https://www.docker.com/products/docker-desktop) for the full local stack.
* Node.js `24.x` and npm `11.x` for local frontend development.
* Python `3.12` for local backend development outside Docker.
* A Supabase PostgreSQL connection string when using the shared cloud database.

The project can run with either Supabase PostgreSQL or the local PostgreSQL container from `compose.yaml`. For normal local development, Docker Compose is the fastest setup because it starts the frontend, backend, Celery worker, Celery Beat dispatcher, PostgreSQL, and RabbitMQ together.

### Environment Variables

Use `.env.local.example` as the local setup template. Copy it to `.env` when running the Docker Compose/backend flow, then fill in secrets only in your local `.env`. Keep `.env.local.example` free of real API keys so teammates do not accidentally commit or reuse private credentials.

| Variable | Used By | Local Default | Notes |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | Backend, Celery | `postgresql://postgres:postgres@localhost:5432/luvcraft` outside Docker, `postgresql://postgres:postgres@postgres:5432/luvcraft` inside Compose | Set this to the Supabase PostgreSQL connection string for shared environments. |
| `CELERY_BROKER_URL` | Backend, Celery | `pyamqp://luvcraft:luvcraft@localhost:5672//` outside Docker, `pyamqp://luvcraft:luvcraft@rabbitmq:5672//` inside Compose | RabbitMQ replaces Redis as the persistent task broker. |
| `CELERY_RESULT_BACKEND` | Celery | `db+<DATABASE_URL>` | Optional. The backend defaults to storing Celery results in PostgreSQL. |
| `CORS_ORIGINS` | Backend | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated frontend origins allowed to call the FastAPI service. |
| `YOUTUBE_API_KEY` | Backend, Celery | None | Task 4 YouTube collector API key. Do not commit real keys. |
| `YOUTUBE_REGION_CODE` | Backend, Celery | `VN` | Task 4 YouTube search region filter. |
| `YOUTUBE_RELEVANCE_LANGUAGE` | Backend, Celery | `vi` | Task 4 YouTube search relevance language and persisted signal language. |
| `YOUTUBE_MAX_RESULTS` | Celery | `50` | Maximum videos requested per YouTube search. The collector clamps this to YouTube's per-request limit of 50. |
| `YOUTUBE_MIN_RECORDS_THRESHOLD` | Celery | `20` | Minimum persisted YouTube signals before the module omits the insufficient-data warning. |
| `YOUTUBE_TIMEOUT_MAX_RETRIES` | Celery | `3` | Maximum Celery retries for transient YouTube timeout errors before marking the module failed. |
| `YOUTUBE_TIMEOUT_RETRY_DELAY_SECONDS` | Celery | `60` | Delay between retries after a transient YouTube timeout. |
| `DEBUG_HTTP` | Backend, Celery | `false` | Enables verbose `httpx`/`httpcore` logging for local debugging. Leave disabled when using real API keys. |
| `NEXT_PUBLIC_API_URL` | Frontend | `http://localhost:8000` | API base URL used by the Next.js app. |

If the Supabase database password contains special characters, URL-encode the password before placing it in `DATABASE_URL`.

Task 4 update: YouTube collector verification is backend/API/database only. A completed run means the YouTube collection task finished and persisted `CollectedSignal` records; `/runs/{run_id}/result` still depends on synthesis output and is not part of the Task 4 collector scope.

### Option 1: Run The Full Stack With Docker Compose

Use this path when the team wants the complete app running with the fewest manual steps.

```bash
docker compose up --build
```

The backend applies all pending Alembic migrations before starting the API. When running FastAPI manually from `backend/`, run `python -m app.db.migrate` before starting Uvicorn.

Local Compose pins RabbitMQ to `3.13-management-alpine` for compatibility with the current Celery queue declarations.

For deployed environments, set `DATABASE_URL` to the Supabase PostgreSQL connection string. Local Compose falls back to a development PostgreSQL container when `DATABASE_URL` is not provided.

### Access Points

* **Researcher Dashboard:** [http://localhost:3000](http://localhost:3000)
* **Backend API (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
* **RabbitMQ Management UI:** [http://localhost:15672](http://localhost:15672), login with `luvcraft` / `luvcraft`
* **Local PostgreSQL:** `localhost:5432`, database `luvcraft`, user `postgres`, password `postgres`

### Supabase Setup

For shared development, staging, or production environments, set `DATABASE_URL` to the Supabase PostgreSQL connection string before starting the backend or Compose stack.

PowerShell:

```powershell
$env:DATABASE_URL = "postgresql://<user>:<password>@<host>:5432/<database>"
docker compose up --build
```

macOS/Linux:

```bash
DATABASE_URL="postgresql://<user>:<password>@<host>:5432/<database>" docker compose up --build
```

Do not commit real Supabase credentials to the repository.

### Troubleshooting

* If `next build` fails with a Node.js version error, switch to Node.js `24.x`.
* If the backend cannot connect to RabbitMQ, confirm RabbitMQ is running and `CELERY_BROKER_URL` uses the correct host: `rabbitmq` inside Docker, `localhost` outside Docker.
* If the backend cannot connect to PostgreSQL, confirm `DATABASE_URL` points to either Supabase or the local Compose database.
* If ports are already in use, stop the conflicting local services or change the exposed ports in `compose.yaml`.
* If Docker commands fail before containers start, confirm Docker Desktop is running.

## Documentation

* [YouTube Collector MVP Documentation](docs/collector.md)

## Contribution & Git Rules

Please refer to [CONTRIBUTING.md](CONTRIBUTING.md) for the mandatory Git Commit Conventions and structural guidelines required by the Project Pluto team.

## Team Members (Project Pluto)

| Member | Role |
| :--- | :--- |
| **Duong Phu Dong** | Technical Leader / Full-stack Developer |
| **Huynh Quang Dong** | Scrum Master / QA Engineer |
| **Ho Quang Huy** | DevOps / Backend Developer |
| **Vu Thien Minh Hao** | Backend Developer / AI Engineer |
| **Tran Vu Nhat Tin** | Frontend Developer |

## Leadership & Supervision

* **Academic Supervisor:** Dr. Kapil Dev
* **Industry Partner:** Project Pluto
* **Company Representatives:** Mr. Danh Pham, Mr. Hien Nguyen, Mr. Gia Kiet
