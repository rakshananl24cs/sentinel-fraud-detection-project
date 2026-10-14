# Presentation & Demonstration Outline
## Cost-Sensitive Credit Card Fraud Detection with Immutable Ledger & Drift Governance

**Presentation Context:** Academic Defense / Engineering Capstone / Technical Demonstration  
**Target Duration:** 15–20 minutes + Q&A  
**Project Workspace:** `C:\FraudDetection`  
**Active Model:** `xgb-cost-v1` (Calibrated XGBoost)  
**Database Schema Head:** Alembic Revision `20b46b28f9db`

---

## Slide 1: Title and Overview
- **Title:** End-to-End Cost-Sensitive Fraud Detection with Ledger Immutability and Statistical Drift Monitoring
- **Speaker / Team:** Machine Learning & Systems Engineering
- **Core Thesis:** Why symmetric ML metrics (accuracy, F1) fail in financial fraud, and how integrating asymmetric financial loss matrices, probability calibration, immutable database triggers, and statistical drift detection delivers an audit-compliant, operationally viable fraud system.

---

## Slide 2: Problem Formulation & The Asymmetric Loss Reality
- **Class Imbalance in Financial Payments:** 284,807 transactions, 492 fraud cases (0.17% prevalence; 578:1 ratio).
- **The Financial Asymmetry:**
  - Standard ML treats False Positives and False Negatives equally.
  - In banking, False Negatives cost stolen funds (\$100+), while False Positives cost minor operational friction (\$5.00).
- **Human Capacity Bottlenecks:** Human fraud investigation teams have strict daily review budgets (capped at $\le 5\%$ of total transaction flow).
- **Three-Way Routing Paradigm:**
  - $\mathbf{APPROVE}$: Low risk $\implies$ automated instant settlement.
  - $\mathbf{REVIEW}$: Borderline uncertainty $\implies$ human investigator queue.
  - $\mathbf{BLOCK}$: Critical risk $\implies$ automated transaction rejection.

---

## Slide 3: Chronological Splitting & Research Integrity
- **Temporal Causality:** Financial data cannot be randomly shuffled due to time-series dependencies and concept evolution.
- **Split Breakdown:**
  - **Training (70%):** 199,368 rows ($T \le 115,595$ s), 384 fraud cases.
  - **Validation (15%):** 42,718 rows ($115,595 < T \le 137,885$ s), 56 fraud cases.
  - **Held-Out Test (15%):** 42,721 rows ($T > 137,885$ s), 52 fraud cases.
- **Strict Isolation Safeguard:** The held-out test split was strictly quarantined—never accessed for training, calibration fitting, threshold selection, or drift baselines.

---

## Slide 4: Modeling & Probability Calibration
- **Primary Model:** XGBoost classifier with `scale_pos_weight = 518.19` (class ratio compensation).
- **The Need for Calibration:** Boosted tree margins with class weighting produce distorted probabilities that violate posterior probabilities $P(Y=1 \mid X)$.
- **Empirical Results (Validation Partition):**
  - **Uncalibrated XGBoost:** Brier Score: 0.000329, ECE: 0.000152, Precision: 93.6%, Recall: 78.6%.
  - **Platt Scaling (Sigmoid):** Brier Score: 0.000326, ECE: 0.000091, Precision: 95.7%, Recall: 78.6%.
  - **Isotonic Calibration:** Brier Score: **0.000289**, ECE: **$5.4 \times 10^{-20}$**, Precision: **97.8%**, Recall: 78.6%.
- **Methodological Disclosure:** Isotonic calibrator was fitted on the validation split; its near-zero ECE represents an in-sample fit artifact, clearly disclosed in documentation.

---

## Slide 5: Cost-Sensitive Optimization & Decision Thresholds
- **Cost Formulation:**
  $$\text{Total Cost} = C_{FN} \cdot FN + C_{FP} \cdot FP_{block} + C_{Review} \cdot N_{rev} + C_{Friction} \cdot FP_{block}$$
- **Parameters:** $C_{FN}=\$100.00$, $C_{FP}=\$5.00$, $C_{Review}=\$5.00$, $C_{Friction}=\$50.00$, Capacity Cap $= 5.0\%$.
- **Validation Optimization Results:**
  - **Isotonic Policy:** $t_{review} = 0.042$, $t_{block} = 0.75388$.
  - **Total Cost:** **\$1,095.00** across 42,718 transactions (\$0.0256 per transaction).
  - **Review Rate:** 0.0913% (39 transactions reviewed), comfortably within the 5.0% operational ceiling.

---

## Slide 6: Model Explainability (TreeSHAP)
- **Investigation Triage:** Review queue returns top-5 SHAP feature contributions for each transaction.
- **Technical Limitations Disclosed:**
  - Explanations describe model attribution, not causal mechanics.
  - PCA anonymization ($V1 \dots V28$) restricts operational interpretability without upstream inversion tables.

---

## Slide 7: Software Architecture & Docker Orchestration
- **FastAPI Core:** Asynchronous REST API, Pydantic v2 schemas, JWT authentication, and RBAC (`ADMIN`, `OPERATOR`, `ANALYST`).
- **PostgreSQL 16 Layer:** SQLAlchemy 2.0 with Alembic migrations (`20b46b28f9db`).
- **Port Isolation & Preservation:**
  - Container PostgreSQL runs on host port **5433**.
  - Host port **5432** strictly preserved for native Windows PostgreSQL.
  - Backend API accessible on host port **8000**.
- **Container Health Probes:** Automated container health checks via `/health/ready` (database ping).

