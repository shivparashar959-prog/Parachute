export default function AccountMenu({ session, loading, error, onSignOut }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="text-right">
        <p className="text-sm font-medium text-slate-200">
          {session.user.display_name}
        </p>
        <p className="text-xs text-slate-400">
          {session.workspace.name} · {session.workspace.role}
        </p>
      </div>
      <button
        type="button"
        onClick={onSignOut}
        disabled={loading}
        className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading ? 'Signing out...' : 'Sign out'}
      </button>
      {error && (
        <p role="alert" className="w-full text-right text-xs text-rose-300">
          {error}
        </p>
      )}
    </div>
  );
}
