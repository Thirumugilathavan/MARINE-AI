# Contributing to MARINE-AI Platform

Welcome to the **MARINE-AI Platform** development team. To ensure code quality, platform security, and seamless collaboration, all contributors must follow the guidelines outlined below.

---

## 1. Golden Rules of Collaboration

1. **NEVER push directly to `main`**: All code must arrive on `main` through a Pull Request (PR). Direct pushes to `main` are strictly prohibited.
2. **NEVER merge your own Pull Request**: All PRs targeting `main` require explicit review and approval from the project lead (`Thirumugilathavan`) before merging.
3. **NEVER commit sensitive data or credentials**:
   - Never commit `.env` or files containing passwords, API tokens, or secrets.
   - Never commit local database dumps or `postgres-data/`.
   - Never commit SeaweedFS volume files or `seaweedfs-data/`.
   - Never commit raw binary datasets or files in `dataset-staging/`.
4. **Always verify `.gitignore`**: Before staging any files, run `git status` to ensure machine-specific or sensitive data is not tracked.

---

## 2. Getting Started & Cloning the Repository

Clone the official repository to your local workspace:

```bash
git clone https://github.com/Thirumugilathavan/MARINE-AI.git
cd MARINE-AI
```

Check available remote branches:

```bash
git fetch origin
git branch -r
```

---

## 3. Switching to Your Assigned Branch

The platform has established two active feature branches for provider connectors and validation:

### Branch A: NOAA & Argo Connectors
Assigned to research, implement, and test NOAA and Argo data providers.
```bash
git checkout -b feature/noaa-argo-connectors origin/feature/noaa-argo-connectors
```

**Scope**:
- NOAA ERDDAP / NODC API client integration and catalogue discovery.
- Argo float data retrieval and profile metadata parsing.
- Verified provider access methods with realistic error handling.
- Common response normalization.
- Provider-specific unit and integration tests.
- Documentation in `project-documents/`.

### Branch B: INCOIS Integration & Data Validation
Assigned to research, implement, and test INCOIS data services and marine quality checks.
```bash
git checkout -b feature/incois-validation origin/feature/incois-validation
```

**Scope**:
- INCOIS web service integration and Indian Ocean data feeds.
- Marine data quality indicators and physical bounds validation.
- Ingestion provenance tracking and retrieval timestamps.
- Metadata normalization conforming to platform schemas.
- Provider-specific unit and integration tests.
- Documentation in `project-documents/`.

---

## 4. Local Environment Setup

Each teammate must set up their own local Docker infrastructure and Python environment:

1. **Docker Infrastructure**:
   - Start your local PostgreSQL 17 / PostGIS container.
   - Start your local SeaweedFS container on port 8333.
   - Run `python create_buckets.py` using your local `config/s3.json`.

2. **Environment Variables**:
   - Copy `.env.example` to `backend/.env`.
   - Set `DATABASE_PASSWORD`, `SEAWEEDFS_ACCESS_KEY`, and `SEAWEEDFS_SECRET_KEY` according to your local Docker containers.
   - Keep your `.env` private—it is ignored by Git.

3. **Virtual Environment**:
   ```bash
   cd backend
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\Activate.ps1
   # Linux/macOS:
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

---

## 5. Development & Testing Workflow

### Testing Connectors Independently
When implementing or modifying provider connectors:
1. Write mock-based unit tests under `backend/tests/` to verify request construction, parameter validation, and response transformation without relying on active internet access during CI.
2. Provide integration test scripts for live endpoint validation that can be triggered locally with appropriate credentials.
3. Run the full test suite before committing:
   ```bash
   cd backend
   python -m unittest discover tests
   ```

---

## 6. Creating Commits & Pushing

Write clear, concise commit messages adhering to standard conventions:

```bash
# Check status - make sure NO .env, data, or cache files are staged
git status

# Stage only relevant source, test, or documentation files
git add backend/app/modules/data_sources/your_provider/
git add backend/tests/test_your_provider.py

# Commit with a descriptive imperative message
git commit -m "feat(connector): add NOAA ERDDAP catalogue search client"

# Push to your feature branch on origin
git push origin feature/noaa-argo-connectors
# or
git push origin feature/incois-validation
```

---

## 7. Opening a Pull Request & Code Review

1. Navigate to the GitHub repository: `https://github.com/Thirumugilathavan/MARINE-AI`
2. Click **New Pull Request**.
3. Set **Base branch**: `main`
4. Set **Compare branch**: your feature branch (e.g. `feature/noaa-argo-connectors` or `feature/incois-validation`).
5. Complete the PR description:
   - Summary of changes implemented.
   - Provider API endpoints verified (link to official provider documentation).
   - Test results demonstrating passing test suite.
   - Any new environment variable keys required in `.env.example`.
6. Assign **Reviewer**: `Thirumugilathavan`.
7. Address any code review feedback promptly.
8. **Do NOT merge the PR yourself**—the repository owner will approve and merge the PR once review is complete.
