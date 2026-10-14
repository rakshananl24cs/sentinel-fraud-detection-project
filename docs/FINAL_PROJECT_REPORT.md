# Cost-Sensitive Fraud Detection System
## Final Project Technical Report and Architecture Handover

**Document Version:** 1.0.0  
**Date:** 2026-10-12  
**Workspace:** `C:\FraudDetection`  
**System Classification:** Pre-Production / Staging Prototype  
**Active Model Version:** `xgb-cost-v1`  
**Database Schema Head:** Alembic Revision `20b46b28f9db`

---

## Executive Summary

The **Cost-Sensitive Fraud Detection System** is an end-to-end machine learning and software engineering solution designed to evaluate, triage, and monitor credit card transaction fraud in high-frequency payment streams.

Unlike traditional machine learning systems that optimize symmetric classification metrics such as F1-score or accuracy, this system operationalizes a **cost-sensitive decision framework**. In real-world financial fraud, the cost of a false negative (missed fraud resulting in stolen funds and chargeback fees) is substantially higher than the cost of a false positive (customer inconvenience or manual review fee). 

The platform integrates:
1. An **extreme gradient boosting (XGBoost) classifier** with probability calibration and cost-minimizing three-way triage (`APPROVE`, `REVIEW`, `BLOCK`).
2. An explainability engine leveraging **TreeSHAP** to compute feature attributions for human investigators.
3. A production-ready **FastAPI** backend with JWT authentication and strict role-based access control (RBAC).
4. A **PostgreSQL 16** persistence layer featuring trigger-enforced immutable prediction ledgers and database-level retraining eligibility constraints.
5. An automated **statistical data drift detector** utilizing Kolmogorov-Smirnov (KS) tests and Population Stability Index (PSI) against a frozen training reference baseline.
6. Container orchestration via **Docker Compose**, preserving development environments on native Windows host ports.
7. A verified local **backup and recovery procedure** ensuring data safety without modifying live database states.

---

## 1. Problem Statement and Objectives

### 1.1 The Challenge of Payment Fraud Detection
Financial institutions process millions of daily card transactions where fraud prevalence is extremely low (typically $< 0.2\%$). Naive machine learning models optimizing standard cross-entropy or symmetric metrics often fail in production because:
- **Severe Class Imbalance:** Models default to predicting genuine transactions to maximize accuracy.
- **Asymmetric Financial Losses:** Missing a \$500 fraud costs \$500 plus operational penalties, whereas flagging a genuine cardholder costs a \$5.00 phone verification or minor friction.
- **Human Review Constraints:** Fraud investigation teams have finite daily queue capacity (typically $\le 5\%$ of total transaction flow). An algorithm routing too many borderline transactions overwhelms human operators.
- **Feedback Loops and Contamination:** Unverified or disputed customer chargebacks can corrupt retraining sets if ingested prematurely into future model iterations.
- **Data Distribution Drift:** Fraud patterns evolve rapidly due to adversarial adaptation, requiring continuous statistical monitoring of transaction distributions.

### 1.2 Core System Objectives
- **Cost-Optimal Three-Way Routing:** Route each transaction to `APPROVE`, `REVIEW`, or `BLOCK` to minimize total expected financial cost under investigator capacity constraints.
- **Strict Ledger Immutability:** Guarantee through database triggers that once a transaction is scored, its historical prediction cannot be modified or deleted.
- **Auditable Operator Feedback:** Enforce two-stage feedback adjudication where only verified labels can enter candidate pools for model retraining.
- **Safe Architecture Coexistence:** Run containerized services on Docker host port `5433` while protecting native Windows PostgreSQL services running on port `5432`.
- **Reproducible Verification:** Ensure all evaluations, test suites, and backups can be verified non-destructively.

---

## 2. Dataset and Partitioning Methodology

### 2.1 Dataset Profile
The system is built upon the standard European Cardholder Credit Card Fraud Detection benchmark:
- **Total Transactions:** 284,807 transactions recorded over two days in September 2013.
- **Fraud Instances:** 492 cases (0.1727% fraud prevalence; 578:1 class imbalance).
- **Features:** 30 numeric features consisting of:
  - `Time`: Elapsed seconds since initial recording.
  - `V1` through `V28`: Anonymized principal components resulting from PCA transformation.
  - `Amount`: Transaction monetary amount.
  - `Class`: Binary ground-truth target (0 = Genuine, 1 = Fraud). *Strictly excluded from inference payloads.*

### 2.2 Chronological Partitioning
To reflect true production deployment and prevent temporal look-ahead leakage, the dataset was split chronologically rather than through random shuffling:

