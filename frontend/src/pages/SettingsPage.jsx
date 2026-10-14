import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { healthApi, modelsApi } from '../api/client';
import StatusBadge from '../components/StatusBadge';
import { 
  Settings, 
  User, 
  Cpu, 
  Sliders, 
  CheckCircle2, 
  AlertCircle, 
  LogOut,
  Layers,
  RotateCw
} from 'lucide-react';

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const [dbStatus, setDbStatus] = useState('checking');
  const [activeModel, setActiveModel] = useState('xgb-cost-v1');
  const [checking, setChecking] = useState(false);

  const checkInfrastructure = async () => {
    setChecking(true);
    try {
      const [healthRes, modelRes] = await Promise.allSettled([
        healthApi.getReady(),
        modelsApi.getCurrent()
      ]);

      if (healthRes.status === 'fulfilled') {
        setDbStatus(healthRes.value.database === 'connected' ? 'connected' : 'disconnected');
      } else {
        setDbStatus('disconnected');
      }

      if (modelRes.status === 'fulfilled' && modelRes.value?.version) {
        setActiveModel(modelRes.value.version);
      }
    } catch {
      setDbStatus('disconnected');
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    checkInfrastructure();
  }, []);

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <Settings className="w-6 h-6 text-teal" />
            <span>System & Policy Settings</span>
          </h1>
          <p className="page-subtitle">
            Operator profile configuration, cost-sensitive policy parameters, and inference engine connectivity.
          </p>
        </div>

        <button
          type="button"
          onClick={checkInfrastructure}
          disabled={checking}
          className="btn btn-secondary flex items-center gap-1.5"
        >
          <RotateCw className={`w-3.5 h-3.5 ${checking ? 'animate-spin' : ''}`} />
          <span>Verify Connectivity</span>
        </button>
      </div>

      <div className="grid-2col mb-6">
        {/* Section 1: Analyst Profile & Authorization */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <User className="w-5 h-5 text-teal" />
            <h2 className="text-sm font-bold text-primary">Analyst Identity & Authorization</h2>
          </div>

          <div className="space-y-3">
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-md">
              <span className="text-xs text-muted block uppercase tracking-wider mb-1">Authenticated Account</span>
              <strong className="text-sm text-primary font-mono">{user?.email || 'operator@bank.internal'}</strong>
              <div className="mt-2 flex items-center gap-2">
                <StatusBadge type="role" value={user?.role} />
                <span className="badge badge-success text-xs font-mono">SESSION ACTIVE</span>
              </div>
            </div>

            <div className="p-3 bg-slate-50 border border-slate-200 rounded-md text-xs space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-secondary">Authentication Standard:</span>
                <span className="font-mono text-primary font-medium">Signed Bearer JWT (HMAC-SHA256)</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-secondary">Token Validity:</span>
                <span className="font-mono text-primary">60 Minutes Sliding Expiration</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-secondary">Authorization Scope:</span>
                <span className="font-mono text-primary">
                  {user?.role === 'ADMIN' ? 'Score, Review, Retrain Verify' : 'Score, Review Triage'}
                </span>
              </div>
            </div>

            <div className="pt-2 flex justify-between items-center">
              <span className="text-xs text-muted">To switch operator profiles:</span>
              <button
                type="button"
                onClick={logout}
                className="btn btn-secondary btn-sm flex items-center gap-1 text-red-600 hover:text-red-700"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        </div>

        {/* Section 2: Infrastructure & Engine Connectivity */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Cpu className="w-5 h-5 text-teal" />
            <h2 className="text-sm font-bold text-primary">Inference Engine & Persistence</h2>
          </div>

          <div className="space-y-3">
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-md text-xs space-y-2 font-mono">
              <div className="flex justify-between items-center">
                <span className="text-secondary">REST API Base:</span>
                <strong className="text-primary truncate max-w-[240px]">{apiBaseUrl}</strong>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-secondary">Database Persistence:</span>
                {dbStatus === 'connected' ? (
                  <span className="text-emerald flex items-center gap-1 font-semibold">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Connected (PostgreSQL 16)
                  </span>
                ) : (
                  <span className="text-red flex items-center gap-1 font-semibold">
                    <AlertCircle className="w-3.5 h-3.5" /> Disconnected
                  </span>
                )}
              </div>
              <div className="flex justify-between items-center">
                <span className="text-secondary">Active Model ID:</span>
                <strong className="text-teal font-semibold">{activeModel}</strong>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-secondary">Audit Trail:</span>
                <span className="text-primary">Append-Only Immutable Ledger</span>
              </div>
            </div>

            <div className="p-3 bg-slate-50 border border-slate-200 rounded-md text-xs text-secondary leading-relaxed">
              <strong className="text-primary block mb-1">Retraining Eligibility Safeguard:</strong>
              Database check constraint <code className="text-primary font-mono text-xs">ck_feedback_retraining_eligibility</code> strictly requires human adjudications to be administrator-verified before inclusion in downstream ML candidate training splits.
            </div>
          </div>
        </div>
      </div>

      {/* Section 3: Cost-Sensitive Decision Matrix & Policy Thresholds */}
      <div className="card p-5 mb-6">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Sliders className="w-5 h-5 text-teal" />
            <div>
              <h2 className="text-sm font-bold text-primary">Cost-Sensitive Decision Policy Parameters</h2>
              <p className="text-xs text-muted">
                Asymmetric financial loss matrix and decision thresholds enforced by the active model policy.
              </p>
            </div>
          </div>
          <span className="badge badge-success font-mono text-xs">ACTIVE PRODUCTION POLICY</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
          <div className="p-3 bg-slate-50 border border-slate-200 rounded">
            <span className="text-xs text-muted uppercase block font-semibold">Investigation Cost (C_review)</span>
            <div className="text-base font-bold font-mono text-primary mt-1">$5.00</div>
            <p className="text-xs text-muted mt-1">Operator triage overhead cost</p>
          </div>

          <div className="p-3 bg-slate-50 border border-slate-200 rounded">
            <span className="text-xs text-muted uppercase block font-semibold">False Positive Cost (C_FP)</span>
            <div className="text-base font-bold font-mono text-amber mt-1">$25.00</div>
            <p className="text-xs text-muted mt-1">Customer friction & card decline penalty</p>
          </div>

          <div className="p-3 bg-slate-50 border border-slate-200 rounded">
            <span className="text-xs text-muted uppercase block font-semibold">False Negative Cost (C_FN)</span>
            <div className="text-base font-bold font-mono text-red mt-1">Transaction Amount</div>
            <p className="text-xs text-muted mt-1">Full unrecovered fraud loss</p>
          </div>

          <div className="p-3 bg-slate-50 border border-slate-200 rounded">
            <span className="text-xs text-muted uppercase block font-semibold">Capacity Constraint (B)</span>
            <div className="text-base font-bold font-mono text-teal mt-1">5.0%</div>
            <p className="text-xs text-muted mt-1">Max daily transactions routed to review</p>
          </div>
        </div>

        <div className="p-4 bg-white border border-slate-200 rounded-md">
          <h3 className="text-xs font-bold text-primary uppercase tracking-wider mb-3">Enforced Operational Thresholds</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded text-xs">
              <div className="flex items-center justify-between mb-1">
                <StatusBadge type="decision" value="APPROVE" />
                <span className="font-mono font-bold text-emerald-800">P &lt; 0.0420</span>
              </div>
              <p className="text-emerald-900 mt-1">
                Immediate settlement. Expected risk cost is below human investigation overhead threshold.
              </p>
            </div>

            <div className="p-3 bg-amber-50 border border-amber-200 rounded text-xs">
              <div className="flex items-center justify-between mb-1">
                <StatusBadge type="decision" value="REVIEW" />
                <span className="font-mono font-bold text-amber-800">0.0420 ≤ P &lt; 0.7539</span>
              </div>
              <p className="text-amber-900 mt-1">
                Operator review queue. Uncertainty zone where human verification minimizes total financial cost.
              </p>
            </div>

            <div className="p-3 bg-red-50 border border-red-200 rounded text-xs">
              <div className="flex items-center justify-between mb-1">
                <StatusBadge type="decision" value="BLOCK" />
                <span className="font-mono font-bold text-red-800">P ≥ 0.7539</span>
              </div>
              <p className="text-red-900 mt-1">
                Automated decline. High-confidence fraud risk warrants immediate cardholder protection.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Section 4: Standard Features & Model Dimension */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-3">
          <Layers className="w-5 h-5 text-teal" />
          <h2 className="text-sm font-bold text-primary">Canonical Feature Dimensions</h2>
        </div>
        <p className="text-xs text-secondary leading-relaxed mb-3">
          The inference engine strictly processes 30 canonical numeric features. Payloads with missing required fields or additional unexpected properties are rejected with HTTP 422 to prevent label leakage.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-xs font-mono text-center">
          <div className="p-2 bg-slate-50 border rounded font-semibold text-primary">Amount ($)</div>
          <div className="p-2 bg-slate-50 border rounded font-semibold text-primary">Time (sec)</div>
          <div className="p-2 bg-slate-50 border rounded text-secondary">V1 — V5</div>
          <div className="p-2 bg-slate-50 border rounded text-secondary">V6 — V12</div>
          <div className="p-2 bg-slate-50 border rounded text-secondary">V13 — V20</div>
          <div className="p-2 bg-slate-50 border rounded text-secondary">V21 — V28</div>
        </div>
      </div>
    </div>
  );
}
