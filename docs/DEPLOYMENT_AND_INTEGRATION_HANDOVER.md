# Cost-Sensitive Fraud Detection System
## End-to-End Deployment, Integration, and System Handover Specification

**Document Version:** 1.0.0  
**Audit Head Date:** 2026-10-12  
**Target Architecture:** Multi-service FastAPI + PostgreSQL 16 on Docker Compose & Native Windows Dev  
**Alembic Migration Head:** `20b46b28f9db`  
**Active Production Model:** `xgb-cost-v1` (Calibrated XGBoost Baseline)

---

## 1. Project Purpose, Architecture, and Key Design Decisions

### 1.1 Purpose
This system provides real-time, cost-sensitive fraud scoring, operator review triage, feedback adjudication, and statistical data drift monitoring for high-frequency financial payment streams. Rather than maximizing standard symmetric accuracy or F1-score, the scoring engine balances asymmetric financial risk:
- **Cost of False Negative ($C_{FN}$):** Severe loss incurred when fraudulent transactions go undetected ($100 per fraud instance or full transaction amount).
- **Cost of False Positive ($C_{FP}$):** Customer friction, verification overhead, and potential customer churn ($5 to $50).
- **Cost of Human Review ($C_{Review}$):** Fixed investigator operational overhead ($5.00 per reviewed transaction).
- **Operational Capacity Constraint:** Strict cap limiting transactions routed to the human investigation queue (maximum 5.0% capacity; operating at ~0.09% in validation).

### 1.2 Architecture Overview
The system follows a decoupled, layered microservices architecture:
1. **Inference Pipeline (`ml/`):**
   - Preprocessor (`ml/models/preprocessor.joblib`): Standardizes amounts and preserves anonymized PCA components $V1 \dots V28$.
   - Classifier (`ml/models/xgboost_baseline.joblib`): XGBoost binary classifier trained with class-weight compensation (`scale_pos_weight = 518.19`).
   - Calibrators (`ml/models/calibrator_isotonic.joblib`, `ml/models/calibrator_platt.joblib`): Post-hoc probability calibration transforming raw margins into reliable empirical posterior fraud probabilities.
   - Decision Engine (`ml/src/decision/`): Cost-minimizing 3-way decision logic (`APPROVE`, `REVIEW`, `BLOCK`).
   - Explainability Engine (`ml/src/models/inference.py`): TreeSHAP explainer returning top-5 feature contributions for human auditability.
   - Reference Profile (`ml/models/reference_profile.joblib`): Precomputed Kolmogorov-Smirnov and Population Stability Index (PSI) baseline extracted exclusively from the 70% chronological training split.
2. **Persistence Layer (`backend/app/db/`, `database/migrations/`):**
   - PostgreSQL 16 engine managed via SQLAlchemy 2.0 ORM with psycopg v3 driver.
   - Strictly enforced ledger immutability (`trg_predictions_immutable`) and referential deletion protection (`ON DELETE RESTRICT`).
   - Enforced retraining eligibility constraints (`ck_feedback_retraining_eligibility`).
3. **Application API (`backend/app/`):**
   - FastAPI framework exposing synchronous scoring, operator review queues, feedback adjudication, and batch drift evaluation.
   - PyJWT + native bcrypt authentication and role-based access control (RBAC).

---

## 2. Docker Services, Ports, Volumes, and Health Probes

### 2.1 Multi-Service Topology

| Service | Container Name | Base Image | Internal Port | Host Port | Mount / Volume | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Database** | `fraud_detection_db` | `postgres:16-alpine` | `5432` | `5433` | `fraud_detection_pgdata` $\rightarrow$ `/var/lib/postgresql/data` | Persistent transaction & prediction ledger |
| **Backend** | `fraud_detection_backend` | `frauddetection-backend:latest` | `8000` | `8000` | Stateless container running as non-root `appuser` | FastAPI REST API & ML inference engine |

### 2.2 Host Port Preservation
- **Host Port 5433:** Dedicated to Docker PostgreSQL (`fraud_detection_db`).
- **Host Port 5432:** Strictly preserved for native Windows PostgreSQL services without conflict.
- **Host Port 8000:** Published for external API access.

### 2.3 Health Probes
- **Liveness Probe (`GET /health/live`):** Verifies the API web server process is accepting connections. Returns `{"status": "ok", "service": "fraud-detection-api"}` with HTTP 200.
- **Readiness Probe (`GET /health/ready`):** Executes an active ping (`SELECT 1`) to the database. Returns `{"status": "ok", "database": "connected"}` with HTTP 200, or HTTP 503 if disconnected. Docker Compose uses this probe to gate backend readiness.

