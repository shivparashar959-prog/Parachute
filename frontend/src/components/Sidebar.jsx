import { NavLink } from 'react-router-dom';

const NAV_ITEMS = [
  { to: '/dashboard/analyze', label: 'New analysis', end: true },
  { to: '/dashboard/history', label: 'Analysis history' },
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
      <header className="flex items-center justify-between border-b border-slate-800 bg-slate-900 px-4 py-3 lg:hidden">
        <NavLink
          to="/dashboard/analyze"
          className="font-semibold tracking-tight text-white"
        >
          DocGuard
        </NavLink>
        <button
          type="button"
          aria-expanded={mobileMenuOpen}
          aria-controls="dashboard-navigation"
          onClick={() => setMobileMenuOpen((previous) => !previous)}
          className="rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200"
        >
          {mobileMenuOpen ? 'Close menu' : 'Open menu'}
        </button>
      </header>

      <aside
        id="dashboard-navigation"
        className={`${
          mobileMenuOpen ? 'block' : 'hidden'
        } shrink-0 border-b border-slate-800 bg-slate-900/80 lg:flex lg:w-64 lg:flex-col lg:justify-between lg:border-b-0 lg:border-r`}
      >
        <div className="p-5">
          <NavLink
            to="/dashboard/analyze"
            className="hidden border-b border-slate-800 pb-5 lg:block"
          >
            <span className="text-lg font-bold tracking-tight text-white">
              DocGuard
            </span>
            <span className="mt-1 block text-xs text-slate-400">
              Documentation Drift Platform
            </span>
          </NavLink>

          <nav
            className="space-y-1.5 lg:mt-6"
            aria-label="Dashboard navigation"
          >
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => setMobileMenuOpen(false)}
                className={({ isActive }) =>
                  `block rounded-lg px-3 py-2.5 text-sm transition-colors ${
                    isActive
                      ? 'border border-indigo-500/30 bg-indigo-600/15 font-medium text-indigo-300'
                      : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>

        <section
          className="m-4 rounded-xl border border-slate-800 bg-slate-950/90 p-4"
          aria-label="Backend service status"
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              API health
            </span>
            <button
              type="button"
              onClick={onRefreshHealth}
              className="text-xs font-medium text-indigo-400 hover:text-indigo-300"
            >
              Refresh
            </button>
          </div>
          {healthState === 'checking' ? (
            <p role="status" className="text-xs text-amber-300">
              Checking backend...
            </p>
          ) : healthState === 'connected' ? (
            <>
              <p className="text-xs font-semibold text-emerald-400">
                Backend connected
              </p>
              <p className="mt-1.5 break-words text-[11px] text-slate-400">
                {healthData?.application} v{healthData?.version}
              </p>
            </>
          ) : (
            <p role="alert" className="break-words text-xs text-rose-300">
              {healthError || 'Could not connect to the backend.'}
            </p>
          )}
          {lastChecked && (
            <p className="mt-2 text-[10px] text-slate-500">
              Checked {lastChecked}
            </p>
          )}
        </section>
      </aside>
    </>
  );
}
