import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { healthApi, reviewQueueApi, monitoringApi, transactionsApi } from '../api/client';
import MetricCard from '../components/MetricCard';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import CaseDetailsModal from '../components/CaseDetailsModal';
import { 
  Inbox, 
  Activity, 
  ShieldCheck, 
  ArrowRight, 
  AlertCircle, 
  Layers, 
  BarChart3, 
  TrendingUp, 
  FileCheck2, 
  RotateCw, 
  ExternalLink, 
  Loader2,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  Search,
  Calendar
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell
} from 'recharts';

const RISK_COLORS = {
  APPROVE: '#10b981',
  REVIEW: '#f59e0b',
  BLOCK: '#ef4444',
  HIGH: '#ef4444',
  MEDIUM: '#f59e0b',
  LOW: '#10b981',
};

export default function OverviewPage() {
  const [viewMode, setViewMode] = useState('batch'); // 'batch' | 'all'
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [selectedCase, setSelectedCase] = useState(null);

  // Batch Filter & Search State
  const [batchSearch, setBatchSearch] = useState('');
  const [batchDecisionFilter, setBatchDecisionFilter] = useState('ALL');

  // Backend Data State
  const [latestBatch, setLatestBatch] = useState(null);
  const [operationalStats, setOperationalStats] = useState(null);
  const [recentTransactions, setRecentTransactions] = useState([]);
  const [summaryData, setSummaryData] = useState({
    health: null,
    queueTotal: null,
    pendingTotal: null,
    reviewedTotal: null,
    queueItems: [],
    latestDrift: null,
    driftHistory: [],
  });

  const fetchOverviewData = async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true);
    else setLoading(true);
    setError('');

    try {
      const [
        batchRes,
        statsRes,
        recentRes,
        healthRes,
        queueAllRes,
        queuePendingRes,
        queueReviewedRes,
        driftRes,
      ] = await Promise.allSettled([
        transactionsApi.getLatestBatch(),
        transactionsApi.getOperationalStats(),
        transactionsApi.getRecent({ limit: 10 }),
        healthApi.getReady(),
        reviewQueueApi.getQueue({ limit: 50 }),
        reviewQueueApi.getQueue({ limit: 1, statusFilter: 'PENDING' }),
        reviewQueueApi.getQueue({ limit: 1, statusFilter: 'REVIEWED' }),
        monitoringApi.listReports({ limit: 5 }),
      ]);

      if (batchRes.status === 'fulfilled') {
        setLatestBatch(batchRes.value);
      } else {
        setLatestBatch(null);
      }

      if (statsRes.status === 'fulfilled') {
        setOperationalStats(statsRes.value);
      }

      if (recentRes.status === 'fulfilled') {
        setRecentTransactions(recentRes.value.items || []);
      }

      setSummaryData({
        health: healthRes.status === 'fulfilled' ? healthRes.value : null,
        queueTotal: queueAllRes.status === 'fulfilled' ? queueAllRes.value.total : 0,
        pendingTotal: queuePendingRes.status === 'fulfilled' ? queuePendingRes.value.total : 0,
        reviewedTotal: queueReviewedRes.status === 'fulfilled' ? queueReviewedRes.value.total : 0,
        queueItems: queueAllRes.status === 'fulfilled' ? (queueAllRes.value.items || []) : [],
        latestDrift: driftRes.status === 'fulfilled' && driftRes.value.items?.length > 0 ? driftRes.value.items[0] : null,
        driftHistory: driftRes.status === 'fulfilled' ? (driftRes.value.items || []) : [],
      });
    } catch {
      setError('Failed to fetch operational dashboard metrics from the backend API.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchOverviewData();
  }, []);

  // ---------------------------------------------------------------------------
  // BATCH VIEW DATA COMPUTATIONS
  // ---------------------------------------------------------------------------
  const batchDecisionChartData = useMemo(() => {
    if (!latestBatch?.summary) return [];
    const s = latestBatch.summary;
    return [
      { name: 'Approve (Low Risk)', count: s.approved_count, color: RISK_COLORS.APPROVE, percent: s.total_processed > 0 ? (s.approved_count / s.total_processed) * 100 : 0 },
      { name: 'Review Queue', count: s.review_count, color: RISK_COLORS.REVIEW, percent: s.total_processed > 0 ? (s.review_count / s.total_processed) * 100 : 0 },
      { name: 'Block (High Risk)', count: s.block_count, color: RISK_COLORS.BLOCK, percent: s.total_processed > 0 ? (s.block_count / s.total_processed) * 100 : 0 },
    ].filter(item => item.count >= 0);
  }, [latestBatch]);

  const batchProbabilityBinsData = useMemo(() => {
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

  const filteredBatchItems = useMemo(() => {
    if (!latestBatch?.items) return [];
    return latestBatch.items.filter((item) => {
      // Decision filter
      if (batchDecisionFilter !== 'ALL' && item.decision !== batchDecisionFilter) {
        return false;
      }
      // Search filter
      if (batchSearch.trim()) {
        const query = batchSearch.toLowerCase().trim();
        const idMatch = (item.external_id || '').toLowerCase().includes(query);
        const amountMatch = String(item.amount || '').includes(query);
        return idMatch || amountMatch;
      }
      return true;
    });
  }, [latestBatch, batchDecisionFilter, batchSearch]);

  // ---------------------------------------------------------------------------
  // ALL ACTIVITY VIEW DATA COMPUTATIONS
  // ---------------------------------------------------------------------------
  const allDecisionChartData = useMemo(() => {
    if (!operationalStats) return [];
    const s = operationalStats;
    return [
      { name: 'Approve', count: s.approved_count, color: RISK_COLORS.APPROVE },
      { name: 'Review Queue', count: s.review_count, color: RISK_COLORS.REVIEW },
      { name: 'Block', count: s.block_count, color: RISK_COLORS.BLOCK },
    ];
  }, [operationalStats]);

  const allQueueProbabilityBinsData = useMemo(() => {
    if (!summaryData.queueItems || summaryData.queueItems.length === 0) return [];
    const bins = [
      { range: '0.04-0.10', count: 0 },
      { range: '0.10-0.25', count: 0 },
      { range: '0.25-0.50', count: 0 },
      { range: '0.50-0.75', count: 0 },
    ];
    summaryData.queueItems.forEach((item) => {
      const p = item.fraud_probability;
      if (typeof p === 'number') {
        if (p < 0.10) bins[0].count += 1;
        else if (p < 0.25) bins[1].count += 1;
        else if (p < 0.50) bins[2].count += 1;
        else bins[3].count += 1;
      }
    });
    return bins;
  }, [summaryData.queueItems]);

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header flex justify-between items-start flex-wrap gap-4">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Layers className="w-6 h-6 text-teal" />
            <span>Fraud Risk Dashboard</span>
          </h1>
          <p className="page-subtitle">
            Enterprise fraud risk monitoring, batch scoring telemetry, and operational decision analytics.
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {/* Mode Switcher: Latest Uploaded Batch vs All Activity */}
          <div className="button-group">
            <button
              type="button"
              className={`filter-btn flex items-center gap-1.5 ${viewMode === 'batch' ? 'active' : ''}`}
              onClick={() => setViewMode('batch')}
            >
              <FileSpreadsheet className="w-3.5 h-3.5" />
              <span>Latest Batch</span>
            </button>
            <button
              type="button"
              className={`filter-btn flex items-center gap-1.5 ${viewMode === 'all' ? 'active' : ''}`}
              onClick={() => setViewMode('all')}
            >
              <Activity className="w-3.5 h-3.5" />
              <span>All Activity</span>
            </button>
          </div>

          <button
            type="button"
            className="btn btn-secondary flex items-center gap-1.5"
            onClick={() => fetchOverviewData(true)}
            disabled={loading || refreshing}
          >
            <RotateCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert-error mb-6">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* =======================================================================
          VIEW MODE 1: LATEST UPLOADED BATCH
          ======================================================================= */}
      {viewMode === 'batch' && (
        <>
          {loading ? (
            <div className="card p-12 text-center flex flex-col items-center justify-center">
              <Loader2 className="w-8 h-8 animate-spin text-teal mb-3" />
              <p className="text-sm font-semibold text-primary">Loading Batch Risk Telemetry...</p>
              <p className="text-xs text-muted mt-1">Retrieving latest analyzed transaction records</p>
            </div>
          ) : !latestBatch ? (
            /* EMPTY STATE WHEN NO BATCH HAS BEEN ANALYZED */
            <div className="card p-12 text-center">
              <EmptyState
                icon={FileSpreadsheet}
                title="No Transaction Batch Analyzed Yet"
                description="Upload a CSV file containing transactions on the Transaction Analysis page to evaluate calibrated fraud probabilities and inspect batch risk distributions here."
                className="py-6"
              />
              <div className="mt-6 flex justify-center gap-3">
                <Link to="/scoring" className="btn btn-primary flex items-center gap-1.5">
                  <FileSpreadsheet className="w-4 h-4" />
                  <span>Go to Batch CSV Analysis</span>
                </Link>
                <button
                  type="button"
                  className="btn btn-secondary flex items-center gap-1.5"
                  onClick={() => setViewMode('all')}
                >
                  <Activity className="w-4 h-4" />
                  <span>View Cumulative Operational Activity</span>
                </button>
              </div>
            </div>
          ) : (
            /* BATCH DASHBOARD CONTENT */
            <>
              {/* Batch Metadata Header Card */}
              <div className="card p-4 mb-6 bg-slate-50 border-slate-200">
                <div className="flex justify-between items-center flex-wrap gap-4 text-xs">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="badge badge-success font-bold font-mono">LATEST BATCH</span>
                    <div>
                      <span className="text-muted block">Batch Identifier</span>
                      <span className="font-mono font-bold text-primary">{latestBatch.summary.batch_id}</span>
                    </div>
                    <div className="border-l border-slate-200 pl-3">
                      <span className="text-muted block">Source File</span>
                      <span className="font-medium text-primary flex items-center gap-1">
                        <FileSpreadsheet className="w-3.5 h-3.5 text-teal" />
                        <span>{latestBatch.summary.filename}</span>
                      </span>
                    </div>
                    <div className="border-l border-slate-200 pl-3">
                      <span className="text-muted block">Analyzed At</span>
                      <span className="font-medium text-secondary flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5 text-muted" />
                        <span>{new Date(latestBatch.summary.created_at).toLocaleString()}</span>
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 border-l border-slate-200 pl-4">
                    <div>
                      <span className="text-muted block">Total Batch Volume</span>
                      <span className="font-mono font-bold text-primary text-sm">
                        ${Number(latestBatch.summary.total_amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </div>
                    <Link to="/scoring" className="btn btn-secondary btn-xs flex items-center gap-1">
                      <span>Upload New Batch</span>
                      <ArrowRight className="w-3 h-3" />
                    </Link>
                  </div>
                </div>
              </div>

              {/* 5 Primary KPI Cards for Batch */}
              <div className="grid-cards mb-6">
                {/* Metric 1: Processed Volume */}
                <MetricCard
                  title="Batch Processed"
                  value={`${latestBatch.summary.total_processed} / ${latestBatch.summary.total_submitted}`}
                  icon={Layers}
                  iconColor="text-teal"
                  iconBg="bg-teal-subtle"
                  tooltip="Total transactions ingested and evaluated by the calibrated XGBoost model"
                  subtext={
                    latestBatch.summary.total_submitted > 0
                      ? `${Math.round((latestBatch.summary.total_processed / latestBatch.summary.total_submitted) * 100)}% successful inference`
                      : 'Complete batch'
                  }
                  loading={false}
                />

                {/* Metric 2: Auto-Approved */}
                <MetricCard
                  title="Auto-Approved (Low Risk)"
                  value={latestBatch.summary.approved_count}
                  icon={CheckCircle2}
                  iconColor="text-emerald"
                  iconBg="bg-emerald-subtle"
                  tooltip="Immediate frictionless settlement under cost-sensitive policy (P < 0.0420)"
                  subtext={
                    latestBatch.summary.total_processed > 0
                      ? `${((latestBatch.summary.approved_count / latestBatch.summary.total_processed) * 100).toFixed(1)}% of batch volume`
                      : 'P < 0.0420'
                  }
                  loading={false}
                />

                {/* Metric 3: Flagged for Review */}
                <MetricCard
                  title="Routed to Review Queue"
                  value={latestBatch.summary.review_count}
                  icon={Inbox}
                  iconColor="text-amber"
                  iconBg="bg-amber-subtle"
                  tooltip="Borderline cases routed to human operators under the 5% capacity constraint (0.0420 ≤ P < 0.7539)"
                  subtext="Borderline human triage"
                  linkTo="/queue"
                  linkText="Open Queue"
                  loading={false}
                />

                {/* Metric 4: Auto-Blocked */}
                <MetricCard
                  title="Auto-Blocked (High Risk)"
                  value={latestBatch.summary.block_count}
                  icon={AlertTriangle}
                  iconColor="text-red"
                  iconBg="bg-red-subtle"
                  tooltip="Automated transaction decline for high-confidence fraud risk (P ≥ 0.7539)"
                  subtext={
                    latestBatch.summary.total_processed > 0
                      ? `${((latestBatch.summary.block_count / latestBatch.summary.total_processed) * 100).toFixed(1)}% blocked`
                      : 'P ≥ 0.7539'
                  }
                  loading={false}
                />

                {/* Metric 5: Average Posterior Fraud Probability */}
                <MetricCard
                  title="Mean Fraud Probability"
                  value={`${(latestBatch.summary.average_fraud_probability * 100).toFixed(2)}%` }
                  icon={TrendingUp}
                  iconColor="text-teal"
                  iconBg="bg-teal-subtle"
                  tooltip="Batch-wide mean calibrated fraud probability derived via Isotonic regression"
                  subtext="Isotonic calibrated risk"
                  loading={false}
                />
              </div>

              {/* Visualizations Section: Decision Breakdown & P(Fraud) Histogram */}
              <div className="grid-2col mb-6">
                {/* Chart 1: Batch Decision Composition */}
                <div className="card p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-sm font-bold text-primary flex items-center gap-1.5">
                        <BarChart3 className="w-4 h-4 text-teal" />
                        <span>Batch Policy Decision Breakdown</span>
                      </h3>
                      <p className="text-xs text-muted mt-1">
                        Operational distribution across Approve, Review, and Block tiers
                      </p>
                    </div>
                    <span className="text-xs font-mono text-muted bg-slate-100 px-2 py-0.5 rounded">
                      {latestBatch.summary.total_processed} Scored
                    </span>
                  </div>

                  <div style={{ width: '100%', height: 230 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={batchDecisionChartData} margin={{ top: 10, right: 10, left: -20, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                        <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#cbd5e1' }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#cbd5e1' }} />
                        <Tooltip 
                          contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '6px', color: '#fff', fontSize: '12px' }}
                          formatter={(value, name, props) => [`${value} cases (${props.payload.percent?.toFixed(1) || 0}%)`, 'Volume']}
                          cursor={{ fill: 'rgba(241, 245, 249, 0.6)' }}
                        />
                        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                          {batchDecisionChartData.map((entry, index) => (
                            <Cell key={`batch-decision-cell-${index}`} fill={entry.color} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Chart 2: P(Fraud) Probability Deciles */}
                <div className="card p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-sm font-bold text-primary flex items-center gap-1.5">
                        <TrendingUp className="w-4 h-4 text-teal" />
                        <span>Posterior Probability Density</span>
                      </h3>
                      <p className="text-xs text-muted mt-1">
                        Empirical distribution of calibrated fraud probabilities in uploaded batch
                      </p>
                    </div>
                    <span className="text-xs font-mono text-muted bg-slate-100 px-2 py-0.5 rounded">
                      Risk Tiers
                    </span>
                  </div>

                  <div style={{ width: '100%', height: 230 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={batchProbabilityBinsData} margin={{ top: 10, right: 10, left: -20, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                        <XAxis dataKey="range" tick={{ fontSize: 10, fill: '#64748b' }} axisLine={{ stroke: '#cbd5e1' }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#cbd5e1' }} />
                        <Tooltip 
                          contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '6px', color: '#fff', fontSize: '12px' }}
                          cursor={{ fill: 'rgba(241, 245, 249, 0.6)' }}
                        />
                        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                          {batchProbabilityBinsData.map((entry, index) => (
                            <Cell key={`batch-bin-cell-${index}`} fill={entry.color} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              {/* Batch Transactions Ledger Table */}
              <div className="card mb-6">
                <div className="p-4 border-b border-slate-200 flex justify-between items-center flex-wrap gap-3">
                  <div>
                    <h3 className="text-sm font-bold text-primary flex items-center gap-2">
                      <FileSpreadsheet className="w-4 h-4 text-teal" />
                      <span>Uploaded Batch Transactions ({filteredBatchItems.length} of {latestBatch.items.length})</span>
                    </h3>
                    <p className="text-xs text-muted mt-0.5">
                      Row-level predictions evaluated against active production XGBoost baseline
                    </p>
                  </div>

                  {/* Search and Decision Filters */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="relative">
                      <Search className="w-3.5 h-3.5 text-muted absolute left-2.5 top-1/2 -translate-y-1/2" />
                      <input
                        type="text"
                        placeholder="Search ID or Amount..."
                        value={batchSearch}
                        onChange={(e) => setBatchSearch(e.target.value)}
                        className="form-input form-input-sm pl-8 font-mono text-xs w-48"
                      />
                    </div>

                    <div className="button-group">
                      <button
                        type="button"
                        className={`filter-btn ${batchDecisionFilter === 'ALL' ? 'active' : ''}`}
                        onClick={() => setBatchDecisionFilter('ALL')}
                      >
                        All
                      </button>
                      <button
                        type="button"
                        className={`filter-btn ${batchDecisionFilter === 'APPROVE' ? 'active' : ''}`}
                        onClick={() => setBatchDecisionFilter('APPROVE')}
                      >
                        Approve ({latestBatch.summary.approved_count})
                      </button>
                      <button
                        type="button"
                        className={`filter-btn ${batchDecisionFilter === 'REVIEW' ? 'active' : ''}`}
                        onClick={() => setBatchDecisionFilter('REVIEW')}
                      >
                        Review ({latestBatch.summary.review_count})
                      </button>
                      <button
                        type="button"
                        className={`filter-btn ${batchDecisionFilter === 'BLOCK' ? 'active' : ''}`}
                        onClick={() => setBatchDecisionFilter('BLOCK')}
                      >
                        Block ({latestBatch.summary.block_count})
                      </button>
                    </div>
                  </div>
                </div>

                <div className="table-responsive max-h-96 overflow-y-auto">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Transaction ID</th>
                        <th>Amount</th>
                        <th>Calibrated P(Fraud)</th>
                        <th>Risk Tier</th>
                        <th>Decision Policy</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredBatchItems.length === 0 ? (
                        <tr>
                          <td colSpan={7} className="table-empty-cell">
                            <EmptyState
                              icon={Search}
                              title="No Transactions Match Filters"
                              description="No batch transactions match the active search query or decision filter."
                              className="py-6"
                            />
                          </td>
                        </tr>
                      ) : (
                        filteredBatchItems.slice(0, 50).map((tx, idx) => (
                          <tr key={tx.external_id || idx}>
                            <td className="font-mono text-xs text-muted">{idx + 1}</td>
                            <td>
                              <span className="font-mono text-xs font-semibold text-primary">{tx.external_id}</span>
                            </td>
                            <td>
                              <span className="font-mono font-semibold text-primary text-xs">
                                ${Number(tx.amount || 0).toFixed(2)}
                              </span>
                            </td>
                            <td>
                              <span className={`font-mono font-bold text-xs ${
                                tx.fraud_probability >= 0.75388
                                  ? 'text-red'
                                  : tx.fraud_probability >= 0.042
                                  ? 'text-amber'
                                  : 'text-teal'
                              }`}>
                                {(tx.fraud_probability * 100).toFixed(2)}%
                              </span>
                            </td>
                            <td>
                              <StatusBadge type="risk" value={tx.risk_level} />
                            </td>
                            <td>
                              <StatusBadge type="decision" value={tx.decision} />
                            </td>
                            <td>
                              <button
                                type="button"
                                onClick={() => setSelectedCase({
                                  transaction_id: tx.external_id,
                                  external_id: tx.external_id,
                                  amount: tx.amount,
                                  fraud_probability: tx.fraud_probability,
                                  raw_probability: tx.raw_probability,
                                  risk_level: tx.risk_level,
                                  decision: tx.decision,
                                  model_version: tx.model_version,
                                })}
                                className="btn btn-secondary btn-xs flex items-center gap-1 font-semibold"
                              >
                                <span>Inspect</span>
                                <ExternalLink className="w-3 h-3" />
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                {filteredBatchItems.length > 50 && (
                  <div className="p-3 bg-slate-50 border-t border-slate-200 text-center text-xs text-muted">
                    Displaying first 50 transactions of {filteredBatchItems.length}. Download complete results CSV from Transaction Analysis for full ledger.
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}

      {/* =======================================================================
          VIEW MODE 2: ALL ACTIVITY (OPERATIONAL CUMULATIVE VIEW)
          ======================================================================= */}
      {viewMode === 'all' && (
        <>
          {/* Primary KPI Metrics Grid */}
          <div className="grid-cards mb-6">
            {/* Metric 1: Pending Review Cases */}
            <MetricCard
              title="Fraud Review Queue (Pending)"
              value={loading ? '--' : summaryData.pendingTotal ?? 0}
              icon={Inbox}
              iconColor="text-amber"
              iconBg="bg-amber-subtle"
              tooltip="Transactions routed to human triage under the cost-sensitive 5% capacity constraint"
              subtext={
                summaryData.queueTotal !== null 
                  ? `${summaryData.queueTotal} total items in queue ledger`
                  : 'Borderline triage queue'
              }
              linkTo="/queue"
              linkText="Open Queue"
              loading={loading}
            />

            {/* Metric 2: Adjudicated Feedback */}
            <MetricCard
              title="Analyst Adjudications"
              value={loading ? '--' : summaryData.reviewedTotal ?? 0}
              icon={FileCheck2}
              iconColor="text-teal"
              iconBg="bg-teal-subtle"
              tooltip="Transactions in the review queue with completed operator adjudications"
              subtext="Human triage completed"
              linkTo="/feedback"
              linkText="Feedback Analytics"
              loading={loading}
            />

            {/* Metric 3: Latest Data Drift Status */}
            <MetricCard
              title="Model Drift Health"
              value={
                loading ? (
                  '--'
                ) : summaryData.latestDrift ? (
                  summaryData.latestDrift.status
                ) : (
                  'No Reports'
                )
              }
              icon={Activity}
              iconColor={
                summaryData.latestDrift?.status === 'CRITICAL'
                  ? 'text-red'
                  : summaryData.latestDrift?.status === 'WARNING'
                  ? 'text-amber'
                  : 'text-emerald'
              }
              iconBg={
                summaryData.latestDrift?.status === 'CRITICAL'
                  ? 'bg-red-subtle'
                  : summaryData.latestDrift?.status === 'WARNING'
                  ? 'bg-amber-subtle'
                  : 'bg-emerald-subtle'
              }
              tooltip="Population Stability Index (PSI) computed against the reference training baseline"
              subtext={
                summaryData.latestDrift
                  ? `Max PSI: ${summaryData.latestDrift.metric_value?.toFixed(4) || '0.0000'}`
                  : 'Run drift evaluation'
              }
              linkTo="/monitoring"
              linkText="View Reports"
              loading={loading}
            />

            {/* Metric 4: Cumulative System Transactions */}
            <MetricCard
              title="Historical Volume"
              value={loading ? '--' : operationalStats ? operationalStats.total_transactions : summaryData.queueTotal ?? 0}
              icon={Layers}
              iconColor="text-teal"
              iconBg="bg-teal-subtle"
              tooltip="Total transactions persisted in the operational database"
              subtext={
                operationalStats
                  ? `$${Number(operationalStats.total_amount || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })} volume`
                  : 'Ingested records'
              }
              linkTo="/scoring"
              linkText="Score New"
              loading={loading}
            />
          </div>

          {/* Visualizations Section */}
          <div className="grid-2col mb-6">
            {/* Chart 1: Review Queue Risk Distribution */}
            <div className="card p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-primary flex items-center gap-1.5">
                    <BarChart3 className="w-4 h-4 text-teal" />
                    <span>Operational Risk Composition</span>
                  </h3>
                  <p className="text-xs text-muted mt-1">
                    Cumulative breakdown of decisions across all operational transactions
                  </p>
                </div>
                <span className="text-xs font-mono text-muted bg-slate-100 px-2 py-0.5 rounded">
                  {operationalStats ? `${operationalStats.total_transactions} Total` : 'Ledger'}
                </span>
              </div>

              {!operationalStats || operationalStats.total_transactions === 0 ? (
                <EmptyState
                  icon={Inbox}
                  title="No Ingested Transactions"
                  description="No transactions have been persisted in the operational database yet."
                  className="py-10"
                />
              ) : (
                <div style={{ width: '100%', height: 230 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={allDecisionChartData} margin={{ top: 10, right: 10, left: -20, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                      <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#cbd5e1' }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#cbd5e1' }} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '6px', color: '#fff', fontSize: '12px' }}
                        cursor={{ fill: 'rgba(241, 245, 249, 0.6)' }}
                      />
                      <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                        {allDecisionChartData.map((entry, index) => (
                          <Cell key={`all-cell-${index}`} fill={entry.color} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            {/* Chart 2: Fraud Probability Distribution in Queue */}
            <div className="card p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-primary flex items-center gap-1.5">
                    <TrendingUp className="w-4 h-4 text-teal" />
                    <span>Queue Calibrated P(Fraud)</span>
                  </h3>
                  <p className="text-xs text-muted mt-1">
                    Posterior probability density of transactions in review queue
                  </p>
                </div>
                <span className="text-xs font-mono text-muted bg-slate-100 px-2 py-0.5 rounded">
                  Queue Deciles
                </span>
              </div>

              {summaryData.queueItems.length === 0 ? (
                <EmptyState
                  icon={BarChart3}
                  title="Queue is Empty"
                  description="No queued transactions available to construct probability distribution buckets."
                  className="py-10"
                />
              ) : (
                <div style={{ width: '100%', height: 230 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={allQueueProbabilityBinsData} margin={{ top: 10, right: 10, left: -20, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                      <XAxis dataKey="range" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#cbd5e1' }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#cbd5e1' }} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '6px', color: '#fff', fontSize: '12px' }}
                        cursor={{ fill: 'rgba(241, 245, 249, 0.6)' }}
                      />
                      <Bar dataKey="count" fill="#0d9488" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          {/* Recent Operational Transactions Table */}
          <div className="card mb-6">
            <div className="p-4 border-b border-slate-200 flex justify-between items-center flex-wrap gap-2">
              <div>
                <h3 className="text-sm font-bold text-primary flex items-center gap-1.5">
                  <Activity className="w-4 h-4 text-teal" />
                  <span>Recent Operational Transactions</span>
                </h3>
                <p className="text-xs text-muted mt-0.5">
                  Chronological audit of recently ingested financial transactions
                </p>
              </div>
              <Link to="/queue" className="btn btn-secondary btn-sm flex items-center gap-1">
                <span>View Full Review Queue</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Transaction ID</th>
                    <th>Amount</th>
                    <th>Calibrated P(Fraud)</th>
                    <th>Risk Tier</th>
                    <th>Decision</th>
                    <th>Timestamp</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={7} className="table-loading-cell">
                        <div className="flex items-center justify-center gap-2 text-muted text-xs">
                          <Loader2 className="w-4 h-4 animate-spin text-teal" />
                          <span>Loading operational transactions...</span>
                        </div>
                      </td>
                    </tr>
                  ) : recentTransactions.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="table-empty-cell">
                        <EmptyState
                          icon={Activity}
                          title="No Recent Transactions"
                          description="No transactions have been ingested yet."
                          className="py-6"
                        />
                      </td>
                    </tr>
                  ) : (
                    recentTransactions.map((tx) => (
                      <tr key={tx.id || tx.external_id}>
                        <td>
                          <span className="font-mono text-xs font-semibold text-primary">{tx.external_id}</span>
                        </td>
                        <td>
                          <span className="font-mono font-semibold text-primary text-xs">
                            ${Number(tx.amount || 0).toFixed(2)}
                          </span>
                        </td>
                        <td>
                          <span className={`font-mono font-bold text-xs ${
                            tx.fraud_probability >= 0.75388
                              ? 'text-red'
                              : tx.fraud_probability >= 0.042
                              ? 'text-amber'
                              : 'text-teal'
                          }`}>
                            {(tx.fraud_probability * 100).toFixed(2)}%
                          </span>
                        </td>
                        <td>
                          <StatusBadge type="risk" value={tx.risk_level} />
                        </td>
                        <td>
                          <StatusBadge type="decision" value={tx.decision} />
                        </td>
                        <td>
                          <span className="text-xs text-muted">
                            {tx.created_at ? new Date(tx.created_at).toLocaleString() : 'Recent'}
                          </span>
                        </td>
                        <td>
                          <button
                            type="button"
                            onClick={() => setSelectedCase({
                              transaction_id: tx.id,
                              external_id: tx.external_id,
                              amount: tx.amount,
                              fraud_probability: tx.fraud_probability,
                              risk_level: tx.risk_level,
                              decision: tx.decision,
                            })}
                            className="btn btn-secondary btn-xs flex items-center gap-1 font-semibold"
                          >
                            <span>Inspect</span>
                            <ExternalLink className="w-3 h-3" />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Operational Policy Reference Card (Universal Across Views) */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h3 className="text-sm font-bold text-primary flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-teal" />
            <span>Active Cost-Sensitive Policy Thresholds (xgb-cost-v1)</span>
          </h3>
          <span className="badge badge-success font-mono text-xs">ENFORCED IN PRODUCTION</span>
        </div>
        <p className="text-xs text-secondary mb-4 leading-relaxed">
          Operational policy weights financial losses: False Negative fraud loss ($100.00 default / transaction amount) against operator investigation overhead ($5.00) and friction penalty ($25.00).
        </p>

        <div className="policy-matrix">
          <div className="policy-row">
            <div>
              <StatusBadge type="decision" value="APPROVE" />
            </div>
            <div className="text-xs text-secondary">
              <strong className="text-primary font-medium">Instant Settlement:</strong> Expected fraud loss is below human investigation overhead threshold.
            </div>
            <div className="policy-threshold-col">P &lt; 0.0420</div>
          </div>

          <div className="policy-row">
            <div>
              <StatusBadge type="decision" value="REVIEW" />
            </div>
            <div className="text-xs text-secondary">
              <strong className="text-primary font-medium">Operator Triage:</strong> Borderline cases routed to review queue under 5.0% capacity constraint.
            </div>
            <div className="policy-threshold-col">0.0420 ≤ P &lt; 0.7539</div>
          </div>

          <div className="policy-row">
            <div>
              <StatusBadge type="decision" value="BLOCK" />
            </div>
            <div className="text-xs text-secondary">
              <strong className="text-primary font-medium">Automated Block:</strong> High-confidence fraud risk warrants immediate cardholder protection.
            </div>
            <div className="policy-threshold-col">P ≥ 0.7539</div>
          </div>
        </div>
      </div>

      {/* Case Details Modal for Direct Dashboard Triage */}
      {selectedCase && (
        <CaseDetailsModal
          transaction={selectedCase}
          caseData={selectedCase}
          onClose={() => setSelectedCase(null)}
          onAdjudicationSuccess={() => {
            setSelectedCase(null);
            fetchOverviewData(true);
          }}
        />
      )}
    </div>
  );
}
