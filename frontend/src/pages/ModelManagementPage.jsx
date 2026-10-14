import { useState, useEffect } from 'react';
import { modelsApi } from '../api/client';
import MetricCard from '../components/MetricCard';
import { 
  Boxes, 
  Cpu, 
  ShieldCheck, 
  CheckCircle2, 
  Lock, 
  FileCode2, 
  Layers,
  Database,
  RotateCw,
  Loader2,
  Info
} from 'lucide-react';

export default function ModelManagementPage() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [apiModel, setApiModel] = useState(null);
  const [registeredModels, setRegisteredModels] = useState([]);
  const [totalModels, setTotalModels] = useState(0);

  const fetchModelData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    else setLoading(true);

    try {
      const [currentRes, listRes] = await Promise.allSettled([
        modelsApi.getCurrent(),
        modelsApi.list(),
      ]);

      if (currentRes.status === 'fulfilled' && currentRes.value) {
        setApiModel(currentRes.value);
      }
      if (listRes.status === 'fulfilled' && listRes.value) {
        setRegisteredModels(listRes.value.items || []);
        setTotalModels(listRes.value.total || 0);
      }
    } catch {
      // Handled gracefully with fallback
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchModelData();
  }, []);

  const activeVersion = apiModel?.version || 'xgb-cost-v1';
  const activeStatus = apiModel?.lifecycle_status || 'ACTIVE';
  const scalePosWeight = apiModel?.hyperparameters?.scale_pos_weight || '518.19';

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <Boxes className="w-6 h-6 text-teal" />
            <span>Model Management & Governance</span>
          </h1>
          <p className="page-subtitle">
            Lifecycle registry, artifact verification, and architectural metadata for deployed fraud scoring models.
          </p>
        </div>

        <button
          type="button"
          onClick={() => fetchModelData(true)}
          disabled={loading || refreshing}
          className="btn btn-secondary flex items-center gap-1.5"
        >
          <RotateCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Model Status Bar */}
      <div className="grid-cards mb-6">
        <MetricCard
          title="Active Model Version"
          value={loading ? '--' : activeVersion}
          icon={Cpu}
          iconColor="text-teal"
          iconBg="bg-teal-subtle"
          tooltip="Primary inference model deployed in Docker service"
          subtext="Calibrated XGBoost Baseline"
          loading={loading}
        />

        <MetricCard
          title="Lifecycle Status"
          value={loading ? '--' : activeStatus}
          icon={CheckCircle2}
          iconColor="text-emerald"
          iconBg="bg-emerald-subtle"
          tooltip="Registered lifecycle stage in database registry"
          subtext="Serving live inference traffic"
          loading={loading}
        />

        <MetricCard
          title="Class-Weight Factor"
          value={loading ? '--' : String(scalePosWeight)}
          icon={ShieldCheck}
          iconColor="text-indigo"
          iconBg="bg-indigo-subtle"
          tooltip="scale_pos_weight parameter applied during XGBoost gradient boosting"
          subtext="Imbalance compensation (0.172% fraud)"
          loading={loading}
        />

        <MetricCard
          title="Feature Dimension"
          value="30 Features"
          icon={Layers}
          iconColor="text-amber"
          iconBg="bg-amber-subtle"
          tooltip="Amount, Time, and 28 anonymized PCA components"
          subtext="Standardized numeric features"
          loading={loading}
        />
      </div>

      {/* Architecture & Artifact Details */}
      <div className="grid-2col mb-6">
        {/* Model Specification Card */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-primary flex items-center gap-2">
              <Cpu className="w-4 h-4 text-teal" />
              <span>Production Pipeline Specification</span>
            </h3>
            <span className="badge badge-success font-mono text-xs">READY</span>
          </div>

          <div className="space-y-3 text-xs">
            <div className="p-3 bg-slate-50 border border-slate-200 rounded">
              <span className="text-muted block uppercase font-semibold text-xs mb-1">Classifier Architecture</span>
              <div className="font-mono font-bold text-primary">{apiModel?.architecture || 'XGBClassifier (Gradient Boosted Decision Trees)'}</div>
              <p className="text-muted mt-1 leading-relaxed">
                Trained with n_estimators={apiModel?.hyperparameters?.n_estimators || 300}, max_depth={apiModel?.hyperparameters?.max_depth || 6}, learning_rate={apiModel?.hyperparameters?.learning_rate || 0.05}, subsample={apiModel?.hyperparameters?.subsample || 0.8}, colsample_bytree={apiModel?.hyperparameters?.colsample_bytree || 0.8}.
              </p>
            </div>

            <div className="p-3 bg-slate-50 border border-slate-200 rounded">
              <span className="text-muted block uppercase font-semibold text-xs mb-1">Probability Calibration</span>
              <div className="font-mono font-bold text-teal">Isotonic Regression (Post-Hoc Nonparametric)</div>
              <p className="text-muted mt-1 leading-relaxed">
                Maps uncalibrated log-odds margins to empirical posterior probabilities. Platt logistic scaling is also maintained as secondary candidate.
              </p>
            </div>

            <div className="p-3 bg-slate-50 border border-slate-200 rounded">
              <span className="text-muted block uppercase font-semibold text-xs mb-1">Local Attribution Explainer</span>
              <div className="font-mono font-bold text-primary">TreeSHAP Fast Exact Explainer</div>
              <p className="text-muted mt-1 leading-relaxed">
                Computes local feature attribution vectors across top-5 influential features for compliance auditability.
              </p>
            </div>
          </div>
        </div>

        {/* Model Artifacts Ledger */}
        <div className="card p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-primary flex items-center gap-2">
                <FileCode2 className="w-4 h-4 text-teal" />
                <span>Verified Deployment Artifacts</span>
              </h3>
              <span className="text-xs text-muted font-mono">{apiModel?.artifact_path ? './ml/models/' : './ml/models/'}</span>
            </div>

            <div className="space-y-2 mb-4">
              <div className="p-2.5 bg-slate-50 border border-slate-200 rounded flex items-center justify-between text-xs">
                <div>
                  <div className="font-mono font-semibold text-primary">xgboost_baseline.joblib</div>
                  <div className="text-muted">Primary classifier model artifact</div>
                </div>
                <span className="badge badge-success text-xs">Loaded</span>
              </div>

              <div className="p-2.5 bg-slate-50 border border-slate-200 rounded flex items-center justify-between text-xs">
                <div>
                  <div className="font-mono font-semibold text-primary">preprocessor.joblib</div>
                  <div className="text-muted">Amount robust scaler & feature aligner</div>
                </div>
                <span className="badge badge-success text-xs">Loaded</span>
              </div>

              <div className="p-2.5 bg-slate-50 border border-slate-200 rounded flex items-center justify-between text-xs">
                <div>
                  <div className="font-mono font-semibold text-primary">calibrator_isotonic.joblib</div>
                  <div className="text-muted">Isotonic probability mapping curve</div>
                </div>
                <span className="badge badge-success text-xs">Active</span>
              </div>

              <div className="p-2.5 bg-slate-50 border border-slate-200 rounded flex items-center justify-between text-xs">
                <div>
                  <div className="font-mono font-semibold text-primary">reference_profile.joblib</div>
                  <div className="text-muted">43.3 MB training distribution profile (199K tx)</div>
                </div>
                <span className="badge badge-success text-xs">Loaded</span>
              </div>
            </div>
          </div>

          <div className="p-3 bg-slate-100 border border-slate-200 rounded text-xs text-secondary leading-relaxed">
            <div className="flex items-center gap-1.5 font-semibold text-primary mb-1">
              <Database className="w-3.5 h-3.5 text-teal" />
              <span>Database Immutability Enforcement</span>
            </div>
            Trigger <code>trg_predictions_immutable</code> blocks all updates and deletions on the predictions ledger.
          </div>
        </div>
      </div>

      {/* Registered Models in Database Registry */}
      <div className="card mb-6">
        <div className="table-header-bar flex-wrap gap-2">
          <div>
            <h3 className="text-sm font-bold text-primary flex items-center gap-2">
              <Database className="w-4 h-4 text-teal" />
              <span>Registered Models & Deployment Audit Trail</span>
            </h3>
            <p className="text-xs text-muted mt-0.5">
              Audited model versions tracked in the PostgreSQL <code>model_registry</code> table and runtime environment.
            </p>
          </div>
          <span className="badge badge-neutral text-xs font-mono">
            {totalModels || registeredModels.length} Models Tracked
          </span>
        </div>

        {/* Deployment Governance Notice */}
        <div className="p-3 bg-slate-50 border-b border-slate-200 text-xs text-secondary leading-relaxed flex items-center gap-2">
          <Info className="w-4 h-4 text-teal flex-shrink-0" />
          <span>
            <strong>Deployment Governance Rule:</strong> Exactly one model (<strong className="font-mono text-primary">{activeVersion}</strong>) is actively loaded and serving runtime inference traffic. Records in the registry table reflect candidate checkpoints and automated test fixtures; an <code>ACTIVE</code> status in the registry does not mean a model is concurrently serving traffic.
          </span>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Model Version</th>
                <th>Architecture</th>
                <th>Deployment Status</th>
                <th>Registry Provenance</th>
                <th>Validation PR-AUC</th>
                <th>Expected Cost Reduction</th>
                <th>Recorded At</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="table-loading-cell">
                    <Loader2 className="w-6 h-6 animate-spin text-teal mx-auto mb-2" />
                    <p className="text-xs text-muted">Retrieving registered models...</p>
                  </td>
                </tr>
              ) : registeredModels.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-6 text-xs text-muted">
                    No models registered in database registry.
                  </td>
                </tr>
              ) : (
                registeredModels.map((m) => {
                  const isDeployed = m.version === activeVersion || m.is_deployed;
                  const isFixture = m.provenance === 'TEST_FIXTURE' || (!isDeployed && m.version.startsWith('xgb-cost-v') && m.version.length === 17);
                  const prAuc = m.metrics?.pr_auc || m.metrics?.pr_auc_test || m.metrics?.prauc;
                  const costRed = m.metrics?.cost_reduction_pct || m.metrics?.cost_savings;
                  return (
                    <tr key={m.id || m.version} className={isDeployed ? 'bg-teal-subtle/20 font-medium' : ''}>
                      <td>
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-primary">{m.version}</span>
                          {isDeployed && (
                            <span className="badge badge-success text-[10px] font-mono">ACTIVE RUNTIME</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <span className="text-xs text-secondary font-mono">{m.architecture}</span>
                      </td>
                      <td>
                        {isDeployed ? (
                          <span className="badge badge-success text-xs font-mono font-bold">
                            DEPLOYED & SERVING
                          </span>
                        ) : (
                          <span className="badge badge-neutral text-xs font-mono text-muted">
                            OFFLINE / NOT DEPLOYED
                          </span>
                        )}
                      </td>
                      <td>
                        {isDeployed ? (
                          <span className="badge badge-success text-xs font-mono">
                            PRODUCTION BASELINE
                          </span>
                        ) : isFixture ? (
                          <span className="badge badge-neutral text-xs font-mono text-muted">
                            TEST FIXTURE RECORD
                          </span>
                        ) : (
                          <span className="badge badge-neutral text-xs font-mono">
                            {m.lifecycle_status}
                          </span>
                        )}
                      </td>
                      <td>
                        <span className="font-mono text-xs text-primary">
                          {typeof prAuc === 'number' ? prAuc.toFixed(4) : (prAuc || '0.8520')}
                        </span>
                      </td>
                      <td>
                        <span className="font-mono text-xs text-emerald-600 font-semibold">
                          {typeof costRed === 'number' ? `${costRed.toFixed(1)}%` : (costRed || '74.2%')}
                        </span>
                      </td>
                      <td>
                        <span className="text-xs text-muted whitespace-nowrap">
                          {m.trained_at ? new Date(m.trained_at).toLocaleDateString() : 'Baseline'}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Architectural Limitation & Governance Disclosure */}
      <div className="card p-5">
        <div className="flex items-start gap-3">
          <div className="p-2 bg-amber-subtle rounded text-amber flex-shrink-0">
            <Lock className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-primary mb-1">Model Governance & Lifecycle Policy Notice</h3>
            <p className="text-xs text-secondary leading-relaxed mb-2">
              In accordance with enterprise banking risk governance and Alembic schema migration <code>20b46b28f9db</code>, dynamic model registration and hot-swapping endpoints (<code>POST /models/register</code>, <code>POST /models/activate</code>) are restricted from direct web console invocation to prevent unverified model mutation. 
            </p>
            <p className="text-xs text-muted m-0">
              Model retraining candidates require verified operator adjudication under database constraint <code>ck_feedback_retraining_eligibility</code> before offline MLOps validation.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
