import { useState, useEffect, useCallback } from 'react';
import { transactionsApi, reviewQueueApi, monitoringApi } from '../api/client';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import CaseDetailsModal from '../components/CaseDetailsModal';
import { 
  History, 
  RotateCw, 
  AlertCircle, 
  Search, 
  ExternalLink,
  Loader2,
  Filter,
  Layers,
  FileSpreadsheet,
  Info
} from 'lucide-react';

export default function AuditHistoryPage() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [auditEvents, setAuditEvents] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCase, setSelectedCase] = useState(null);

  // Filters
  const [eventTypeFilter, setEventTypeFilter] = useState('ALL'); // 'ALL' | 'TRANSACTION' | 'ADJUDICATION' | 'DRIFT'
  const [decisionFilter, setDecisionFilter] = useState('ALL');   // 'ALL' | 'APPROVE' | 'REVIEW' | 'BLOCK'
  const [batchScope, setBatchScope] = useState('ALL');          // 'ALL' | 'LATEST_BATCH'
  const [latestBatchId, setLatestBatchId] = useState(() => localStorage.getItem('fraud_latest_batch_id') || '');

  // Load latest batch ID
  useEffect(() => {
    async function checkLatestBatch() {
      try {
        const batchRes = await transactionsApi.getLatestBatch();
        if (batchRes?.summary?.batch_id) {
          setLatestBatchId(batchRes.summary.batch_id);
          localStorage.setItem('fraud_latest_batch_id', batchRes.summary.batch_id);
        }
      } catch {
        // No batch uploaded yet
      }
    }
    checkLatestBatch();
  }, []);

  const fetchAuditTrail = useCallback(async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true);
    else setLoading(true);
    setError('');

    try {
      const activeBatchId = batchScope === 'LATEST_BATCH' ? latestBatchId : null;

      const [txRes, queueRes, driftRes] = await Promise.allSettled([
        transactionsApi.getRecent({ 
          limit: 100, 
          decision: decisionFilter !== 'ALL' ? decisionFilter : null,
          batch_id: activeBatchId || undefined,
        }),
        reviewQueueApi.getQueue({ 
          limit: 100,
          batch_id: activeBatchId || undefined,
        }),
        monitoringApi.listReports({ limit: 20 }),
      ]);

      const events = [];

      // 1. Persisted operational transaction scorings (includes uploaded batch & single scoring)
      if (txRes.status === 'fulfilled' && txRes.value?.items) {
        txRes.value.items.forEach((tx) => {
          events.push({
            id: `TX-${tx.id}`,
            type: 'TRANSACTION_SCORING',
            entity_id: tx.external_id,
            transaction_id: tx.id,
            amount: tx.amount,
            batch_id: tx.batch_id,
            action: `Model Scoring (${tx.decision})`,
            decision: tx.decision,
            risk_level: tx.risk_level,
            probability: tx.calibrated_probability,
            timestamp: tx.created_at,
            operator: tx.batch_id ? 'Batch Ingestion' : 'Inference API',
            rawItem: {
              transaction_id: tx.id,
              external_id: tx.external_id,
              amount: tx.amount,
              fraud_probability: tx.calibrated_probability,
              decision: tx.decision,
              risk_level: tx.risk_level,
              batch_id: tx.batch_id,
              transaction_created_at: tx.created_at,
            },
          });
        });
      }

      // 2. Human adjudications recorded in review queue
      if (queueRes.status === 'fulfilled' && queueRes.value?.items) {
        queueRes.value.items.forEach((item) => {
          if (item.feedback_count > 0 && item.latest_feedback_decision) {
            events.push({
              id: `FB-${item.external_id}`,
              type: 'OPERATOR_ADJUDICATION',
              entity_id: item.external_id,
              transaction_id: item.transaction_id,
              amount: item.amount,
              batch_id: item.batch_id,
              action: `Human Adjudication (${item.latest_feedback_decision})`,
              decision: item.latest_feedback_decision,
              risk_level: item.risk_level,
              probability: item.fraud_probability,
              timestamp: item.transaction_created_at,
              operator: item.latest_feedback_verified ? 'Admin Verified' : 'Operator Submission',
              rawItem: item,
            });
          }
        });
      }

      // 3. Statistical drift monitoring evaluation runs (only if not filtering by batch)
      if (batchScope === 'ALL' && driftRes.status === 'fulfilled' && driftRes.value?.items) {
        driftRes.value.items.forEach((report) => {
          events.push({
            id: `DRIFT-${report.id.slice(0, 8)}`,
            type: 'DRIFT_ANALYSIS',
            entity_id: report.id,
            amount: null,
            batch_id: null,
            action: `KS/PSI Statistical Drift Evaluation (${report.status})`,
            decision: report.status,
            risk_level: report.status === 'CRITICAL' ? 'HIGH' : report.status === 'WARNING' ? 'MEDIUM' : 'LOW',
            probability: null,
            timestamp: report.created_at,
            operator: 'System Administrator',
            rawItem: null,
          });
        });
      }

      // Sort deterministically by descending recency
      events.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      setAuditEvents(events);
    } catch {
      setError('Failed to fetch historical audit records.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [batchScope, latestBatchId, decisionFilter]);

  useEffect(() => {
    fetchAuditTrail();
  }, [fetchAuditTrail]);

  // Client-side filtering by event type and search query
  const filteredEvents = auditEvents.filter((ev) => {
    if (eventTypeFilter === 'TRANSACTION' && ev.type !== 'TRANSACTION_SCORING') return false;
    if (eventTypeFilter === 'ADJUDICATION' && ev.type !== 'OPERATOR_ADJUDICATION') return false;
    if (eventTypeFilter === 'DRIFT' && ev.type !== 'DRIFT_ANALYSIS') return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      const matchId = String(ev.entity_id || '').toLowerCase().includes(q);
      const matchAction = String(ev.action || '').toLowerCase().includes(q);
      const matchOperator = String(ev.operator || '').toLowerCase().includes(q);
      const matchBatch = String(ev.batch_id || '').toLowerCase().includes(q);
      if (!matchId && !matchAction && !matchOperator && !matchBatch) return false;
    }
    return true;
  });

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <History className="w-6 h-6 text-teal" />
            <span>Decision & Operational Audit History</span>
          </h1>
          <p className="page-subtitle">
            Immutable chronological audit log of automated inference scores, human adjudications, and drift monitoring evaluations.
          </p>
        </div>

        <div className="header-actions">
          <button
            type="button"
            className="btn btn-secondary flex items-center gap-1.5"
            onClick={() => fetchAuditTrail(true)}
            disabled={loading || refreshing}
          >
            <RotateCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Scope Info Alert */}
      <div className="p-3 bg-slate-100 border border-slate-200 rounded-md text-xs text-secondary mb-6 flex items-start justify-between gap-2">
        <div className="flex items-start gap-2">
          <Info className="w-4 h-4 text-teal flex-shrink-0 mt-0.5" />
          <div>
            <strong>Operational Audit Ledger:</strong> Captures all persisted model predictions (both real-time API scores and uploaded CSV batches), operator triage adjudications, and KS/PSI statistical drift reports.
          </div>
        </div>
        {batchScope === 'LATEST_BATCH' && latestBatchId && (
          <span className="badge badge-neutral font-mono text-xs whitespace-nowrap">
            Batch: {latestBatchId}
          </span>
        )}
      </div>

      {error && (
        <div className="alert alert-error mb-6">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Audit Log Card */}
      <div className="card">
        {/* Table Search & Filter Toolbar */}
        <div className="table-header-bar flex-wrap gap-3">
          {/* Batch Scope */}
          <div className="flex items-center gap-1">
            <span className="text-xs text-muted font-medium flex items-center gap-1">
              <Layers className="w-3.5 h-3.5" /> Scope:
            </span>
            <div className="button-group">
              <button
                type="button"
                className={`filter-btn ${batchScope === 'ALL' ? 'active' : ''}`}
                onClick={() => setBatchScope('ALL')}
              >
                All Activity
              </button>
              <button
                type="button"
                className={`filter-btn ${batchScope === 'LATEST_BATCH' ? 'active' : ''}`}
                onClick={() => setBatchScope('LATEST_BATCH')}
                disabled={!latestBatchId}
                title={latestBatchId ? `Filter by batch ${latestBatchId}` : 'No recent batch found'}
              >
                <FileSpreadsheet className="w-3.5 h-3.5 inline mr-1" />
                Latest Batch
              </button>
            </div>
          </div>

          {/* Event Type Filter */}
          <div className="flex items-center gap-1">
            <span className="text-xs text-muted font-medium flex items-center gap-1">
              <Filter className="w-3.5 h-3.5" /> Type:
            </span>
            <div className="button-group">
              <button
                type="button"
                className={`filter-btn ${eventTypeFilter === 'ALL' ? 'active' : ''}`}
                onClick={() => setEventTypeFilter('ALL')}
              >
                All
              </button>
              <button
                type="button"
                className={`filter-btn ${eventTypeFilter === 'TRANSACTION' ? 'active' : ''}`}
                onClick={() => setEventTypeFilter('TRANSACTION')}
              >
                Scored
              </button>
              <button
                type="button"
                className={`filter-btn ${eventTypeFilter === 'ADJUDICATION' ? 'active' : ''}`}
                onClick={() => setEventTypeFilter('ADJUDICATION')}
              >
                Adjudicated
              </button>
              <button
                type="button"
                className={`filter-btn ${eventTypeFilter === 'DRIFT' ? 'active' : ''}`}
                onClick={() => setEventTypeFilter('DRIFT')}
              >
                Drift
              </button>
            </div>
          </div>

          {/* Decision Filter */}
          <div className="flex items-center gap-1">
            <span className="text-xs text-muted font-medium">Decision:</span>
            <select
              value={decisionFilter}
              onChange={(e) => setDecisionFilter(e.target.value)}
              className="form-input form-input-sm w-32"
            >
              <option value="ALL">All Decisions</option>
              <option value="APPROVE">APPROVE</option>
              <option value="REVIEW">REVIEW</option>
              <option value="BLOCK">BLOCK</option>
            </select>
          </div>

          {/* Search Box */}
          <div className="input-with-icon ml-auto">
            <Search className="input-icon" />
            <input
              type="text"
              placeholder="Search ID, action, batch, actor..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="form-input form-input-sm w-64 font-mono"
            />
          </div>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Event Type</th>
                <th>Entity Identifier</th>
                <th>Amount</th>
                <th>Action & Summary</th>
                <th>Outcome / Status</th>
                <th>Actor / Origin</th>
                <th>Timestamp</th>
                <th className="text-right">Inspect</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="table-loading-cell">
                    <Loader2 className="w-6 h-6 animate-spin text-teal mx-auto mb-2" />
                    <p className="text-xs text-muted">Loading audit records from database...</p>
                  </td>
                </tr>
              ) : filteredEvents.length === 0 ? (
                <tr>
                  <td colSpan={8} className="table-empty-cell">
                    <EmptyState
                      icon={History}
                      title="No Audit Records Found"
                      description={
                        batchScope === 'LATEST_BATCH'
                          ? 'No audit records match the selected criteria for the latest batch.'
                          : 'No matching decisions or operational events have been recorded yet.'
                      }
                      className="py-8"
                    />
                  </td>
                </tr>
              ) : (
                filteredEvents.map((ev) => (
                  <tr key={ev.id} className="hover-row">
                    <td>
                      <span className="badge badge-neutral text-xs font-mono">
                        {ev.type === 'TRANSACTION_SCORING'
                          ? 'SCORING'
                          : ev.type === 'OPERATOR_ADJUDICATION'
                          ? 'ADJUDICATION'
                          : 'DRIFT'}
                      </span>
                    </td>
                    <td>
                      <div className="flex flex-col">
                        <span className="font-mono font-semibold text-primary">
                          {typeof ev.entity_id === 'string' && ev.entity_id.length > 24
                            ? `${ev.entity_id.slice(0, 16)}...`
                            : ev.entity_id}
                        </span>
                        {ev.batch_id && (
                          <span className="text-[10px] font-mono text-muted mt-0.5">
                            {ev.batch_id}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      {typeof ev.amount === 'number' ? (
                        <span className="font-mono font-bold text-primary">
                          ${ev.amount.toFixed(2)}
                        </span>
                      ) : (
                        <span className="text-xs text-muted">—</span>
                      )}
                    </td>
                    <td>
                      <div className="flex flex-col">
                        <span className="text-xs font-medium text-secondary">{ev.action}</span>
                        {typeof ev.probability === 'number' && (
                          <span className="text-[10px] font-mono text-muted">
                            P(Fraud): {(ev.probability * 100).toFixed(2)}%
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <StatusBadge 
                        type={
                          ev.type === 'DRIFT_ANALYSIS' 
                            ? 'drift' 
                            : ev.type === 'OPERATOR_ADJUDICATION'
                            ? 'feedback'
                            : 'decision'
                        } 
                        value={ev.decision} 
                      />
                    </td>
                    <td>
                      <span className="text-xs text-muted font-mono">{ev.operator}</span>
                    </td>
                    <td>
                      <span className="text-xs text-muted whitespace-nowrap">
                        {new Date(ev.timestamp).toLocaleString()}
                      </span>
                    </td>
                    <td className="text-right">
                      {ev.rawItem ? (
                        <button
                          type="button"
                          onClick={() => setSelectedCase(ev.rawItem)}
                          className="btn btn-secondary btn-xs flex items-center gap-1"
                        >
                          <span>View</span>
                          <ExternalLink className="w-3 h-3" />
                        </button>
                      ) : (
                        <span className="text-xs text-muted font-mono">System</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Case Inspector Modal */}
      {selectedCase && (
        <CaseDetailsModal
          transaction={selectedCase}
          onClose={() => setSelectedCase(null)}
          onFeedbackSubmitted={() => {
            fetchAuditTrail();
          }}
        />
      )}
    </div>
  );
}
