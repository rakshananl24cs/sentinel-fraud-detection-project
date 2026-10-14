import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { ShieldCheck, Lock, Mail, AlertCircle, Loader2 } from 'lucide-react';

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please provide both email and password.');
      return;
    }

    setError('');
    setLoading(true);
    try {
      await login(email, password);
    } catch (err) {
      const detail = err.response?.data?.detail || 'Authentication failed. Please verify credentials.';
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyPreset = (presetEmail) => {
    setEmail(presetEmail);
    setPassword('SecurePassword123!');
    setError('');
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <div className="login-icon-badge">
            <ShieldCheck className="w-8 h-8 text-teal" />
          </div>
          <h2>Sentinel Fraud Console</h2>
          <p className="subtitle">Enterprise Cost-Sensitive Decision Platform</p>
        </div>

        {error && (
          <div className="alert alert-error mb-4">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group mb-3">
            <label className="form-label" htmlFor="email">Analyst / Operator Email</label>
            <div className="input-with-icon">
              <Mail className="input-icon" />
              <input
                id="email"
                type="email"
                required
                placeholder="operator@bank.internal"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={loading}
                autoComplete="email"
                className="form-input text-xs"
              />
            </div>
          </div>

          <div className="form-group mb-4">
            <label className="form-label" htmlFor="password">Password</label>
            <div className="input-with-icon">
              <Lock className="input-icon" />
              <input
                id="password"
                type="password"
                required
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                autoComplete="current-password"
                className="form-input text-xs"
              />
            </div>
          </div>

          <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin mr-1" />
                <span>Authenticating Analyst...</span>
              </>
            ) : (
              'Sign In to Decision Console'
            )}
          </button>
        </form>

        {/* Quick Role Fill Presets for Local Testing */}
        <div className="login-presets">
          <span className="login-presets-title">Quick Role Credentials</span>
          <div className="login-presets-buttons">
            <button
              type="button"
              onClick={() => handleApplyPreset('analyst@bank.internal')}
              className="btn btn-secondary btn-xs flex-1"
            >
              Analyst
            </button>
            <button
              type="button"
              onClick={() => handleApplyPreset('operator@bank.internal')}
              className="btn btn-secondary btn-xs flex-1"
            >
              Operator
            </button>
            <button
              type="button"
              onClick={() => handleApplyPreset('admin@bank.internal')}
              className="btn btn-secondary btn-xs flex-1"
            >
              Admin
            </button>
          </div>
        </div>

        <div className="login-footer">
          <p className="text-xs text-muted leading-relaxed">
            Role-Based Access: Analysing, triaging, and verifying adjudications are strictly enforced by signed JWT tokens and database check constraints.
          </p>
        </div>
      </div>
    </div>
  );
}