---

## 3. Environment Configuration & Safe Procedures

### 3.1 Environment Variables Template (`.env.example`)
*Never commit plaintext secrets or production keys.*

```bash
# Application Runtime
APP_ENV=development
APP_DEBUG=true
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# PostgreSQL Database (Host dev connects via 5433; Container backend connects via db:5432)
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

# Model Governance
MODEL_DIR=./ml/models
ACTIVE_MODEL_VERSION=xgb-cost-v1

# Cost-Sensitive Decision Policy Assumptions (Configured parameters, not validated financials)
COST_FALSE_NEGATIVE=100.00
COST_FALSE_POSITIVE=5.00
COST_OPERATOR_REVIEW=5.00
COST_BLOCK_FRICTION=50.00
MAX_REVIEW_CAPACITY_PCT=5.0
```

### 3.2 Safe Lifecycle Procedures

#### Starting the Stack
```powershell
# Start both PostgreSQL and FastAPI backend in background
docker compose up -d

# Verify service state and health status
docker compose ps
```

#### Stopping the Stack Safely
```powershell
# Stop services while strictly preserving database volume and container identity
docker compose stop
# or
docker compose down
# WARNING: NEVER run 'docker compose down -v' as this destroys the persistent volume!
```

---

## 4. Database Schema Governance & Alembic Migrations

### 4.1 Migration History
1. **`db1aec0b0a89` (`001_initial_schema`):** Creates core tables (`users`, `transactions`, `predictions`, `operator_feedback`, `audit_logs`, `drift_reports`, `model_registry`).
2. **`dc187c3ba103` (`002_feedback_and_drift_constraints`):**
   - Check constraint `ck_feedback_retraining_eligibility`: Enforces that feedback cannot be marked retraining-eligible unless `is_verified = TRUE` AND `decision IN ('CONFIRMED_FRAUD', 'CONFIRMED_GENUINE')`.
   - Check constraint `ck_drift_reports_time_window`: Enforces `time_window_end >= time_window_start`.
3. **`20b46b28f9db` (`003_prediction_ledger_immutability` - HEAD):**
   - Changes `predictions_transaction_id_fkey` constraint from `ON DELETE CASCADE` to `ON DELETE RESTRICT`.
   - Creates PL/pgSQL function `prevent_prediction_update_or_delete()` and attaches trigger `trg_predictions_immutable` (`BEFORE UPDATE OR DELETE ON predictions`).

### 4.2 Alembic Commands
```powershell
# Check current migration revision
.\.venv\Scripts\python.exe -m alembic current

# Upgrade database to head
.\.venv\Scripts\python.exe -m alembic upgrade head

# Inspect migration history
.\.venv\Scripts\python.exe -m alembic history --verbose
```

---

## 5. API Endpoints & Role-Based Access Control (RBAC)

