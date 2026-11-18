import { useEffect, useState, useCallback } from 'react';
import { fetchBackendHealth } from './api/health';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard Overview', badge: 'Active', active: true },
  { id: 'analysis', label: 'Repository Diff', badge: 'Milestone 2', active: false },
  { id: 'findings', label: 'Drift Findings', badge: 'Milestone 3', active: false },
  { id: 'docs', label: 'Documentation Map', badge: 'Milestone 4', active: false },
];

export default function App() {
  // Live backend health state ('checking' | 'connected' | 'disconnected')
  const [healthState, setHealthState] = useState('checking');
  const [healthData, setHealthData] = useState(null);
  const [healthError, setHealthError] = useState('');
  const [lastChecked, setLastChecked] = useState(null);

  // Form inputs (UI foundation for Milestone 1)
  const [repoUrl, setRepoUrl] = useState('');
  const [baseCommit, setBaseCommit] = useState('');
  const [headCommit, setHeadCommit] = useState('');

  // Milestone 1 placeholder notice when clicking "Analyze Repository"
  const [milestoneNotice, setMilestoneNotice] = useState('');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const checkBackendHealth = useCallback(async () => {
    setHealthState('checking');
    setHealthError('');
    try {
      const data = await fetchBackendHealth();
      if (data && data.status === 'ok') {
        setHealthData(data);
        setHealthState('connected');
      } else {
        setHealthData(data);
        setHealthState('disconnected');
        setHealthError('Unexpected response format from /api/health');
      }
    } catch (err) {
      setHealthData(null);
      setHealthState('disconnected');
      setHealthError(
        err instanceof Error
          ? err.message
          : 'Unable to reach FastAPI server at /api/health'
      );
    } finally {
      setLastChecked(new Date().toLocaleTimeString());
    }
  }, []);

  useEffect(() => {
    checkBackendHealth();
  }, [checkBackendHealth]);

  const handleAnalyzeSubmit = (event) => {
    event.preventDefault();
    setMilestoneNotice(
      'Repository analysis will be available in a later milestone. Milestone 1 establishes the project foundation and frontend-backend connectivity only.'
    );
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col lg:flex-row">
      {/* Top Bar for Mobile */}
      <header className="lg:hidden flex items-center justify-between px-4 py-3 bg-slate-900 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400 font-bold">
            DG
          </div>
          <div>
            <span className="font-semibold tracking-tight text-white">DocGuard</span>
            <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">
              v0.1.0
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setMobileMenuOpen((prev) => !prev)}
          className="px-3 py-1.5 rounded-md text-xs font-medium bg-slate-800 text-slate-200 border border-slate-700 hover:bg-slate-700"
        >
          {mobileMenuOpen ? 'Close Menu' : 'Navigation'}
        </button>
      </header>

      {/* Sidebar Navigation */}
      <aside
        className={`${
          mobileMenuOpen ? 'block' : 'hidden'
        } lg:flex lg:flex-col lg:w-72 bg-slate-900/80 border-b lg:border-b-0 lg:border-r border-slate-800 shrink-0 justify-between`}
      >
        <div className="p-6">
          {/* Brand Logo & Title */}
          <div className="flex items-center gap-3 pb-6 border-b border-slate-800">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <svg
                className="w-6 h-6 text-white"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                />
              </svg>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold tracking-tight text-white">DocGuard</h1>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                  M1
                </span>
              </div>
              <p className="text-xs text-slate-400">Documentation Drift Platform</p>
            </div>
          </div>

          {/* Navigation Menu */}
          <nav className="mt-6 space-y-1.5" aria-label="Sidebar Navigation">
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">
              Workspace
            </p>
            {NAV_ITEMS.map((item) => (
              <div
                key={item.id}
                className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  item.active
                    ? 'bg-indigo-600/15 text-indigo-300 border border-indigo-500/30 font-medium'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                <span>{item.label}</span>
                <span
                  className={`text-[11px] px-2 py-0.5 rounded-full ${
                    item.active
                      ? 'bg-indigo-500/20 text-indigo-300'
                      : 'bg-slate-800 text-slate-500'
                  }`}
                >
                  {item.badge}
                </span>
              </div>
            ))}
          </nav>
        </div>

        {/* Sidebar Footer: Live Backend Health Widget */}
        <div className="p-5 m-4 rounded-xl bg-slate-950/90 border border-slate-800">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              API Health
            </span>
            <button
              type="button"
              onClick={checkBackendHealth}
              className="text-xs text-indigo-400 hover:text-indigo-300 font-medium cursor-pointer"
            >
              Refresh
            </button>
          </div>

          {healthState === 'checking' && (
            <div className="flex items-center gap-2 text-xs text-amber-300">
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400 animate-pulse" />
              <span>Checking /api/health...</span>
            </div>
          )}

          {healthState === 'connected' && (
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-emerald-400">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
                <span>Backend connected</span>
              </div>
              <p className="mt-1.5 text-[11px] font-mono text-slate-400">
                {healthData?.application} v{healthData?.version} ({healthData?.status})
              </p>
            </div>
          )}

          {healthState === 'disconnected' && (
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-rose-400">
                <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
                <span>Backend disconnected</span>
              </div>
              <p className="mt-1.5 text-[11px] text-rose-300/90 break-words">
                {healthError || 'Could not connect to FastAPI server.'}
              </p>
            </div>
          )}

          {lastChecked && (
            <p className="mt-2 text-[10px] text-slate-500">Last checked: {lastChecked}</p>
          )}
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto">
        {/* Top Utility Header */}
        <div className="border-b border-slate-800 bg-slate-900/40 px-6 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              Documentation Drift Dashboard
            </h2>
            <p className="text-sm text-slate-400">
              Monitor repository changes and detect outdated documentation before it ships.
            </p>
          </div>

          {/* Prominent Connection Badge in Header */}
          <div className="flex items-center gap-3">
            <div
              className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-medium border ${
                healthState === 'connected'
                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                  : healthState === 'checking'
                  ? 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                  : 'bg-rose-500/10 text-rose-300 border-rose-500/30'
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  healthState === 'connected'
                    ? 'bg-emerald-400'
                    : healthState === 'checking'
                    ? 'bg-amber-400 animate-pulse'
                    : 'bg-rose-400'
                }`}
              />
              <span>
                {healthState === 'connected'
                  ? 'Backend connected'
                  : healthState === 'checking'
                  ? 'Checking backend...'
                  : 'Backend disconnected'}
              </span>
            </div>
            <button
              type="button"
              onClick={checkBackendHealth}
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors cursor-pointer"
            >
              Test /api/health
            </button>
          </div>
        </div>

        <div className="p-6 max-w-7xl mx-auto space-y-6">
          {/* Dashboard Overview Cards */}
          <section aria-label="Dashboard Overview" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                Backend Service
              </p>
              <p className="mt-2 text-lg font-bold text-white">
                {healthState === 'connected'
                  ? 'Backend connected'
                  : healthState === 'checking'
                  ? 'Connecting...'
                  : 'Backend disconnected'}
              </p>
              <p className="mt-1 text-xs text-slate-400 font-mono">
                GET /api/health
              </p>
            </div>

            <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                Application Version
              </p>
              <p className="mt-2 text-lg font-bold text-white">
                {healthData?.version ? `v${healthData.version}` : 'v0.1.0'}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Milestone 1 Foundation
              </p>
            </div>

            <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                Analysis Status
              </p>
              <p className="mt-2 text-lg font-bold text-amber-300">
                Idle / Not Started
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Awaiting future milestone engine
              </p>
            </div>

            <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                Drift Findings
              </p>
              <p className="mt-2 text-lg font-bold text-white">0 Findings</p>
              <p className="mt-1 text-xs text-slate-400">
                No repositories analyzed yet
              </p>
            </div>
          </section>

          {/* Main Grid: Repository Configuration & Analysis Status */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Repository Analysis Form (2 columns on desktop) */}
            <section className="lg:col-span-2 rounded-xl bg-slate-900/70 border border-slate-800 p-6">
              <div className="flex items-center justify-between pb-4 mb-6 border-b border-slate-800">
                <div>
                  <h3 className="text-base font-semibold text-white">
                    Repository Drift Scan Configuration
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Specify a target Git repository and commit range to inspect for documentation drift.
                  </p>
                </div>
                <span className="text-xs px-2.5 py-1 rounded-md bg-slate-800 text-slate-300 border border-slate-700 font-mono">
                  UI Foundation
                </span>
              </div>

              <form onSubmit={handleAnalyzeSubmit} className="space-y-5">
                <div>
                  <label
                    htmlFor="repo-url"
                    className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-2"
                  >
                    Repository URL
                  </label>
                  <input
                    id="repo-url"
                    type="url"
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    placeholder="https://github.com/organization/repository"
                    className="w-full rounded-lg bg-slate-950 border border-slate-800 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label
                      htmlFor="base-commit"
                      className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-2"
                    >
                      Base Commit / Reference
                    </label>
                    <input
                      id="base-commit"
                      type="text"
                      value={baseCommit}
                      onChange={(e) => setBaseCommit(e.target.value)}
                      placeholder="e.g., main or a1b2c3d"
                      className="w-full rounded-lg bg-slate-950 border border-slate-800 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="head-commit"
                      className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-2"
                    >
                      Head Commit / Reference
                    </label>
                    <input
                      id="head-commit"
                      type="text"
                      value={headCommit}
                      onChange={(e) => setHeadCommit(e.target.value)}
                      placeholder="e.g., feature/update-api or 9f8e7d6"
                      className="w-full rounded-lg bg-slate-950 border border-slate-800 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono"
                    />
                  </div>
                </div>

                <div className="pt-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <p className="text-xs text-slate-400">
                    Comparisons evaluate code changes against Markdown and API documentation.
                  </p>
                  <button
                    type="submit"
                    className="px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-sm shadow-lg shadow-indigo-600/25 transition-colors cursor-pointer shrink-0"
                  >
                    Analyze Repository
                  </button>
                </div>
              </form>

              {/* Honest Milestone 1 Notice when "Analyze Repository" is clicked */}
              {milestoneNotice && (
                <div
                  role="status"
                  className="mt-5 p-4 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-200 text-sm flex items-start justify-between gap-4"
                >
                  <div>
                    <p className="font-semibold text-amber-300">
                      Feature Scheduled for Future Milestone
                    </p>
                    <p className="mt-1 text-xs text-amber-200/90 leading-relaxed">
                      {milestoneNotice}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setMilestoneNotice('')}
                    className="text-xs text-amber-300 hover:text-white underline shrink-0 cursor-pointer"
                  >
                    Dismiss
                  </button>
                </div>
              )}
            </section>

            {/* Analysis Status Section (1 column on desktop) */}
            <section className="rounded-xl bg-slate-900/70 border border-slate-800 p-6 flex flex-col justify-between">
              <div>
                <div className="pb-4 mb-4 border-b border-slate-800">
                  <h3 className="text-base font-semibold text-white">Analysis Status</h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Real-time pipeline and backend connection telemetry.
                  </p>
                </div>

                <div className="space-y-4 text-sm">
                  <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-xs text-slate-400 block">Pipeline State</span>
                    <span className="text-sm font-semibold text-slate-200 mt-0.5 block">
                      {milestoneNotice
                        ? 'Placeholder Triggered (Milestone 1)'
                        : 'Standby — No Active Job'}
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
                </div>
              </div>

              <div className="mt-6 pt-4 border-t border-slate-800 text-xs text-slate-500">
                Milestone 1 verifies full-stack setup between React + Vite and FastAPI.
              </div>
            </section>
          </div>

          {/* Empty Findings State Section */}
          <section className="rounded-xl bg-slate-900/70 border border-slate-800 p-6">
            <div className="flex items-center justify-between pb-4 mb-6 border-b border-slate-800">
              <div>
                <h3 className="text-base font-semibold text-white">
                  Documentation Drift Findings
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Detected discrepancies between source code changes and project documentation.
                </p>
              </div>
              <span className="text-xs font-mono px-2.5 py-1 rounded bg-slate-800 text-slate-400">
                0 items
              </span>
            </div>

            <div className="py-12 px-4 text-center max-w-md mx-auto">
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
                No analysis has been performed yet
              </h4>
              <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                No documentation drift findings to display. Once repository analysis and code-to-doc comparison are implemented in upcoming milestones, detected drift items and remediation suggestions will appear here.
              </p>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
