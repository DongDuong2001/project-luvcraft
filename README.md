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
* **Asynchronous Processing:** Uses Celery and RabbitMQ for scraping and AI background tasks.
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
* LangChain & LiteLLM (AI Services)

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
|-- compose.yaml             # Local Postgres, RabbitMQ, Celery, Backend, Frontend
`-- CONTRIBUTING.md          # Mandatory Git conventions and team rules
```

## Getting Started

### Prerequisites

Ensure you have [Docker Desktop](https://www.docker.com/products/docker-desktop) installed.

### Launching the Cluster

To spin up the entire stack locally for development:

```bash
docker compose up --build
```

For deployed environments, set `DATABASE_URL` to the Supabase PostgreSQL connection string. Local Compose falls back to a development PostgreSQL container when `DATABASE_URL` is not provided.

### Access Points

* **Researcher Dashboard:** [http://localhost:3000](http://localhost:3000)
* **Backend API (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)

## Contribution & Git Rules

Please refer to [CONTRIBUTING.md](CONTRIBUTING.md) for the mandatory Git Commit Conventions and structural guidelines required by the Project Pluto team.

## Team Members (Project Pluto)

| Member | Role |
| :--- | :--- |
| **Duong Phu Dong** | Project Leader / Full-stack Developer |
| **Huynh Quang Dong** | Scrum Master / QA Engineer |
| **Ho Quang Huy** | DevOps / Backend Developer |
| **Vu Thien Minh Hao** | Backend Developer / AI Engineer |
| **Tran Vu Nhat Tin** | Frontend Developer |

## Leadership & Supervision

* **Academic Supervisor:** Dr. Kapil Dev
* **Industry Partner:** Project Pluto
* **Company Representatives:** Mr. Danh Pham, Mr. Hien Nguyen, Mr. Gia Kiet
