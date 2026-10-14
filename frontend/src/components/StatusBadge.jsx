import { 
  ShieldCheck, 
  AlertTriangle, 
  ShieldAlert, 
  CheckCircle2, 
  HelpCircle, 
  Clock, 
  Check
} from 'lucide-react';

export default function StatusBadge({ type = 'decision', value, className = '' }) {
  if (!value) return null;

  const normalized = String(value).toUpperCase().trim();

  // 1. Transaction Decisions: APPROVE, REVIEW, BLOCK
  if (type === 'decision') {
    switch (normalized) {
      case 'APPROVE':
        return (
          <span className={`badge badge-success ${className}`}>
            <ShieldCheck className="w-3.5 h-3.5 mr-1" />
            APPROVE
          </span>
        );
      case 'REVIEW':
        return (
          <span className={`badge badge-warning ${className}`}>
            <AlertTriangle className="w-3.5 h-3.5 mr-1" />
            REVIEW
          </span>
        );
      case 'BLOCK':
        return (
          <span className={`badge badge-danger ${className}`}>
            <ShieldAlert className="w-3.5 h-3.5 mr-1" />
            BLOCK
          </span>
        );
      default:
        return <span className={`badge badge-neutral ${className}`}>{normalized}</span>;
    }
  }

  // 2. Risk Levels: LOW, MEDIUM, HIGH
  if (type === 'risk') {
    switch (normalized) {
      case 'LOW':
        return (
          <span className={`badge badge-success ${className}`}>
            <span className="dot dot-success mr-1"></span>
            Low Risk
          </span>
        );
      case 'MEDIUM':
        return (
          <span className={`badge badge-warning ${className}`}>
            <span className="dot dot-warning mr-1"></span>
            Medium Risk
          </span>
        );
      case 'HIGH':
        return (
          <span className={`badge badge-danger ${className}`}>
            <span className="dot dot-danger mr-1"></span>
            High Risk
          </span>
        );
      default:
        return <span className={`badge badge-neutral ${className}`}>{normalized}</span>;
    }
  }

  // 3. Operator Feedback Decisions: CONFIRMED_FRAUD, CONFIRMED_GENUINE, DISPUTED, INCONCLUSIVE
  if (type === 'feedback') {
    switch (normalized) {
      case 'CONFIRMED_FRAUD':
        return (
          <span className={`badge badge-danger font-mono ${className}`}>
            <ShieldAlert className="w-3 h-3 mr-1" />
            Confirmed Fraud
          </span>
        );
      case 'CONFIRMED_GENUINE':
        return (
          <span className={`badge badge-success font-mono ${className}`}>
            <CheckCircle2 className="w-3 h-3 mr-1" />
            Confirmed Genuine
          </span>
        );
      case 'DISPUTED':
        return (
          <span className={`badge badge-warning font-mono ${className}`}>
            <AlertTriangle className="w-3 h-3 mr-1" />
            Disputed
          </span>
        );
      case 'INCONCLUSIVE':
        return (
          <span className={`badge badge-neutral font-mono ${className}`}>
            <HelpCircle className="w-3 h-3 mr-1" />
            Inconclusive
          </span>
        );
      default:
        return <span className={`badge badge-neutral ${className}`}>{normalized}</span>;
    }
  }

  // 4. Drift Monitoring Status: NORMAL, WARNING, CRITICAL
  if (type === 'drift') {
    switch (normalized) {
      case 'NORMAL':
        return (
          <span className={`badge badge-success ${className}`}>
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
            NORMAL
          </span>
        );
      case 'WARNING':
        return (
          <span className={`badge badge-warning ${className}`}>
            <AlertTriangle className="w-3.5 h-3.5 mr-1" />
            WARNING
          </span>
        );
      case 'CRITICAL':
        return (
          <span className={`badge badge-danger ${className}`}>
            <ShieldAlert className="w-3.5 h-3.5 mr-1" />
            CRITICAL
          </span>
        );
      default:
        return <span className={`badge badge-neutral ${className}`}>{normalized}</span>;
    }
  }

  // 5. Verification Status: VERIFIED, PENDING
  if (type === 'verified') {
    if (value === true || normalized === 'TRUE' || normalized === 'VERIFIED') {
      return (
        <span className={`badge badge-verified ${className}`}>
          <Check className="w-3 h-3 mr-1 text-teal" />
          Verified
        </span>
      );
    }
    return (
      <span className={`badge badge-neutral ${className}`}>
        <Clock className="w-3 h-3 mr-1" />
        Unverified
      </span>
    );
  }

  // 6. User Roles: ADMIN, OPERATOR, ANALYST
  if (type === 'role') {
    switch (normalized) {
      case 'ADMIN':
        return <span className={`badge badge-admin ${className}`}>ADMIN</span>;
      case 'OPERATOR':
        return <span className={`badge badge-operator ${className}`}>OPERATOR</span>;
      case 'ANALYST':
        return <span className={`badge badge-analyst ${className}`}>ANALYST</span>;
      default:
        return <span className={`badge badge-neutral ${className}`}>{normalized}</span>;
    }
  }

  return <span className={`badge badge-neutral ${className}`}>{normalized}</span>;
}
