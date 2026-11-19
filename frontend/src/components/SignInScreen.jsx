import { useState } from 'react';

export default function SignInScreen({
  loading,
  signInEnabled,
  githubOAuthEnabled,
  error,
  onAuthenticate,
  onGitHubSignIn,
  onRetry,
}) {
  const [mode, setMode] = useState('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');

  async function submit(event) {
    event.preventDefault();
    setFormError('');
    setBusy(true);
    try {
      await onAuthenticate(mode, { name, email, password });
    } catch (requestError) {
      setFormError(
        requestError instanceof Error
          ? requestError.message
          : 'Authentication failed.'
      );
    } finally {
      setBusy(false);
    }
  }

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
            <li>Connect GitHub separately to grant repository access.</li>
            <li>AI explanations are optional.</li>
          </ul>
        </section>
        <section className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-xl">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-600/20 font-bold text-indigo-300">
              DG
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">
                {mode === 'login' ? 'Welcome back' : 'Create your account'}
              </h2>
              <p className="text-sm text-slate-400">
                Secure email and password sign-in
              </p>
            </div>
          </div>
          {loading ? (
            <p role="status" className="text-sm text-slate-300">
              Checking your session...
            </p>
          ) : (
            <>
              {(error || formError) && (
                <p
                  role="alert"
                  className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200"
                >
                  {formError || error}
                </p>
              )}
              {signInEnabled && (
                <form onSubmit={submit} className="space-y-4">
                  {mode === 'register' && (
                    <label className="block text-sm text-slate-300">
                      Full name
                      <input
                        autoComplete="name"
                        required
                        maxLength={200}
                        value={name}
                        onChange={(event) => setName(event.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-3 text-white outline-none focus:border-indigo-400"
                      />
                    </label>
                  )}
                  <label className="block text-sm text-slate-300">
                    Email
                    <input
                      type="email"
                      autoComplete="email"
                      required
                      maxLength={320}
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-3 text-white outline-none focus:border-indigo-400"
                    />
                  </label>
                  <label className="block text-sm text-slate-300">
                    Password
                    <input
                      type="password"
                      autoComplete={
                        mode === 'login' ? 'current-password' : 'new-password'
                      }
                      required
                      minLength={mode === 'register' ? 10 : 1}
                      maxLength={256}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-3 text-white outline-none focus:border-indigo-400"
                    />
                    {mode === 'register' && (
                      <span className="mt-1 block text-xs text-slate-500">
                        Use at least 10 characters.
                      </span>
                    )}
                  </label>
                  <button
                    disabled={busy}
                    type="submit"
                    className="w-full rounded-lg bg-indigo-600 px-4 py-3 font-semibold text-white transition-colors hover:bg-indigo-500 disabled:opacity-60"
                  >
                    {busy
                      ? 'Please wait...'
                      : mode === 'login'
                        ? 'Sign in'
                        : 'Create account'}
                  </button>
                </form>
              )}
              <p className="mt-5 text-center text-sm text-slate-400">
                {mode === 'login'
                  ? "Don't have an account?"
                  : 'Already have an account?'}{' '}
                <button
                  type="button"
                  onClick={() => {
                    setMode(mode === 'login' ? 'register' : 'login');
                    setFormError('');
                  }}
                  className="font-semibold text-indigo-300 hover:text-indigo-200"
                >
                  {mode === 'login' ? 'Create account' : 'Sign in'}
                </button>
              </p>
              {githubOAuthEnabled && (
                <button
                  type="button"
                  onClick={onGitHubSignIn}
                  className="mt-4 w-full rounded-lg border border-slate-700 px-4 py-3 font-semibold text-white transition-colors hover:bg-slate-800"
                >
                  Continue with GitHub
                </button>
              )}
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="mt-4 w-full text-sm text-slate-500 hover:text-slate-300"
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
