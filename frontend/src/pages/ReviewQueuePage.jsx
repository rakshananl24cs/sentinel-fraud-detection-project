import { useState, useEffect, useCallback } from 'react';
import { reviewQueueApi, transactionsApi } from '../api/client';
import CaseDetailsModal from '../components/CaseDetailsModal';
import StatusBadge from '../components/StatusBadge';

import { 
  Inbox, 
  Search, 
  Filter, 
  RotateCw, 
  ChevronLeft, 
  ChevronRight, 
  AlertTriangle, 
  CheckCircle2, 
  ExternalLink,
  Loader2,
  SlidersHorizontal,
  X,
  Layers,
  FileSpreadsheet,
  Info
} from 'lucide-react';

export default function ReviewQueuePage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Scope state: 'ALL' or 'BATCH'
  const [scope, setScope] = useState('ALL');
  const [latestBatchId, setLatestBatchId] = useState(() => localStorage.getItem('fraud_latest_batch_id') || '');

  // Filter & Pagination state
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [minProb, setMinProb] = useState('');
  const [maxProb, setMaxProb] = useState('');
  const [searchId, setSearchId] = useState('');
  const [limit] = useState(20);
  const [offset, setOffset] = useState(0);

  // Modal inspection state
  const [selectedCase, setSelectedCase] = useState(null);

  // Fetch latest batch ID on mount if not already present
  useEffect(() => {
    async function loadLatestBatchId() {
      try {
        const batchData = await transactionsApi.getLatestBatch();
        if (batchData?.summary?.batch_id) {
          setLatestBatchId(batchData.summary.batch_id);
          localStorage.setItem('fraud_latest_batch_id', batchData.summary.batch_id);
        }
      } catch {
        // No batch uploaded yet
      }
    }
    loadLatestBatchId();
  }, []);

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await reviewQueueApi.getQueue({
        limit,
        offset,
        statusFilter,
        minProb: minProb !== '' ? parseFloat(minProb) : null,
        maxProb: maxProb !== '' ? parseFloat(maxProb) : null,
        batch_id: scope === 'BATCH' && latestBatchId ? latestBatchId : null,
      });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load review queue. Please verify your connection.');
    } finally {
      setLoading(false);
    }
  }, [limit, offset, statusFilter, minProb, maxProb, scope, latestBatchId]);

  useEffect(() => {
    fetchQueue();
  }, [fetchQueue]);

  const handleResetFilters = () => {
    setScope('ALL');
    setStatusFilter('ALL');
    setMinProb('');
    setMaxProb('');
    setSearchId('');
    setOffset(0);
  };

  const handleStatusFilterChange = (newStatus) => {
    setStatusFilter(newStatus);
    setOffset(0);
  };

  const handleScopeChange = (newScope) => {
    setScope(newScope);
    setOffset(0);
  };

  const handlePageChange = (newOffset) => {
    setOffset(Math.max(0, newOffset));
  };

  // Filter client-side by search ID if user typed in search input
  const displayedItems = searchId.trim()
    ? items.filter((it) => it.external_id.toLowerCase().includes(searchId.toLowerCase().trim()))
    : items;

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <Inbox className="w-6 h-6 text-teal" />
            <span>Operator Review Queue</span>
          </h1>
          <p className="page-subtitle">
            Manual triage queue for transactions falling into the cost-sensitive borderline uncertainty band (0.042 ≤ P &lt; 0.7539).
          </p>
        </div>
        <div className="header-actions">
          <button 
            type="button" 
            className="btn btn-secondary flex items-center gap-1.5"
            onClick={fetchQueue}
            disabled={loading}
          >
            <RotateCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Scope Disclaimer Alert */}
      <div className="p-3 bg-slate-100 border border-slate-200 rounded-md text-xs text-secondary mb-6 flex items-start justify-between gap-2">
        <div className="flex items-start gap-2">
          <Info className="w-4 h-4 text-teal flex-shrink-0 mt-0.5" />
          <div>
            <strong>Queue Scope & Sidebar Badge Disclosure:</strong> The sidebar counter displays <strong>pending triage cases</strong> awaiting operator investigation. By default, this table displays <strong>all review cases</strong> (both pending and completed adjudications). Only transactions with the latest model decision <strong>REVIEW</strong> (0.0420 ≤ P &lt; 0.7539) enter this queue; automated <strong>APPROVE</strong> and <strong>BLOCK</strong> transactions do not require human triage.
          </div>
        </div>
        {scope === 'BATCH' && latestBatchId && (
          <span className="badge badge-neutral font-mono text-xs whitespace-nowrap">
            Batch: {latestBatchId}
          </span>
        )}
      </div>

      {/* Filter Toolbar */}
      <div className="card filter-bar mb-6 flex-wrap gap-4">
        {/* Scope selector */}
        <div className="filter-group">
          <label className="filter-label flex items-center gap-1">
            <Layers className="w-3.5 h-3.5" /> Scope
          </label>
          <div className="button-group">
            <button
              type="button"
              className={`filter-btn ${scope === 'ALL' ? 'active' : ''}`}
              onClick={() => handleScopeChange('ALL')}
            >
              All Queued
            </button>
            <button
              type="button"
              className={`filter-btn ${scope === 'BATCH' ? 'active' : ''}`}
              onClick={() => handleScopeChange('BATCH')}
              disabled={!latestBatchId}
              title={latestBatchId ? `Filter by batch ${latestBatchId}` : 'No recent batch found'}
            >
              <FileSpreadsheet className="w-3.5 h-3.5 inline mr-1" />
              Latest Batch Only
            </button>
          </div>
        </div>

        {/* Adjudication Status */}
        <div className="filter-group">
          <label className="filter-label flex items-center gap-1">
            <Filter className="w-3.5 h-3.5" /> Adjudication Status
          </label>
          <div className="button-group">
            <button
              type="button"
              className={`filter-btn ${statusFilter === 'ALL' ? 'active' : ''}`}
              onClick={() => handleStatusFilterChange('ALL')}
            >
              All Cases
            </button>
            <button
              type="button"
              className={`filter-btn ${statusFilter === 'PENDING' ? 'active' : ''}`}
              onClick={() => handleStatusFilterChange('PENDING')}
            >
              Pending Triage
            </button>
            <button
              type="button"
              className={`filter-btn ${statusFilter === 'REVIEWED' ? 'active' : ''}`}
              onClick={() => handleStatusFilterChange('REVIEWED')}
            >
              Adjudicated
            </button>
          </div>
        </div>

        {/* Search External ID */}
        <div className="filter-group">
          <label className="filter-label flex items-center gap-1">
            <Search className="w-3.5 h-3.5" /> Search External ID
          </label>
          <input
            type="text"
            placeholder="Filter by TX ID..."
            value={searchId}
            onChange={(e) => setSearchId(e.target.value)}
            className="form-input form-input-sm w-44 font-mono"
          />
        </div>

        {/* Probability Range */}
        <div className="filter-group">
          <label className="filter-label flex items-center gap-1">
            <SlidersHorizontal className="w-3.5 h-3.5" /> Probability Range
          </label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              placeholder="Min (e.g. 0.05)"
              value={minProb}
              onChange={(e) => {
                setMinProb(e.target.value);
                setOffset(0);
              }}
              className="form-input form-input-sm w-28"
            />
            <span className="text-muted text-xs">to</span>
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              placeholder="Max (e.g. 0.20)"
              value={maxProb}
              onChange={(e) => {
                setMaxProb(e.target.value);
                setOffset(0);
              }}
              className="form-input form-input-sm w-28"
            />
          </div>
        </div>

        {(scope !== 'ALL' || statusFilter !== 'ALL' || minProb !== '' || maxProb !== '' || searchId !== '') && (
          <div className="ml-auto self-end">
            <button
              type="button"
              onClick={handleResetFilters}
              className="btn btn-secondary btn-sm flex items-center gap-1 text-muted"
            >
              <X className="w-3 h-3" /> Clear Filters
            </button>
          </div>
        )}
      </div>

      {/* Error Message */}
      {error && (
        <div className="alert alert-error mb-6">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Queue Table Card */}
      <div className="card table-card">
        <div className="table-header-bar">
          <div className="text-xs text-secondary">
            <span>Showing </span>
            <strong className="text-primary">{total > 0 ? offset + 1 : 0}</strong>
            <span> to </span>
            <strong className="text-primary">{Math.min(offset + limit, total)}</strong>
            <span> of </span>
            <strong className="text-primary">{total}</strong>
            <span>
              {' '}
              {statusFilter === 'ALL'
                ? 'review cases (pending + adjudicated)'
                : statusFilter === 'PENDING'
                ? 'pending cases awaiting triage'
                : 'adjudicated cases'}
            </span>
            {scope === 'BATCH' && (
              <span className="text-muted"> (filtered to latest batch)</span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={offset === 0 || loading}
              onClick={() => handlePageChange(offset - limit)}
              className="btn btn-secondary btn-sm"
            >
              <ChevronLeft className="w-4 h-4" />
              <span>Previous</span>
            </button>
            <span className="text-xs font-mono text-muted px-2">
              Page {currentPage} of {totalPages}
            </span>
            <button
              type="button"
              disabled={offset + limit >= total || loading}
              onClick={() => handlePageChange(offset + limit)}
              className="btn btn-secondary btn-sm"
            >
              <span>Next</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>External ID</th>
                <th>Amount</th>
                <th>Calibrated Risk</th>
                <th>Raw ML Score</th>
                <th>Risk Tier</th>
                <th>Review Status</th>
                <th>Ingested</th>
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="table-loading-cell">
                    <Loader2 className="w-6 h-6 animate-spin text-teal mx-auto mb-2" />
                    <p className="text-xs text-muted">Retrieving review queue transactions...</p>
                  </td>
                </tr>
              ) : displayedItems.length === 0 ? (
                <tr>
                  <td colSpan={8} className="table-empty-cell">
                    <CheckCircle2 className="w-8 h-8 text-emerald mx-auto mb-2 opacity-80" />
                    <p className="text-sm font-bold text-primary">Queue Clear</p>
                    <p className="text-xs text-muted max-w-md mx-auto mt-1">
                      {scope === 'BATCH'
                        ? 'No transactions from the latest batch required manual review triage. All transactions in this batch received automated decisions (APPROVE or BLOCK).'
                        : 'No transactions matching the selected criteria require operational triage.'}
                    </p>
                  </td>
                </tr>
              ) : (
                displayedItems.map((item) => (
                  <tr 
                    key={item.transaction_id}
                    className="hover-row"
                    onClick={() => setSelectedCase(item)}
                  >
                    <td>
                      <div className="flex flex-col">
                        <span className="font-mono font-semibold text-primary">
                          {item.external_id}
                        </span>
                        {item.batch_id && (
                          <span className="text-[10px] font-mono text-muted mt-0.5">
                            {item.batch_id}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className="font-mono font-bold text-primary">
                        ${typeof item.amount === 'number' ? item.amount.toFixed(2) : Number(item.amount || 0).toFixed(2)}
                      </span>
                    </td>
                    <td>
                      <div className="prob-bar-container">
                        <span className="font-mono font-medium text-xs text-primary">
                          {(item.fraud_probability * 100).toFixed(2)}%
                        </span>
                        <div className="progress-track">
                          <div
                            className="progress-fill"
                            style={{
                              width: `${Math.min(100, Math.max(2, item.fraud_probability * 100))}%`,
                              backgroundColor: item.fraud_probability > 0.15 ? '#d97706' : '#0d9488',
                            }}
                          />
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="font-mono text-xs text-muted">
                        {(item.raw_probability * 100).toFixed(2)}%
                      </span>
                    </td>
                    <td>
                      <StatusBadge type="risk" value={item.risk_level} />
                    </td>
                    <td>
                      {item.feedback_count === 0 ? (
                        <span className="badge badge-warning">
                          PENDING
                        </span>
                      ) : (
                        <div className="flex items-center gap-1">
                          <StatusBadge type="feedback" value={item.latest_feedback_decision} />
                          {item.latest_feedback_verified && (
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald flex-shrink-0" title="Verified by Administrator" />
                          )}
                        </div>
                      )}
                    </td>
                    <td>
                      <span className="text-xs text-muted whitespace-nowrap">
                        {new Date(item.transaction_created_at).toLocaleString()}
                      </span>
                    </td>
                    <td className="text-right" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={() => setSelectedCase(item)}
                        className="btn btn-secondary btn-xs flex items-center gap-1"
                      >
                        <span>Review</span>
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

      {/* Case Details Drawer */}
      {selectedCase && (
        <CaseDetailsModal
          transaction={selectedCase}
          onClose={() => setSelectedCase(null)}
          onFeedbackSubmitted={() => {
            fetchQueue();
          }}
        />
      )}
    </div>
  );
}
