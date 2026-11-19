const DRIFT_STATUS_TABS = [
  { id: 'ALL', label: 'All Findings' },
  { id: 'CONFIRMED_DRIFT', label: 'Confirmed Drift' },
  { id: 'POTENTIAL_DRIFT', label: 'Potential Drift' },
  { id: 'UNCERTAIN', label: 'Uncertain' },
  { id: 'RESOLVED', label: 'Resolved' },
];

const DRIFT_SEVERITY_OPTIONS = [
  { id: 'ALL', label: 'All Severities' },
  { id: 'CRITICAL', label: 'Critical' },
  { id: 'HIGH', label: 'High' },
  { id: 'MEDIUM', label: 'Medium' },
  { id: 'LOW', label: 'Low' },
];

const DRIFT_STATUS_STYLES = {
  CONFIRMED_DRIFT: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
  POTENTIAL_DRIFT: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  UNCERTAIN: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/40',
  RESOLVED: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  UNCHANGED: 'bg-slate-800 text-slate-400 border-slate-700',
};

const DRIFT_SEVERITY_STYLES = {
  CRITICAL: 'bg-rose-600/20 text-rose-200 border-rose-500/50',
  HIGH: 'bg-amber-500/20 text-amber-200 border-amber-500/40',
  MEDIUM: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  LOW: 'bg-slate-800 text-slate-300 border-slate-700',
};

