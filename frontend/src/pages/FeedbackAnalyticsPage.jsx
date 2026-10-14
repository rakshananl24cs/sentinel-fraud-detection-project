import { useState, useEffect } from 'react';
import { reviewQueueApi } from '../api/client';
import MetricCard from '../components/MetricCard';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import CaseDetailsModal from '../components/CaseDetailsModal';
import { 
  MessageSquareCheck, 
  RotateCw, 
  AlertCircle, 
  ShieldCheck, 
  ShieldAlert, 
  FileText,
  UserCheck,
  ExternalLink,
  Info
} from 'lucide-react';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend
} from 'recharts';

const DECISION_COLORS = {
  CONFIRMED_FRAUD: '#ef4444',
  CONFIRMED_GENUINE: '#10b981',
  DISPUTED: '#f59e0b',
  INCONCLUSIVE: '#64748b',
};

export default function FeedbackAnalyticsPage() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [reviewedItems, setReviewedItems] = useState([]);
  const [totalReviewed, setTotalReviewed] = useState(0);

  // Inspector modal
  const [selectedCase, setSelectedCase] = useState(null);

  const fetchFeedbackData = async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true);
    else setLoading(true);
    setError('');

    try {
      const data = await reviewQueueApi.getQueue({
        limit: 100,
        statusFilter: 'REVIEWED',
      });
      setReviewedItems(data.items || []);
      setTotalReviewed(data.total || 0);
    } catch {
      setError('Failed to fetch adjudication analytics records from the API.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchFeedbackData();
  }, []);

  // Compute breakdown metrics
  const analytics = (() => {
    if (reviewedItems.length === 0) {
      return {
        total: 0,
        fraudCount: 0,
        genuineCount: 0,
        disputedCount: 0,
        inconclusiveCount: 0,
        verifiedCount: 0,
        verifiedRate: 0,
      };
    }

    let fraud = 0;
    let genuine = 0;
    let disputed = 0;
    let inconclusive = 0;
    let verified = 0;

    reviewedItems.forEach((item) => {
      const d = item.latest_feedback_decision;
      if (d === 'CONFIRMED_FRAUD') fraud += 1;
      else if (d === 'CONFIRMED_GENUINE') genuine += 1;
      else if (d === 'DISPUTED') disputed += 1;
      else if (d === 'INCONCLUSIVE') inconclusive += 1;

      if (item.latest_feedback_verified) verified += 1;
    });

    const total = reviewedItems.length;
    return {
      total,
      fraudCount: fraud,
      genuineCount: genuine,
      disputedCount: disputed,
      inconclusiveCount: inconclusive,
      verifiedCount: verified,
      verifiedRate: total > 0 ? (verified / total) * 100 : 0,
    };
  })();

  const decisionChartData = [
    { name: 'Confirmed Fraud', value: analytics.fraudCount, color: DECISION_COLORS.CONFIRMED_FRAUD },
    { name: 'Confirmed Genuine', value: analytics.genuineCount, color: DECISION_COLORS.CONFIRMED_GENUINE },
    { name: 'Disputed', value: analytics.disputedCount, color: DECISION_COLORS.DISPUTED },
    { name: 'Inconclusive', value: analytics.inconclusiveCount, color: DECISION_COLORS.INCONCLUSIVE },
  ].filter((d) => d.value > 0);

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <MessageSquareCheck className="w-6 h-6 text-teal" />
            <span>Operator Feedback & Adjudication Analytics</span>
          </h1>
          <p className="page-subtitle">
            Analysis of human-in-the-loop decisions, administrator verifications, and model retraining eligibility.
          </p>
        </div>

        <div className="header-actions">
          <button
            type="button"
            className="btn btn-secondary flex items-center gap-1.5"
            onClick={() => fetchFeedbackData(true)}
            disabled={loading || refreshing}
          >
            <RotateCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Statistical Scope Disclosure */}
      <div className="p-3 bg-slate-100 border border-slate-200 rounded-md text-xs text-secondary mb-6 flex items-start justify-between gap-2">
        <div className="flex items-start gap-2">
          <Info className="w-4 h-4 text-teal flex-shrink-0 mt-0.5" />
          <div>
            <strong>Analyst Feedback Scope:</strong> Metrics reflect <strong>human operator adjudications</strong> recorded in the review ledger. Category counts and verification rates are computed consistently across the <strong>latest {analytics.total} adjudications</strong> ({totalReviewed} total recorded in ledger). Raw model inference scores are never counted as confirmed fraud or genuine outcomes.
          </div>
        </div>
        <span className="badge badge-neutral font-mono text-xs whitespace-nowrap">
          Sample: {analytics.total} / {totalReviewed} Total
        </span>
      </div>

      {error && (
        <div className="alert alert-error mb-6">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="grid-cards mb-6">
        <MetricCard
          title="Analyzed Adjudications"
          value={loading ? '--' : analytics.total}
          icon={FileText}
          iconColor="text-teal"
          iconBg="bg-teal-subtle"
          tooltip="Human operator review decisions in this analytical sample"
          subtext={totalReviewed > analytics.total ? `Latest ${analytics.total} of ${totalReviewed} total recorded` : `All ${analytics.total} recorded cases`}
          loading={loading}
        />

        <MetricCard
          title="Confirmed Fraud Cases"
          value={loading ? '--' : analytics.fraudCount}
          icon={ShieldAlert}
          iconColor="text-red"
          iconBg="bg-red-subtle"
          tooltip="Operator verified fraud chargebacks and account breaches"
          subtext={analytics.total > 0 ? `${((analytics.fraudCount / analytics.total) * 100).toFixed(1)}% of analyzed cases` : '0%'}
          loading={loading}
        />

        <MetricCard
          title="Confirmed Genuine Cases"
          value={loading ? '--' : analytics.genuineCount}
          icon={ShieldCheck}
          iconColor="text-emerald"
          iconBg="bg-emerald-subtle"
          tooltip="Operator cleared transactions with valid cardholder confirmation"
          subtext={analytics.total > 0 ? `${((analytics.genuineCount / analytics.total) * 100).toFixed(1)}% of analyzed cases` : '0%'}
          loading={loading}
        />

        <MetricCard
          title="Admin Verification Rate"
          value={loading ? '--' : `${analytics.verifiedRate.toFixed(1)}%`}
          icon={UserCheck}
          iconColor="text-indigo"
          iconBg="bg-indigo-subtle"
          tooltip="Percentage of operator decisions audited and verified by administrators"
          subtext={`${analytics.verifiedCount} of ${analytics.total} verified`}
          loading={loading}
        />
      </div>

      {reviewedItems.length === 0 ? (
        <div className="card p-10 mb-6">
          <EmptyState
            icon={MessageSquareCheck}
            title="No Operator Adjudications Recorded"
            description="No feedback records have been logged in the review queue yet. Open the Review Queue to triage pending borderline cases and record operator feedback."
            action={
              <a href="/queue" className="btn btn-primary btn-sm">
                Open Review Queue
              </a>
            }
          />
        </div>
      ) : (
        <div className="grid-2col mb-6">
          {/* Chart: Adjudication Decision Distribution */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-bold text-primary flex items-center gap-1.5">
                  <PieChart className="w-4 h-4 text-teal" />
                  <span>Adjudication Decision Distribution</span>
                </h3>
                <p className="text-xs text-muted mt-1">
                  Categorical breakdown of human investigator decisions
                </p>
              </div>
            </div>

            <div style={{ width: '100%', height: 240 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={decisionChartData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={80}
                    paddingAngle={3}
                  >
                    {decisionChartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '6px', color: '#fff', fontSize: '12px' }}
                  />
                  <Legend 
                    verticalAlign="bottom" 
                    height={36} 
                    iconType="circle"
                    formatter={(val) => <span style={{ fontSize: '12px', color: '#334155' }}>{val}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Table: Decision Counts */}
          <div className="card p-5 flex flex-col justify-between">
            <div>
              <h3 className="text-sm font-bold text-primary mb-3">Adjudication Label Summary</h3>
              <div className="space-y-2 mb-4">
                <div className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded">
                  <div className="flex items-center gap-2">
                    <span className="dot dot-danger"></span>
                    <span className="text-xs font-semibold text-primary">CONFIRMED_FRAUD</span>
                  </div>
                  <span className="font-mono font-bold text-xs">{analytics.fraudCount}</span>
                </div>

                <div className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded">
                  <div className="flex items-center gap-2">
                    <span className="dot dot-success"></span>
                    <span className="text-xs font-semibold text-primary">CONFIRMED_GENUINE</span>
                  </div>
                  <span className="font-mono font-bold text-xs">{analytics.genuineCount}</span>
                </div>

                <div className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded">
                  <div className="flex items-center gap-2">
                    <span className="dot dot-warning"></span>
                    <span className="text-xs font-semibold text-primary">DISPUTED</span>
                  </div>
                  <span className="font-mono font-bold text-xs">{analytics.disputedCount}</span>
                </div>

                <div className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded">
                  <div className="flex items-center gap-2">
                    <span className="dot dot-neutral"></span>
                    <span className="text-xs font-semibold text-primary">INCONCLUSIVE</span>
                  </div>
                  <span className="font-mono font-bold text-xs">{analytics.inconclusiveCount}</span>
                </div>
              </div>
            </div>

            <div className="p-3 bg-teal-50 border border-teal-200 rounded text-xs text-teal-900 leading-relaxed">
              <strong>Retraining Eligibility Governance:</strong> Confirmed Genuine and Fraud decisions verified by Administrators qualify as candidate ground-truth labels for shadow model retraining.
            </div>
          </div>
        </div>
      )}

      {/* Adjudication Ledger Table */}
      {reviewedItems.length > 0 && (
        <div className="card">
          <div className="table-header-bar">
            <h3 className="text-sm font-bold text-primary">Recent Adjudication Records</h3>
            <span className="text-xs text-muted">Showing up to 100 reviewed cases</span>
          </div>

          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>External ID</th>
                  <th>Amount</th>
                  <th>P(Fraud)</th>
                  <th>Adjudication Decision</th>
                  <th>Admin Verification</th>
                  <th>Ingested Timestamp</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {reviewedItems.map((item) => (
                  <tr key={item.transaction_id} className="hover-row">
                    <td>
                      <span className="font-mono font-semibold text-primary">{item.external_id}</span>
                    </td>
                    <td className="font-mono font-bold text-primary">
                      ${typeof item.amount === 'number' ? item.amount.toFixed(2) : Number(item.amount || 0).toFixed(2)}
                    </td>
                    <td>
                      <span className="font-mono text-teal font-semibold">
                        {(item.fraud_probability * 100).toFixed(2)}%
                      </span>
                    </td>
                    <td>
                      <StatusBadge type="feedback" value={item.latest_feedback_decision} />
                    </td>
                    <td>
                      <StatusBadge type="verified" value={item.latest_feedback_verified} />
                    </td>
                    <td>
                      <span className="text-xs text-muted">
                        {new Date(item.transaction_created_at).toLocaleString()}
                      </span>
                    </td>
                    <td className="text-right">
                      <button
                        type="button"
                        onClick={() => setSelectedCase(item)}
                        className="btn btn-secondary btn-xs flex items-center gap-1"
                      >
                        <span>History</span>
                        <ExternalLink className="w-3 h-3" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal Drawer */}
      {selectedCase && (
        <CaseDetailsModal
          transaction={selectedCase}
          onClose={() => setSelectedCase(null)}
          onFeedbackSubmitted={() => fetchFeedbackData()}
        />
      )}
    </div>
  );
}
