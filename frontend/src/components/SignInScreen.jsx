export default function SignInScreen({
  loading,
  signInEnabled,
  error,
  onSignIn,
  onRetry,
}) {
  return (
    <main className="min-h-screen bg-slate-950 px-5 py-12 text-slate-100 sm:px-8">
      <div className="mx-auto grid min-h-[75vh] max-w-6xl items-center gap-12 lg:grid-cols-2">
        <section className="space-y-6">
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-indigo-300">
            DocGuard
          </p>
          <h1 className="max-w-xl text-4xl font-bold leading-tight text-white sm:text-5xl">
            Keep engineering documentation aligned with code.
          </h1>
          <p className="max-w-xl leading-relaxed text-slate-300">
            Analyze authorized GitHub changes with deterministic Python AST,
            Markdown mapping, and evidence-based drift detection.
          </p>
          <ul className="list-disc space-y-3 pl-5 text-sm text-slate-300">
            <li>Read-only repository analysis; source code is never executed.</li>
            <li>Public and private repositories require explicit GitHub App access.</li>
            <li>AI explanations are optional; selected evidence is shared with Gemini only when requested.</li>
          </ul>
        </section>
        <section className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-xl">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-600/20 font-bold text-indigo-300">
              DG
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">Sign in</h2>
              <p className="text-sm text-slate-400">Use your GitHub identity</p>
            </div>
          </div>

          {loading ? (
            <p role="status" className="text-sm text-slate-300">
              Checking your session...
            </p>
          ) : (
            <>
              {error && (
                <p
                  role="alert"
                  className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200"
                >
                  {error}
                </p>
              )}
              {signInEnabled ? (
                <button
                  type="button"
                  onClick={onSignIn}
                  className="w-full rounded-lg bg-white px-4 py-3 font-semibold text-slate-900 transition-colors hover:bg-slate-200"
                >
                  Continue with GitHub
                </button>
              ) : (
                <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
                  GitHub sign-in is not configured. Set the backend OAuth
                  environment variables and restart the API.
                </p>
              )}
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="mt-4 text-sm text-indigo-300 hover:text-indigo-200"
                >
                  Retry connection
                </button>
              )}
            </>
          )}
        </section>
      </div>
    </main>
  );
}
