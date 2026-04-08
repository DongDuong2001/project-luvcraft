# Project Luvcraft

## An internal AI-powered fandom intelligence platform by Project Pluto

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io/)

---

## Overview

**Project Luvcraft** is exclusively developed for the **Project Pluto** team. The platform is designed to aggregate public market signals, track hype cycles, measure sentiment across social platforms, and utilize Large Language Models (LLMs) to generate multi-dimensional brand collaboration insights tailored to our strategic objectives.

## Key Features

* **Signal Aggregation:** Collects real-time data from various social and community platforms.
* **Hype Tracking:** Measures velocity and volume of market trends.
* **AI-Powered Insights:** Utilizes LangChain and LLMs to generate deep, actionable reports.
* **Asynchronous Processing:** Powered by Celery and Redis to handle heavy scraping and AI background tasks.
* **Interactive Dashboard:** A robust researcher portal built with Next.js and Tailwind CSS.

## Tech Stack

**Frontend:**

* Next.js 14 & React 18
* Tailwind CSS
* Recharts

**Backend:**

* Python 3.12 & FastAPI
* Celery & Redis (Task Queues)
* SQLAlchemy & PostgreSQL (Persistence)
* LangChain & LiteLLM (AI Services)

## Architecture & Structure

The repository follows a clean, modular, cloud-ready monorepo structure:

```text
project-luvcraft/
├── backend/                # Core API and Worker services
│   ├── app/collectors/     # Modular scrapers (Reddit, generic APIs, etc.)
│   ├── app/services/       # LLM intelligence & PDF reporting modules
│   └── app/db/             # PostgreSQL database models
├── frontend/               # User Interface
│   └── components/         # Internal Researcher Dashboard UI
├── docker-compose.yml      # Orchestrates Postgres, Redis, Celery, Backend, Frontend
└── CONTRIBUTING.md         # Mandatory Git conventions and team rules
```

## Getting Started

### Prerequisites

Ensure you have [Docker Desktop](https://www.docker.com/products/docker-desktop) installed.

### Launching the Cluster

To spin up the entire stack locally for development:

```bash
docker-compose up --build
```

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

* **Academic Supervisor:** Dr. Kapil Dev ([kapil.dev@rmit.edu.vn](mailto:kapil.dev@rmit.edu.vn))
* **Industrial Coordinator:** Project Pluto