| Method | Path | Required Role | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health/live` | Public | Process liveness check |
| `GET` | `/health/ready` | Public | Database connectivity readiness check |
| `GET` | `/api/v1/openapi.json` | Public | Complete OpenAPI v3.1 schema specification |
| `POST` | `/api/v1/auth/login` | Public | OAuth2 token exchange returning JWT Bearer token |
| `GET` | `/api/v1/auth/me` | Any Authenticated | Retrieve current user profile and role |
| `POST` | `/api/v1/transactions/predict` | `ANALYST`, `ADMIN` | Synchronous fraud scoring, SHAP generation, and atomic ledger insertion |
| `GET` | `/api/v1/transactions/review-queue`| `ANALYST`, `OPERATOR`, `ADMIN` | Paginated review queue sorted deterministically by recency |
| `POST` | `/api/v1/transactions/{id}/feedback` | `OPERATOR`, `ADMIN` | Submit operator feedback adjudication. Pre-verified feedback restricted to `ADMIN`. |
| `POST` | `/api/v1/monitoring/drift-reports` | `ADMIN` | Generate KS/PSI statistical drift report over a time window |
| `GET` | `/api/v1/monitoring/drift-reports` | `ANALYST`, `OPERATOR`, `ADMIN` | Paginated list of historical drift evaluations |
| `GET` | `/api/v1/monitoring/drift-reports/{id}`| `ANALYST`, `OPERATOR`, `ADMIN` | Retrieve single drift report and per-feature metric breakdown |

---

## 6. Machine Learning Pipeline & Statistical Methodology

### 6.1 Dataset Partitioning & Isolation
- **Dataset:** Credit Card Fraud Detection (284,807 total rows, 492 fraud cases, class imbalance 0.172%).
- **Chronological Split:** Preserves temporal causality without future-information leakage:
  - **Training Split (70%):** 199,368 rows, 384 fraud cases ($T \le 115,595$).
  - **Validation Split (15%):** 42,718 rows, 56 fraud cases ($115,595 < T \le 137,885$).
  - **Held-Out Test Split (15%):** 42,721 rows, 52 fraud cases ($T > 137,885$).
- **Test Set Isolation Safeguard:** The held-out test split was strictly untouched during model training, hyperparameter tuning, Platt/Isotonic calibration fitting, cost-threshold searches, and reference-profile generation.

### 6.2 Model Calibration & Validation Disclosure
- **Calibrator Fitting:** Platt scaling (logistic sigmoid) and Isotonic regression were fitted on the **Validation Split**.
- **Important Disclosure on In-Sample Validation Metrics:** The calibration error metrics reported in `xgboost_calibration_validation_report.json` (such as Isotonic ECE $\approx 5.4 \times 10^{-20}$) were evaluated on the same validation data on which the calibrators were fitted. Consequently, these metrics represent **in-sample goodness-of-fit**, NOT unbiased out-of-sample generalization.
- **Production Default:** Isotonic calibrator (`calibrator_isotonic.joblib`) is integrated with threshold policy ($t_{review} = 0.042$, $t_{block} = 0.75388$).

### 6.3 Explainability Limitations
- TreeSHAP explanations are computed dynamically for the top-5 feature contributions.
- **Operational Limitation:** SHAP values explain model attribution, not real-world causation. For PCA components $V1 \dots V28$, anonymized transformation limits actionable business interpretation beyond statistical anomaly detection.

---

## 7. Retraining Safeguards and Ledger Immutability

### 7.1 Prediction Ledger Immutability
1. **Trigger Enforcement (`trg_predictions_immutable`):** The PostgreSQL trigger immediately raises a SQL exception on any `UPDATE` or `DELETE` statement targeting the `predictions` table.
2. **Referential Integrity (`ON DELETE RESTRICT`):** Transactions referenced by a prediction cannot be deleted, preventing dangling ledger entries or orphaned historical records.

### 7.2 Feedback Retraining Safeguards
1. **Append-Only Feedback:** Each operator review appends a new record to `operator_feedback`. Repeated submissions increment sequence counters and flag conflicting decisions without mutating past audits.
2. **Two-Stage Verification:** Standard operators can only submit unverified feedback (`is_verified = FALSE`), which defaults to `is_eligible_for_retraining = FALSE`. Only `ADMIN` users can verify feedback.
3. **Database Check Constraint:** Even if an application bug attempts to insert an invalid state, PostgreSQL enforces:
   $$\text{is\_eligible\_for\_retraining} = \text{FALSE} \lor (\text{is\_verified} = \text{TRUE} \land \text{decision} \in \{\text{'CONFIRMED\_FRAUD'}, \text{'CONFIRMED\_GENUINE'}\})$$
   `DISPUTED` and `INCONCLUSIVE` records can NEVER be marked retraining-eligible under any circumstance.

---

## 8. Data Drift Monitoring & Reference Profile Governance

### 8.1 Reference Profile Integrity
- **Artifact:** `ml/models/reference_profile.joblib` (43.3 MB).
- **Origin:** Constructed exclusively from the 70% chronological training partition (`sample_count = 199,368`, version `training_v1_chronological_70`).
- **Feature Coverage:** All 30 canonical numeric features (`Time`, $V1 \dots V28$, `Amount`).
- **Container Inclusion:** Packaged directly into the Docker image, enabling real-time KS-test and PSI evaluation without shipping the 150MB raw CSV file.

### 8.2 Metric Semantics
- **Kolmogorov-Smirnov (KS) Test:** Detects continuous distribution shape divergence ($p < 0.01$ indicates drift).
- **Population Stability Index (PSI):** Quantifies bin shift across 10 empirical quantiles:
  - $\text{PSI} < 0.10$: Stable / No significant drift.
  - $0.10 \le \text{PSI} < 0.25$: Moderate drift (warning threshold).
  - $\text{PSI} \ge 0.25$: Significant drift (critical alert).
- **Empty / Low Sample Windows:** Gracefully handled by the API returning `status = "WARNING"` with descriptive notes rather than failing or crashing.

---

## 9. Automated Regression Testing & Verification Results

### 9.1 Test Execution Evidence
Automated regression test suite executed via Python 3.12 virtual environment:
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```
**Outcome:**
- **Total Tests:** 98
- **Passed:** 98
- **Failed:** 0
- **Skipped:** 0
- **Warnings:** 1 (scikit-learn LogisticRegression optimizer warning: `OptimizeWarning: Unknown solver options: iprint`)
- **Execution Time:** ~35.5 seconds

