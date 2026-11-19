import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  deleteAnalysis,
  fetchAnalysisHistory,
  retryAnalysis,
} from '../api/analyses.js';

const PAGE_SIZE = 20;
const RETRYABLE_ERROR_CATEGORIES = new Set([
  'analysis_timeout',
  'github_rate_limited',
  'github_temporarily_unavailable',
  'git_timeout',
  'queue_unavailable',
  'repository_unavailable',
  'worker_lost',
]);

function requestMessage(error) {
  if (error?.status === 429) return 'Rate limit reached. Wait before trying again.';
  if (error?.status === 502 || error?.status === 503) {
    return 'The repository service is temporarily unavailable. Try again shortly.';
  }
  return error instanceof Error ? error.message : 'Could not load analysis history.';
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : 'Not completed';
}

export default function AnalysisHistoryPage() {
  const navigate = useNavigate();
  const [offset, setOffset] = useState(0);
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busyAnalysisId, setBusyAnalysisId] = useState('');
  const [deleteCandidate, setDeleteCandidate] = useState('');

  const loadHistory = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetchAnalysisHistory({
        limit: PAGE_SIZE,
        offset,
        signal,
      });
      if (!signal?.aborted) {
        setHistory(response);
        if (response.total_count > 0 && offset >= response.total_count) {
          setOffset(Math.floor((response.total_count - 1) / PAGE_SIZE) * PAGE_SIZE);
        }
      }
    } catch (requestError) {
      if (requestError?.name !== 'AbortError' && !signal?.aborted) {
        setError(requestMessage(requestError));
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    const controller = new AbortController();
    loadHistory(controller.signal);
    return () => controller.abort();
  }, [loadHistory]);

  const handleRetry = async (item) => {
    setBusyAnalysisId(item.analysis_id);
    setActionError('');
    try {
      const job = await retryAnalysis(item.analysis_id);
      navigate(`/dashboard/history/${job.analysis_id}`);
    } catch (requestError) {
      setActionError(requestMessage(requestError));
    } finally {
      setBusyAnalysisId('');
    }
  };

  const handleDelete = async () => {
    if (!deleteCandidate) return;
    setBusyAnalysisId(deleteCandidate);
    setActionError('');
    try {
      await deleteAnalysis(deleteCandidate);
      setDeleteCandidate('');
      await loadHistory();
    } catch (requestError) {
      setActionError(requestMessage(requestError));
    } finally {
      setBusyAnalysisId('');
    }
  };

  const items = history?.items || [];
  const totalCount = history?.total_count || 0;
  const canGoBack = offset > 0;
  const canGoForward = offset + PAGE_SIZE < totalCount;

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-4 text-slate-100 sm:p-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Analysis history</h2>
          <p className="mt-1 text-sm text-slate-400">
            Persisted analysis jobs for repositories currently authorized to this workspace.
          </p>
        </div>
        <Link
          to="/dashboard/analyze"
          className="rounded-lg bg-indigo-600 px-4 py-2 text-center text-sm font-medium text-white hover:bg-indigo-500"
        >
          Start an analysis
        </Link>
      </header>

      {actionError && (
        <p role="alert" className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
          {actionError}
        </p>
      )}

      {deleteCandidate && (
        <section
          role="alertdialog"
          aria-labelledby="delete-analysis-heading"
          className="flex flex-col gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <h3 id="delete-analysis-heading" className="text-sm font-semibold text-amber-200">
              Delete this analysis?
            </h3>
            <p className="mt-1 text-xs text-slate-300">
              Persisted findings will be removed. Spend accounting remains available for quota enforcement.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setDeleteCandidate('')}
              className="rounded-md border border-slate-700 px-3 py-2 text-xs text-slate-200"
            >
              Keep analysis
            </button>
            <button
              type="button"
              onClick={handleDelete}
              disabled={Boolean(busyAnalysisId)}
              className="rounded-md bg-rose-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60"
            >
              Delete permanently
            </button>
          </div>
        </section>
      )}

      {loading ? (
        <p role="status" className="py-10 text-center text-sm text-slate-300">
          Loading saved analyses...
        </p>
      ) : error ? (
        <section className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-5">
          <p role="alert" className="text-sm text-rose-200">{error}</p>
          <button
            type="button"
            onClick={() => loadHistory()}
            className="mt-3 text-sm font-medium text-indigo-300 underline"
          >
            Try again
          </button>
        </section>
      ) : items.length === 0 && offset === 0 ? (
        <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-8 text-center">
          <h3 className="text-base font-semibold text-white">No saved analyses yet</h3>
          <p className="mt-2 text-sm text-slate-400">
            Analyses you run against authorized repositories will appear here.
          </p>
          <Link
            to="/dashboard/analyze"
            className="mt-4 inline-flex rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
          >
            Connect a repository
          </Link>
        </section>
      ) : (
        <section className="space-y-3" aria-label="Saved analyses">
          {items.map((item) => {
            const terminal = ['succeeded', 'failed', 'cancelled'].includes(item.status);
            return (
              <article
                key={item.analysis_id}
                className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 sm:p-5"
              >
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded border border-indigo-500/30 bg-indigo-500/10 px-2 py-0.5 text-xs font-semibold uppercase text-indigo-200">
                        {item.status}
                      </span>
                      <span className="text-xs text-slate-400">
                        {formatDate(item.created_at)}
                      </span>
                    </div>
                    <h3 className="break-all text-base font-semibold text-white">
                      {item.repository_accessible ? (
                        <Link
                          to={`/dashboard/history/${item.analysis_id}`}
                          className="hover:text-indigo-300"
                        >
                          {item.repository_full_name}
                        </Link>
                      ) : (
                        'Repository access unavailable'
                      )}
                    </h3>
                    {item.repository_accessible ? (
                      <p className="break-all font-mono text-xs text-slate-400">
                        {item.base_commit?.slice(0, 7)} → {item.head_commit?.slice(0, 7)}
                        {' · '}{item.finding_count} finding(s)
                      </p>
                    ) : (
                      <p className="text-xs text-amber-200">
                        Reauthorize this repository to view its commits, findings, or manage its history.
                      </p>
                    )}
                    {item.error_category && (
                      <p className="text-xs text-rose-300">
                        Last status detail: {item.error_category}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    {item.repository_accessible &&
                      (item.status === 'cancelled' ||
                        (item.status === 'failed' &&
                          RETRYABLE_ERROR_CATEGORIES.has(item.error_category))) && (
                      <button
                        type="button"
                        onClick={() => handleRetry(item)}
                        disabled={Boolean(busyAnalysisId)}
                        className="rounded-md border border-indigo-500/40 px-3 py-2 text-xs font-medium text-indigo-200 hover:bg-indigo-500/10 disabled:opacity-60"
                      >
                        Retry
                      </button>
                    )}
                    {item.repository_accessible && terminal && (
                      <button
                        type="button"
                        onClick={() => setDeleteCandidate(item.analysis_id)}
                        disabled={Boolean(busyAnalysisId)}
                        className="rounded-md border border-rose-500/30 px-3 py-2 text-xs font-medium text-rose-200 hover:bg-rose-500/10 disabled:opacity-60"
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
          <div className="flex items-center justify-between pt-2">
            <p className="text-xs text-slate-400">
              {totalCount ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, totalCount)} of ${totalCount}` : 'No results'}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
                disabled={!canGoBack}
                className="rounded-md border border-slate-700 px-3 py-2 text-xs text-slate-200 disabled:opacity-40"
              >
                Previous
              </button>
              <button
                type="button"
                onClick={() => setOffset((current) => current + PAGE_SIZE)}
                disabled={!canGoForward}
                className="rounded-md border border-slate-700 px-3 py-2 text-xs text-slate-200 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
