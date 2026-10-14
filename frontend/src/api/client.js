import axios from 'axios';

// Read API base URL from Vite environment variable or fall back to local development URL
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000,
});

// Attach Authorization Bearer token to outgoing requests if available
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('fraud_app_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Intercept 401 Unauthorized responses to safely clear sessions
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      // Discard invalid token
      localStorage.removeItem('fraud_app_token');
      // Trigger a custom event for AuthContext to pick up
      window.dispatchEvent(new Event('auth:unauthorized'));
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  login: async (email, password) => {
    const res = await api.post('/api/v1/auth/login', { email, password });
    return res.data;
  },
  getMe: async () => {
    const res = await api.get('/api/v1/auth/me');
    return res.data;
  },
};

export const healthApi = {
  getLive: async () => {
    const res = await api.get('/health/live');
    return res.data;
  },
  getReady: async () => {
    const res = await api.get('/health/ready');
    return res.data;
  },
};

export const transactionsApi = {
  score: async (payload) => {
    const res = await api.post('/api/v1/transactions/predict', payload);
    return res.data;
  },
  batchPredict: async ({ batch_id, filename, items }) => {
    const res = await api.post('/api/v1/transactions/batch-predict', { batch_id, filename, items });
    return res.data;
  },
  getLatestBatch: async () => {
    const res = await api.get('/api/v1/transactions/batches/latest');
    return res.data;
  },
  getBatch: async (batchId) => {
    const res = await api.get(`/api/v1/transactions/batches/${batchId}`);
    return res.data;
  },
  getOperationalStats: async () => {
    const res = await api.get('/api/v1/transactions/operational-stats');
    return res.data;
  },
  getRecent: async ({ limit = 20, offset = 0, decision = null, batch_id = null } = {}) => {
    const params = { limit, offset };
    if (decision && decision !== 'ALL') params.decision = decision;
    if (batch_id) params.batch_id = batch_id;
    const res = await api.get('/api/v1/transactions/recent', { params });
    return res.data;
  },
};

export const reviewQueueApi = {
  getQueue: async ({ limit = 20, offset = 0, statusFilter = null, minProb = null, maxProb = null, batch_id = null } = {}) => {
    const params = { limit, offset };
    if (statusFilter && statusFilter !== 'ALL') params.status_filter = statusFilter;
    if (minProb !== null && minProb !== '') params.min_probability = parseFloat(minProb);
    if (maxProb !== null && maxProb !== '') params.max_probability = parseFloat(maxProb);
    if (batch_id) params.batch_id = batch_id;
    const res = await api.get('/api/v1/transactions/review-queue', { params });
    return res.data;
  },
};

export const feedbackApi = {
  submit: async (transactionId, { decision, reason_code, comment, is_verified = false }) => {
    const payload = { decision, is_verified };
    if (reason_code && reason_code.trim()) payload.reason_code = reason_code.trim();
    if (comment && comment.trim()) payload.comment = comment.trim();
    const res = await api.post(`/api/v1/transactions/${transactionId}/feedback`, payload);
    return res.data;
  },
  verify: async (transactionId, feedbackId) => {
    const res = await api.post(`/api/v1/transactions/${transactionId}/feedback/${feedbackId}/verify`);
    return res.data;
  },
  getHistory: async (transactionId) => {
    const res = await api.get(`/api/v1/transactions/${transactionId}/feedback`);
    return res.data;
  },
};

export const monitoringApi = {
  listReports: async ({ limit = 20, offset = 0, statusFilter = null } = {}) => {
    const params = { limit, offset };
    if (statusFilter && statusFilter !== 'ALL') params.status_filter = statusFilter;
    const res = await api.get('/api/v1/monitoring/drift-reports', { params });
    return res.data;
  },
  getReport: async (reportId) => {
    const res = await api.get(`/api/v1/monitoring/drift-reports/${reportId}`);
    return res.data;
  },
  createReport: async ({ time_window_start, time_window_end, model_version = 'xgb-cost-v1' }) => {
    const res = await api.post('/api/v1/monitoring/drift-reports', {
      time_window_start,
      time_window_end,
      model_version,
    });
    return res.data;
  },
};

export const modelsApi = {
  getCurrent: async () => {
    try {
      const res = await api.get('/api/v1/models/current');
      return res.data;
    } catch {
      return null;
    }
  },
  list: async () => {
    try {
      const res = await api.get('/api/v1/models');
      return res.data;
    } catch {
      return null;
    }
  },
};

export const alertsApi = {
  list: async ({ limit = 20, offset = 0, unreadOnly = false, alertType = null } = {}) => {
    const params = { limit, offset };
    if (unreadOnly) params.unread_only = true;
    if (alertType && alertType !== 'ALL') params.alert_type = alertType;
    const res = await api.get('/api/v1/alerts', { params });
    return res.data;
  },
  getStats: async () => {
    const res = await api.get('/api/v1/alerts/stats');
    return res.data;
  },
  markAsRead: async (alertId) => {
    const res = await api.patch(`/api/v1/alerts/${alertId}/read`);
    return res.data;
  },
  markAllAsRead: async () => {
    const res = await api.post('/api/v1/alerts/mark-all-read');
    return res.data;
  },
  getDetails: async (alertId) => {
    const res = await api.get(`/api/v1/alerts/${alertId}`);
    return res.data;
  },
};

export default api;

