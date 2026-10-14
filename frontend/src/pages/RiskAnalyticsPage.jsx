import { useState, useEffect, useMemo } from 'react';
import { transactionsApi } from '../api/client';
import MetricCard from '../components/MetricCard';
import EmptyState from '../components/EmptyState';
import { 
  BarChart3, 
  RotateCw, 
  AlertCircle, 
  Inbox, 
  TrendingUp, 
  ShieldAlert, 
  DollarSign, 
  Scale, 
  Info,
  FileSpreadsheet,
  Layers,
  PieChart as PieIcon
} from 'lucide-react';

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
  Legend
} from 'recharts';

const RISK_COLORS = {
  APPROVE: '#10b981',
  REVIEW: '#f59e0b',
  BLOCK: '#ef4444',
  HIGH: '#ef4444',
  MEDIUM: '#f59e0b',
  LOW: '#10b981',
};

export default function RiskAnalyticsPage() {
  const [viewMode, setViewMode] = useState('batch'); // 'batch' | 'all'
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  // Operational and Batch Data
  const [operationalStats, setOperationalStats] = useState(null);
  const [latestBatch, setLatestBatch] = useState(null);
  const [recentTransactions, setRecentTransactions] = useState([]);

  const fetchRiskData = async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true);
    else setLoading(true);
    setError('');

    try {
      const [statsRes, batchRes, recentRes] = await Promise.allSettled([
        transactionsApi.getOperationalStats(),
        transactionsApi.getLatestBatch(),
        transactionsApi.getRecent({ limit: 100 }),
      ]);

      if (statsRes.status === 'fulfilled') {
        setOperationalStats(statsRes.value);
      }
      if (batchRes.status === 'fulfilled') {
        setLatestBatch(batchRes.value);
      } else {
        setLatestBatch(null);
      }
      if (recentRes.status === 'fulfilled') {
        setRecentTransactions(recentRes.value.items || []);
      }
    } catch {
      setError('Failed to fetch risk analytics metrics from the backend API.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchRiskData();
  }, []);

  // ---------------------------------------------------------------------------
  // ALL ACTIVITY COMPUTATIONS
  // ---------------------------------------------------------------------------
  const allDecisionData = useMemo(() => {
    if (!operationalStats) return [];
    const total = operationalStats.total_transactions || 1;
    return [
      { 
        name: 'Approve (Low Risk)', 
        value: operationalStats.approved_count, 
        color: RISK_COLORS.APPROVE,
        percent: ((operationalStats.approved_count / total) * 100).toFixed(1)
      },
      { 
        name: 'Review (Uncertainty)', 
        value: operationalStats.review_count, 
        color: RISK_COLORS.REVIEW,
        percent: ((operationalStats.review_count / total) * 100).toFixed(1)
      },
      { 
        name: 'Block (High Risk)', 
        value: operationalStats.block_count, 
        color: RISK_COLORS.BLOCK,
        percent: ((operationalStats.block_count / total) * 100).toFixed(1)
      },
    ].filter((d) => d.value > 0);
  }, [operationalStats]);

  const allProbBins = useMemo(() => {
    const bins = [
      { range: '< 4.2% (Approve)', count: 0, color: '#10b981' },
      { range: '4.2% - 25% (Low Review)', count: 0, color: '#0d9488' },
      { range: '25% - 75.4% (High Review)', count: 0, color: '#f59e0b' },
      { range: '≥ 75.4% (Block)', count: 0, color: '#ef4444' },
    ];

    if (recentTransactions.length > 0) {
      recentTransactions.forEach((tx) => {
        const p = tx.calibrated_probability;
        if (typeof p === 'number') {
          if (p < 0.042) bins[0].count += 1;
          else if (p < 0.25) bins[1].count += 1;
          else if (p < 0.75388) bins[2].count += 1;
          else bins[3].count += 1;
        }
      });
    } else if (operationalStats) {
      // Approximate from aggregated counts if no individual rows
      bins[0].count = operationalStats.approved_count || 0;
      bins[1].count = Math.round((operationalStats.review_count || 0) * 0.6);
      bins[2].count = Math.round((operationalStats.review_count || 0) * 0.4);
      bins[3].count = operationalStats.block_count || 0;
    }
    return bins;
  }, [recentTransactions, operationalStats]);

  // ---------------------------------------------------------------------------
  // LATEST BATCH COMPUTATIONS
  // ---------------------------------------------------------------------------
  const batchSummary = latestBatch?.summary;

  const batchDecisionData = useMemo(() => {
    if (!batchSummary) return [];
    const total = batchSummary.total_processed || 1;
    return [
      { 
        name: 'Approve (Low Risk)', 
        value: batchSummary.approved_count, 
        color: RISK_COLORS.APPROVE,
        percent: ((batchSummary.approved_count / total) * 100).toFixed(1)
      },
      { 
        name: 'Review (Uncertainty)', 
        value: batchSummary.review_count, 
        color: RISK_COLORS.REVIEW,
        percent: ((batchSummary.review_count / total) * 100).toFixed(1)
      },
      { 
        name: 'Block (High Risk)', 
        value: batchSummary.block_count, 
        color: RISK_COLORS.BLOCK,
        percent: ((batchSummary.block_count / total) * 100).toFixed(1)
      },
    ].filter((d) => d.value > 0);
  }, [batchSummary]);

  const batchProbBins = useMemo(() => {
    if (!latestBatch?.items || latestBatch.items.length === 0) return [];
    const bins = [
      { range: '< 4.2% (Approve)', count: 0, color: '#10b981' },
      { range: '4.2% - 25% (Low Review)', count: 0, color: '#0d9488' },
      { range: '25% - 75.4% (High Review)', count: 0, color: '#f59e0b' },
      { range: '≥ 75.4% (Block)', count: 0, color: '#ef4444' },
    ];
    latestBatch.items.forEach((item) => {
      const p = item.fraud_probability;
      if (typeof p === 'number') {
        if (p < 0.042) bins[0].count += 1;
        else if (p < 0.25) bins[1].count += 1;
        else if (p < 0.75388) bins[2].count += 1;
        else bins[3].count += 1;
      }
    });
    return bins;
  }, [latestBatch]);

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <BarChart3 className="w-6 h-6 text-teal" />
            <span>Risk & Decision Analytics</span>
          </h1>
          <p className="page-subtitle">
            Statistical risk profiles, decision thresholds, and operational review metrics derived from backend ledger data.
          </p>
        </div>

        <div className="header-actions flex items-center gap-2">
          {/* Segmented View Mode Toggle */}
          <div className="button-group">
            <button
              type="button"
              className={`filter-btn ${viewMode === 'batch' ? 'active' : ''}`}
              onClick={() => setViewMode('batch')}
            >
              <FileSpreadsheet className="w-3.5 h-3.5 inline mr-1" />
              Latest Batch
            </button>
            <button
              type="button"
              className={`filter-btn ${viewMode === 'all' ? 'active' : ''}`}
              onClick={() => setViewMode('all')}
            >
              <Layers className="w-3.5 h-3.5 inline mr-1" />
              All Activity
            </button>
          </div>

          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => fetchRiskData(true)}
            disabled={loading || refreshing}
          >
            <RotateCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Scope Disclaimer Alert */}
      <div className="p-3 bg-slate-100 border border-slate-200 rounded-md text-xs text-secondary mb-6 flex items-start justify-between gap-2">
        <div className="flex items-start gap-2">
          <Info className="w-4 h-4 text-teal flex-shrink-0 mt-0.5" />
          <div>
            <strong>Analytics Scope:</strong>{' '}
            {viewMode === 'batch' ? (
              <span>
                Displaying metrics for the most recent uploaded batch{' '}
                <strong className="font-mono text-primary">{batchSummary?.batch_id || 'None'}</strong>{' '}
                ({batchSummary?.filename || 'No batch file'}).
              </span>
            ) : (
              <span>
                Displaying cumulative operational metrics across all persisted transaction records in the ledger.
              </span>
            )}
          </div>
        </div>
        {viewMode === 'batch' && batchSummary && (
          <span className="badge badge-neutral font-mono text-xs whitespace-nowrap">
            {batchSummary.total_processed} Scored / {batchSummary.total_submitted} Submitted
          </span>
        )}
      </div>

      {error && (
        <div className="alert alert-error mb-6">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* VIEW MODE 1: LATEST BATCH */}
      {viewMode === 'batch' && (
        <>
          {!batchSummary ? (
            <div className="card p-10 mb-6">
              <EmptyState
                icon={FileSpreadsheet}
                title="No Uploaded Batch Available"
                description="No transaction batch has been analyzed yet. Upload a CSV file on the Transaction Analysis page to view batch risk statistics."
                action={
                  <a href="/score" className="btn btn-primary btn-sm">
                    Upload CSV Batch
                  </a>
                }
              />
            </div>
          ) : (
            <>
              {/* Batch Metric Cards Grid */}
              <div className="grid-cards mb-6">
                <MetricCard
                  title="Batch Volume"
                  value={loading ? '--' : batchSummary.total_processed}
                  icon={Inbox}
                  iconColor="text-teal"
                  iconBg="bg-teal-subtle"
                  tooltip="Transactions successfully processed in this batch"
                  subtext={`${batchSummary.approved_count} approved, ${batchSummary.review_count} review, ${batchSummary.block_count} blocked`}
                  loading={loading}
                />

                <MetricCard
                  title="Avg Calibrated P(Fraud)"
                  value={loading ? '--' : `${(batchSummary.average_fraud_probability * 100).toFixed(2)}%`}
                  icon={TrendingUp}
                  iconColor="text-teal"
                  iconBg="bg-teal-subtle"
                  tooltip="Average Isotonic-calibrated posterior fraud probability across batch records"
                  subtext="Isotonic regression calibration"
                  loading={loading}
                />

                <MetricCard
                  title="Review Queue Routing"
                  value={loading ? '--' : batchSummary.review_count}
                  icon={ShieldAlert}
                  iconColor="text-amber"
                  iconBg="bg-amber-subtle"
                  tooltip="Transactions falling into human triage uncertainty band (0.042 ≤ P < 0.7539)"
                  subtext={`${((batchSummary.review_count / Math.max(1, batchSummary.total_processed)) * 100).toFixed(1)}% triage rate`}
                  linkTo="/queue"
                  linkText="Open Queue"
                  loading={loading}
                />

                <MetricCard
                  title="Batch Financial Volume"
                  value={loading ? '--' : `$${Number(batchSummary.total_amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                  icon={DollarSign}
                  iconColor="text-emerald"
                  iconBg="bg-emerald-subtle"
                  tooltip="Total cumulative monetary volume across all scored batch transactions"
                  subtext="Monetary exposure"
                  loading={loading}
                />
              </div>

              {/* Batch Charts Grid */}
              <div className="grid-2col mb-6">
                {/* Chart 1: Batch Decision Composition */}
                <div className="card p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-sm font-bold text-primary flex items-center gap-1.5">
                        <PieIcon className="w-4 h-4 text-teal" />
                        <span>Batch Policy Decision Distribution</span>
                      </h3>
                      <p className="text-xs text-muted mt-1">
                        Breakdown of automated cost-minimizing policy outcomes
                      </p>
                    </div>
                    <span className="text-xs font-mono text-muted bg-slate-100 px-2 py-0.5 rounded">
                      {batchSummary.total_processed} Records
                    </span>
                  </div>

                  <div style={{ width: '100%', height: 240 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={batchDecisionData}
                          dataKey="value"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius={55}
                          outerRadius={80}
                          paddingAngle={3}
                        >
                          {batchDecisionData.map((entry, index) => (
                            <Cell key={`batch-pie-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '6px', color: '#fff', fontSize: '12px' }}
                          formatter={(value, name) => [`${value} transactions (${((value / batchSummary.total_processed) * 100).toFixed(1)}%)`, name]}
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

                {/* Chart 2: Batch Probability Histogram */}
                <div className="card p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-sm font-bold text-primary flex items-center gap-1.5">
                        <BarChart3 className="w-4 h-4 text-teal" />
                        <span>Calibrated Risk Distribution</span>
                      </h3>
                      <p className="text-xs text-muted mt-1">
                        Distribution of posterior fraud risk probabilities across threshold boundaries
                      </p>
                    </div>
                  </div>

                  <div style={{ width: '100%', height: 240 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={batchProbBins} margin={{ top: 10, right: 10, left: -20, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                        <XAxis dataKey="range" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#cbd5e1' }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#cbd5e1' }} />
                        <Tooltip 
                          contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '6px', color: '#fff', fontSize: '12px' }}
                          cursor={{ fill: 'rgba(241, 245, 249, 0.6)' }}
                        />
                        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                          {batchProbBins.map((entry, index) => (
                            <Cell key={`prob-bin-${index}`} fill={entry.color} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            </>
          )}
        </>
      )}

      {/* VIEW MODE 2: ALL ACTIVITY (CUMULATIVE LEDGER) */}
      {viewMode === 'all' && (
        <>
          {/* Cumulative Ledger Metric Cards */}
          <div className="grid-cards mb-6">
            <MetricCard
              title="Cumulative Volume"
              value={loading ? '--' : (operationalStats?.total_transactions || 0)}
              icon={Inbox}
              iconColor="text-teal"
              iconBg="bg-teal-subtle"
              tooltip="Total transactions scored and persisted in database ledger"
              subtext={`${operationalStats?.approved_count || 0} approved, ${operationalStats?.review_count || 0} review, ${operationalStats?.block_count || 0} blocked`}
              loading={loading}
            />

            <MetricCard
              title="Avg Calibrated P(Fraud)"
              value={loading ? '--' : `${((operationalStats?.average_fraud_probability || 0) * 100).toFixed(2)}%`}
              icon={TrendingUp}
              iconColor="text-teal"
              iconBg="bg-teal-subtle"
              tooltip="Average calibrated fraud probability across all persisted transactions"
              subtext="Isotonic regression calibration"
              loading={loading}
            />

            <MetricCard
              title="Review Queue Volume"
              value={loading ? '--' : (operationalStats?.review_count || 0)}
              icon={ShieldAlert}
              iconColor="text-amber"
              iconBg="bg-amber-subtle"
              tooltip="Transactions routed to human investigation queue"
              subtext="Borderline uncertainty band"
              linkTo="/queue"
              linkText="Go to Queue"
              loading={loading}
            />

            <MetricCard
              title="Cumulative Ledger Value"
              value={loading ? '--' : `$${Number(operationalStats?.total_amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
              icon={DollarSign}
              iconColor="text-emerald"
              iconBg="bg-emerald-subtle"
              tooltip="Total monetary value processed across all historical records"
              subtext="Total transaction volume"
              loading={loading}
            />
          </div>

          {/* Cumulative Ledger Charts */}
          <div className="grid-2col mb-6">
            {/* Chart 1: All Activity Decision Distribution */}
            <div className="card p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-primary flex items-center gap-1.5">
                    <PieIcon className="w-4 h-4 text-teal" />
                    <span>Operational Decision Breakdown</span>
                  </h3>
                  <p className="text-xs text-muted mt-1">
                    Cumulative proportion of automated decisions across all recorded activity
                  </p>
                </div>
                <span className="text-xs font-mono text-muted bg-slate-100 px-2 py-0.5 rounded">
                  {operationalStats?.total_transactions || 0} Total
                </span>
              </div>

              <div style={{ width: '100%', height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={allDecisionData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={55}
                      outerRadius={80}
                      paddingAngle={3}
                    >
                      {allDecisionData.map((entry, index) => (
                        <Cell key={`all-pie-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '6px', color: '#fff', fontSize: '12px' }}
                      formatter={(val, name) => [`${val} transactions`, name]}
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

            {/* Chart 2: All Activity Risk Tier Distribution */}
            <div className="card p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-primary flex items-center gap-1.5">
                    <BarChart3 className="w-4 h-4 text-teal" />
                    <span>Calibrated Risk Distribution</span>
                  </h3>
                  <p className="text-xs text-muted mt-1">
                    Empirical distribution of posterior probabilities across policy boundaries
                  </p>
                </div>
              </div>

              <div style={{ width: '100%', height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={allProbBins} margin={{ top: 10, right: 10, left: -20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                    <XAxis dataKey="range" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#cbd5e1' }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#cbd5e1' }} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '6px', color: '#fff', fontSize: '12px' }}
                      cursor={{ fill: 'rgba(241, 245, 249, 0.6)' }}
                    />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {allProbBins.map((entry, index) => (
                        <Cell key={`all-bin-${index}`} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Cost-Sensitive Financial Decision Engine Specification */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Scale className="w-5 h-5 text-teal" />
            <h3 className="text-sm font-bold text-primary">Cost-Sensitive Decision Policy Architecture</h3>
          </div>
          <span className="badge badge-success font-mono text-xs">MODEL: xgb-cost-v1</span>
        </div>

        <p className="text-xs text-secondary leading-relaxed mb-4">
          Standard accuracy-maximizing models treat false positives and false negatives symmetrically. 
          In high-volume payment processing, financial losses are heavily asymmetric:
        </p>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-5">
          <div className="p-3 bg-slate-50 border border-slate-200 rounded">
            <span className="text-xs font-semibold text-muted uppercase block mb-1">Cost of False Negative ($C_FN$)</span>
            <div className="text-lg font-bold font-mono text-red">$100.00</div>
            <p className="text-xs text-muted mt-1">Direct monetary chargeback loss from undetected fraud.</p>
          </div>

          <div className="p-3 bg-slate-50 border border-slate-200 rounded">
            <span className="text-xs font-semibold text-muted uppercase block mb-1">Cost of False Positive ($C_FP$)</span>
            <div className="text-lg font-bold font-mono text-amber">$25.00</div>
            <p className="text-xs text-muted mt-1">Cardholder friction, verification overhead, churn risk.</p>
          </div>

          <div className="p-3 bg-slate-50 border border-slate-200 rounded">
            <span className="text-xs font-semibold text-muted uppercase block mb-1">Human Review Cost ($C_Review$)</span>
            <div className="text-lg font-bold font-mono text-teal">$5.00</div>
            <p className="text-xs text-muted mt-1">Operator investigation salary and manual triage cost.</p>
          </div>

          <div className="p-3 bg-slate-50 border border-slate-200 rounded">
            <span className="text-xs font-semibold text-muted uppercase block mb-1">Review Capacity Cap</span>
            <div className="text-lg font-bold font-mono text-primary">&le; 5.0%</div>
            <p className="text-xs text-muted mt-1">Strict ceiling limiting human queue triage capacity.</p>
          </div>
        </div>

        <div className="p-3 bg-teal-50 border border-teal-200 rounded text-xs text-teal-900 flex justify-between items-center">
          <span>Production Thresholds: <strong>τ_rev = 0.0420</strong>, <strong>τ_blk = 0.7539</strong> with Isotonic calibration.</span>
          <span className="font-mono text-xs">Expected Cost Minimizer</span>
        </div>
      </div>
    </div>
  );
}
