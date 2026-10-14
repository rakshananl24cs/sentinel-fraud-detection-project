# Cost-Sensitive Fraud Detection System

An end-to-end machine learning and software engineering platform for cost-sensitive credit card fraud scoring, operator review adjudication, prediction ledger immutability, and automated statistical data drift monitoring.

---

## 1. Prerequisites

- **Operating System:** Windows 10/11 or Linux / macOS
- **Python:** Python 3.12+ (virtual environment at `./.venv`)
- **Docker:** Docker Desktop with Docker Compose v2+
- **PostgreSQL Client (Optional):** psql / pg_restore v16+

---

## 2. Environment Configuration

1. Copy the environment configuration template:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Open `.env` and configure local values using strong, unique secrets:
   ```env
   # Application Runtime
   APP_ENV=development
   APP_DEBUG=true
   API_HOST=0.0.0.0
   API_PORT=8000
   CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

   # PostgreSQL Database (Host dev port 5433; Container backend uses db:5432)
   POSTGRES_USER=fraud_user
   POSTGRES_PASSWORD=<STRONG_DATABASE_PASSWORD>
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5433
   POSTGRES_DB=fraud_db
   DATABASE_URL=postgresql+psycopg://fraud_user:<STRONG_DATABASE_PASSWORD>@localhost:5433/fraud_db

   # Dedicated Test Database (Isolated from working application database)
   TEST_POSTGRES_DB=fraud_test_db
   TEST_DATABASE_URL=postgresql+psycopg://fraud_user:<STRONG_DATABASE_PASSWORD>@localhost:5433/fraud_test_db

   # Security & Authentication (JWT)
   JWT_SECRET_KEY=<32_BYTE_HEX_ENCODED_SECRET_KEY>
   JWT_ALGORITHM=HS256
   JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
   BCRYPT_ROUNDS=12

   # Model Paths & Active Governance
   MODEL_DIR=./ml/models
   ACTIVE_MODEL_VERSION=xgb-cost-v1
   ```
   *Never commit `.env` or secrets to version control.*

---

## 3. Starting the Services

### 3.1 Backend & Database (Docker Compose)

Start the multi-service Docker Compose stack (FastAPI backend and PostgreSQL 16 database):

```powershell
docker compose up -d
```

Verify service status and health checks:
```powershell
docker compose ps
```
- **Backend API:** Available at `http://localhost:8000`
- **Database Service:** Accessible on host port `5433` (native port `5432` remains preserved for local Windows services).

### 3.2 Operator Dashboard Frontend (React / Vite)

Start the fintech operator console web application:

```powershell
cd frontend
npm run dev
```
- **Operator Console URL:** `http://localhost:5173`
- **API Target:** `http://localhost:8000` (configurable via `VITE_API_BASE_URL` in `frontend/.env`)
- **Production Bundle:**
  ```powershell
  cd frontend
  npm run build
  ```

---

## 4. Health Checks and API Documentation

Verify application readiness and interactive OpenAPI documentation:

- **Liveness Probe:**
  ```powershell
  curl.exe http://localhost:8000/health/live
  ```
  *Response:* `{"status":"ok","service":"fraud-detection-api",...}`

- **Readiness Probe:**
  ```powershell
  curl.exe http://localhost:8000/health/ready
  ```
  *Response:* `{"status":"ok","database":"connected",...}`

- **Interactive API Documentation:**  
  Visit `http://localhost:8000/docs` or `http://localhost:8000/redoc` in your web browser.

---

## 5. Running Automated Tests

Run the full automated pytest regression test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

All 98 tests should pass across preprocessing, calibration, cost-sensitive decision optimization, drift detection, security, and FastAPI integration endpoints.

---

## 6. Database Migrations (Alembic)

Database schema migrations are managed via Alembic:

- Check current database revision:
  ```powershell
  .\.venv\Scripts\python.exe -m alembic current
  ```
  *(Expected Head: `20b46b28f9db`)*

- Upgrade database schema to head:
  ```powershell
  .\.venv\Scripts\python.exe -m alembic upgrade head
  ```

---

## 7. Local Database Backup & Verification

Backups are executed using PostgreSQL's custom binary format (`-F c`):

1. **Create Local Backup:**
   ```powershell
   docker exec fraud_detection_db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c -b -f /tmp/backup.dump'
   docker cp fraud_detection_db:/tmp/backup.dump .\backups\fraud_db_backup.dump
   docker exec fraud_detection_db rm -f /tmp/backup.dump
   ```

2. **Verify Checksum & Table of Contents:**
   ```powershell
   Get-FileHash -Path .\backups\fraud_db_backup.dump -Algorithm SHA256
   docker exec fraud_detection_db pg_restore --list /tmp/backup.dump
   ```

3. **Isolated Test Restoration:**  
   Always restore into an isolated temporary database (e.g. `fraud_db_restore_verify`), **never** over the live `fraud_db`. See [`docs/DEPLOYMENT_AND_INTEGRATION_HANDOVER.md`](file:///C:/FraudDetection/docs/DEPLOYMENT_AND_INTEGRATION_HANDOVER.md) for full steps.

---

## 8. Safe Shutdown

To stop running containers while strictly preserving the database volume and container identity:

```powershell
# Stop services safely
docker compose stop
# or
docker compose down
```

> [!WARNING]
> **NEVER** run `docker compose down -v`. The `-v` flag deletes named volumes and will permanently destroy `fraud_detection_pgdata`.

---

## 9. Documentation Index

- **Final Technical Report:** [`docs/FINAL_PROJECT_REPORT.md`](file:///C:/FraudDetection/docs/FINAL_PROJECT_REPORT.md)
- **Deployment & Handover Specification:** [`docs/DEPLOYMENT_AND_INTEGRATION_HANDOVER.md`](file:///C:/FraudDetection/docs/DEPLOYMENT_AND_INTEGRATION_HANDOVER.md)
- **Academic Presentation Outline:** [`docs/PRESENTATION_OUTLINE.md`](file:///C:/FraudDetection/docs/PRESENTATION_OUTLINE.md)
