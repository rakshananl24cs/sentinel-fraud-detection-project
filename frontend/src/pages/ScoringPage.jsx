import { useState, useEffect, useMemo, useRef } from 'react';
import { Link } from 'react-router-dom';
import { transactionsApi, reviewQueueApi } from '../api/client';
import CaseDetailsModal from '../components/CaseDetailsModal';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import { 
  Cpu, 
  Play, 
  RotateCcw, 
  Sparkles, 
  AlertCircle, 
  AlertTriangle,
  Layers,
  ExternalLink,
  Search,
  ArrowUpDown,
  History,
  Info,
  Loader2,
  UploadCloud,
  FileSpreadsheet,
  Download,
  CheckCircle2,
  XCircle,
  ArrowRight
} from 'lucide-react';

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  ReferenceLine
} from 'recharts';

const CANONICAL_FEATURES = ['Amount', 'Time', ...Array.from({ length: 28 }, (_, i) => `V${i + 1}`)];

const PRESETS = {
  genuine: {
    name: 'Low-Risk Genuine',
    description: 'Routine verified transaction ($29.50) with standard baseline PCA factors',
    data: {
      Time: 406.0,
      Amount: 29.50,
      V1: -0.429, V2: 0.875, V3: 1.341, V4: 0.402, V5: 0.125,
      V6: -0.321, V7: 0.654, V8: 0.052, V9: -0.210, V10: -0.154,
      V11: 0.112, V12: 0.245, V13: 0.512, V14: -0.120, V15: 0.340,
      V16: 0.180, V17: -0.220, V18: 0.090, V19: 0.150, V20: 0.040,
      V21: -0.080, V22: -0.150, V23: -0.020, V24: 0.380, V25: 0.120,
      V26: -0.210, V27: 0.010, V28: 0.030
    }
  },
  borderline: {
    name: 'Borderline Uncertainty (REVIEW)',
    description: 'Unusual card-not-present transaction ($480.00) falling into operator review triage band',
    data: {
      Time: 42000.0,
      Amount: 480.00,
      V1: -1.250, V2: 1.420, V3: -1.850, V4: 2.150, V5: -0.920,
      V6: -0.450, V7: -1.650, V8: 0.890, V9: -1.340, V10: -2.100,
      V11: 1.850, V12: -2.450, V13: 0.120, V14: -2.850, V15: 0.450,
      V16: -1.650, V17: -2.120, V18: -0.850, V19: 0.650, V20: 0.320,
      V21: 0.450, V22: -0.120, V23: -0.180, V24: 0.050, V25: 0.220,
      V26: -0.150, V27: 0.350, V28: 0.120
    }
  },
  fraud: {
    name: 'High-Risk Fraud (BLOCK)',
    description: 'Anomalous multi-factor exploitation ($999.00) triggering automated block',
    data: {
      Time: 406.0,
      Amount: 999.00,
      V1: -2.312, V2: 1.951, V3: -1.609, V4: 3.997, V5: -0.522,
      V6: -1.426, V7: -2.537, V8: 1.391, V9: -2.770, V10: -4.708,
      V11: 3.208, V12: -6.072, V13: -0.275, V14: -9.043, V15: -0.560,
      V16: -4.845, V17: -8.450, V18: -2.976, V19: 0.416, V20: 0.126,
      V21: 0.517, V22: -0.035, V23: -0.465, V24: 0.320, V25: 0.044,
      V26: 0.177, V27: 0.261, V28: -0.143
    }
  }
};

const INITIAL_FORM = {
  external_id: '',
  Time: '0',
  Amount: '0.00',
  ...Object.fromEntries(Array.from({ length: 28 }, (_, i) => [`V${i + 1}`, '0.0']))
};

function generateSimExternalId(presetKey) {
  return `SIM-${presetKey.toUpperCase()}-${Date.now().toString(36).slice(-4)}`;
}