### 9.2 End-to-End Lifecycle Verification Evidence
Executed against live Docker Compose container API (`http://localhost:8000`) and PostgreSQL database (`localhost:5433`):
- Health probes (`/health/live`, `/health/ready`, `/openapi.json`): **PASSED**
- Authentication & RBAC enforcement (ADMIN, OPERATOR, ANALYST): **PASSED**
- Request schema validation (missing fields, extra fields, `Class` leakage, NaN): **PASSED**
- Transaction scoring & 3-way decision generation: **PASSED**
- Atomic database persistence: **PASSED**
- Trigger-enforced prediction immutability (UPDATE & DELETE rejected): **PASSED**
- Foreign key `ON DELETE RESTRICT` transaction protection: **PASSED**
- Review queue retrieval & deterministic ordering: **PASSED**
- Operator unverified feedback submission (`is_eligible = FALSE`): **PASSED**
- Admin feedback verification (`is_eligible = TRUE` for confirmed labels): **PASSED**
- `DISPUTED` and `INCONCLUSIVE` eligibility denial (`is_eligible = FALSE`): **PASSED**
- DB check constraint `ck_feedback_retraining_eligibility` SQL rejection: **PASSED**
- Empty window & batch drift report generation and retrieval: **PASSED**

---

## 10. Known Limitations and Production Hardening Notes

1. **Validation Re-use Disclosure:** Probability calibration models and cost-optimal thresholds were derived on the validation split. Metrics should be validated against ongoing live production streams using A/B testing or shadow deployments.
2. **Synchronous Drift Processing Limit:** Current drift evaluation processes up to 30 days synchronously. For enterprise-scale payment volume (>1M transactions/day), drift reporting should be offloaded to asynchronous Celery/Redis background workers.
3. **Local Backup vs Offsite Disaster Recovery:** Local backups stored on the host filesystem protect against accidental data corruption or application bugs, but do NOT constitute an offsite disaster recovery solution. Offsite replication and continuous WAL archiving remain required for full production deployment.

---

## 11. Database Backup, Recovery, and Disaster Recovery Governance

### 11.1 Local Backup Architecture and Specification
- **Tooling:** PostgreSQL native `pg_dump` custom format (`-F c`), executing within the existing database container `fraud_detection_db`.
- **Format:** Custom archive format (`-F c`), providing built-in gzip compression, blob support (`-b`), and selective table restoration via `pg_restore`.
- **Target Storage Location:** Host directory `C:\FraudDetection\backups\` (excluded from Git tracking via `.gitignore`).
- **Isolation:** Dump operations are initiated in container `/tmp/` (outside `/var/lib/postgresql/data`) and transferred binary-safely to the host via `docker cp`.

### 11.2 Exact Backup Command (Redacted Environment Variables)
*Never execute with plaintext passwords printed in console logs.*

```bash
# 1. Execute custom-format binary dump inside the running database container
docker exec fraud_detection_db sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c -b -f /tmp/fraud_db_backup_<TIMESTAMP>.dump'

# 2. Securely copy dump from container to host backups/ directory
docker cp fraud_detection_db:/tmp/fraud_db_backup_<TIMESTAMP>.dump ./backups/fraud_db_backup_<TIMESTAMP>.dump

# 3. Clean up container temporary dump file
docker exec fraud_detection_db rm -f /tmp/fraud_db_backup_<TIMESTAMP>.dump
```

Required environment variables (injected directly from `.env` / container environment):
- `POSTGRES_USER`: Database superuser username (`fraud_user`)
- `POSTGRES_PASSWORD`: Strong database password (placeholder: `<DATABASE_PASSWORD>`)
- `POSTGRES_DB`: Target production database name (`fraud_db`)

### 11.3 Checksum and Dump Integrity Verification
Every generated backup must be validated before being archived:

```powershell
# 1. Compute SHA-256 Checksum on the host
Get-FileHash -Path .\backups\fraud_db_backup_<TIMESTAMP>.dump -Algorithm SHA256

