# Project Pluto: Luvcraft

This repository contains the source code for Project Luvcraft, an internal AI-powered fandom intelligence platform developed exclusively for the Project Pluto team.

The platform aggregates public market signals, tracks hype cycles, measures sentiment across social platforms, and utilizes LLMs to generate multi-dimensional brand collaboration insights tailored to our team's strategic objectives.

## Project Structure (Monorepo)

The repository is structured to be clean, modular, and cloud-ready for scale:

```text
project-luvcraft/
├── backend/                # Python / FastAPI / Celery / SQLAlchemy
│   ├── app/collectors/     # Modular scrapers (Reddit, APIs, etc.)
│   ├── app/services/       # LLM intelligence & PDF reporting modules
│   └── app/db/             # PostgreSQL database models for historical persistence
├── frontend/               # Node.js / React / Next.js / TailwindCSS
│   └── components/         # Internal Researcher Dashboard UI
├── docker-compose.yml      # Orchestrates Postgres, Redis, Celery, Backend, Frontend
├── package.json            # Root dev-dependencies (Git Commit formatting)
└── README.md
```

## Contribution & Git Rules

Please refer to [CONTRIBUTING.md](CONTRIBUTING.md) for the mandatory Git Commit Conventions and structural guidelines required by the Project Pluto team.

## Getting Started

1. **Start the Platform cluster:**
   ```bash
   docker-compose up --build
   ```
2. **Access Vectors:**
   * Researcher Dashboard: `http://localhost:3000`
   * Backend API / Swagger: `http://localhost:8000/docs`

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

