import { useState, useEffect } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { healthApi, reviewQueueApi } from '../api/client';
import StatusBadge from './StatusBadge';
import NotificationBell from './NotificationBell';
import CaseDetailsModal from './CaseDetailsModal';
import { 
  ShieldCheck, 
  Layers, 
  Inbox, 
  Activity, 
  LogOut, 
  Cpu, 
  CheckCircle2, 
  AlertCircle,
  Menu,
  X,
  BarChart3,
  MessageSquareCheck,
  History,
  Settings
} from 'lucide-react';


export default function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [dbStatus, setDbStatus] = useState('checking');
  const [pendingQueueCount, setPendingQueueCount] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [selectedAlertCase, setSelectedAlertCase] = useState(null);

  // Close mobile sidebar on route change
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  // Periodic health check and pending queue count
  useEffect(() => {
    let isMounted = true;

    async function checkHealthAndQueue() {
      try {
        const [healthRes, queueRes] = await Promise.allSettled([
          healthApi.getReady(),
          reviewQueueApi.getQueue({ limit: 1, statusFilter: 'PENDING' }),
        ]);

        if (isMounted) {
          if (healthRes.status === 'fulfilled') {
            setDbStatus(healthRes.value.database === 'connected' ? 'connected' : 'disconnected');
          } else {
            setDbStatus('disconnected');
          }

          if (queueRes.status === 'fulfilled') {
            setPendingQueueCount(queueRes.value.total);
          }
        }
      } catch {
        if (isMounted) setDbStatus('disconnected');
      }
    }

    checkHealthAndQueue();
    const interval = setInterval(checkHealthAndQueue, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Compute breadcrumb page title
  const getPageTitle = (path) => {
    if (path === '/') return 'Dashboard';
    if (path.startsWith('/score') || path.startsWith('/transaction')) return 'Transaction Analysis';
    if (path.startsWith('/queue')) return 'Fraud Review Queue';
    if (path.startsWith('/risk')) return 'Risk Analytics';
    if (path.startsWith('/feedback')) return 'Analyst Feedback';
    if (path.startsWith('/monitoring') || path.startsWith('/drift')) return 'Model Performance';
    if (path.startsWith('/models')) return 'Model Management';
    if (path.startsWith('/history') || path.startsWith('/audit')) return 'Transaction History';
    if (path.startsWith('/settings')) return 'Settings';
    return 'Console';
  };

  const userInitial = user?.email ? user.email.charAt(0).toUpperCase() : 'U';

  return (
    <div className="app-layout">
      {/* Mobile Backdrop */}
      <div 
        className={`sidebar-backdrop ${mobileOpen ? 'mobile-open' : ''}`}
        onClick={() => setMobileOpen(false)}
      />

      {/* Persistent Dark Navy Sidebar */}
      <aside className={`app-sidebar ${mobileOpen ? 'mobile-open' : ''}`}>
        {/* Brand Header */}
        <div className="sidebar-header">
          <NavLink to="/" className="brand-wrapper">
            <div className="brand-icon">
              <ShieldCheck className="w-5 h-5 text-teal" />
            </div>
            <div className="brand-meta">
              <span className="brand-title">Sentinel Fraud Console</span>
              <span className="brand-subtitle">Enterprise Risk Management</span>
            </div>
          </NavLink>
          {mobileOpen && (
            <button 
              type="button" 
              className="btn-icon text-muted" 
              onClick={() => setMobileOpen(false)}
              aria-label="Close menu"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Sidebar Navigation */}
        <div className="sidebar-body">
          {/* Core Operations Section */}
          <div className="sidebar-group">
            <div className="sidebar-group-label">Core Operations</div>
            <NavLink 
              to="/" 
              end 
              className={({ isActive }) => (isActive ? 'sidebar-link active' : 'sidebar-link')}
            >
              <Layers className="w-4 h-4" />
              <span>Dashboard</span>
            </NavLink>

            <NavLink 
              to="/score" 
              className={({ isActive }) => (isActive || location.pathname.startsWith('/transaction') ? 'sidebar-link active' : 'sidebar-link')}
            >
              <Cpu className="w-4 h-4" />
              <span>Transaction Analysis</span>
            </NavLink>

            <NavLink 
              to="/queue" 
              className={({ isActive }) => (isActive ? 'sidebar-link active' : 'sidebar-link')}
            >
              <Inbox className="w-4 h-4" />
              <span>Fraud Review Queue</span>
              {pendingQueueCount !== null && pendingQueueCount > 0 && (
                <span className="sidebar-link-badge" title={`${pendingQueueCount} pending review cases awaiting triage`}>
                  {pendingQueueCount}
                </span>
              )}
            </NavLink>
          </div>

          {/* Analytics & Risk Intelligence */}
          <div className="sidebar-group">
            <div className="sidebar-group-label">Risk & Intelligence</div>
            <NavLink 
              to="/risk" 
              className={({ isActive }) => (isActive ? 'sidebar-link active' : 'sidebar-link')}
            >
              <BarChart3 className="w-4 h-4" />
              <span>Risk Analytics</span>
            </NavLink>

            <NavLink 
              to="/feedback" 
              className={({ isActive }) => (isActive ? 'sidebar-link active' : 'sidebar-link')}
            >
              <MessageSquareCheck className="w-4 h-4" />
              <span>Analyst Feedback</span>
            </NavLink>
          </div>

          {/* Governance & Monitoring */}
          <div className="sidebar-group">
            <div className="sidebar-group-label">Model Governance</div>
            <NavLink 
              to="/monitoring" 
              className={({ isActive }) => (isActive || location.pathname.startsWith('/drift') ? 'sidebar-link active' : 'sidebar-link')}
            >
              <Activity className="w-4 h-4" />
              <span>Model Performance</span>
            </NavLink>

            <NavLink 
              to="/history" 
              className={({ isActive }) => (isActive || location.pathname.startsWith('/audit') ? 'sidebar-link active' : 'sidebar-link')}
            >
              <History className="w-4 h-4" />
              <span>Transaction History</span>
            </NavLink>
          </div>

          {/* Configuration */}
          <div className="sidebar-group">
            <div className="sidebar-group-label">Configuration</div>
            <NavLink 
              to="/settings" 
              className={({ isActive }) => (isActive ? 'sidebar-link active' : 'sidebar-link')}
            >
              <Settings className="w-4 h-4" />
              <span>Settings</span>
            </NavLink>
          </div>
        </div>

        {/* Sidebar Footer — User Profile */}
        <div className="sidebar-footer">
          <div className="sidebar-user-card">
            <div className="user-avatar-initials">{userInitial}</div>
            <div className="user-info">
              <span className="user-email-text" title={user?.email}>{user?.email}</span>
              <div className="mt-1">
                <StatusBadge type="role" value={user?.role} />
              </div>
            </div>
            <button 
              type="button" 
              onClick={logout} 
              className="btn-icon" 
              title="Sign Out"
              aria-label="Sign Out"
            >
              <LogOut className="w-4 h-4 text-slate-400 hover:text-red-400" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Workspace */}
      <div className="app-main-wrapper">
        {/* Top Navigation Bar */}
        <header className="top-navbar">
          <div className="navbar-left">
            <button 
              type="button" 
              className="mobile-menu-btn"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation menu"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="navbar-breadcrumbs">
              <NavLink to="/" className="breadcrumb-root">Console</NavLink>
              <span className="breadcrumb-separator">/</span>
              <span className="breadcrumb-current">{getPageTitle(location.pathname)}</span>
            </div>
          </div>

          <div className="navbar-right">
            {/* Active Model Indicator */}
            <span className="nav-pill pill-active-model" title="Active inference model loaded in Docker service">
              <span className="dot dot-success mr-1"></span>
              xgb-cost-v1
            </span>

            {/* DB Health Indicator */}
            {dbStatus === 'connected' ? (
              <span className="nav-pill pill-health-online" title="PostgreSQL 16 persistence connected">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald" />
                DB Online
              </span>
            ) : (
              <span className="nav-pill pill-health-offline" title="Database connectivity check failed">
                <AlertCircle className="w-3.5 h-3.5 text-red" />
                DB Offline
              </span>
            )}

            {/* Fraud Alert Notification Bell */}
            <NotificationBell onOpenCase={(caseItem) => setSelectedAlertCase(caseItem)} />

            {/* User Role & Quick Signout */}
            <div className="hidden sm:flex items-center gap-2">
              <StatusBadge type="role" value={user?.role} />
            </div>

            <button 
              type="button" 
              onClick={logout} 
              className="btn-signout-nav"
              title="Sign Out"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>Logout</span>
            </button>
          </div>
        </header>

        {/* Page Content View */}
        <main className="app-content">
          <Outlet />
        </main>
      </div>

      {/* Case Details Modal (triggered by alerts) */}
      {selectedAlertCase && (
        <CaseDetailsModal
          caseData={selectedAlertCase}
          onClose={() => setSelectedAlertCase(null)}
          onAdjudicationSuccess={() => setSelectedAlertCase(null)}
        />
      )}
    </div>
  );
}
