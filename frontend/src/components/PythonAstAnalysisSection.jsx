function getAstChangeBadgeStyle(changeType) {
  if (!changeType) return 'bg-slate-800 text-slate-300 border-slate-700';
  if (changeType.endsWith('_ADDED')) {
    return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
  }
  if (changeType.endsWith('_REMOVED')) {
    return 'bg-rose-500/15 text-rose-300 border-rose-500/30';
  }
  if (changeType.endsWith('_RENAMED') || changeType.endsWith('_REORDERED')) {
    return 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30';
  }
  return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
}

export default function PythonAstAnalysisSection({
  repoInfo,
  baseCommit,
  headCommit,
  canCompare,
  astLoading,
  astError,
  onDismissAstError,
  astResult,
  onAnalyzePythonChanges,
}) {
  return (
    <section
      aria-label="PYTHON CODE ANALYSIS"
      className="rounded-xl bg-slate-900/70 border border-slate-800 p-6 space-y-6"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2.5">
            <h3 className="text-base font-bold tracking-wide uppercase text-white">
              PYTHON CODE ANALYSIS
            </h3>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
              Milestone 3 Static AST
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Static Python AST structural comparison detecting function, class, method, parameter, annotation, and async changes without executing code.
          </p>
        </div>

        <button
          type="button"
          onClick={onAnalyzePythonChanges}
          disabled={!canCompare}
          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-xs shadow-lg shadow-indigo-600/20 transition-colors cursor-pointer shrink-0 flex items-center gap-2"
        >
          {astLoading ? (
            <>
              <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
              <span>Running AST Analysis...</span>
            </>
          ) : (
            <span>Analyze Python Changes</span>
          )}
        </button>
      </div>

      {/* 1. Loading Progress State */}
      {astLoading && (
        <div className="py-10 px-4 text-center space-y-3">
          <div className="mx-auto h-8 w-8 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin" />
          <p className="text-sm font-medium text-indigo-300">
            Retrieving Python blobs and parsing AST trees for Base (
            {baseCommit ? baseCommit.slice(0, 7) : ''}) → Head (
            {headCommit ? headCommit.slice(0, 7) : ''})...
          </p>
          <p className="text-xs text-slate-400">
            Static analysis only — repository code is never executed or imported.
          </p>
        </div>
      )}

      {/* 2. Failed Analysis Error State */}
      {!astLoading && astError && (
        <div
          role="alert"
          className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start justify-between gap-4"
        >
          <div>
            <p className="font-semibold text-rose-300">
              Python AST Code Analysis Failed
            </p>
            <p className="mt-1 leading-relaxed">{astError}</p>
          </div>
          <button
            type="button"
            onClick={onDismissAstError}
            className="text-rose-300 hover:text-white underline shrink-0 cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* 3. Initial Idle Prompt before Analysis is Triggered */}
      {!astLoading && !astError && !astResult && (
        <div className="py-8 px-4 text-center max-w-lg mx-auto">
          <p className="text-sm font-medium text-slate-300">
            {repoInfo
              ? 'Ready to analyze Python AST changes between the selected commits.'
              : 'Connect a GitHub repository and select Base and Head commits above to run Python AST analysis.'}
          </p>
          <p className="mt-1.5 text-xs text-slate-400">
            Click &ldquo;Analyze Python Changes&rdquo; to inspect added, removed, modified, and renamed Python functions, classes, methods, parameters, default values, and type annotations.
          </p>
        </div>
      )}

      {/* 4. AST Analysis Results */}
      {!astLoading && astResult && (
        <div className="space-y-6">
          {/* Status Banner Distinguishing Analysis Outcomes */}
          {astResult.summary.parse_errors_count > 0 ? (
            <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs">
              <p className="font-semibold text-amber-300">
                Partial Analysis Completed with Syntax Parse Errors ({astResult.summary.parse_errors_count})
              </p>
              <p className="mt-1">
                Analyzed {astResult.summary.analyzed_python_files_count} Python file(s) and detected {astResult.summary.total_symbol_changes} symbol change(s), while {astResult.summary.parse_errors_count} file version(s) contained invalid Python syntax.
              </p>
            </div>
          ) : astResult.summary.total_symbol_changes > 0 ? (
            <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 text-xs">
              <p className="font-semibold text-emerald-300">
                AST Analysis Complete — {astResult.summary.total_symbol_changes} Symbol Change(s) Detected
              </p>
              <p className="mt-1">
                Inspected {astResult.summary.analyzed_python_files_count} changed Python file(s) between {astResult.base_commit.slice(0, 7)} and {astResult.head_commit.slice(0, 7)}.
              </p>
            </div>
          ) : (
            <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-slate-300 text-xs">
              <p className="font-semibold text-white">
                AST Analysis Complete — No Python Symbol Changes Detected
              </p>
              <p className="mt-1 text-slate-400">
                {astResult.summary.analyzed_python_files_count > 0
                  ? `Inspected ${astResult.summary.analyzed_python_files_count} changed Python file(s); no function, class, method, or parameter signature/body changes were found.`
                  : `No changed Python (.py) files were present between ${astResult.base_commit.slice(0, 7)} and ${astResult.head_commit.slice(0, 7)}.`}
              </p>
            </div>
          )}

          {/* Summary Metric Tiles */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Python Files Analyzed
              </span>
              <span className="mt-1 text-xl font-bold text-white block">
                {astResult.summary.analyzed_python_files_count}
              </span>
            </div>
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Changed Symbols
              </span>
              <span className="mt-1 text-xl font-bold text-indigo-300 block">
                {astResult.summary.total_symbol_changes}
              </span>
            </div>
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Skipped Files
              </span>
              <span className="mt-1 text-xl font-bold text-slate-300 block">
                {astResult.summary.skipped_files_count}
              </span>
            </div>
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Parse Errors
              </span>
              <span
                className={`mt-1 text-xl font-bold block ${
                  astResult.summary.parse_errors_count > 0
                    ? 'text-amber-300'
                    : 'text-emerald-400'
                }`}
              >
                {astResult.summary.parse_errors_count}
              </span>
            </div>
          </div>

          {/* Counts by Change Type */}
          {Object.keys(astResult.summary.counts_by_change_type).length > 0 && (
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 block mb-3">
                Counts by Change Type
              </span>
              <div className="flex flex-wrap gap-2">
                {Object.entries(astResult.summary.counts_by_change_type).map(
                  ([cType, count]) => (
                    <span
                      key={cType}
                      className={`text-xs font-mono px-2.5 py-1 rounded-md border ${getAstChangeBadgeStyle(
                        cType
                      )}`}
                    >
                      {cType}: <strong>{count}</strong>
                    </span>
                  )
                )}
              </div>
            </div>
          )}

          {/* Detailed List of Detected Symbol Changes */}
          {astResult.changed_symbols.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Detected Symbol Changes ({astResult.changed_symbols.length})
              </h4>
              <div className="divide-y divide-slate-800 rounded-xl bg-slate-950 border border-slate-800 overflow-hidden">
                {astResult.changed_symbols.map((change, idx) => (
                  <div
                    key={`${change.file_path}-${change.qualified_name}-${change.change_type}-${idx}`}
                    className="p-4 space-y-2.5"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`text-[11px] font-mono px-2 py-0.5 rounded border ${getAstChangeBadgeStyle(
                            change.change_type
                          )}`}
                        >
                          {change.change_type}
                        </span>
                        <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-800">
                          {change.symbol_type}
                        </span>
                        <span className="text-sm font-semibold font-mono text-white">
                          {change.qualified_name}
                        </span>
                      </div>
                      <div className="text-xs font-mono text-slate-400">
                        <span className="text-indigo-300">{change.file_path}</span>
                        {change.old_line && change.new_line ? (
                          <span className="ml-2">
                            (L{change.old_line} → L{change.new_line})
                          </span>
                        ) : change.new_line ? (
                          <span className="ml-2 text-emerald-400">
                            (New L{change.new_line})
                          </span>
                        ) : change.old_line ? (
                          <span className="ml-2 text-rose-400">
                            (Old L{change.old_line})
                          </span>
                        ) : null}
                      </div>
                    </div>

                    <p className="text-xs text-slate-300">{change.summary}</p>

                    {(change.old_signature || change.new_signature) && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-1 font-mono text-xs">
                        {change.old_signature && (
                          <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/25 text-rose-200 overflow-x-auto">
                            <span className="text-[10px] uppercase tracking-wider text-rose-400 block mb-0.5">
                              Base Signature {change.old_line ? `(line ${change.old_line})` : ''}
                            </span>
                            <code>{change.old_signature}</code>
                          </div>
                        )}
                        {change.new_signature && (
                          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/25 text-emerald-200 overflow-x-auto">
                            <span className="text-[10px] uppercase tracking-wider text-emerald-400 block mb-0.5">
                              Head Signature {change.new_line ? `(line ${change.new_line})` : ''}
                            </span>
                            <code>{change.new_signature}</code>
                          </div>
                        )}
                      </div>
                    )}

                    {change.details && Object.keys(change.details).length > 0 && (
                      <div className="text-[11px] font-mono text-slate-400 bg-slate-900/80 px-3 py-1.5 rounded border border-slate-800/80 overflow-x-auto">
                        Details: {JSON.stringify(change.details)}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Parse Errors Section */}
          {astResult.parse_errors.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-amber-300">
                Syntax / Parse Errors ({astResult.parse_errors.length})
              </h4>
              <div className="divide-y divide-amber-500/20 rounded-xl bg-amber-500/10 border border-amber-500/30 overflow-hidden">
                {astResult.parse_errors.map((err, idx) => (
                  <div
                    key={`${err.file_path}-${err.version}-${idx}`}
                    className="p-3.5 text-xs text-amber-200 font-mono"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold text-amber-300">
                        {err.file_path} ({err.version} commit)
                      </span>
                      <span>
                        {err.error_type}
                        {err.line ? ` at line ${err.line}` : ''}
                        {err.column ? `, col ${err.column}` : ''}
                      </span>
                    </div>
                    <p className="mt-1 text-amber-100/90">{err.message}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Analyzed Python Files & Skipped Files Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300 mb-3">
                Analyzed Python Files ({astResult.analyzed_files.length})
              </h4>
              {astResult.analyzed_files.length === 0 ? (
                <p className="text-xs text-slate-500">No Python (.py) files in commit range.</p>
              ) : (
                <ul className="space-y-2 max-h-48 overflow-y-auto text-xs font-mono">
                  {astResult.analyzed_files.map((af) => (
                    <li
                      key={af.file_path}
                      className="flex items-center justify-between gap-2 pb-1.5 border-b border-slate-800/80 last:border-b-0"
                    >
                      <span className="text-slate-200 truncate">{af.file_path}</span>
                      <span className="text-slate-400 shrink-0">
                        {af.changes_count} change(s) ({af.base_symbol_count}→{af.head_symbol_count} symbols)
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300 mb-3">
                Skipped Files ({astResult.skipped_files.length})
              </h4>
              {astResult.skipped_files.length === 0 ? (
                <p className="text-xs text-slate-500">No files were skipped.</p>
              ) : (
                <ul className="space-y-2 max-h-48 overflow-y-auto text-xs font-mono">
                  {astResult.skipped_files.map((sf, idx) => (
                    <li
                      key={`${sf.file_path}-${idx}`}
                      className="flex items-center justify-between gap-2 pb-1.5 border-b border-slate-800/80 last:border-b-0"
                    >
                      <span className="text-slate-300 truncate">{sf.file_path}</span>
                      <span className="text-slate-500 shrink-0">{sf.reason}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
