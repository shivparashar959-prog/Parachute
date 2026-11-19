export default function AuthorizedRepositoryPicker({
  repositories,
  selectedRepositoryId,
  onSelectRepositoryId,
  onSubmit,
  loading,
  catalogLoading,
  appConfigured,
  appConnected,
  onConnectGitHubApp,
  installLoading,
  error,
}) {
  return (
    <section className="space-y-3">
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
          Authorized GitHub repositories
        </h4>
        <p className="mt-1 text-xs text-slate-400">
          Choose a repository explicitly authorized for this workspace. Private
          repository access stays on the backend.
        </p>
      </div>

      {error && (
        <p role="alert" className="text-xs text-rose-300">
          {error}
        </p>
      )}

      {!appConfigured ? (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
          GitHub App integration is not configured on the backend.
        </p>
      ) : !appConnected ? (
        <button
          type="button"
          onClick={onConnectGitHubApp}
          disabled={installLoading}
          className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {installLoading ? 'Opening GitHub...' : 'Connect GitHub App'}
        </button>
      ) : (
        <form onSubmit={onSubmit} className="flex flex-col gap-3 sm:flex-row">
          <label htmlFor="authorized-repository" className="sr-only">
            Select an authorized repository
          </label>
          <select
            id="authorized-repository"
            value={selectedRepositoryId}
            onChange={(event) => onSelectRepositoryId(event.target.value)}
            disabled={loading || catalogLoading}
            className="min-w-0 flex-1 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">
              {catalogLoading
                ? 'Refreshing authorized repositories...'
                : repositories.length
                ? 'Select an authorized repository'
                : 'No repositories authorized'}
            </option>
            {repositories.map((repository) => (
              <option
                key={repository.github_repository_id}
                value={repository.github_repository_id}
              >
                {repository.full_name} ({repository.visibility}
                {repository.is_archived ? ', archived' : ''})
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={loading || catalogLoading || !selectedRepositoryId}
            className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-lg shadow-indigo-600/20 transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
          >
            {loading ? 'Loading repository...' : 'Load repository'}
          </button>
          <button
            type="button"
            onClick={onConnectGitHubApp}
            disabled={installLoading}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {installLoading ? 'Opening...' : 'Add repositories'}
          </button>
        </form>
      )}
    </section>
  );
}
