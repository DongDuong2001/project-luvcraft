# Project Pluto: Contribution Guidelines

Welcome to the **Project Luvcraft** repository. To keep this internal tool clean, professional, and highly maintainable, all Project Pluto team members must adhere to the following rules when pushing code.

## 1. Git Commit Convention

We follow the **Conventional Commits** standard. Please format all commit messages accordingly to ensure an easily readable Git history. We rely on team discipline rather than automated hooks.

**Format:**
```text
<type>[optional scope]: <description>
```

**Allowed Types:**
*   `feat`: A new feature (e.g., a new collector or frontend component)
*   `fix`: A bug fix
*   `docs`: Documentation only changes
*   `style`: Changes that do not affect the meaning of the code (white-space, formatting)
*   `refactor`: A code change that neither fixes a bug nor adds a feature
*   `perf`: A code change that improves performance
*   `test`: Adding missing tests or correcting existing tests
*   `chore`: Changes to the build process or auxiliary tools and libraries

**Examples:**

* [VALID] `feat(backend): add anomaly detection for hype velocity`
* [VALID] `fix(frontend): update export button spacing on dashboard`
* [VALID] `docs: update deployment instructions`
* [INVALID] `added new stuff` (Invalid - no type)

## 2. Project Structure Rules

When building extending Project Luvcraft, follow the established monorepo separation of concerns:

### Backend (Python/FastAPI)

* **New Data Sources**: Do NOT hardcode endpoints. Always add new platforms to `backend/app/conf/collectors.yaml`.
* **New Collectors**: All new collector modules must inherit from `BaseCollector` (in `backend/app/collectors/collector_base.py`) to inherit the mandatory SLA timeout tracking, Spam/Bot filtering, and PII stripping logic.
* **Database Changes**: Any new tables or columns tracking analytics criteria must be represented in `backend/app/db/models.py`.

### Frontend (React/Next.js)

* **Styling**: Use strictly Tailwind CSS utility classes. Avoid creating custom CSS files unless absolutely necessary.
* **Components**: Keep layout structures modular. If the `DashboardLayout.tsx` grows too large, break charts and tables out into smaller sub-components inside the `frontend/components/` directory.

## 3. Compliance & Ethics

* Never commit real passwords, API keys, or database credentials.
* Ensure all new collector logic relies on Public/SERP data only. Simulated authenticated logins are strictly forbidden by Project Pluto policy.

## 4. Pull Request & Code Review Workflow

* **Branching**: Always create a new branch for your feature or bug fix (e.g., `feat/hype-collector`, `fix/dashboard-ui`). Do not commit directly to `main`.
* **Draft PRs**: When you start coding a feature, open a **Draft Pull Request (PR)** immediately to signal to the team what you are working on.
* **Mandatory Review Rule**: When your code is ready, transition to a standard PR. You **MUST add the Project Leader (Duong Phu Dong) as a reviewer**. No code can be merged into `main` without explicit approval and code review from the Project Leader.
