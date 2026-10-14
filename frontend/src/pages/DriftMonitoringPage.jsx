const BENCHMARK_METRICS = [
  { label: 'Precision', value: '0.8125' },
  { label: 'Recall', value: '0.7500' },
  { label: 'F1 Score', value: '0.7800' },
  { label: 'PR-AUC', value: '0.7689' },
  { label: 'ROC-AUC', value: '0.9783' },
];

export default function DriftMonitoringPage() {
  return (
    <div className="page-container">
      <section className="benchmark-container" aria-label="Production Baseline Benchmark">
        {/* Benchmark Section Heading */}
        <header className="benchmark-header">
          <h1 className="benchmark-title">Production Baseline Benchmark</h1>
          <p className="benchmark-subtitle">Held-Out 15% Test Split</p>
        </header>

        {/* Balanced Grid: 2 rows of 2, 5th centered */}
        <div className="benchmark-grid">
          {BENCHMARK_METRICS.map((metric) => (
            <div key={metric.label} className="benchmark-card">
              <span className="benchmark-label">{metric.label}</span>
              <div className="benchmark-value">{metric.value}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