export default function ScoringPage() {
  const [activeTab, setActiveTab] = useState('single'); // 'single' | 'batch' | 'ledger'
  const [formData, setFormData] = useState(INITIAL_FORM);
  const [scoring, setScoring] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  // Review drawer modal state
  const [reviewCase, setReviewCase] = useState(null);

  // Scored transactions session history & ledger
  const [sessionScored, setSessionScored] = useState([]);
  const [queueLedger, setQueueLedger] = useState([]);
  const [loadingLedger, setLoadingLedger] = useState(false);
  const [searchFilter, setSearchFilter] = useState('');
  const [sortField, setSortField] = useState('timestamp'); // 'timestamp' | 'amount' | 'prob'
  const [sortAsc, setSortAsc] = useState(false);

  // Batch CSV State
  const fileInputRef = useRef(null);
  const [csvFile, setCsvFile] = useState(null);
  const [csvError, setCsvError] = useState('');
  const [batchProcessing, setBatchProcessing] = useState(false);
  const [batchProgress, setBatchProgress] = useState({ current: 0, total: 0 });
  const [batchResults, setBatchResults] = useState([]);
  const [batchSuccessBanner, setBatchSuccessBanner] = useState(null);
  const abortBatchRef = useRef(false);

  // Fetch queue ledger items on mount
  useEffect(() => {
    let isMounted = true;
    async function loadQueueLedger() {
      setLoadingLedger(true);
      try {
        const data = await reviewQueueApi.getQueue({ limit: 50 });
        if (isMounted && data.items) {
          setQueueLedger(data.items);
        }
      } catch {
        // Safe fallback
      } finally {
        if (isMounted) setLoadingLedger(false);
      }
    }
    loadQueueLedger();
    return () => { isMounted = false; };
  }, []);

  const handleInputChange = (field, value) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const applyPreset = (presetKey) => {
    const preset = PRESETS[presetKey];
    if (!preset) return;
    const newForm = {
      external_id: generateSimExternalId(presetKey),
      Time: String(preset.data.Time),
      Amount: String(preset.data.Amount),
    };
    for (let i = 1; i <= 28; i++) {
      newForm[`V${i}`] = String(preset.data[`V${i}`]);
    }
    setFormData(newForm);
    setResult(null);
    setError('');
  };

  const handleReset = () => {
    setFormData(INITIAL_FORM);
    setResult(null);
    setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (scoring) return; // Prevent accidental duplicate submissions

    setScoring(true);
    setError('');
    setResult(null);

    try {
      const payload = {
        Time: parseFloat(formData.Time) || 0.0,
        Amount: parseFloat(formData.Amount) || 0.0,
      };

      if (formData.external_id && formData.external_id.trim()) {
        payload.external_id = formData.external_id.trim();
      }

      for (let i = 1; i <= 28; i++) {
        payload[`V${i}`] = parseFloat(formData[`V${i}`]) || 0.0;
      }

      const res = await transactionsApi.score(payload);
      setResult(res);

      // Add to session ledger
      const record = {
        transaction_id: res.prediction_id,
        external_id: res.external_id,
        amount: payload.Amount,
        fraud_probability: res.fraud_probability,
        raw_probability: res.raw_probability,
        decision: res.decision,
        risk_level: res.risk_level,
        expected_cost: res.expected_cost,
        model_version: res.model_version,
        created_at: res.created_at || new Date().toISOString(),
        explanation_summary: res.explanation?.analyst_summary,
      };
      setSessionScored((prev) => [record, ...prev]);
    } catch (err) {
      if (err.response?.status === 409) {
        setError(`Conflict: Transaction ID '${formData.external_id}' already exists in the database. Please provide a unique external ID or clear it for auto-generation.`);
      } else if (err.response?.status === 422) {
        const detail = err.response?.data?.detail;
        setError(`Validation Error: ${typeof detail === 'string' ? detail : JSON.stringify(detail || 'Invalid feature inputs. Ensure all 30 canonical numeric fields are provided.')}`);
      } else {
        setError(err.response?.data?.detail || 'Scoring request failed. Please check backend API availability.');
      }
    } finally {
      setScoring(false);
    }
  };

  // CSV Batch Parsing and Scoring Logic
  const handleDownloadSampleCsv = () => {
    const headers = ['external_id', 'Time', 'Amount', ...Array.from({ length: 28 }, (_, i) => `V${i + 1}`), 'Class'].join(',');
    const ts = Date.now().toString(36).slice(-4).toUpperCase();
    const makeRow = (id, preset, label) => {
      const vCols = Array.from({ length: 28 }, (_, i) => preset[`V${i + 1}`]);
      return [id, preset.Time, preset.Amount, ...vCols, label].join(',');
    };
    const row1 = makeRow(`TX-SMPL-GEN-${ts}`, PRESETS.genuine.data, 0);
    const row2 = makeRow(`TX-SMPL-REV-${ts}`, PRESETS.borderline.data, 0);
    const row3 = makeRow(`TX-SMPL-BLK-${ts}`, PRESETS.fraud.data, 1);
    const content = [headers, row1, row2, row3].join('\n');
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `fraud_scoring_sample_template_${Date.now()}.csv`);
    link.click();
  };

  const handleCsvFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setCsvFile(file);
      setCsvError('');
      setBatchResults([]);
      setBatchSuccessBanner(null);
      setBatchProgress({ current: 0, total: 0 });
    }
  };

  const parseCsvText = (text) => {
    const lines = text.split(/\r?\n/).filter(line => line.trim().length > 0);
    if (lines.length < 2) {
      throw new Error('The selected CSV file must contain a header row and at least one data row.');
    }

    const headers = lines[0].split(',').map(h => h.trim().replace(/^["']|["']$/g, ''));
    const headerMap = {};
    headers.forEach((h, idx) => {
      headerMap[h.toUpperCase()] = idx;
      headerMap[h.toLowerCase()] = idx;
      headerMap[h] = idx;
    });

    // Check all 30 canonical features (case-insensitively; Class target label is safely ignored)
    const missing = [];
    CANONICAL_FEATURES.forEach(feat => {
      if (
        headerMap[feat.toUpperCase()] === undefined &&
        headerMap[feat.toLowerCase()] === undefined &&
        headerMap[feat] === undefined
      ) {
        missing.push(feat);
      }
    });

    if (missing.length > 0) {
      throw new Error(
        `CSV is missing ${missing.length} required feature column(s): ${missing.slice(0, 5).join(', ')}${
          missing.length > 5 ? '...' : ''
        }. The ML model requires exactly 30 canonical numeric dimensions (Time, Amount, V1-V28).`
      );
    }

    const parsedRows = [];
    const parseErrors = [];

    for (let i = 1; i < lines.length; i++) {
      const rawCols = lines[i].split(',').map(c => c.trim().replace(/^["']|["']$/g, ''));
      if (rawCols.length < 2) continue;

      const rowPayload = {};
      let valid = true;
      let errorMsg = null;

      // Optional external_id
      const idIdx =
        headerMap['EXTERNAL_ID'] ??
        headerMap['ID'] ??
        headerMap['TRANSACTION_ID'] ??
        headerMap['external_id'] ??
        headerMap['id'] ??
        headerMap['transaction_id'];
      const rawId = (idIdx !== undefined && rawCols[idIdx]) ? rawCols[idIdx] : null;

      if (rawId) {
        rowPayload.external_id = rawId;
      } else {
        rowPayload.external_id = `BATCH-${i}-${Date.now().toString(36).slice(-4)}`;
      }

      let parsedAmount = null;
      for (const feat of CANONICAL_FEATURES) {
        const colIdx =
          headerMap[feat.toUpperCase()] ?? headerMap[feat.toLowerCase()] ?? headerMap[feat];
        const valStr = rawCols[colIdx];
        if (valStr === undefined || valStr === '') {
          valid = false;
          errorMsg = `Row ${i}: Column '${feat}' is missing or empty.`;
          break;
        }
        const numVal = parseFloat(valStr);
        if (Number.isNaN(numVal)) {
          valid = false;
          errorMsg = `Row ${i}: Column '${feat}' has non-numeric value '${valStr}'.`;
          break;
        }
        if (feat.toLowerCase() === 'amount') {
          if (numVal < 0) {
            valid = false;
            errorMsg = `Row ${i}: Amount must be non-negative (received ${numVal}).`;
            break;
          }
          parsedAmount = numVal;
        }
        rowPayload[feat] = numVal;
      }

      if (valid) {
        parsedRows.push({ rowIndex: i, payload: rowPayload });
      } else {
        parseErrors.push({
          rowIndex: i,
          external_id: rawId || `Row ${i}`,
          amount: parsedAmount,
          error: errorMsg,
        });
      }
    }

    return { parsedRows, parseErrors, totalRows: lines.length - 1 };
  };

  const handleStartBatchScoring = async () => {
    if (!csvFile) return;

    setBatchProcessing(true);
    setCsvError('');
    setBatchSuccessBanner(null);
    abortBatchRef.current = false;

    try {
      const text = await csvFile.text();
      const { parsedRows, parseErrors, totalRows } = parseCsvText(text);

      if (parsedRows.length === 0 && parseErrors.length === 0) {
        setCsvError('No transaction rows found in the CSV file.');
        setBatchProcessing(false);
        return;
      }

      const batchId = `BATCH-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
      setBatchProgress({ current: 0, total: totalRows || parsedRows.length });

      const allResults = [
        ...parseErrors.map(e => ({
          external_id: e.external_id || `Row ${e.rowIndex}`,
          amount: e.amount ?? null,
          decision: 'REJECTED',
          risk_level: 'UNKNOWN',
          status: 'ERROR',
          error: e.error,
        }))
      ];

      // Execute in chunks of 50 items for smooth progress reporting
      const CHUNK_SIZE = 50;
      let processedCount = 0;

      for (let i = 0; i < parsedRows.length; i += CHUNK_SIZE) {
        if (abortBatchRef.current) break;

        const chunk = parsedRows.slice(i, i + CHUNK_SIZE);
        const chunkItems = chunk.map(r => r.payload);

        try {
          const res = await transactionsApi.batchPredict({
            batch_id: batchId,
            filename: csvFile.name,
            items: chunkItems,
          });

          if (res.items && res.items.length > 0) {
            allResults.push(...res.items);
            const validScored = res.items.filter(item => item.status === 'SUCCESS' || (!item.error && item.decision !== 'FAILED'));
            if (validScored.length > 0) {
              setSessionScored(prev => [...validScored, ...prev]);
            }
          }
        } catch (chunkErr) {
          const formatErrorMsg = (err, rowIdx) => {
            const prefix = `Row ${rowIdx}: `;
            if (err.response) {
              const status = err.response.status;
              const detail = err.response.data?.detail;
              if (status === 404) {
                return `${prefix}Batch endpoint '/api/v1/transactions/batch-predict' not found (HTTP 404). Ensure backend service is up to date.`;
              }
              if (status === 401) {
                return `${prefix}Authentication expired (HTTP 401). Please re-login.`;
              }
              if (status === 403) {
                return `${prefix}Access forbidden (HTTP 403): insufficient analyst permissions.`;
              }
              if (status === 422) {
                if (Array.isArray(detail)) {
                  const issues = detail.map(d => `${d.loc ? d.loc.slice(-1)[0] : 'field'}: ${d.msg}`).join('; ');
                  return `${prefix}Payload validation failed (HTTP 422): ${issues}`;
                }
                return `${prefix}Validation error (HTTP 422): ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`;
              }
              if (status === 409) {
                return `${prefix}Transaction ID conflict (HTTP 409): ${typeof detail === 'string' ? detail : 'Duplicate identifier'}`;
              }
              if (typeof detail === 'string' && detail.trim()) {
                return `${prefix}${detail} (HTTP ${status})`;
              }
              return `${prefix}Server responded with HTTP ${status}`;
            }
            if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
              return `${prefix}Request timed out while waiting for inference service response`;
            }
            return `${prefix}${err.message || 'Inference connection failure'}`;
          };

          chunk.forEach(r => {
            allResults.push({
              external_id: r.payload.external_id || `Row ${r.rowIndex}`,
              amount: r.payload.Amount,
              decision: 'FAILED',
              risk_level: 'UNKNOWN',
              status: 'ERROR',
              error: formatErrorMsg(chunkErr, r.rowIndex),
            });
          });
        }

        processedCount += chunk.length;
        setBatchProgress({ current: Math.min(processedCount, parsedRows.length), total: parsedRows.length });
        setBatchResults([...allResults]);
      }

      setBatchResults([...allResults]);

      const successfulCount = allResults.filter(
        r => r.status === 'SUCCESS' || (!r.error && r.decision !== 'REJECTED' && r.decision !== 'FAILED')
      ).length;
      const failedCount = allResults.length - successfulCount;

      if (successfulCount > 0) {
        localStorage.setItem('fraud_latest_batch_id', batchId);
      }

      setBatchSuccessBanner({
        batchId,
        filename: csvFile.name,
        totalSubmitted: allResults.length,
        totalProcessed: successfulCount,
        failedCount: failedCount,
        hasErrors: failedCount > 0,
      });

    } catch (err) {
      setCsvError(err.message || 'Failed to process batch CSV.');
    } finally {
      setBatchProcessing(false);
    }
  };

  const handleDownloadResultsCsv = () => {
    if (batchResults.length === 0) return;
    const headers = ['Row', 'External_ID', 'Amount', 'Decision', 'Fraud_Probability', 'Raw_Probability', 'Risk_Level', 'Expected_Cost', 'Model_Version', 'Status'];
    const rows = batchResults.map((r, idx) => [
      idx + 1,
      r.external_id || '',
      r.amount !== null && r.amount !== undefined ? r.amount : '',
      r.decision || 'N/A',
      r.fraud_probability !== undefined ? (r.fraud_probability * 100).toFixed(2) + '%' : '',
      r.raw_probability !== undefined ? (r.raw_probability * 100).toFixed(2) + '%' : '',
      r.risk_level || 'N/A',
      r.expected_cost !== undefined ? '$' + r.expected_cost.toFixed(2) : '',
      r.model_version || '',
      r.error ? `Error: ${r.error}` : 'SUCCESS'
    ].join(','));
    const content = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `batch_fraud_results_${Date.now()}.csv`);
    link.click();
  };

  // Combine session scored and queue ledger items
  const combinedTransactions = useMemo(() => {
    const list = [...sessionScored];
    const seen = new Set(sessionScored.map((item) => item.external_id));

    queueLedger.forEach((item) => {
      if (!seen.has(item.external_id)) {
        list.push({
          transaction_id: item.transaction_id,
          external_id: item.external_id,
          amount: item.amount,
          fraud_probability: item.fraud_probability,
          raw_probability: item.raw_probability,
          decision: item.decision,
          risk_level: item.risk_level,
          expected_cost: null,
          model_version: item.model_version,
          created_at: item.transaction_created_at,
          explanation_summary: item.explanation_summary,
        });
        seen.add(item.external_id);
      }
    });

    let filtered = list;
    if (searchFilter.trim()) {
      const q = searchFilter.toLowerCase().trim();
      filtered = filtered.filter(
        (t) =>
          t.external_id.toLowerCase().includes(q) ||
          String(t.amount).includes(q) ||
          (t.risk_level && t.risk_level.toLowerCase().includes(q))
      );
    }

    return filtered.sort((a, b) => {
      let comparison = 0;
      if (sortField === 'amount') {
        comparison = (a.amount || 0) - (b.amount || 0);
      } else if (sortField === 'prob') {
        comparison = (a.fraud_probability || 0) - (b.fraud_probability || 0);
      } else {
        const timeA = new Date(a.created_at).getTime() || 0;
        const timeB = new Date(b.created_at).getTime() || 0;
        comparison = timeA - timeB;
      }
      return sortAsc ? comparison : -comparison;
    });
  }, [sessionScored, queueLedger, searchFilter, sortField, sortAsc]);

  const toggleSort = (field) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  // Batch summary stats
  const batchStats = useMemo(() => {
    let approve = 0;
    let review = 0;
    let block = 0;
    let errors = 0;
    batchResults.forEach(r => {
      if (r.error || r.status === 'ERROR' || r.decision === 'FAILED' || r.decision === 'REJECTED') {
        errors++;
      } else if (r.decision === 'APPROVE') {
        approve++;
      } else if (r.decision === 'REVIEW') {
        review++;
      } else if (r.decision === 'BLOCK') {
        block++;
      }
    });
    const successfullyScored = approve + review + block;
    return { approve, review, block, errors, successfullyScored, total: batchResults.length };
  }, [batchResults]);

  // Extract and format SHAP feature contributions from the prediction response
  const shapContributions = useMemo(() => {
    const expl = result?.explanation;
    if (!expl) return [];

    // The backend prediction API returns top_contributions
    const list = expl.top_contributions || expl.top_features || expl.contributions || [];
    if (!Array.isArray(list) || list.length === 0) return [];

    return list.map((item) => {
      const featName = item.feature || item.feature_name || item.name || 'Unknown';
      const val = typeof item.contribution === 'number'
        ? item.contribution
        : typeof item.shap_value === 'number'
        ? item.shap_value
        : typeof item.value === 'number'
        ? item.value
        : parseFloat(item.contribution || item.shap_value || item.value) || 0;

      return {
        feature: featName,
        contribution: val,
        absolute_contribution: typeof item.absolute_contribution === 'number'
          ? item.absolute_contribution
          : Math.abs(val),
        direction: item.direction || (val >= 0 ? 'increases_risk' : 'decreases_risk'),
      };
    });
  }, [result]);

  return (
    <div className="page-container">
      {/* Page Header with Tab Navigation */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <Cpu className="w-6 h-6 text-teal" />
            <span>Transaction Analysis</span>
          </h1>
          <p className="page-subtitle">
            Synchronous calibrated risk scoring, cost-sensitive operational decisions, and TreeSHAP feature attributions.
          </p>
        </div>

        <div className="button-group">
          <button
            type="button"
            className={`filter-btn ${activeTab === 'single' ? 'active' : ''}`}
            onClick={() => setActiveTab('single')}
          >
            Single Transaction
          </button>
          <button
            type="button"
            className={`filter-btn ${activeTab === 'batch' ? 'active' : ''}`}
            onClick={() => setActiveTab('batch')}
          >
            Batch CSV Analysis
          </button>
          <button
            type="button"
            className={`filter-btn ${activeTab === 'ledger' ? 'active' : ''}`}
            onClick={() => setActiveTab('ledger')}
          >
            Transaction History ({combinedTransactions.length})
          </button>
        </div>
      </div>

      {/* =========================================================================
          TAB 1: SINGLE TRANSACTION ANALYSIS (INPUT -> PROCESSING -> OUTPUT)
          ========================================================================= */}
      {activeTab === 'single' && (
        <>
          {/* Preset Benchmark Toolbar */}
          <div className="card preset-bar mb-6">
            <div className="flex items-center gap-2 text-xs font-semibold text-primary">
              <Sparkles className="w-4 h-4 text-teal" />
              <span>Load Benchmark Scenario:</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(PRESETS).map(([key, preset]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => applyPreset(key)}
                  className="btn btn-secondary btn-sm"
                  title={preset.description}
                  disabled={scoring}
                >
                  {preset.name}
                </button>
              ))}
              <button
                type="button"
                onClick={handleReset}
                className="btn btn-secondary btn-sm text-muted"
                title="Reset all inputs"
                disabled={scoring}
              >
                <RotateCcw className="w-3.5 h-3.5 mr-1" />
                Reset
              </button>
            </div>
          </div>

          {error && (
            <div className="alert alert-error mb-6">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Explicit INPUT -> PROCESSING -> OUTPUT Grid */}
          <div className="grid-score-layout">
            {/* INPUT SECTION */}
            <div>
              <form onSubmit={handleSubmit} className="card p-5">
                <div className="flex justify-between items-center mb-4 pb-3 border-b border-slate-200">
                  <div className="flex items-center gap-2">
                    <span className="flow-step-badge active">STEP 1</span>
                    <h2 className="text-sm font-bold text-primary">Transaction Input Payload</h2>
                  </div>
                  <span className="text-xs text-muted font-mono">30 Required Features</span>
                </div>

                <div className="grid-form-header mb-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className="form-group">
                    <label className="form-label">External Identifier (Optional)</label>
                    <input
                      type="text"
                      placeholder="Auto-generated if empty"
                      value={formData.external_id}
                      onChange={(e) => handleInputChange('external_id', e.target.value)}
                      disabled={scoring}
                      className="form-input font-mono text-xs"
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">
                      Transaction Amount ($ USD) <span className="text-red font-bold">*</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      required
                      min="0"
                      value={formData.Amount}
                      onChange={(e) => handleInputChange('Amount', e.target.value)}
                      disabled={scoring}
                      className="form-input font-mono font-semibold"
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">
                      Time Reference (sec) <span className="text-red font-bold">*</span>
                    </label>
                    <input
                      type="number"
                      step="1"
                      required
                      value={formData.Time}
                      onChange={(e) => handleInputChange('Time', e.target.value)}
                      disabled={scoring}
                      className="form-input font-mono text-xs"
                    />
                  </div>
                </div>

                <div className="mb-2 flex justify-between items-center">
                  <span className="text-xs font-semibold text-secondary uppercase tracking-wider">
                    PCA Dimension Inputs (V1 — V28)
                  </span>
                  <span className="text-xs text-muted">Standardized Latent Factors</span>
                </div>

                <div className="grid-pca-inputs">
                  {Array.from({ length: 28 }, (_, i) => `V${i + 1}`).map((feat) => (
                    <div key={feat} className="pca-input-item">
                      <label className="pca-label font-mono">{feat}</label>
                      <input
                        type="number"
                        step="0.001"
                        required
                        value={formData[feat]}
                        onChange={(e) => handleInputChange(feat, e.target.value)}
                        disabled={scoring}
                        className="form-input form-input-sm font-mono text-right"
                      />
                    </div>
                  ))}
                </div>

                {/* Submit / Trigger Processing */}
                <div className="mt-5 pt-4 border-t border-slate-200 flex items-center justify-between">
                  <span className="text-xs text-muted">Payload evaluated against active production XGBoost baseline</span>
                  <button
                    type="submit"
                    disabled={scoring}
                    className="btn btn-primary px-6"
                  >
                    {scoring ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin mr-1" />
                        <span>Processing Inference...</span>
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4 mr-1" />
                        <span>Score Transaction</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>

            {/* PROCESSING & OUTPUT SECTION */}
            <div>
              {scoring ? (
                /* PROCESSING STATE */
                <div className="card p-8 h-full flex flex-col items-center justify-center text-center">
                  <div className="w-14 h-14 rounded-full bg-teal-50 border border-teal-200 flex items-center justify-center text-teal mb-4 animate-pulse">
                    <Cpu className="w-7 h-7" />
                  </div>
                  <span className="flow-step-badge active mb-2">STEP 2: PROCESSING</span>
                  <h3 className="text-base font-bold text-primary mb-1">Analyzing Transaction Risk</h3>
                  <p className="text-xs text-secondary max-w-sm mb-4 leading-relaxed">
                    Executing gradient-boosted decision trees, applying isotonic posterior probability calibration, and computing local TreeSHAP attributions...
                  </p>
                  <div className="w-48 csv-progress-container">
                    <div className="csv-progress-fill w-3/4 animate-pulse"></div>
                  </div>
                  <span className="text-xs text-muted font-mono mt-2">Active model: xgb-cost-v1</span>
                </div>
              ) : result ? (
                /* OUTPUT SECTION */
                <div className="flex flex-col gap-4">
                  {/* Decision Summary Card */}
                  <div className="card p-5">
                    <div className="flex justify-between items-start mb-4 pb-3 border-b border-slate-200">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="flow-step-badge completed">STEP 3: OUTPUT</span>
                          <span className="text-xs font-semibold uppercase tracking-wider text-muted">
                            Cost-Sensitive Decision
                          </span>
                        </div>
                        <div className="mt-1 flex items-center gap-2">
                          <StatusBadge type="decision" value={result.decision} className="text-sm px-3 py-1 font-bold" />
                          <StatusBadge type="risk" value={result.risk_level} />
                        </div>
                      </div>
                      <div className="text-right">
                        <span className="text-xs text-muted block">Model Version</span>
                        <div className="text-xs font-mono font-bold text-primary">{result.model_version}</div>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-3 p-3 bg-slate-50 border border-slate-200 rounded-md mb-4">
                      <div>
                        <span className="text-xs font-semibold text-muted uppercase">Calibrated P(Fraud)</span>
                        <div className="text-lg font-bold font-mono text-teal">
                          {(result.fraud_probability * 100).toFixed(2)}%
                        </div>
                      </div>
                      <div>
                        <span className="text-xs font-semibold text-muted uppercase">Raw Model Margin</span>
                        <div className="text-lg font-bold font-mono text-muted">
                          {(result.raw_probability * 100).toFixed(2)}%
                        </div>
                      </div>
                      <div>
                        <span className="text-xs font-semibold text-muted uppercase">Expected Loss</span>
                        <div className="text-lg font-bold font-mono text-primary">
                          ${result.expected_cost?.toFixed(2) || '0.00'}
                        </div>
                      </div>
                    </div>

                    <div className="p-2.5 bg-slate-50 border border-slate-200 rounded text-xs font-mono space-y-1 mb-3 text-secondary">
                      <div className="flex justify-between">
                        <span className="text-muted">Transaction ID:</span>
                        <strong className="text-primary">{result.external_id}</strong>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Decision Policy Thresholds:</span>
                        <span>τ_rev={result.policy_parameters?.threshold_review} | τ_blk={result.policy_parameters?.threshold_block}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Probability Calibration:</span>
                        <span>{result.policy_parameters?.calibration_variant}</span>
                      </div>
                    </div>

                    {/* Operational Next Action */}
                    {result.decision === 'REVIEW' && (
                      <div className="p-3 bg-amber-50 border border-amber-200 rounded text-xs text-amber-900 flex justify-between items-center">
                        <div className="flex items-center gap-1.5">
                          <AlertTriangle className="w-4 h-4 text-amber" />
                          <span>Requires operator review (0.042 ≤ P &lt; 0.7539).</span>
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            setReviewCase({
                              external_id: result.external_id,
                              transaction_id: result.prediction_id || result.transaction_id,
                              amount: parseFloat(formData.Amount),
                              fraud_probability: result.fraud_probability,
                              raw_probability: result.raw_probability,
                              risk_level: result.risk_level,
                              explanation_summary: result.explanation?.analyst_summary,
                            })
                          }
                          className="btn btn-secondary btn-xs font-semibold"
                        >
                          <span>Review Case</span>
                          <ExternalLink className="w-3 h-3 ml-1" />
                        </button>
                      </div>
                    )}
                  </div>

                  {/* TreeSHAP Local Explanation Card */}
                  {result && (
                    <div className="card p-5" key={result.prediction_id || result.external_id || 'shap-card'}>
                      <div className="flex justify-between items-center mb-3">
                        <h3 className="text-sm font-bold text-primary flex items-center gap-1.5">
                          <Layers className="w-4 h-4 text-teal" />
                          <span>TreeSHAP Local Feature Attributions</span>
                        </h3>
                        {result.explanation?.base_value !== undefined && (
                          <span className="text-xs font-mono text-muted">
                            Base Margin: {result.explanation.base_value.toFixed(3)}
                          </span>
                        )}
                      </div>

                      {result.explanation?.analyst_summary && (
                        <div className="p-2.5 bg-slate-50 border border-slate-200 rounded text-xs text-secondary mb-3 leading-relaxed">
                          {result.explanation.analyst_summary}
                        </div>
                      )}

                      {shapContributions.length > 0 ? (
                        <>
                          <div className="mb-2">
                            <span className="text-xs font-semibold text-muted block mb-1 uppercase">
                              Top Risk Drivers (SHAP Value Impact in Log-Odds Space)
                            </span>
                            <div style={{ width: '100%', height: Math.max(180, shapContributions.length * 36) }}>
                              <ResponsiveContainer width="100%" height="100%">
                                <BarChart
                                  data={shapContributions}
                                  layout="vertical"
                                  margin={{ top: 5, right: 25, left: 15, bottom: 5 }}
                                >
                                  <XAxis
                                    type="number"
                                    tick={{ fontSize: 10, fill: '#64748b' }}
                                    domain={['auto', 'auto']}
                                    tickFormatter={(val) => (typeof val === 'number' ? val.toFixed(2) : val)}
                                  />
                                  <YAxis
                                    dataKey="feature"
                                    type="category"
                                    tick={{ fontSize: 11, fill: '#1e293b', fontWeight: 600 }}
                                    width={45}
                                  />
                                  <ReferenceLine x={0} stroke="#94a3b8" strokeDasharray="3 3" />
                                  <Tooltip
                                    contentStyle={{
                                      backgroundColor: '#0f172a',
                                      borderColor: '#1e293b',
                                      borderRadius: '6px',
                                      color: '#fff',
                                      fontSize: '11px',
                                    }}
                                    formatter={(val) => {
                                      const num = typeof val === 'number' ? val : parseFloat(val) || 0;
                                      const sign = num > 0 ? '+' : '';
                                      const dir = num > 0 ? 'Increases Risk' : 'Decreases Risk';
                                      return [`${sign}${num.toFixed(4)} (${dir})`, 'SHAP Attribution'];
                                    }}
                                    labelFormatter={(label) => `Feature: ${label}`}
                                  />
                                  <Bar dataKey="contribution">
                                    {shapContributions.map((entry, index) => (
                                      <Cell
                                        key={`shap-cell-${entry.feature}-${index}`}
                                        fill={entry.contribution > 0 ? '#ef4444' : '#0d9488'}
                                      />
                                    ))}
                                  </Bar>
                                </BarChart>
                              </ResponsiveContainer>
                            </div>
                          </div>

                          {/* Feature Contribution Value Cards */}
                          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 my-2">
                            {shapContributions.map((item) => (
                              <div
                                key={item.feature}
                                className="p-2 rounded bg-slate-50 border border-slate-200 text-center font-mono"
                              >
                                <div className="text-xs font-bold text-primary">{item.feature}</div>
                                <div
                                  className={`text-xs font-semibold ${
                                    item.contribution > 0 ? 'text-red' : 'text-teal'
                                  }`}
                                >
                                  {item.contribution > 0
                                    ? `+${item.contribution.toFixed(4)}`
                                    : item.contribution.toFixed(4)}
                                </div>
                              </div>
                            ))}
                          </div>

                          <div className="text-xs text-muted pt-2 border-t border-slate-100 flex items-center gap-1">
                            <Info className="w-3.5 h-3.5 flex-shrink-0" />
                            <span>Positive SHAP values (red) increase fraud probability; negative values (teal) decrease risk.</span>
                          </div>
                        </>
                      ) : (
                        <div className="p-5 text-center bg-slate-50 border border-slate-200 rounded-md my-2">
                          <Info className="w-5 h-5 text-muted mx-auto mb-1.5" />
                          <p className="text-xs text-muted font-medium">Feature attribution unavailable for this prediction</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                /* INITIAL EMPTY STATE */
                <div className="card p-8 h-full flex flex-col items-center justify-center text-center">
                  <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center text-muted mb-3">
                    <Cpu className="w-6 h-6" />
                  </div>
                  <h3 className="text-base font-bold text-primary mb-1">Awaiting Scoring Submission</h3>
                  <p className="text-xs text-muted max-w-sm mb-4 leading-relaxed">
                    Enter transaction values or select one of the benchmark presets above, then click <strong>Score Transaction</strong> to evaluate ML risk.
                  </p>
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {/* =========================================================================
          TAB 2: BATCH CSV ANALYSIS
          ========================================================================= */}
      {activeTab === 'batch' && (
        <div className="space-y-6">
          {/* Format Specification Card */}
          <div className="card p-5">
            <div className="flex justify-between items-start flex-wrap gap-3 mb-3">
              <div>
                <h2 className="text-sm font-bold text-primary flex items-center gap-2">
                  <FileSpreadsheet className="w-5 h-5 text-teal" />
                  <span>Batch CSV Inference Pipeline</span>
                </h2>
                <p className="text-xs text-muted mt-1">
                  Upload transaction batches in CSV format for automated client-validated scoring against the production model.
                </p>
              </div>
              <button
                type="button"
                onClick={handleDownloadSampleCsv}
                className="btn btn-secondary btn-sm flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download Sample CSV Template</span>
              </button>
            </div>

            <div className="p-3 bg-slate-50 border border-slate-200 rounded-md text-xs text-secondary mb-3 space-y-1">
              <strong className="text-primary block">Supported Format & Required Schema:</strong>
              <div>• File format: Comma-Separated Values (<code className="font-mono text-primary">.csv</code>)</div>
              <div>• <strong>30 Mandatory Columns:</strong> <code className="font-mono text-primary">Amount</code>, <code className="font-mono text-primary">Time</code>, and <code className="font-mono text-primary">V1</code> through <code className="font-mono text-primary">V28</code> (case-insensitive headers supported).</div>
              <div>• <strong>Optional Column:</strong> <code className="font-mono text-primary">external_id</code> (unique transaction identifier).</div>
              <div>• All feature cells must contain valid numeric float values. Rows with missing columns or non-numeric tokens will fail client-side preflight validation.</div>
            </div>

            {/* Dropzone */}
            <div 
              className="csv-dropzone"
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={handleCsvFileChange}
                disabled={batchProcessing}
              />
              <UploadCloud className="csv-dropzone-icon" />
              <div className="text-sm font-semibold text-primary mb-1">
                {csvFile ? csvFile.name : 'Click to select CSV file or drag and drop'}
              </div>
              <p className="text-xs text-muted">
                {csvFile ? `${(csvFile.size / 1024).toFixed(1)} KB — Ready for evaluation` : 'Standard UTF-8 formatted CSV with up to 500 rows per batch'}
              </p>
            </div>

            {csvError && (
              <div className="alert alert-error mt-4">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{csvError}</span>
              </div>
            )}

            {/* Action Bar */}
            {csvFile && (
              <div className="mt-4 pt-3 border-t border-slate-200 flex justify-between items-center">
                <span className="text-xs text-muted">
                  Selected file: <strong className="text-primary font-mono">{csvFile.name}</strong>
                </span>

                <div className="flex items-center gap-2">
                  {batchProcessing ? (
                    <button
                      type="button"
                      onClick={() => { abortBatchRef.current = true; }}
                      className="btn btn-secondary btn-sm text-red-600"
                    >
                      Abort Batch
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={handleStartBatchScoring}
                      className="btn btn-primary btn-sm flex items-center gap-1.5"
                    >
                      <Play className="w-3.5 h-3.5" />
                      <span>Execute Batch Inference</span>
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Live Progress Bar */}
            {batchProcessing && (
              <div className="mt-4 p-4 bg-slate-50 border border-slate-200 rounded-md">
                <div className="flex justify-between text-xs font-semibold text-primary mb-1">
                  <span>Processing Row {batchProgress.current} of {batchProgress.total}</span>
                  <span>{Math.round((batchProgress.current / (batchProgress.total || 1)) * 100)}%</span>
                </div>
                <div className="csv-progress-container">
                  <div 
                    className="csv-progress-fill"
                    style={{ width: `${(batchProgress.current / (batchProgress.total || 1)) * 100}%` }}
                  />
                </div>
                <p className="text-xs text-muted mt-2">
                  Evaluating calibrated probabilities against asymmetric cost matrix...
                </p>
              </div>
            )}
          </div>

          {/* Batch Completion Banner */}
          {batchSuccessBanner && (
            <div
              className={`alert ${
                batchSuccessBanner.totalProcessed === 0
                  ? 'alert-error'
                  : batchSuccessBanner.hasErrors
                  ? 'alert-warning'
                  : 'alert-success'
              } flex items-center justify-between flex-wrap gap-3`}
            >
              <div className="flex items-center gap-2.5">
                {batchSuccessBanner.totalProcessed === 0 ? (
                  <XCircle className="w-5 h-5 text-red flex-shrink-0" />
                ) : batchSuccessBanner.hasErrors ? (
                  <AlertTriangle className="w-5 h-5 text-amber flex-shrink-0" />
                ) : (
                  <CheckCircle2 className="w-5 h-5 text-emerald flex-shrink-0" />
                )}
                <div>
                  <div className="text-sm font-bold text-primary">
                    {batchSuccessBanner.totalProcessed === 0
                      ? 'Batch Processing Failed: Zero Predictions Produced'
                      : batchSuccessBanner.hasErrors
                      ? 'Batch Completed with Errors'
                      : 'Batch Fraud Scoring Complete & Persisted'}
                  </div>
                  <div className="text-xs text-secondary mt-0.5">
                    Batch ID: <span className="font-mono font-semibold text-primary">{batchSuccessBanner.batchId}</span> •{' '}
                    {batchSuccessBanner.totalProcessed === 0 ? (
                      <span className="text-red font-medium">
                        Scored 0 of {batchSuccessBanner.totalSubmitted} records. All rows failed preflight validation or model inference.
                      </span>
                    ) : (
                      <span>
                        Successfully scored {batchSuccessBanner.totalProcessed} of {batchSuccessBanner.totalSubmitted} records against calibrated XGBoost.
                        {batchSuccessBanner.hasErrors && (
                          <span className="text-red font-semibold ml-1.5">
                            ({batchSuccessBanner.failedCount} row{batchSuccessBanner.failedCount > 1 ? 's' : ''} failed)
                          </span>
                        )}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              {batchSuccessBanner.totalProcessed > 0 && (
                <Link
                  to="/"
                  className="btn btn-primary btn-sm flex items-center gap-1.5"
                >
                  <span>View Scored Records in Dashboard</span>
                  <ArrowRight className="w-4 h-4" />
                </Link>
              )}
            </div>
          )}

          {/* Batch Summary KPI Grid */}
          {batchResults.length > 0 && (
            <>
              <div className="grid-cards">
                <div className="card p-4">
                  <span className="text-xs text-muted uppercase font-semibold">Successfully Scored</span>
                  <div className="text-2xl font-bold font-mono text-primary mt-1">
                    {batchStats.successfullyScored} <span className="text-sm font-normal text-muted">/ {batchStats.total}</span>
                  </div>
                  <span className="text-xs text-muted">Successfully processed records</span>
                </div>

                <div className="card p-4">
                  <span className="text-xs text-muted uppercase font-semibold">Approved</span>
                  <div className="text-2xl font-bold font-mono text-emerald mt-1">{batchStats.approve}</div>
                  <span className="text-xs text-muted">P &lt; 0.0420 (Immediate settlement)</span>
                </div>

                <div className="card p-4">
                  <span className="text-xs text-muted uppercase font-semibold">Flagged for Review</span>
                  <div className="text-2xl font-bold font-mono text-amber mt-1">{batchStats.review}</div>
                  <span className="text-xs text-muted">0.0420 ≤ P &lt; 0.7539 (Operator queue)</span>
                </div>

                <div className="card p-4">
                  <span className="text-xs text-muted uppercase font-semibold">Blocked High-Risk</span>
                  <div className="text-2xl font-bold font-mono text-red mt-1">{batchStats.block}</div>
                  <span className="text-xs text-muted">P ≥ 0.7539 (Automated decline)</span>
                </div>

                {batchStats.errors > 0 && (
                  <div className="card p-4">
                    <span className="text-xs text-muted uppercase font-semibold">Failed Validation</span>
                    <div className="text-2xl font-bold font-mono text-red mt-1">{batchStats.errors}</div>
                    <span className="text-xs text-muted">Malformed or rejected rows</span>
                  </div>
                )}
              </div>

              {/* Batch Results Table */}
              <div className="card">
                <div className="p-4 border-b border-slate-200 flex justify-between items-center flex-wrap gap-2">
                  <div>
                    <h3 className="text-sm font-bold text-primary">Batch Inference Results</h3>
                    <p className="text-xs text-muted">Row-level operational decisions and calibrated probabilities</p>
                  </div>
                  <button
                    type="button"
                    onClick={handleDownloadResultsCsv}
                    className="btn btn-secondary btn-sm flex items-center gap-1.5"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download Results CSV</span>
                  </button>
                </div>

                <div className="table-responsive max-h-96 overflow-y-auto">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Identifier</th>
                        <th>Amount</th>
                        <th>Calibrated P(Fraud)</th>
                        <th>Risk Tier</th>
                        <th>Decision</th>
                        <th>Expected Cost</th>
                        <th>Status / Error Details</th>
                      </tr>
                    </thead>
                    <tbody>
                      {batchResults.map((r, idx) => (
                        <tr key={idx}>
                          <td className="font-mono text-xs text-muted">{idx + 1}</td>
                          <td className="font-mono text-xs font-semibold text-primary">{r.external_id}</td>
                          <td className="font-mono text-xs text-primary font-semibold">
                            {r.amount !== null && r.amount !== undefined ? `$${r.amount.toFixed(2)}` : '--'}
                          </td>
                          <td className="font-mono text-xs font-bold text-teal">
                            {r.fraud_probability !== undefined && r.fraud_probability !== null ? `${(r.fraud_probability * 100).toFixed(2)}%` : '--'}
                          </td>
                          <td>
                            <StatusBadge type="risk" value={r.risk_level} />
                          </td>
                          <td>
                            <StatusBadge type="decision" value={r.decision} />
                          </td>
                          <td className="font-mono text-xs text-primary">
                            {r.expected_cost !== undefined && r.expected_cost !== null ? `$${r.expected_cost.toFixed(2)}` : '--'}
                          </td>
                          <td>
                            {r.error ? (
                              <div className="flex flex-col gap-0.5">
                                <span className="text-xs text-red font-semibold flex items-center gap-1">
                                  <XCircle className="w-3.5 h-3.5 flex-shrink-0" /> Failed
                                </span>
                                <span className="text-[11px] text-red leading-tight max-w-xs break-words" title={r.error}>
                                  {r.error}
                                </span>
                              </div>
                            ) : (
                              <span className="text-xs text-emerald font-semibold flex items-center gap-1">
                                <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" /> Scored
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* =========================================================================
          TAB 3: TRANSACTION LEDGER & HISTORY
          ========================================================================= */}
      {activeTab === 'ledger' && (
        <div className="card">
          {/* Table Toolbar */}
          <div className="table-header-bar flex-wrap gap-3">
            <div className="flex items-center gap-2">
              <div className="input-with-icon">
                <Search className="input-icon" />
                <input
                  type="text"
                  placeholder="Search by Transaction ID or Amount..."
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  className="form-input form-input-sm w-72"
                />
              </div>
            </div>

            <div className="text-xs text-muted">
              Showing <strong className="text-primary">{combinedTransactions.length}</strong> recorded transactions
            </div>
          </div>

          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th onClick={() => toggleSort('timestamp')} className="cursor-pointer">
                    <div className="flex items-center gap-1">
                      <span>Transaction ID / Time</span>
                      <ArrowUpDown className="w-3 h-3" />
                    </div>
                  </th>
                  <th onClick={() => toggleSort('amount')} className="cursor-pointer">
                    <div className="flex items-center gap-1">
                      <span>Amount</span>
                      <ArrowUpDown className="w-3 h-3" />
                    </div>
                  </th>
                  <th onClick={() => toggleSort('prob')} className="cursor-pointer">
                    <div className="flex items-center gap-1">
                      <span>P(Fraud)</span>
                      <ArrowUpDown className="w-3 h-3" />
                    </div>
                  </th>
                  <th>Raw Score</th>
                  <th>Risk Level</th>
                  <th>Decision</th>
                  <th>Model Version</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {loadingLedger ? (
                  <tr>
                    <td colSpan={8} className="table-loading-cell">
                      <div className="flex items-center justify-center gap-2 text-muted text-xs">
                        <Loader2 className="w-4 h-4 animate-spin text-teal" />
                        <span>Loading transaction records...</span>
                      </div>
                    </td>
                  </tr>
                ) : combinedTransactions.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="table-empty-cell">
                      <EmptyState
                        icon={History}
                        title="No Transactions Found"
                        description="Score a transaction above or check the review queue to view ingested ledger records."
                        className="py-6"
                      />
                    </td>
                  </tr>
                ) : (
                  combinedTransactions.map((tx) => (
                    <tr key={tx.transaction_id || tx.external_id}>
                      <td>
                        <span className="font-mono text-xs font-semibold text-primary">{tx.external_id}</span>
                        <div className="text-xs text-muted">
                          {tx.created_at ? new Date(tx.created_at).toLocaleString() : 'Recent'}
                        </div>
                      </td>
                      <td>
                        <span className="font-mono font-semibold text-primary text-xs">
                          ${typeof tx.amount === 'number' ? tx.amount.toFixed(2) : tx.amount}
                        </span>
                      </td>
                      <td>
                        <span className="font-mono font-bold text-teal text-xs">
                          {typeof tx.fraud_probability === 'number'
                            ? `${(tx.fraud_probability * 100).toFixed(2)}%`
                            : '--'}
                        </span>
                      </td>
                      <td>
                        <span className="font-mono text-xs text-muted">
                          {typeof tx.raw_probability === 'number'
                            ? `${(tx.raw_probability * 100).toFixed(2)}%`
                            : '--'}
                        </span>
                      </td>
                      <td>
                        <StatusBadge type="risk" value={tx.risk_level} />
                      </td>
                      <td>
                        <StatusBadge type="decision" value={tx.decision} />
                      </td>
                      <td>
                        <span className="font-mono text-xs text-muted">{tx.model_version || 'xgb-cost-v1'}</span>
                      </td>
                      <td>
                        {tx.decision === 'REVIEW' ? (
                          <button
                            type="button"
                            onClick={() =>
                              setReviewCase({
                                external_id: tx.external_id,
                                transaction_id: tx.transaction_id,
                                amount: tx.amount,
                                fraud_probability: tx.fraud_probability,
                                raw_probability: tx.raw_probability,
                                risk_level: tx.risk_level,
                                explanation_summary: tx.explanation_summary,
                              })
                            }
                            className="btn btn-secondary btn-xs font-semibold flex items-center gap-1"
                          >
                            <span>Review</span>
                            <ExternalLink className="w-3 h-3" />
                          </button>
                        ) : (
                          <span className="text-xs text-muted font-mono">Completed</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Case Details Drawer Modal */}
      {reviewCase && (
        <CaseDetailsModal
          caseData={reviewCase}
          onClose={() => setReviewCase(null)}
          onAdjudicationSuccess={() => {
            setReviewCase(null);
            // Refresh ledger
            reviewQueueApi.getQueue({ limit: 50 }).then((data) => {
              if (data.items) setQueueLedger(data.items);
            });
          }}
        />
      )}
    </div>
  );
}
