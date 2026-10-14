import { Info } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function MetricCard({
  title,
  value,
  subtext,
  icon: Icon,
  iconColor = 'text-teal',
  iconBg = 'bg-teal-subtle',
  badge,
  linkTo,
  linkText,
  tooltip,
  loading = false,
}) {
  return (
    <div className="card stat-card">
      <div className="stat-header">
        <div className="flex items-center gap-1.5">
          <span className="stat-label">{title}</span>
          {tooltip && (
            <span className="stat-tooltip-trigger" title={tooltip}>
              <Info className="w-3.5 h-3.5 text-muted" />
            </span>
          )}
        </div>
        {Icon && (
          <div className={`stat-icon-wrapper ${iconBg} ${iconColor}`}>
            <Icon className="w-4 h-4" />
          </div>
        )}
      </div>

      <div className="stat-value-container">
        {loading ? (
          <div className="skeleton-line w-24 h-7 my-1"></div>
        ) : (
          <div className="stat-value">{value}</div>
        )}
        {badge && <div className="stat-badge-wrapper">{badge}</div>}
      </div>

      {(subtext || (linkTo && linkText)) && (
        <div className="stat-footer">
          {subtext && <span className="stat-subtext text-muted">{subtext}</span>}
          {linkTo && linkText && (
            <Link to={linkTo} className="stat-action-link ml-auto">
              {linkText} &rarr;
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
