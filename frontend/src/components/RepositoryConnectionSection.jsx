function formatCommitTimestamp(isoString) {
  if (!isoString) return '';
  try {
    const dt = new Date(isoString);
    return dt.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoString;
  }
}

export default function RepositoryConnectionSection({
  repoUrl,
  onRepoUrlChange,
  onSelectPresetUrl,
  inspectLoading,
  inspectError,
  onDismissInspectError,
  onConnectRepository,
  repoInfo,
  baseCommit,
  headCommit,
  onBaseCommitChange,
  onHeadCommitChange,
  canCompare,
  canAnalyzeDocs,
  compareLoading,
  compareError,
  onDismissCompareError,
  compareResult,
  astLoading,
  docLoading,
  driftLoading,
  onCompareCommits,
  onAnalyzePythonChanges,
  onAnalyzeDocumentation,
  onAnalyzeDrift,
  healthState,
  healthData,
  healthError,
}) {
  const selectedBaseCommitObj = repoInfo?.commits?.find(
    (c) => c.sha === baseCommit
  );
  const selectedHeadCommitObj = repoInfo?.commits?.find(
    (c) => c.sha === headCommit
  );

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Repository Connection & Commit Comparison Panel (2 columns) */}
      <section className="lg:col-span-2 rounded-xl bg-slate-900/70 border border-slate-800 p-6 space-y-6">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div>
            <h3 className="text-base font-semibold text-white">
              GitHub Repository Connection & Commit Comparison
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Connect a public HTTPS GitHub repository to retrieve live commit history and inspect code diffs.
            </p>
          </div>
          <span className="text-xs px-2.5 py-1 rounded-md bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 font-mono">
            Milestone 2 Live
          </span>
        </div>

        {/* Step 1: Connect Repository Form */}
        <form onSubmit={onConnectRepository} className="space-y-3">
          <label
            htmlFor="repo-url"
            className="block text-xs font-semibold uppercase tracking-wider text-slate-300"
          >
            1. Public GitHub Repository URL
          </label>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              id="repo-url"
              type="url"
              value={repoUrl}
              onChange={(e) => onRepoUrlChange(e.target.value)}
              disabled={inspectLoading}
              placeholder="https://github.com/pallets/flask"
              className="flex-1 rounded-lg bg-slate-950 border border-slate-800 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={inspectLoading || !repoUrl.trim()}
              className="px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-sm shadow-lg shadow-indigo-600/20 transition-colors cursor-pointer shrink-0 flex items-center justify-center gap-2"
            >
              {inspectLoading ? (
                <>
                  <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  <span>Connecting...</span>
                </>
              ) : (
                <span>Connect Repository</span>
              )}
            </button>
          </div>

          {/* Quick-Select Preset Buttons for Hackathon Demo & Real-World Testing */}
          <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
            <span className="text-slate-400">Quick Presets:</span>
            <button
              type="button"
              disabled={inspectLoading}
              onClick={() =>
                onSelectPresetUrl('https://github.com/docguard-demo/billing-api')
              }
              className="px-2.5 py-1 rounded-md bg-indigo-500/15 hover:bg-indigo-500/25 text-indigo-300 border border-indigo-500/30 font-mono text-[11px] cursor-pointer"
            >
              Controlled Demo (docguard-demo/billing-api)
            </button>
            <button
              type="button"
              disabled={inspectLoading}
              onClick={() =>
                onSelectPresetUrl('https://github.com/pallets/flask')
              }
              className="px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 font-mono text-[11px] cursor-pointer"
            >
              Real GitHub (pallets/flask)
            </button>
          </div>
        </form>

        {/* Inspect Error Banner */}
        {inspectError && (
          <div
            role="alert"
            className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start justify-between gap-4"
          >
            <div>
              <p className="font-semibold text-rose-300">
                Repository Connection Failed
              </p>
              <p className="mt-1 leading-relaxed">{inspectError}</p>
            </div>
            <button
              type="button"
              onClick={onDismissInspectError}
              className="text-rose-300 hover:text-white underline shrink-0 cursor-pointer"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Step 2: Repository Metadata & Commit Dropdowns */}
        {repoInfo && (
          <div className="pt-4 border-t border-slate-800 space-y-5">
            {/* Repository Details Pill Bar */}
            <div className="p-4 rounded-xl bg-slate-950/90 border border-slate-800 grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                  Owner / Repository
                </span>
                <a
                  href={repoInfo.repository_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 text-sm font-semibold text-indigo-300 hover:text-indigo-200 font-mono inline-flex items-center gap-1"
                >
                  {repoInfo.owner}/{repoInfo.name}
                </a>
              </div>
              <div>
                <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                  Default Branch
                </span>
                <span className="mt-1 inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-mono bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                  {repoInfo.default_branch}
                </span>
              </div>
              <div>
                <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                  Recent Commits Loaded
                </span>
                <span className="mt-1 text-sm font-semibold text-white block">
                  {repoInfo.commits.length} commits
                </span>
              </div>
            </div>

            {/* Base & Head Commit Selectors */}
            <form onSubmit={onCompareCommits} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label
                    htmlFor="base-commit-select"
                    className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-2"
                  >
                    2. Base Commit (Older / Starting Point)
                  </label>
                  <select
                    id="base-commit-select"
                    value={baseCommit}
                    onChange={(e) => onBaseCommitChange(e.target.value)}
                    disabled={inspectLoading}
                    className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono"
                  >
                    <option value="">-- Select Base Commit --</option>
                    {repoInfo.commits.map((commit) => (
                      <option key={`base-${commit.sha}`} value={commit.sha}>
                        [{commit.short_sha}] {commit.message.slice(0, 55)} ({commit.author})
                      </option>
                    ))}
                  </select>
                  {selectedBaseCommitObj && (
                    <p className="mt-1.5 text-[11px] text-slate-400 truncate">
                      Author:{' '}
                      <span className="text-slate-300">
                        {selectedBaseCommitObj.author}
                      </span>{' '}
                      • {formatCommitTimestamp(selectedBaseCommitObj.timestamp)}
                    </p>
                  )}
                </div>

                <div>
                  <label
                    htmlFor="head-commit-select"
                    className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-2"
                  >
                    3. Head Commit (Newer / Target Point)
                  </label>
                  <select
                    id="head-commit-select"
                    value={headCommit}
                    onChange={(e) => onHeadCommitChange(e.target.value)}
                    disabled={inspectLoading}
                    className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono"
                  >
                    <option value="">-- Select Head Commit --</option>
                    {repoInfo.commits.map((commit) => (
                      <option key={`head-${commit.sha}`} value={commit.sha}>
                        [{commit.short_sha}] {commit.message.slice(0, 55)} ({commit.author})
                      </option>
                    ))}
                  </select>
                  {selectedHeadCommitObj && (
                    <p className="mt-1.5 text-[11px] text-slate-400 truncate">
                      Author:{' '}
                      <span className="text-slate-300">
                        {selectedHeadCommitObj.author}
                      </span>{' '}
                      • {formatCommitTimestamp(selectedHeadCommitObj.timestamp)}
                    </p>
                  )}
                </div>
              </div>

              {baseCommit && headCommit && baseCommit === headCommit && (
                <p className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
                  Base commit and head commit must be different to perform a comparison.
                </p>
              )}

              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pt-1">
                <p className="text-xs text-slate-400">
                  Compare Git diffs or perform static Python AST symbol change analysis between Base (
                  {baseCommit ? baseCommit.slice(0, 7) : 'none'}) and Head (
                  {headCommit ? headCommit.slice(0, 7) : 'none'}).
                </p>
                <div className="flex flex-wrap items-center gap-3 shrink-0">
                  <button
                    type="submit"
                    disabled={!canCompare}
                    className="px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-sm shadow-lg shadow-emerald-600/20 transition-colors cursor-pointer flex items-center justify-center gap-2"
                  >
                    {compareLoading ? (
                      <>
                        <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                        <span>Comparing Commits...</span>
                      </>
                    ) : (
                      <span>Compare Commits</span>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={onAnalyzePythonChanges}
                    disabled={!canCompare}
                    className="px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-sm shadow-lg shadow-indigo-600/20 transition-colors cursor-pointer flex items-center justify-center gap-2"
                  >
                    {astLoading ? (
                      <>
                        <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                        <span>Analyzing Python AST...</span>
                      </>
                    ) : (
                      <span>Analyze Python Changes</span>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={onAnalyzeDocumentation}
                    disabled={!canAnalyzeDocs}
                    className="px-4 py-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-sm shadow-lg shadow-cyan-600/20 transition-colors cursor-pointer flex items-center justify-center gap-2"
                  >
                    {docLoading ? (
                      <>
                        <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                        <span>Mapping Docs...</span>
                      </>
                    ) : (
                      <span>Analyze Documentation</span>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={onAnalyzeDrift}
                    disabled={!canCompare}
                    className="px-4 py-2.5 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-semibold text-sm shadow-lg shadow-rose-600/25 transition-colors cursor-pointer flex items-center justify-center gap-2"
                  >
                    {driftLoading ? (
                      <>
                        <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                        <span>Detecting Drift...</span>
                      </>
                    ) : (
                      <span>ANALYZE DOCUMENTATION DRIFT</span>
                    )}
                  </button>
                </div>
              </div>
            </form>
          </div>
        )}

        {/* Compare Error Banner */}
        {compareError && (
          <div
            role="alert"
            className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start justify-between gap-4"
          >
            <div>
              <p className="font-semibold text-rose-300">
                Commit Comparison Failed
              </p>
              <p className="mt-1 leading-relaxed">{compareError}</p>
            </div>
            <button
              type="button"
              onClick={onDismissCompareError}
              className="text-rose-300 hover:text-white underline shrink-0 cursor-pointer"
            >
              Dismiss
            </button>
          </div>
        )}
      </section>

      {/* Analysis Status & Recent Commit Feed (1 column) */}
      <section className="rounded-xl bg-slate-900/70 border border-slate-800 p-6 flex flex-col justify-between">
        <div>
          <div className="pb-4 mb-4 border-b border-slate-800">
            <h3 className="text-base font-semibold text-white">Analysis Status</h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Real-time repository and backend connection telemetry.
            </p>
          </div>

          <div className="space-y-4 text-sm">
            <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800">
              <span className="text-xs text-slate-400 block">Pipeline State</span>
              <span className="text-sm font-semibold text-slate-200 mt-0.5 block">
                {inspectLoading
                  ? 'Cloning & Inspecting Repository...'
                  : compareLoading
                  ? 'Computing Git Commit Diff...'
                  : astLoading
                  ? 'Running Python AST Code Analysis...'
                  : docLoading
                  ? 'Parsing & Mapping Documentation...'
                  : driftLoading
                  ? 'Evaluating Documentation Drift Rules...'
                  : compareResult
                  ? `Diff Complete (${compareResult.total_changed_files} files)`
                  : repoInfo
                  ? `Connected to ${repoInfo.owner}/${repoInfo.name}`
                  : 'Standby — Awaiting Repository'}
              </span>
            </div>

            <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800">
              <span className="text-xs text-slate-400 block">
                FastAPI Health Endpoint
              </span>
              {healthState === 'connected' ? (
                <div className="mt-1">
                  <span className="text-sm font-semibold text-emerald-400 block">
                    Backend connected
                  </span>
                  <code className="mt-1.5 block text-[11px] text-slate-400 font-mono bg-slate-900 p-2 rounded border border-slate-800">
                    {JSON.stringify(healthData)}
                  </code>
                </div>
              ) : healthState === 'checking' ? (
                <span className="text-sm font-semibold text-amber-300 mt-1 block">
                  Querying GET /api/health...
                </span>
              ) : (
                <div className="mt-1">
                  <span className="text-sm font-semibold text-rose-400 block">
                    Backend disconnected
                  </span>
                  <span className="text-xs text-rose-300/90 mt-1 block">
                    {healthError}
                  </span>
                </div>
              )}
            </div>

            {repoInfo && (
              <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800">
                <span className="text-xs text-slate-400 block mb-2">
                  Latest Commits ({repoInfo.default_branch})
                </span>
                <ul className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {repoInfo.commits.slice(0, 6).map((c) => (
                    <li
                      key={c.sha}
                      className="text-xs border-b border-slate-800/80 pb-1.5 last:border-b-0"
                    >
                      <div className="flex items-center justify-between font-mono text-[11px] text-indigo-300">
                        <span>{c.short_sha}</span>
                        <span className="text-slate-500">
                          {formatCommitTimestamp(c.timestamp)}
                        </span>
                      </div>
                      <p className="text-slate-300 truncate mt-0.5">{c.message}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>

        <div className="mt-6 pt-4 border-t border-slate-800 text-xs text-slate-500">
          Repositories are inspected in isolated temporary directories and cleaned up immediately.
        </div>
      </section>
    </div>
  );
}