---

## Slide 8: Data Governance, Immutability & Retraining Safeguards
- **Immutable Prediction Ledger:** PostgreSQL trigger `trg_predictions_immutable` rejects all `UPDATE` and `DELETE` queries on `predictions`.
- **Foreign Key Protection:** `predictions_transaction_id_fkey` enforces `ON DELETE RESTRICT`, preventing transaction record deletion.
- **Two-Stage Operator Feedback:**
  - Operators submit unverified feedback $\implies$ `is_eligible_for_retraining = FALSE`.
  - Only `ADMIN` verification can grant retraining eligibility.
  - Database check constraint `ck_feedback_retraining_eligibility` guarantees that `DISPUTED` and `INCONCLUSIVE` labels can never be flagged as retraining-eligible.

---

## Slide 9: Statistical Data Drift Detection
- **Frozen Reference Baseline:** Precomputed profile (`reference_profile.joblib`, 43.3 MB) derived strictly from 199,368 training rows.
- **Metrics Evaluated:**
  - **Kolmogorov-Smirnov Test:** Identifies continuous feature distribution shifts ($p < 0.01$).
  - **Population Stability Index (PSI):** 10-bin quantile comparison ($<0.10$ Normal, $0.10–0.25$ Warning, $>0.25$ Critical).
- **Operational Handling:** Zero-transaction and low-sample observation windows return safe `WARNING` reports without system failure.

---

## Slide 10: Live Demonstration Sequence (Step-by-Step Script)

### Step 1: Verify System Health
```powershell
curl.exe http://localhost:8000/health/live
curl.exe http://localhost:8000/health/ready
```
*Expected:* Both return status `ok` with database `connected`.

### Step 2: Authenticate and Acquire JWT Token
```powershell
# Exchange analyst credentials for bearer access token
$resp = Invoke-RestMethod -Uri http://localhost:8000/api/v1/auth/login -Method Post -Body '{"email":"analyst@bank.internal","password":"SecurePassword123!"}' -ContentType "application/json"
$token = $resp.access_token
$headers = @{ Authorization = "Bearer $token" }
```

### Step 3: Score Real-Time Transaction
```powershell
# Submit synthetic transaction with 30 numeric features
$body = '{"Time":1000.0, "V1":-1.35, "V2":2.1, "V3":-1.8, "V4":3.2, "Amount":250.0, ...}'
$score = Invoke-RestMethod -Uri http://localhost:8000/api/v1/transactions/predict -Method Post -Body $body -Headers $headers -ContentType "application/json"
$score | Select-Object transaction_id, decision, risk_level, fraud_probability, expected_cost
```
*Expected:* Returns HTTP 201 with calibrated probability, three-way decision (`APPROVE`/`REVIEW`/`BLOCK`), expected cost, and top-5 SHAP explanations.

### Step 4: Demonstrate Trigger-Enforced Ledger Immutability
```powershell
# Attempt direct SQL UPDATE on the newly created prediction
docker exec fraud_detection_db psql -U fraud_user -d fraud_db -c "UPDATE predictions SET decision = 'BLOCK' WHERE id = '$($score.prediction_id)';"
```
*Expected:* Fails with SQL exception: `Prediction records are immutable: UPDATE operations on predictions are prohibited`.

### Step 5: Operator Review Queue & Adjudication
```powershell
# Retrieve active review queue
Invoke-RestMethod -Uri http://localhost:8000/api/v1/transactions/review-queue -Method Get -Headers $headers
```
*Expected:* Returns pending borderline transactions sorted by recency.

### Step 6: Generate Automated Data Drift Report
```powershell
# Trigger drift report evaluation over recent window
$driftBody = '{"time_window_start":"2026-10-01T00:00:00Z","time_window_end":"2026-10-12T00:00:00Z","model_version":"xgb-cost-v1"}'
Invoke-RestMethod -Uri http://localhost:8000/api/v1/monitoring/drift-reports -Method Post -Body $driftBody -Headers $headers -ContentType "application/json"
```
*Expected:* Computes KS and PSI metrics across all 30 features against the frozen training reference profile.

---

## Slide 11: System Verification & Backup Testing
- **Automated Regression Suite:** 98 passed, 0 failed, 1 benign warning across 35.5 seconds.
- **Local Backup Verified:** Custom-format binary backup (`pg_dump -F c`) generated to `backups/` (133.22 KB, SHA-256 verified).
- **Isolated Restore Tested:** Dump successfully restored into `fraud_db_restore_verify`. All 411 users, 336 transactions, 248 predictions, Alembic head `20b46b28f9db`, and triggers matched 100%.

---

## Slide 12: Project Limitations and Production Roadmap
- **Frontend Status:** React dashboard scaffolded; custom UI pages (queue triage, drift plots) remain unimplemented.
- **Monitoring Scalability:** 30-day drift evaluation currently runs synchronously; offload to Celery/Redis for enterprise scale ($>1\text{M}$ tx/day).
- **Disaster Recovery:** Current backup is local host storage; automated continuous WAL replication to offsite cloud storage required for commercial SLA.
- **Out-of-Sample Calibration:** Re-validate probability calibration continuously on live streaming traffic.

---

## Slide 13: Summary & Conclusion
- Successfully operationalized a **cost-sensitive machine learning architecture** prioritizing business financial losses over naive statistical accuracy.
- Enforced **rigorous persistence safeguards** including immutable prediction ledgers and strict feedback retraining barriers.
- Delivered a **reproducible, tested staging prototype** ready for shadow pre-production deployment.
