import { useState, useEffect, useRef, useCallback } from 'react';
import { alertsApi } from '../api/client';
import {
  Bell,
  CheckCheck,
  Check,
  AlertTriangle,
  ShieldAlert,
  Clock,
  ExternalLink,
  RotateCw,
  X,
  ShieldCheck,
  Info
} from 'lucide-react';

function formatTime(isoString) {
  if (!isoString) return '';
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffSecs = Math.floor((now - date) / 1000);
    if (diffSecs < 60) return 'Just now';
    if (diffSecs < 3600) return `${Math.floor(diffSecs / 60)}m ago`;
    if (diffSecs < 86400) return `${Math.floor(diffSecs / 3600)}h ago`;
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return isoString;
  }
}

export default function NotificationBell({ onOpenCase }) {
  const [isOpen, setIsOpen] = useState(false);
  const [stats, setStats] = useState({
    total: 0,
    unread_count: 0,
    high_risk_unread_count: 0,
    review_needed_unread_count: 0,
  });
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('ALL'); // 'ALL' | 'UNREAD' | 'HIGH_RISK' | 'NEEDS_REVIEW'
  const [actionLoading, setActionLoading] = useState(null);
  const containerRef = useRef(null);

  // 1. Fetch unread stats
  const fetchStats = useCallback(async () => {
    try {
      const data = await alertsApi.getStats();
      setStats(data);
    } catch (err) {
      console.warn('Failed to fetch alert stats:', err);
    }
  }, []);

  // 2. Fetch alert list based on active filter
  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const unreadOnly = filter === 'UNREAD';
      const alertType = filter === 'HIGH_RISK' || filter === 'NEEDS_REVIEW' ? filter : null;
      const data = await alertsApi.list({
        limit: 20,
        unreadOnly,
        alertType,
      });
      setAlerts(data.items || []);
      setStats((prev) => ({
        ...prev,
        unread_count: data.unread_count ?? prev.unread_count,
        high_risk_unread_count: data.high_risk_unread_count ?? prev.high_risk_unread_count,
        review_needed_unread_count: data.review_needed_unread_count ?? prev.review_needed_unread_count,
      }));
    } catch (err) {
      console.warn('Failed to load alert list:', err);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  // Initial fetch and 15s polling for background notifications
  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 15000);
    return () => clearInterval(interval);
  }, [fetchStats]);

  // When dropdown opens or filter changes, load alerts
  useEffect(() => {
    if (isOpen) {
      fetchAlerts();
    }
  }, [isOpen, filter, fetchAlerts]);

  // Click outside listener to dismiss notification panel
  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Mark single alert as read
  const handleMarkAsRead = async (alertId, e) => {
    if (e) e.stopPropagation();
    setActionLoading(alertId);
    try {
      await alertsApi.markAsRead(alertId);
      setAlerts((prev) =>
        prev.map((a) => (a.id === alertId ? { ...a, is_read: true, read_at: new Date().toISOString() } : a))
      );
      setStats((prev) => ({
        ...prev,
        unread_count: Math.max(0, prev.unread_count - 1),
      }));
    } catch (err) {
      console.error('Failed to mark alert as read:', err);
    } finally {
      setActionLoading(null);
    }
  };

  // Mark all alerts as read
  const handleMarkAllAsRead = async () => {
    setActionLoading('all');
    try {
      await alertsApi.markAllAsRead();
      setAlerts((prev) =>
        prev.map((a) => ({ ...a, is_read: true, read_at: new Date().toISOString() }))
      );
      setStats({
        ...stats,
        unread_count: 0,
        high_risk_unread_count: 0,
        review_needed_unread_count: 0,
      });
    } catch (err) {
      console.error('Failed to mark all alerts as read:', err);
    } finally {
      setActionLoading(null);
    }
  };

  // Open transaction detail modal
  const handleOpenTransaction = (alert) => {
    // If unread, mark as read concurrently
    if (!alert.is_read) {
      handleMarkAsRead(alert.id);
    }
    if (onOpenCase) {
      onOpenCase({
        id: alert.transaction_id,
        external_id: alert.external_id,
        amount: alert.amount,
        decision: alert.decision,
        risk_level: alert.severity,
        calibrated_probability: alert.fraud_probability,
        created_at: alert.created_at,
      });
    }
    setIsOpen(false);
  };


  const hasHighRisk = stats.high_risk_unread_count > 0;
  const unreadCount = stats.unread_count || 0;

  return (
    <div className="relative inline-block" ref={containerRef}>
      {/* Bell Trigger Button */}
      <button
        type="button"
        className={`notification-bell-btn ${isOpen ? 'active' : ''} ${hasHighRisk ? 'has-critical' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        title={unreadCount > 0 ? `${unreadCount} unread fraud alerts` : 'Fraud Notifications'}
        aria-label="Fraud notifications"
        aria-expanded={isOpen}
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className={`notification-badge ${hasHighRisk ? 'badge-critical' : 'badge-warning'}`}>
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown Notification Panel */}
      {isOpen && (
        <div className="notification-panel" role="region" aria-label="Fraud alerts dropdown">
          {/* Panel Header */}
          <div className="notification-panel-header">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-teal" />
              <span className="font-semibold text-sm text-white">Fraud Alert Notifications</span>
              {unreadCount > 0 && (
                <span className="badge badge-danger text-xs font-mono ml-1">
                  {unreadCount} Unread
                </span>
              )}
            </div>

            <div className="flex items-center gap-1">
              {unreadCount > 0 && (
                <button
                  type="button"
                  className="notification-header-action"
                  onClick={handleMarkAllAsRead}
                  disabled={actionLoading === 'all'}
                  title="Mark all notifications as read"
                >
                  <CheckCheck className="w-3.5 h-3.5" />
                  <span>Mark all read</span>
                </button>
              )}
              <button
                type="button"
                className="notification-header-action"
                onClick={fetchAlerts}
                title="Refresh notifications"
              >
                <RotateCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <button
                type="button"
                className="notification-header-action"
                onClick={() => setIsOpen(false)}
                title="Close panel"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Filter Pills */}
          <div className="notification-filter-bar">
            <button
              type="button"
              className={`notification-filter-btn ${filter === 'ALL' ? 'active' : ''}`}
              onClick={() => setFilter('ALL')}
            >
              All Alerts
            </button>
            <button
              type="button"
              className={`notification-filter-btn ${filter === 'UNREAD' ? 'active' : ''}`}
              onClick={() => setFilter('UNREAD')}
            >
              Unread ({unreadCount})
            </button>
            <button
              type="button"
              className={`notification-filter-btn ${filter === 'HIGH_RISK' ? 'active' : ''}`}
              onClick={() => setFilter('HIGH_RISK')}
            >
              High Risk ({stats.high_risk_unread_count || 0})
            </button>
            <button
              type="button"
              className={`notification-filter-btn ${filter === 'NEEDS_REVIEW' ? 'active' : ''}`}
              onClick={() => setFilter('NEEDS_REVIEW')}
            >
              Needs Review
            </button>
          </div>

          {/* Notification List */}
          <div className="notification-list-container">
            {loading && alerts.length === 0 ? (
              <div className="notification-empty">
                <RotateCw className="w-5 h-5 text-teal animate-spin mb-2" />
                <p className="text-xs text-muted">Checking fraud alerts...</p>
              </div>
            ) : alerts.length === 0 ? (
              <div className="notification-empty">
                <ShieldCheck className="w-8 h-8 text-emerald mb-2" />
                <p className="text-sm font-semibold text-white">No Fraud Alerts</p>
                <p className="text-xs text-muted mt-1 max-w-xs text-center">
                  {filter === 'UNREAD'
                    ? 'All high-risk and review notifications have been read.'
                    : 'No high-risk or review alerts have been generated yet.'}
                </p>
              </div>
            ) : (
              alerts.map((alert) => {
                const isHighRisk = alert.alert_type === 'HIGH_RISK';
                return (
                  <div
                    key={alert.id}
                    className={`notification-card ${!alert.is_read ? 'unread' : ''} ${
                      isHighRisk ? 'border-l-high-risk' : 'border-l-review'
                    }`}
                    onClick={() => handleOpenTransaction(alert)}
                  >
                    {/* Top Row: Type Badge, Timestamp, Unread Dot */}
                    <div className="notification-card-top">
                      <div className="flex items-center gap-1.5">
                        {isHighRisk ? (
                          <span className="badge badge-danger text-xs font-semibold">
                            <ShieldAlert className="w-3 h-3 mr-1 inline" />
                            High Risk
                          </span>
                        ) : (
                          <span className="badge badge-warning text-xs font-semibold">
                            <AlertTriangle className="w-3 h-3 mr-1 inline" />
                            Needs Review
                          </span>
                        )}
                        <span className="badge badge-neutral text-xs font-mono">
                          {alert.decision}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 text-xs text-muted">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatTime(alert.created_at)}
                        </span>
                        {!alert.is_read && (
                          <span
                            className="notification-unread-dot"
                            title="Unread notification"
                          />
                        )}
                      </div>
                    </div>

                    {/* Alert Message */}
                    <p className="notification-message">{alert.message}</p>

                    {/* Metadata Strip: TX ID, Amount, Probability */}
                    <div className="notification-meta-grid">
                      <div className="notification-meta-item">
                        <span className="meta-label">Transaction</span>
                        <span className="meta-val font-mono">{alert.external_id}</span>
                      </div>
                      <div className="notification-meta-item">
                        <span className="meta-label">Amount</span>
                        <span className="meta-val font-mono font-semibold">
                          ${alert.amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                      </div>
                      <div className="notification-meta-item">
                        <span className="meta-label">Fraud Prob</span>
                        <span className={`meta-val font-mono font-bold ${isHighRisk ? 'text-red' : 'text-amber'}`}>
                          {(alert.fraud_probability * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>

                    {/* Recommended Next Action */}
                    <div className="notification-action-box">
                      <span className="action-tag">Recommended Action:</span>
                      <p className="action-text">{alert.recommended_action}</p>
                    </div>

                    {/* Disclaimer */}
                    <div className="notification-disclaimer">
                      <Info className="w-3 h-3 flex-shrink-0 text-slate-500 mt-0.5" />
                      <span>{alert.disclaimer}</span>
                    </div>

                    {/* Card Actions */}
                    <div className="notification-card-actions" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        className="btn-notification-inspect"
                        onClick={() => handleOpenTransaction(alert)}
                      >
                        <span>Open Transaction</span>
                        <ExternalLink className="w-3 h-3" />
                      </button>

                      {!alert.is_read && (
                        <button
                          type="button"
                          className="btn-notification-mark"
                          onClick={(e) => handleMarkAsRead(alert.id, e)}
                          disabled={actionLoading === alert.id}
                          title="Mark this alert as read"
                        >
                          <Check className="w-3 h-3" />
                          <span>Mark Read</span>
                        </button>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Footer Strip */}
          <div className="notification-panel-footer">
            <span className="text-xs text-muted flex items-center gap-1">
              <span className="dot dot-success" />
              Automated high-risk scoring alerts
            </span>
            <span className="text-xs font-mono text-slate-400">
              Total: {stats.total || 0}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
