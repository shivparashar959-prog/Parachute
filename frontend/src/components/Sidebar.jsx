const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard Overview', badge: 'Active', active: true },
  { id: 'analysis', label: 'Repository Diff', badge: 'Active (M2)', active: true },
  { id: 'ast', label: 'Python AST Analysis', badge: 'Active (M3)', active: true },
  { id: 'docs', label: 'Documentation Map', badge: 'Active (M4)', active: true },
  { id: 'findings', label: 'Drift Findings', badge: 'Active (M5)', active: true },
  { id: 'ai', label: 'AI Explanations', badge: 'Active (M6)', active: true },
];

export default function Sidebar({
  mobileMenuOpen,
  setMobileMenuOpen,
  healthState,
  healthData,
  healthError,
  lastChecked,
  onRefreshHealth,
}) {
  return (
    <>
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
                  M7
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
              onClick={onRefreshHealth}
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
    </>
  );
}
