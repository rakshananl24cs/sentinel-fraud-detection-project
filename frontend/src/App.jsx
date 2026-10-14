import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import OverviewPage from './pages/OverviewPage';
import ReviewQueuePage from './pages/ReviewQueuePage';
import ScoringPage from './pages/ScoringPage';
import RiskAnalyticsPage from './pages/RiskAnalyticsPage';
import FeedbackAnalyticsPage from './pages/FeedbackAnalyticsPage';
import DriftMonitoringPage from './pages/DriftMonitoringPage';
import ModelManagementPage from './pages/ModelManagementPage';
import AuditHistoryPage from './pages/AuditHistoryPage';
import SettingsPage from './pages/SettingsPage';
import { Loader2 } from 'lucide-react';

function ProtectedLayout() {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="auth-loading-screen">
        <Loader2 className="w-8 h-8 animate-spin text-teal" />
        <p className="text-sm text-muted mt-3">Verifying analyst credentials...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return <Layout />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<ProtectedLayout />}>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/score" element={<ScoringPage />} />
            <Route path="/transactions" element={<ScoringPage />} />
            <Route path="/risk" element={<RiskAnalyticsPage />} />
            <Route path="/risk-analytics" element={<RiskAnalyticsPage />} />
            <Route path="/queue" element={<ReviewQueuePage />} />
            <Route path="/feedback" element={<FeedbackAnalyticsPage />} />
            <Route path="/monitoring" element={<DriftMonitoringPage />} />
            <Route path="/drift" element={<DriftMonitoringPage />} />
            <Route path="/models" element={<ModelManagementPage />} />
            <Route path="/history" element={<AuditHistoryPage />} />
            <Route path="/audit" element={<AuditHistoryPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
