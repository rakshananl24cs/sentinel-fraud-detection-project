import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { feedbackApi } from '../api/client';
import StatusBadge from './StatusBadge';
import { 
  X, 
  ShieldCheck, 
  Send, 
  Check, 
  Loader2, 
  AlertCircle,
  CheckCircle2,
  History,
  FileText,
  Info
} from 'lucide-react';

export default function CaseDetailsModal({ 
  transaction, 
  caseData,
  onClose, 
  onFeedbackSubmitted,
  onAdjudicationSuccess 
}) {
  const currentTx = transaction || caseData;
  const handleSuccess = onFeedbackSubmitted || onAdjudicationSuccess;
  const { hasRole } = useAuth();
  const isAdmin = hasRole('ADMIN');

  const [feedbacks, setFeedbacks] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [historyError, setHistoryError] = useState('');

  // New feedback form state
  const [decision, setDecision] = useState('CONFIRMED_FRAUD');
  const [reasonCode, setReasonCode] = useState('');
  const [comment, setComment] = useState('');
  const [isVerified, setIsVerified] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // Verifying existing record state
  const [verifyingId, setVerifyingId] = useState(null);

  useEffect(() => {
    let isMounted = true;
    async function loadHistory() {
      if (!currentTx) return;
      setLoadingHistory(true);
      setHistoryError('');
      try {
        const targetId = currentTx.external_id || currentTx.transaction_id;
        const historyData = await feedbackApi.getHistory(targetId);
        if (isMounted) {
          setFeedbacks(historyData);
        }
      } catch (err) {
        if (isMounted) {
          setHistoryError(err.response?.data?.detail || 'Could not load adjudication history.');
        }
      } finally {
        if (isMounted) setLoadingHistory(false);
      }
    }

    if (currentTx) {
      loadHistory();
    }

    return () => {
      isMounted = false;
    };
  }, [currentTx]);

  const handleSubmitFeedback = async (e) => {
    e.preventDefault();
    setFormError('');
    setSuccessMsg('');
    setSubmitting(true);

    try {
      const targetId = currentTx.external_id || currentTx.transaction_id;
      const result = await feedbackApi.submit(targetId, {
        decision,
        reason_code: reasonCode,
        comment,
        is_verified: isAdmin ? isVerified : false,
      });

      setSuccessMsg(`Feedback recorded successfully (Sequence #${result.feedback_sequence}).`);
      setComment('');
      setReasonCode('');
      setIsVerified(false);

      // Refresh feedback history
      const updatedHistory = await feedbackApi.getHistory(targetId);
      setFeedbacks(updatedHistory);

      if (handleSuccess) {
        handleSuccess(result);
      }
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to submit operator feedback.';
      setFormError(detail);
    } finally {
      setSubmitting(false);
    }
  };

  const handleVerifyExistingFeedback = async (feedbackId) => {
    setVerifyingId(feedbackId);
    setFormError('');
    try {
      const targetId = currentTx.external_id || currentTx.transaction_id;
      await feedbackApi.verify(targetId, feedbackId);
      const updatedHistory = await feedbackApi.getHistory(targetId);
      setFeedbacks(updatedHistory);
      setSuccessMsg('Feedback record verified by administrator.');
      if (handleSuccess) {
        handleSuccess();
      }
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to verify feedback record.';
      setFormError(detail);
    } finally {
      setVerifyingId(null);
    }
  };

  if (!currentTx) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-drawer" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-teal" />
            <div>
              <h2 className="modal-title font-mono">{currentTx.external_id}</h2>
              <span className="text-xs text-muted font-mono">
                Internal ID: {currentTx.transaction_id}
              </span>
            </div>
          </div>
          <button 
            type="button" 
            className="btn-icon" 
            onClick={onClose} 
            title="Close drawer"
            aria-label="Close drawer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body">
          {/* Transaction Metadata Grid */}
          <div className="detail-grid mb-5">
            <div className="detail-item">
              <span className="detail-label">Amount</span>
              <span className="detail-value text-base font-bold font-mono">
                ${typeof currentTx.amount === 'number' ? currentTx.amount.toFixed(2) : Number(currentTx.amount || 0).toFixed(2)}
              </span>
            </div>

            <div className="detail-item">
              <span className="detail-label">Calibrated P(Fraud)</span>
              <span className="detail-value font-mono text-base font-bold text-amber">
                {(currentTx.fraud_probability * 100).toFixed(2)}%
              </span>
            </div>

            <div className="detail-item">
              <span className="detail-label">Raw Probability</span>
              <span className="detail-value font-mono text-xs text-muted">
                {typeof currentTx.raw_probability === 'number'
                  ? `${(currentTx.raw_probability * 100).toFixed(2)}%`
                  : '--'}
              </span>
            </div>

            <div className="detail-item">
              <span className="detail-label">Risk Level</span>
              <div>
                <StatusBadge type="risk" value={currentTx.risk_level} />
              </div>
            </div>

            <div className="detail-item">
              <span className="detail-label">Decision Policy</span>
              <div>
                <StatusBadge type="decision" value={currentTx.decision || 'REVIEW'} />
              </div>
            </div>

            <div className="detail-item">
              <span className="detail-label">Model Version</span>
              <span className="detail-value text-xs font-mono">{currentTx.model_version || 'xgb-cost-v1'}</span>
            </div>
          </div>

          {/* Model Explanation Summary */}
          {currentTx.explanation_summary && (
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-md mb-5">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-secondary mb-1">
                <FileText className="w-3.5 h-3.5 text-teal" />
                <span>TreeSHAP Risk Driver Summary</span>
              </div>
              <p className="text-xs text-secondary leading-relaxed m-0">
                {transaction.explanation_summary}
              </p>
            </div>
          )}

          {/* Alerts */}
          {formError && (
            <div className="alert alert-error mb-4">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{formError}</span>
            </div>
          )}
          {successMsg && (
            <div className="alert alert-success mb-4">
              <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
              <span>{successMsg}</span>
            </div>
          )}

          {/* Operator Adjudication Form */}
          <div className="card p-4 mb-5 border-teal">
            <h3 className="text-sm font-bold text-primary mb-3 flex items-center gap-1.5">
              <Send className="w-4 h-4 text-teal" />
              <span>Record Operator Adjudication</span>
            </h3>

            <form onSubmit={handleSubmitFeedback}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                <div className="form-group">
                  <label className="form-label" htmlFor="decisionSelect">
                    Adjudication Label *
                  </label>
                  <select
                    id="decisionSelect"
                    className="form-select font-mono text-xs"
                    value={decision}
                    onChange={(e) => setDecision(e.target.value)}
                    disabled={submitting}
                  >
                    <option value="CONFIRMED_FRAUD">CONFIRMED_FRAUD</option>
                    <option value="CONFIRMED_GENUINE">CONFIRMED_GENUINE</option>
                    <option value="DISPUTED">DISPUTED</option>
                    <option value="INCONCLUSIVE">INCONCLUSIVE</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="reasonCode">
                    Reason Code (Optional)
                  </label>
                  <input
                    id="reasonCode"
                    type="text"
                    placeholder="e.g. CARD_NOT_PRESENT, VERIFIED_USER"
                    value={reasonCode}
                    onChange={(e) => setReasonCode(e.target.value)}
                    disabled={submitting}
                    maxLength={100}
                    className="form-input text-xs"
                  />
                </div>
              </div>

              <div className="form-group mb-3">
                <label className="form-label" htmlFor="comment">
                  Investigator Qualitative Notes (Optional)
                </label>
                <textarea
                  id="comment"
                  rows={2}
                  placeholder="Document merchant inquiry, cardholder contact, or forensic details..."
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  disabled={submitting}
                  maxLength={1000}
                  className="form-textarea text-xs"
                />
              </div>

              {/* Admin Verification Checkbox */}
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-md mb-4 text-xs">
                <label className="flex items-center gap-2 cursor-pointer font-medium text-primary">
                  <input
                    type="checkbox"
                    checked={isVerified}
                    onChange={(e) => setIsVerified(e.target.checked)}
                    disabled={!isAdmin || submitting}
                  />
                  <span>Mark as Verified by Administrator</span>
                </label>
                {!isAdmin ? (
                  <p className="text-muted mt-1 m-0">
                    Pre-verified submissions require Administrator privileges. Submissions by operators default to unverified.
                  </p>
                ) : (
                  <p className="text-teal mt-1 m-0">
                    Admin verification qualifies confirmed genuine/fraud decisions for retraining candidate selection.
                  </p>
                )}
              </div>

              {/* Retraining Safeguard Disclosure */}
              <div className="p-2.5 bg-slate-50 rounded border border-slate-200 text-xs text-muted mb-4 flex items-start gap-1.5">
                <Info className="w-3.5 h-3.5 text-teal flex-shrink-0 mt-0.5" />
                <span>
                  <strong>Database Safeguard (ck_feedback_retraining_eligibility):</strong> Only verified 
                  CONFIRMED_FRAUD or CONFIRMED_GENUINE records qualify for model retraining datasets. 
                  DISPUTED and INCONCLUSIVE records are permanently excluded by database constraints.
                </span>
              </div>

              <div className="flex justify-end">
                <button 
                  type="submit" 
                  className="btn btn-primary" 
                  disabled={submitting}
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Recording Feedback...</span>
                    </>
                  ) : (
                    'Record Adjudication'
                  )}
                </button>
              </div>
            </form>
          </div>

          {/* Historical Feedback Ledger */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-primary flex items-center gap-1.5">
                <History className="w-4 h-4 text-muted" />
                <span>Adjudication Audit History ({feedbacks.length})</span>
              </h3>
              <span className="text-xs text-muted font-mono">Append-Only Audit</span>
            </div>

            {loadingHistory ? (
              <div className="p-4 text-center text-xs text-muted">
                <Loader2 className="w-4 h-4 animate-spin text-teal mx-auto mb-1" />
                <span>Loading adjudication history...</span>
              </div>
            ) : historyError ? (
              <div className="alert alert-error">{historyError}</div>
            ) : feedbacks.length === 0 ? (
              <div className="p-4 bg-slate-50 border border-dashed border-slate-200 rounded text-center text-xs text-muted">
                No prior feedback has been recorded for this transaction yet.
              </div>
            ) : (
              <div className="flex flex-col gap-2.5">
                {feedbacks.map((fb) => (
                  <div 
                    key={fb.id} 
                    className={`p-3 bg-slate-50 border rounded-md ${
                      fb.is_conflicting ? 'border-red-500 bg-red-50/20' : 'border-slate-200'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-muted">#{fb.feedback_sequence}</span>
                        <StatusBadge type="feedback" value={fb.decision} />
                        <StatusBadge type="verified" value={fb.is_verified} />
                        {fb.is_eligible_for_retraining && (
                          <span className="badge badge-success text-xs">Retraining Eligible</span>
                        )}
                        {fb.is_conflicting && (
                          <span className="badge badge-danger text-xs">Conflict</span>
                        )}
                      </div>
                      <span className="text-xs text-muted">
                        {new Date(fb.created_at).toLocaleString()}
                      </span>
                    </div>

                    {fb.reason_code && (
                      <div className="text-xs font-medium text-secondary mb-1">
                        Reason: <code className="text-xs bg-slate-200 px-1 py-0.5 rounded">{fb.reason_code}</code>
                      </div>
                    )}

                    {fb.comment && (
                      <p className="text-xs text-muted mb-2 italic">"{fb.comment}"</p>
                    )}

                    <div className="flex items-center justify-between pt-1 border-t border-slate-200 text-xs text-muted">
                      <span>Logged by: {fb.operator_email}</span>

                      {/* Verify button for Admin if unverified */}
                      {isAdmin && !fb.is_verified && (
                        <button
                          type="button"
                          className="btn btn-secondary btn-xs flex items-center gap-1"
                          disabled={verifyingId === fb.id}
                          onClick={() => handleVerifyExistingFeedback(fb.id)}
                        >
                          {verifyingId === fb.id ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <>
                              <Check className="w-3 h-3" />
                              <span>Verify Now</span>
                            </>
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