export default function DriftFindingsSection({
  healthState,
  baseCommit,
  headCommit,
  canCompare,
  driftLoading,
  driftError,
  driftJob,
  driftCancelLoading,
  onDismissDriftError,
  driftResult,
  driftStatusFilter,
  onDriftStatusFilterChange,
  driftSeverityFilter,
  onDriftSeverityFilterChange,
  expandedFindings,
  onToggleFindingExpanded,
  onAnalyzeDrift,
  onCancelDrift,
  aiProviderInfo,
  selectedAiProvider,
  onSelectAiProvider,
  aiExplanationsById,
  aiLoadingById,
  aiErrorById,
  onDismissAiError,
  aiFocusModeById,
  onRequestFindingAI,
  copiedFindingId,
  onCopySuggestion,
}) {
  const filteredDriftFindings = (driftResult?.findings || []).filter((f) => {
    if (driftStatusFilter !== 'ALL' && f.status !== driftStatusFilter) {
      return false;
    }
    if (driftSeverityFilter !== 'ALL' && f.severity !== driftSeverityFilter) {
      return false;
    }
    return true;
  });

  return (
    <section
      aria-label="DOCUMENTATION DRIFT FINDINGS"
      className="rounded-xl bg-slate-900/70 border border-slate-800 p-6 space-y-6"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2.5">
            <h3 className="text-base font-bold tracking-wide uppercase text-white">
              Documentation Drift Findings
            </h3>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30">
              Milestone 5 Drift Engine
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Deterministic, evidence-based verification connecting Python AST code changes between Base and Head commits to mapped Markdown documentation claims.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Active AI Provider Selector & Status Indicator */}
          <div className="flex items-center gap-2 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800 text-xs">
            <span className="text-slate-400">AI Provider:</span>
            <select
              aria-label="Select AI Provider"
              value={selectedAiProvider}
              onChange={(e) => onSelectAiProvider(e.target.value)}
              disabled={healthState !== 'connected'}
              className="bg-slate-900 text-slate-100 font-mono text-xs px-2 py-0.5 rounded border border-slate-700 focus:outline-none focus:border-indigo-500"
            >
              {(aiProviderInfo?.supported_providers || ['mock', 'gemini']).map(
                (provider) => (
                  <option
                    key={provider}
                    value={provider}
                    disabled={
                      provider === 'gemini' &&
                      (!aiProviderInfo?.gemini_configured ||
                        !aiProviderInfo?.gemini_budget_configured)
                    }
                  >
                    {provider === 'mock'
                      ? 'Mock (Development/Test)'
                      : `Gemini (${aiProviderInfo?.gemini_model || 'not configured'})`}
                  </option>
                )
              )}
            </select>
            <span
              className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                healthState !== 'connected'
                  ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                  : selectedAiProvider === 'gemini' &&
                    aiProviderInfo?.gemini_configured &&
                    aiProviderInfo?.gemini_budget_configured
                  ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                  : selectedAiProvider === 'gemini' &&
                    (!aiProviderInfo?.gemini_configured ||
                      !aiProviderInfo?.gemini_budget_configured)
                  ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                  : 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30'
              }`}
            >
              {healthState !== 'connected'
                ? 'Unavailable'
                : selectedAiProvider === 'gemini'
                ? aiProviderInfo?.gemini_configured &&
                  aiProviderInfo?.gemini_budget_configured
                  ? 'Gemini Ready'
                  : 'Gemini Unavailable'
                : 'Mock Active'}
            </span>
          </div>
          {selectedAiProvider === 'gemini' && (
            <p className="max-w-sm text-[10px] text-slate-400" role="note">
              Selected finding evidence, including limited code and documentation
              excerpts, is sent to Google Gemini for explanation.
            </p>
          )}

          <button
            type="button"
            onClick={driftLoading ? onCancelDrift : onAnalyzeDrift}
            disabled={
              driftLoading
                ? driftCancelLoading || driftJob?.cancellation_requested
                : !canCompare
            }
            className="px-4 py-2.5 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-semibold text-xs shadow-lg shadow-rose-600/25 transition-colors cursor-pointer shrink-0 flex items-center gap-2"
          >
            {driftLoading ? (
              <span>
                {driftJob?.cancellation_requested
                  ? 'CANCELLATION REQUESTED'
                  : driftCancelLoading
                  ? 'CANCELLING...'
                  : 'CANCEL ANALYSIS'}
              </span>
            ) : (
              <span>ANALYZE DOCUMENTATION DRIFT</span>
            )}
          </button>
        </div>
      </div>

      {/* 1. Loading State */}
      {driftLoading && (
        <div className="py-10 px-4 text-center space-y-3">
          <div className="mx-auto h-8 w-8 rounded-full border-2 border-rose-400 border-t-transparent animate-spin" />
          <p className="text-sm font-medium text-rose-300">
            {driftJob?.status === 'queued'
              ? 'Analysis is queued for a worker.'
              : `Analyzing Base (${baseCommit ? baseCommit.slice(0, 7) : ''}) → Head (${headCommit ? headCommit.slice(0, 7) : ''})...`}
          </p>
          <div
            className="mx-auto h-2 max-w-md overflow-hidden rounded-full bg-slate-800"
            role="progressbar"
            aria-label="Analysis progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={driftJob?.progress_percent || 0}
          >
            <div
              className="h-full bg-rose-500 transition-all"
              style={{ width: `${driftJob?.progress_percent || 0}%` }}
            />
          </div>
          <p className="text-xs text-slate-400">
            {driftJob?.status || 'Starting'} · {driftJob?.progress_percent || 0}%
            {driftJob?.attempt_count
              ? ` · attempt ${driftJob.attempt_count}/${driftJob.max_attempts}`
              : ''}
          </p>
          {driftJob?.error_category === 'queue_unavailable' && (
            <p className="text-xs text-amber-300">
              The analysis is safely queued in the database and will be dispatched
              when the worker broker recovers.
            </p>
          )}
          <p className="text-xs text-slate-400">
            Deterministic static rule evaluation only — repository code and Markdown snippets are never executed.
          </p>
        </div>
      )}

      {/* 2. Failed Analysis Error State */}
      {!driftLoading && driftError && (
        <div
          role="alert"
          className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start justify-between gap-4"
        >
          <div>
            <p className="font-semibold text-rose-300">
              Documentation Drift Analysis Failed
            </p>
            <p className="mt-1 leading-relaxed">{driftError}</p>
          </div>
          <button
            type="button"
            onClick={onDismissDriftError}
            className="text-rose-300 hover:text-white underline shrink-0 cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* 3. Initial Idle State before Drift Analysis is Triggered */}
      {!driftLoading && !driftError && !driftResult && !driftJob && (
        <div className="py-10 px-4 text-center max-w-md mx-auto">
          <div className="mx-auto h-12 w-12 rounded-full bg-slate-800/80 border border-slate-700 flex items-center justify-center text-slate-400 mb-4">
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.75}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
          </div>
          <h4 className="text-base font-semibold text-white">
            No drift analysis has been performed yet
          </h4>
          <p className="mt-2 text-xs text-slate-400 leading-relaxed">
            Connect a repository, select two different Base and Head commits, and click &ldquo;ANALYZE DOCUMENTATION DRIFT&rdquo; to detect outdated parameters, defaults, return contracts, removed/renamed functions, and deleted source files.
          </p>
        </div>
      )}

      {!driftLoading && driftJob && !driftResult && !driftError && (
        <div className="rounded-lg border border-slate-700 bg-slate-950/60 p-4 text-xs text-slate-300">
          Analysis status: <span className="font-semibold">{driftJob.status}</span>
          {driftJob.error_category && (
            <span> · {driftJob.error_category}</span>
          )}
        </div>
      )}

      {/* 4. Drift Analysis Results */}
      {!driftLoading && driftResult && (
        <div className="space-y-6">
          {/* Outcome Status Banner Distinguishing Partial, Findings, and Zero-Drift Results */}
          {driftResult.summary.parse_errors_count > 0 ? (
            <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs">
              <p className="font-semibold text-amber-300">
                Partial Drift Analysis Completed ({driftResult.summary.parse_errors_count} syntax parse error(s))
              </p>
              <p className="mt-1">
                Analyzed {driftResult.summary.python_files_analyzed} Python file(s) and {driftResult.summary.documentation_files_analyzed} documentation file(s) with {driftResult.summary.total_findings} finding(s), while {driftResult.summary.parse_errors_count} file(s) could not be parsed.
              </p>
            </div>
          ) : driftResult.summary.confirmed_drift_count > 0 ||
            driftResult.summary.potential_drift_count > 0 ? (
            <div className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs">
              <p className="font-semibold text-rose-300">
                Documentation Drift Detected — {driftResult.summary.confirmed_drift_count} Confirmed, {driftResult.summary.potential_drift_count} Potential
              </p>
              <p className="mt-1">
                Evaluated {driftResult.summary.code_changes_count} AST code change(s) across {driftResult.summary.python_files_analyzed} Python file(s) and {driftResult.summary.documentation_files_analyzed} Markdown file(s) between {driftResult.base_commit.slice(0, 7)} and {driftResult.head_commit.slice(0, 7)}.
              </p>
            </div>
          ) : (
            <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 text-xs">
              <p className="font-semibold text-emerald-300">
                Analysis Successful — No Unresolved Documentation Drift Detected
              </p>
              <p className="mt-1">
                Evaluated {driftResult.summary.code_changes_count} AST code change(s) across {driftResult.summary.python_files_analyzed} Python file(s) and {driftResult.summary.documentation_files_analyzed} Markdown file(s). No outdated documentation claims were identified ({driftResult.summary.resolved_count} resolved, {driftResult.summary.uncertain_count} uncertain).
              </p>
            </div>
          )}

          {/* Summary Metric Tiles */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Total Drift Findings
              </span>
              <span className="mt-1 text-xl font-bold text-white block">
                {driftResult.summary.total_findings}
              </span>
            </div>
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Confirmed Drift
              </span>
              <span className="mt-1 text-xl font-bold text-rose-400 block">
                {driftResult.summary.confirmed_drift_count}
              </span>
            </div>
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Potential Drift
              </span>
              <span className="mt-1 text-xl font-bold text-amber-300 block">
                {driftResult.summary.potential_drift_count}
              </span>
            </div>
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Uncertain Findings
              </span>
              <span className="mt-1 text-xl font-bold text-indigo-300 block">
                {driftResult.summary.uncertain_count}
              </span>
            </div>
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Resolved Findings
              </span>
              <span className="mt-1 text-xl font-bold text-emerald-400 block">
                {driftResult.summary.resolved_count}
              </span>
            </div>
          </div>

          {/* Filters Bar (Status Tabs + Severity Dropdown) */}
          {driftResult.findings.length > 0 && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Drift Status Filters">
                  {DRIFT_STATUS_TABS.map((tab) => {
                    const isActive = driftStatusFilter === tab.id;
                    return (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => onDriftStatusFilterChange(tab.id)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors cursor-pointer ${
                          isActive
                            ? 'bg-rose-500/20 text-rose-200 border-rose-500/40'
                            : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200 hover:bg-slate-900'
                        }`}
                      >
                        {tab.label}
                      </button>
                    );
                  })}
                </div>

                <div className="flex items-center gap-2">
                  <label
                    htmlFor="drift-severity-filter"
                    className="text-xs text-slate-400"
                  >
                    Severity:
                  </label>
                  <select
                    id="drift-severity-filter"
                    value={driftSeverityFilter}
                    onChange={(e) => onDriftSeverityFilterChange(e.target.value)}
                    className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-1.5 text-xs text-slate-200 font-mono focus:outline-none focus:border-rose-500"
                  >
                    {DRIFT_SEVERITY_OPTIONS.map((opt) => (
                      <option key={opt.id} value={opt.id}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {filteredDriftFindings.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-400 bg-slate-950 rounded-xl border border-slate-800">
                  No findings match the selected Status ({driftStatusFilter}) and Severity ({driftSeverityFilter}) filters.
                </div>
              ) : (
                <div className="divide-y divide-slate-800 rounded-xl bg-slate-950 border border-slate-800 overflow-hidden">
                  {filteredDriftFindings.map((finding) => {
                    const isExpanded = Boolean(expandedFindings[finding.finding_id]);
                    const statusStyle =
                      DRIFT_STATUS_STYLES[finding.status] ||
                      DRIFT_STATUS_STYLES.UNCHANGED;
                    const sevStyle =
                      DRIFT_SEVERITY_STYLES[finding.severity] ||
                      DRIFT_SEVERITY_STYLES.LOW;

                    const aiExplanation = aiExplanationsById[finding.finding_id];
                    const isAiLoading = Boolean(aiLoadingById[finding.finding_id]);
                    const aiError = aiErrorById[finding.finding_id];
                    const focusMode = aiFocusModeById[finding.finding_id];

                    return (
                      <div key={finding.finding_id} className="p-4 space-y-3">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="space-y-1.5 min-w-0 flex-1">
                            {/* Badges Row */}
                            <div className="flex flex-wrap items-center gap-2">
                              <span
                                className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border font-semibold ${statusStyle}`}
                              >
                                {finding.status}
                              </span>
                              <span
                                className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border ${sevStyle}`}
                              >
                                {finding.severity} SEVERITY
                              </span>
                              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-800">
                                Confidence: {(finding.confidence * 100).toFixed(0)}% ({finding.confidence})
                              </span>
                              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">
                                {finding.finding_type}
                              </span>
                              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                                {finding.rule_id}
                              </span>
                            </div>

                            {/* File & Symbol Row */}
                            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono">
                              <span className="text-cyan-300">
                                Doc: <strong>{finding.documentation_file}</strong> (L{finding.documentation_line}
                                {finding.documentation_end_line > finding.documentation_line
                                  ? `–L${finding.documentation_end_line}`
                                  : ''}
                                )
                              </span>
                              <span className="text-indigo-300">
                                Symbol: <strong>{finding.qualified_symbol}</strong> in{' '}
                                {finding.source_file}
                                {finding.source_line ? `:L${finding.source_line}` : ''}
                              </span>
                            </div>

                            {/* Detection Reason */}
                            <p className="text-xs text-slate-200 leading-relaxed">
                              {finding.reason}
                            </p>
                          </div>

                          <div className="flex flex-wrap items-center gap-2 shrink-0">
                            <button
                              type="button"
                              onClick={() => onRequestFindingAI(finding, 'explain')}
                              disabled={isAiLoading}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white shadow shadow-indigo-600/20 cursor-pointer"
                            >
                              {isAiLoading && focusMode === 'explain'
                                ? 'Explaining...'
                                : 'EXPLAIN WITH AI'}
                            </button>
                            <button
                              type="button"
                              onClick={() => onRequestFindingAI(finding, 'suggest')}
                              disabled={isAiLoading}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 disabled:text-slate-500 text-white shadow shadow-emerald-600/20 cursor-pointer"
                            >
                              {isAiLoading && focusMode === 'suggest'
                                ? 'Suggesting...'
                                : 'SUGGEST DOCUMENTATION FIX'}
                            </button>
                            <button
                              type="button"
                              onClick={() => onToggleFindingExpanded(finding.finding_id)}
                              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-800 cursor-pointer"
                            >
                              {isExpanded ? 'Hide Evidence' : 'Inspect Evidence'}
                            </button>
                          </div>
                        </div>

                        {/* Milestone 6: AI Loading Indicator for this Finding */}
                        {isAiLoading && (
                          <div className="mt-2 p-3 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-200 text-xs flex items-center gap-2.5">
                            <span className="h-3.5 w-3.5 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin shrink-0" />
                            <span>
                              Generating evidence-based AI explanation and documentation suggestion via{' '}
                              <strong className="uppercase">{selectedAiProvider}</strong> provider...
                            </span>
                          </div>
                        )}

                        {/* Milestone 6: AI Provider Error Banner for this Finding */}
                        {!isAiLoading && aiError && (
                          <div
                            role="alert"
                            className="mt-2 p-3.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start justify-between gap-3"
                          >
                            <div>
                              <p className="font-semibold text-rose-300">
                                AI Provider ({selectedAiProvider.toUpperCase()}) Error
                              </p>
                              <p className="mt-1">{aiError}</p>
                            </div>
                            <button
                              type="button"
                              onClick={() => onDismissAiError(finding.finding_id)}
                              className="text-rose-300 hover:text-white underline shrink-0 cursor-pointer"
                            >
                              Dismiss
                            </button>
                          </div>
                        )}

                        {/* Milestone 6: AI Explanation & Documentation Correction Panel */}
                        {!isAiLoading && aiExplanation && (
                          <div className="mt-3 p-4 rounded-xl bg-slate-900/95 border border-indigo-500/30 space-y-4 text-xs">
                            <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-slate-800">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-200 border border-indigo-500/40 font-semibold">
                                  AI-Generated Explanation
                                </span>
                                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-slate-950 text-cyan-300 border border-slate-800">
                                  Provider: {aiExplanation.provider.toUpperCase()} ({aiExplanation.model_name})
                                </span>
                                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-950 text-slate-400 border border-slate-800">
                                  Deterministic Status Preserved: {aiExplanation.original_status}
                                </span>
                              </div>
                              <span className="text-[11px] text-slate-400 italic">
                                Advisory AI analysis — deterministic engine remains source of truth
                              </span>
                            </div>

                            {/* Explanation & Code/Doc Breakdown */}
                            <div className="space-y-2.5">
                              <div>
                                <span className="text-[10px] font-semibold uppercase tracking-wider text-indigo-300 block mb-1">
                                  Detailed Explanation
                                </span>
                                <p className="text-slate-200 leading-relaxed">
                                  {aiExplanation.explanation}
                                </p>
                              </div>

                              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                                  <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                                    Code Change Summary
                                  </span>
                                  <p className="text-slate-300">
                                    {aiExplanation.code_change_summary}
                                  </p>
                                </div>
                                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                                  <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                                    Documentation Issue
                                  </span>
                                  <p className="text-slate-300">
                                    {aiExplanation.documentation_issue}
                                  </p>
                                </div>
                              </div>
                            </div>

                            {/* AI-Generated Correction Suggestion vs Insufficient Evidence Warning */}
                            <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="flex items-center gap-2">
                                  <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-semibold">
                                    AI-Generated Correction Suggestion
                                  </span>
                                  <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-800">
                                    {aiExplanation.correction_status}
                                  </span>
                                </div>

                                {aiExplanation.correction_available &&
                                  aiExplanation.suggested_correction && (
                                    <button
                                      type="button"
                                      onClick={() =>
                                        onCopySuggestion(
                                          finding.finding_id,
                                          aiExplanation.suggested_correction
                                        )
                                      }
                                      className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-[11px] font-mono cursor-pointer"
                                    >
                                      {copiedFindingId === finding.finding_id
                                        ? 'Copied!'
                                        : 'Copy Suggestion'}
                                    </button>
                                  )}
                              </div>

                              {aiExplanation.insufficient_evidence ||
                              !aiExplanation.correction_available ? (
                                <div className="p-2.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs">
                                  <strong>Insufficient Evidence Warning:</strong> An automated documentation replacement cannot be safely proposed from the available static evidence. Manual author review is required.
                                </div>
                              ) : (
                                <div className="space-y-1.5">
                                  <pre className="p-3 rounded bg-emerald-950/30 border border-emerald-500/30 font-mono text-xs text-emerald-200 whitespace-pre-wrap">
                                    {aiExplanation.suggested_correction}
                                  </pre>
                                  <p className="text-[11px] text-slate-400">
                                    Proposal only — review manually before editing `{finding.documentation_file}`. DocGuard never modifies repository files automatically.
                                  </p>
                                </div>
                              )}
                            </div>

                            {/* Evidence Used & Limitations */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                              <div>
                                <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                                  Repository Evidence Referenced by AI
                                </span>
                                <ul className="list-disc list-inside text-slate-300 space-y-0.5 font-mono text-[11px]">
                                  {aiExplanation.evidence_used.map((ev, idx) => (
                                    <li key={idx}>{ev}</li>
                                  ))}
                                </ul>
                              </div>
                              {aiExplanation.limitations?.length > 0 && (
                                <div>
                                  <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-400 block mb-1">
                                    Notes & Limitations
                                  </span>
                                  <ul className="list-disc list-inside text-slate-300 space-y-0.5 text-[11px]">
                                    {aiExplanation.limitations.map((lim, idx) => (
                                      <li key={idx}>{lim}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          </div>
                        )}

                        {/* Expanded Evidence View */}
                        {isExpanded && (
                          <div className="mt-3 pt-3 border-t border-slate-800/80 space-y-3 text-xs">
                            {/* Original Documentation Text */}
                            <div className="p-3 rounded-lg bg-slate-900 border border-slate-800">
                              <span className="text-[10px] font-semibold uppercase tracking-wider text-cyan-400 block mb-1">
                                Documentation Statement — {finding.documentation_file}:L{finding.documentation_line}
                                {finding.documentation_section
                                  ? ` (Section: ${finding.documentation_section})`
                                  : ''}
                              </span>
                              <pre className="whitespace-pre-wrap font-mono text-xs text-slate-200 leading-relaxed">
                                {finding.documentation_text}
                              </pre>
                              {finding.previous_documentation_text && (
                                <div className="mt-2 pt-2 border-t border-slate-800">
                                  <span className="text-[10px] uppercase tracking-wider text-slate-400 block mb-0.5">
                                    Previous Base Commit Documentation Text:
                                  </span>
                                  <pre className="whitespace-pre-wrap font-mono text-xs text-slate-400">
                                    {finding.previous_documentation_text}
                                  </pre>
                                </div>
                              )}
                            </div>

                            {/* Old and New Code Evidence */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 font-mono">
                              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/25 text-rose-200 overflow-x-auto">
                                <span className="text-[10px] font-semibold uppercase tracking-wider text-rose-400 block mb-1">
                                  Base Commit Code Evidence ({finding.source_file}
                                  {finding.old_source_line ? `:L${finding.old_source_line}` : ''})
                                </span>
                                <pre className="whitespace-pre-wrap text-xs">
                                  {finding.old_code_evidence}
                                </pre>
                              </div>
                              <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/25 text-emerald-200 overflow-x-auto">
                                <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400 block mb-1">
                                  Head Commit Code Evidence ({finding.source_file}
                                  {finding.source_line ? `:L${finding.source_line}` : ''})
                                </span>
                                <pre className="whitespace-pre-wrap text-xs">
                                  {finding.new_code_evidence}
                                </pre>
                              </div>
                            </div>

                            {/* Mapping Evidence & Suggested Action */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                              <div className="p-3 rounded-lg bg-slate-900/90 border border-slate-800">
                                <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                                  Doc-to-Code Mapping Evidence
                                </span>
                                <ul className="list-disc list-inside text-slate-300 space-y-0.5">
                                  {finding.mapping_evidence.map((ev, idx) => (
                                    <li key={idx}>{ev}</li>
                                  ))}
                                </ul>
                              </div>
                              <div className="p-3 rounded-lg bg-slate-900/90 border border-slate-800">
                                <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-400 block mb-1">
                                  Recommended Action
                                </span>
                                <p className="text-slate-200">{finding.suggested_action}</p>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