# 2. Inspect Table of Contents (TOC) using pg_restore without modifying any database
docker exec fraud_detection_db pg_restore --list /tmp/fraud_db_backup_<TIMESTAMP>.dump
# (or using local host pg_restore)
pg_restore.exe --list .\backups\fraud_db_backup_<TIMESTAMP>.dump
```
Verify that the output contains all expected tables (`users`, `transactions`, `predictions`, `operator_feedback`, `audit_logs`, `drift_reports`, `model_registry`, `alembic_version`), table data segments, functions (`prevent_prediction_update_or_delete`), triggers (`trg_predictions_immutable`), and foreign key constraints.

### 11.4 Safe Recovery Procedure (Live Database Protection)
**MANDATORY RULE:** Never restore directly over the active database (`fraud_db`). Always restore into an isolated staging target to verify schema and data integrity before considering service redirection.

```bash
# Step 1: Create an isolated temporary verification database
docker exec fraud_detection_db sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE fraud_db_restore_verify OWNER fraud_user;"'

# Step 2: Copy the dump into the container temporary space
docker cp ./backups/fraud_db_backup_<TIMESTAMP>.dump fraud_detection_db:/tmp/restore_verify.dump

# Step 3: Restore the dump into the isolated verification database
docker exec fraud_detection_db sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" -d fraud_db_restore_verify /tmp/restore_verify.dump'

# Step 4: Verify schema, Alembic revision, row counts, and triggers in the restored copy
docker exec fraud_detection_db sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d fraud_db_restore_verify -c "SELECT version_num FROM alembic_version; SELECT count(*) FROM predictions;"'

# Step 5: Clean up temporary verification resources
docker exec fraud_detection_db sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP DATABASE fraud_db_restore_verify;"'
docker exec fraud_detection_db rm -f /tmp/restore_verify.dump
```

### 11.5 Retention and Access-Control Recommendations
1. **Access Control:** Restrict read and write permissions on `backups/` to service administrators only (`chmod 600` / Windows NTFS restricted ACLs).
2. **Retention Policy:** Implement automated rotation:
   - Daily backups retained for 14 days.
   - Weekly backups retained for 8 weeks.
   - Monthly backups retained for 12 months.
3. **Encryption at Rest:** Ensure backup volumes are stored on encrypted block storage (LUKS, BitLocker, or AWS KMS-encrypted EBS/S3).

### 11.6 Local Backups vs. Offsite Disaster Recovery
| Dimension | Local Host Backup (`backups/`) | Production Offsite Disaster Recovery |
| :--- | :--- | :--- |
| **Storage Target** | Local host volume / disk | Geographically separated object store (e.g. AWS S3 Glacier, GCS) |
| **RPO (Recovery Point Objective)** | Periodic (e.g. 24 hours between dumps) | Continuous (Point-in-Time Recovery via WAL-G / pgBackRest) |
| **RTO (Recovery Time Objective)** | Dependent on full database restore time | Fast automated snapshot hydration |
| **Host Failure Protection** | **NONE** (destroyed if host drive or Docker host fails) | **FULL** (resilient against total host or regional failure) |
| **Ransomware Protection** | Vulnerable if host filesystem is compromised | Protected via immutable / WORM bucket retention policies |

### 11.7 Verification Status of Recovery Steps
- **Actually Tested & Empirically Verified:**
  - Non-destructive execution of custom-format `pg_dump` on live PostgreSQL 16 container.
  - Safe binary transfer to host `backups/` directory outside container storage.
  - Verification of non-empty dump size (133.22 KB) and SHA-256 checksum integrity.
  - Verification of Table of Contents via `pg_restore --list`.
  - Zero disruption of live database during backup (all table row counts identical before and after).
  - Isolated creation of `fraud_db_restore_verify` without touching `fraud_db`.
  - Full restore of custom dump into `fraud_db_restore_verify` (exit code 0).
  - Exact match of Alembic revision (`20b46b28f9db`) and row counts across all 7 core tables.
  - Functional verification of `trg_predictions_immutable` trigger blocking UPDATE/DELETE in restored database.
  - Functional verification of foreign key `ON DELETE RESTRICT` blocking transaction deletion in restored database.
  - Functional verification of `ck_feedback_retraining_eligibility` blocking invalid feedback states in restored database.
  - Clean teardown and dropping of `fraud_db_restore_verify`.
- **Unverified & Remaining for Production Hardening:**
  - Continuous Write-Ahead Log (WAL) archiving and Point-in-Time Recovery (PITR) to a remote storage bucket.
  - Multi-region replication and automated failover orchestration.
  - Restoration tests under extreme high-concurrency database load.