| Partition | Time Range ($T$ in seconds) | Row Count | Percentage | Fraud Cases | Partition Fraud Rate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Training Split** | $T \le 115,595$ | 199,368 | 70.0% | 384 | 0.1926% |
| **Validation Split** | $115,595 < T \le 137,885$ | 42,718 | 15.0% | 56 | 0.1311% |
| **Held-Out Test Split** | $T > 137,885$ | 42,721 | 15.0% | 52 | 0.1217% |

### 2.3 Strict Test Partition Isolation
**Research Integrity Safeguard:** The held-out test split (42,721 rows) was strictly quarantined throughout all development phases:
- It was never used for training baseline models or the primary XGBoost classifier.
- It was never accessed for hyperparameter tuning.
- It was never used to fit Platt scaling or Isotonic probability calibrators.
- It was never used to optimize cost thresholds ($t_{review}, t_{block}$).
- It was never included in the monitoring reference profile.

---

## 3. Data Preprocessing and Model Development

### 3.1 Preprocessing Pipeline (`ml/src/preprocessing/`)
- **Amount Standardization:** `Amount` feature is standardized using `StandardScaler` fitted exclusively on training data.
- **PCA Pass-Through:** Pre-transformed features $V1 \dots V28$ are validated for numeric bounds and preserved.
- **Time Elapsed Handling:** `Time` is converted to float seconds and checked for non-negative values.
- **Serialization:** Preprocessing parameters are serialized to [`ml/models/preprocessor.joblib`](file:///C:/FraudDetection/ml/models/preprocessor.joblib) (1,625 bytes).

### 3.2 Baseline Models (`ml/src/models/baselines.py`)
Two reference baseline models were trained on the training partition and evaluated on the validation partition:
1. **Balanced Logistic Regression:** Fitted with `class_weight='balanced'`, `max_iter=1000`, `solver='lbfgs'`.
2. **Balanced Decision Tree:** Fitted with `max_depth=6`, `min_samples_split=20`, `min_samples_leaf=10`.

### 3.3 Primary Model: Extreme Gradient Boosting (`xgb-cost-v1`)
The primary model is an XGBoost binary classifier (`XGBClassifier`) tuned for class imbalance:
- **Class Compensation:** `scale_pos_weight = 518.1875` (ratio of genuine to fraudulent samples in training partition).
- **Hyperparameters:** `n_estimators = 300`, `max_depth = 6`, `learning_rate = 0.05`, `subsample = 0.8`, `colsample_bytree = 0.8`, `objective = binary:logistic`, `eval_metric = logloss`.
- **Artifact:** Serialized to [`ml/models/xgboost_baseline.joblib`](file:///C:/FraudDetection/ml/models/xgboost_baseline.joblib) (806,662 bytes).

---

## 4. Probability Calibration & Methodological Disclosure

### 4.1 Calibration Rationale
Raw margins from gradient boosted trees with `scale_pos_weight` are heavily distorted and do not reflect true posterior probabilities $P(Y=1 \mid X)$. For cost-sensitive threshold optimization to be mathematically valid, raw outputs must be mapped to calibrated probabilities.

Two calibration techniques were evaluated on the validation split:
1. **Platt Scaling (Logistic Sigmoid):** Parametric logistic regression fitted to raw model decision margins.
2. **Isotonic Regression:** Non-parametric, monotonically increasing step function.

### 4.2 Empirical Calibration Comparison (Validation Split: 42,718 rows)

| Model Variant | Brier Score | Expected Calibration Error (ECE) | Precision | Recall | F1-Score | PR-AUC | ROC-AUC |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Uncalibrated XGBoost** | 0.0003289 | 0.0001515 | 0.9362 | 0.7857 | 0.8544 | 0.8479 | 0.9869 |
| **Platt Scaled XGBoost** | 0.0003264 | 0.0000911 | 0.9565 | 0.7857 | 0.8627 | 0.8479 | 0.9869 |
| **Isotonic Calibrated XGBoost** | **0.0002885** | **$5.41 \times 10^{-20}$** | **0.9778** | **0.7857** | **0.8713** | **0.8449** | **0.9903** |

### 4.3 Methodological Disclosure on Validation Re-Use
> [!IMPORTANT]
> **Explicit Research Disclosure:** The calibration models (`calibrator_isotonic.joblib` and `calibrator_platt.joblib`) were fitted on the **Validation Split** ($N = 42,718$), and the calibration metrics in `xgboost_calibration_validation_report.json` were evaluated on that **same validation split**.
> 
> Consequently, the near-zero ECE achieved by Isotonic regression ($5.41 \times 10^{-20}$) represents an **in-sample goodness-of-fit artifact** of non-parametric isotonic fitting, rather than unbiased out-of-sample generalization. While Isotonic calibration was selected for production integration due to superior Brier Score (0.0002885 vs 0.0003264) and minimum operational cost, out-of-sample calibration error must be re-evaluated on continuous production streams.

---

## 5. Cost-Sensitive Decision Policy & Three-Way Routing

### 5.1 Cost Matrix Formulation
Decisions are evaluated against asymmetric operational costs rather than uniform misclassification counts:

$$\text{Total Cost} = C_{FN} \cdot FN + C_{FP} \cdot FP_{block} + C_{Review} \cdot N_{review} + (1 - \gamma) \cdot C_{FN} \cdot FN_{review} + C_{Friction} \cdot FP_{block}$$

Configured research parameters (provisional baseline assumptions):
- **$C_{FN} = \$100.00$:** Direct financial loss from undetected fraudulent charge.
- **$C_{FP} = \$5.00$:** Customer friction and support inquiry cost from false positive block.
- **$C_{Review} = \$5.00$:** Human fraud analyst salary and triage operational cost per review.
- **$C_{Friction} = \$50.00$:** Churn risk penalty for outright blocking a high-value genuine customer.
- **Review Efficiency $\gamma = 1.0$:** Probability that a human investigator correctly catches fraud in review queue.
- **Maximum Review Capacity = $5.0\%$:** Hard operational constraint on daily review queue volume.

### 5.2 Optimization Results on Validation Split (42,718 Transactions)

| Decision Policy Variant | Review Threshold ($t_{rev}$) | Block Threshold ($t_{block}$) | Total Cost | Cost per Transaction | Review Rate | Reviews Triggered |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Uncalibrated XGBoost** | 0.04400 | 0.95367 | \$1,105.00 | \$0.02587 | 0.0960% | 41 |
| **Platt Scaled XGBoost** | 0.04900 | 0.93551 | \$1,105.00 | \$0.02587 | 0.0960% | 41 |
| **Isotonic Calibrated XGBoost** | **0.04200** | **0.75388** | **\$1,095.00** | **\$0.02563** | **0.0913%** | **39** |

**Integrated Policy:** Isotonic calibration with thresholds $t_{review} = 0.042$ and $t_{block} = 0.75388$ was integrated as active production policy:
- $P(\text{Fraud}) < 0.042 \implies \mathbf{APPROVE}$ (Cost: \$0.00)
- $0.042 \le P(\text{Fraud}) < 0.75388 \implies \mathbf{REVIEW}$ (Routes to Operator Queue)
- $P(\text{Fraud}) \ge 0.75388 \implies \mathbf{BLOCK}$ (Automated Rejection)

---

## 6. Model Explainability & SHAP Limitations

### 6.1 TreeSHAP Implementation
The scoring engine generates dynamic TreeSHAP explanations for every scored transaction using `shap.TreeExplainer`:
- Calculates base value (expected log-odds across background data).
- Extracts top-5 features contributing positively (risk-increasing) or negatively (risk-decreasing) to the prediction.
- Persists explanation vectors directly into `predictions.explanation_json`.

### 6.2 Technical Limitations of Explanations
1. **Attribution vs. Causation:** SHAP values represent model feature attribution within the gradient boosted trees; they do not establish real-world causal fraud mechanisms.
2. **Anonymized Feature Semantics:** Because features $V1$ through $V28$ are anonymized PCA components, human operators cannot easily map statistical shifts (e.g., $V14 < -4.2$) to tangible merchant categories or customer behaviors without upstream PCA inversion matrices.

---

## 7. Backend Architecture, Database, and Security

### 7.1 Backend Architecture
Implemented in Python 3.12 using **FastAPI** with asynchronous concurrency, Pydantic v2 data validation, and SQLAlchemy 2.0 ORM.

### 7.2 Security and Role-Based Access Control (RBAC)
- **Authentication:** OAuth2 Password Bearer flow returning signed HMAC-SHA256 JWT tokens.
- **Password Governance:** Salted password hashing via native Rust/C `bcrypt` (12 rounds) strictly enforcing a 72-byte truncation boundary.
- **Role Permissions Matrix:**

| Role | Scoring (`/predict`) | Review Queue (`/review-queue`) | Feedback Submission (`/feedback`) | Feedback Verification | Drift Trigger (`POST /drift`) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **ADMIN** | Yes | Yes | Yes | **Yes** | **Yes** |
| **OPERATOR** | No | Yes | Yes (Unverified only) | No | No |
| **ANALYST** | Yes | Yes | No | No | Read-only (`GET`) |

### 7.3 Database Persistence & Safeguards (PostgreSQL 16)
- **Head Migration:** `20b46b28f9db` (`003_prediction_ledger_immutability`).
- **Strict Ledger Immutability:** PL/pgSQL trigger `trg_predictions_immutable` (`BEFORE UPDATE OR DELETE ON predictions`) strictly raises SQL exceptions on any mutation attempt.
- **Referential Deletion Protection:** Foreign key `predictions_transaction_id_fkey` enforces `ON DELETE RESTRICT`, preventing transaction row deletion once scored.
- **Two-Stage Retraining Safeguards:** Check constraint `ck_feedback_retraining_eligibility` guarantees that `is_eligible_for_retraining` can only be `TRUE` when `is_verified = TRUE` AND `decision IN ('CONFIRMED_FRAUD', 'CONFIRMED_GENUINE')`. Disputed or inconclusive labels can never contaminate training data.

---

## 8. Data Drift Monitoring & Reference Profile

### 8.1 Drift Detection Architecture (`ml/src/monitoring/drift_detector.py`)
- **Reference Profile:** Serialized into [`ml/models/reference_profile.joblib`](file:///C:/FraudDetection/ml/models/reference_profile.joblib) (43,377,468 bytes).
- **Baseline Sample Origin:** Extracted exclusively from the 199,368 training rows ($T \le 115,595$).
- **Statistical Tests:**
  - **Kolmogorov-Smirnov (KS):** 2-sample test for continuous distribution divergences ($p < 0.01$).
  - **Population Stability Index (PSI):** Quantile-based shift metric across 10 empirical bins:
    - $\text{PSI} < 0.10 \implies \text{NORMAL}$
    - $0.10 \le \text{PSI} < 0.25 \implies \text{WARNING}$
    - $\text{PSI} \ge 0.25 \implies \text{CRITICAL}$
- **Persistence:** Full report JSON, maximum feature PSI, and overall status are persisted to `drift_reports` table.

---

## 9. Frontend Architecture and Status

### 9.1 Frontend Inspection Findings
The frontend directory [`frontend/`](file:///C:/FraudDetection/frontend/) contains a standard Vite + React project scaffold:
- Dependencies installed: `react`, `react-dom`, `vite`.
- Source entry points: `frontend/src/main.jsx`, `frontend/src/App.jsx`.

### 9.2 Status of User Interface
> [!NOTE]
> **Implementation Clarification:** Inspection of `frontend/src/App.jsx` confirms that the frontend currently contains the **default Vite + React starter template**. Custom UI pages (e.g., operator triage queues, manual feedback forms, live transaction input forms, and drift monitoring dashboards) have **not yet been implemented**. All application workflows currently operate via the validated FastAPI REST API and OpenAPI endpoints.

---

## 10. Containerization, Backup, and Recovery

### 10.1 Docker Compose Services
- `fraud_detection_db`: `postgres:16-alpine` on host port `5433` (container port `5432`), attached to persistent volume `fraud_detection_pgdata`.
- `fraud_detection_backend`: `frauddetection-backend:latest` running non-root `appuser` on host port `8000`.
- Native Windows PostgreSQL service preserved on host port `5432` without collision.

### 10.2 Local Backup and Verified Recovery
- **Backup Created:** `backups/fraud_db_backup_20261012_102508.dump` (133.22 KB, SHA-256 `1dcbce11fed17f4f51c390a293739abbce4b22522c6a70278a38a47916867e52`).
- **Recovery Tested:** Restored into an isolated temporary database `fraud_db_restore_verify`. All 7 core tables, 411 users, 336 transactions, 248 predictions, Alembic head `20b46b28f9db`, and triggers were 100% verified before clean teardown.
- **Disaster Recovery Limitation:** This is a **local host backup**. Production deployment requires automated offsite archiving.

---

## 11. Testing and Verification Summary

Automated regression suite executed via:
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

**Results:**
- **Total Tests:** 98
- **Passed:** 98 (100%)
- **Failed:** 0
- **Skipped:** 0
- **Warnings:** 1 (scikit-learn `OptimizeWarning: Unknown solver options: iprint`)
- **Execution Time:** ~35.5 seconds

---

## 12. Known Limitations & Future Work

1. **Frontend Implementation:** Complete React UI dashboard integrating review queues and drift visualization.
2. **Asynchronous Drift Queue:** Migrate 30-day drift evaluation to background Celery workers for transaction volumes exceeding 1M records/day.
3. **Offsite WAL Archiving:** Implement continuous WAL replication (e.g., pgBackRest / WAL-G to AWS S3) for enterprise disaster recovery.
4. **Out-of-Sample Calibration:** Re-validate probability calibration on fresh streaming batches rather than validation split.
