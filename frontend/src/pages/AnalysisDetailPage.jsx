import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  cancelAnalysis,
  fetchAIProviderStatus,
  fetchAnalysisDetail,
  fetchAnalysisStatus,
  generateFindingAIExplanations,
} from '../api/health.js';
import { deleteAnalysis, retryAnalysis } from '../api/analyses.js';
import DriftFindingsSection from '../components/DriftFindingsSection.jsx';

function wait(delay, signal) {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Request cancelled.', 'AbortError'));
      return;
    }
    const cleanup = () => signal.removeEventListener('abort', handleAbort);
    const timer = setTimeout(() => {
      cleanup();
      resolve();
    }, delay);
    const handleAbort = () => {
      clearTimeout(timer);
      cleanup();
      reject(new DOMException('Request cancelled.', 'AbortError'));
    };
    signal.addEventListener('abort', handleAbort, { once: true });
  });
}

function errorText(error) {
  if (error?.status === 404) {
    return 'This analysis is unavailable. The repository may have been removed or its access revoked.';
  }
  if (error?.status === 429) return 'Rate limit reached. Wait before trying again.';
  if (error?.status === 502 || error?.status === 503) {
    return 'GitHub or the analysis service is temporarily unavailable.';
  }
  return error instanceof Error ? error.message : 'Could not load this analysis.';
}

const RETRYABLE_ERROR_CATEGORIES = new Set([
  'analysis_timeout',
  'github_rate_limited',
  'github_temporarily_unavailable',
  'git_timeout',
  'queue_unavailable',
  'repository_unavailable',
  'worker_lost',
]);

export default function AnalysisDetailPage() {
  const { analysisId } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState(null);
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [deleteConfirmation, setDeleteConfirmation] = useState(false);
  const [busy, setBusy] = useState(false);
  const [aiProviderInfo, setAiProviderInfo] = useState(null);
  const [selectedAiProvider, setSelectedAiProvider] = useState('mock');
  const [aiExplanationsById, setAiExplanationsById] = useState({});
  const [aiLoadingById, setAiLoadingById] = useState({});
  const [aiErrorById, setAiErrorById] = useState({});
  const [aiFocusModeById, setAiFocusModeById] = useState({});
  const [expandedFindings, setExpandedFindings] = useState({});
  const [copiedFindingId, setCopiedFindingId] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    const load = async () => {
      setLoading(true);
      setDetail(null);
      setJob(null);
      setError('');
      setActionError('');
      try {
        let current = await fetchAnalysisDetail(analysisId, { signal });
        if (signal.aborted) return;
        setDetail(current);
        setJob(current);
        while (current.status === 'queued' || current.status === 'running') {
          await wait(1500, signal);
          const currentJob = await fetchAnalysisStatus(analysisId, { signal });
          if (signal.aborted) return;
          setJob(currentJob);
          current = { ...current, ...currentJob };
          setDetail(current);
          if (currentJob.status === 'succeeded') {
            current = await fetchAnalysisDetail(analysisId, { signal });
            setDetail(current);
          }
        }
      } catch (requestError) {
        if (requestError?.name !== 'AbortError' && !signal.aborted) {
          setError(errorText(requestError));
        }
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    };
    load();
    fetchAIProviderStatus({ signal })
      .then((providerInfo) => {
        if (!signal.aborted) {
          setAiProviderInfo(providerInfo);
          if (providerInfo?.active_default_provider) {
            setSelectedAiProvider(providerInfo.active_default_provider);
          }
        }
      })
      .catch(() => {
        if (!signal.aborted) setAiProviderInfo(null);
      });
    return () => controller.abort();
  }, [analysisId]);

  const handleRetry = async () => {
    setBusy(true);
    setActionError('');
    try {
      const newJob = await retryAnalysis(analysisId);
      navigate(`/dashboard/history/${newJob.analysis_id}`);
    } catch (requestError) {
      setActionError(errorText(requestError));
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    setBusy(true);
    setActionError('');
    try {
      await deleteAnalysis(analysisId);
      navigate('/dashboard/history', { replace: true });
    } catch (requestError) {
      setActionError(errorText(requestError));
    } finally {
      setBusy(false);
      setDeleteConfirmation(false);
    }
  };

  const handleCancel = async () => {
    setBusy(true);
    setActionError('');
    try {
      const currentJob = await cancelAnalysis(analysisId);
      setJob(currentJob);
      setDetail((current) => current && ({ ...current, ...currentJob }));
    } catch (requestError) {
      setActionError(errorText(requestError));
    } finally {
      setBusy(false);
    }
  };

  const handleRequestAI = async (finding, focusMode = 'explain') => {
    const findingId = finding.finding_id;
    setAiLoadingById((current) => ({ ...current, [findingId]: true }));
    setAiFocusModeById((current) => ({ ...current, [findingId]: focusMode }));
    setAiErrorById((current) => ({ ...current, [findingId]: '' }));
    try {
      const response = await generateFindingAIExplanations({
        analysisId,
        provider: selectedAiProvider,
        findingIds: [findingId],
      });
      const explanation = response?.explanations?.[0];
      if (explanation) {
        setAiExplanationsById((current) => ({ ...current, [findingId]: explanation }));
      } else {
        setAiErrorById((current) => ({
          ...current,
          [findingId]: 'No explanation was returned for this finding.',
        }));
      }
    } catch (requestError) {
      setAiErrorById((current) => ({
        ...current,
        [findingId]: errorText(requestError),
      }));
    } finally {
      setAiLoadingById((current) => ({ ...current, [findingId]: false }));
    }
  };

  const handleCopySuggestion = async (findingId, text) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopiedFindingId(findingId);
    } catch {
      setAiErrorById((current) => ({
        ...current,
        [findingId]: 'Clipboard access is unavailable in this browser.',
      }));
    }
  };

  const toggleFindingExpanded = (findingId) => {
    setExpandedFindings((current) => ({
      ...current,
      [findingId]: !current[findingId],
    }));
  };

  const terminal = detail && ['succeeded', 'failed', 'cancelled'].includes(detail.status);
  const canRetry =
    detail?.status === 'cancelled' ||
    (detail?.status === 'failed' &&
      RETRYABLE_ERROR_CATEGORIES.has(detail.error_category));

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-4 text-slate-100 sm:p-6">
      <Link
        to="/dashboard/history"
        className="text-sm text-indigo-300 underline hover:text-indigo-200"
      >
        Back to analysis history
      </Link>
      {loading && (
        <p role="status" className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 text-sm text-slate-300">
          Loading persisted analysis...
        </p>
      )}
      {error && (
        <section className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-5">
          <p role="alert" className="text-sm text-rose-200">{error}</p>
          <Link
            to="/dashboard/analyze"
            className="mt-3 inline-block text-sm text-indigo-300 underline"
          >
            Reconnect a repository
          </Link>
        </section>
      )}
      {actionError && (
        <p role="alert" className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
          {actionError}
        </p>
      )}
      {detail && !error && (
        <>
          <header className="flex flex-col gap-4 rounded-xl border border-slate-800 bg-slate-900/70 p-5 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="break-all text-xl font-bold text-white">
                  {detail.repository_full_name}
                </h2>
                <span className="rounded border border-indigo-500/30 bg-indigo-500/10 px-2 py-0.5 text-xs uppercase text-indigo-200">
                  {job?.status || detail.status}
                </span>
              </div>
              <p className="mt-2 break-all font-mono text-xs text-slate-400">
                {detail.base_commit} → {detail.head_commit}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Created {new Date(detail.created_at).toLocaleString()}
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              {canRetry && (
                <button
                  type="button"
                  onClick={handleRetry}
                  disabled={busy}
                  className="rounded-md border border-indigo-500/40 px-3 py-2 text-xs font-medium text-indigo-200 disabled:opacity-60"
                >
                  Retry analysis
                </button>
              )}
              {['queued', 'running'].includes(job?.status) && (
                <button
                  type="button"
                  onClick={handleCancel}
                  disabled={busy || job?.cancellation_requested}
                  className="rounded-md border border-amber-500/40 px-3 py-2 text-xs font-medium text-amber-200 disabled:opacity-60"
                >
                  {job?.cancellation_requested ? 'Cancellation requested' : 'Cancel'}
                </button>
              )}
              {terminal && (
                <button
                  type="button"
                  onClick={() => setDeleteConfirmation((value) => !value)}
                  disabled={busy}
                  className="rounded-md border border-rose-500/30 px-3 py-2 text-xs font-medium text-rose-200 disabled:opacity-60"
                >
                  Delete history
                </button>
              )}
            </div>
          </header>

          {deleteConfirmation && (
            <section role="alertdialog" className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
              <p className="text-sm text-amber-100">
                Delete this analysis and its findings? Spend accounting is retained.
              </p>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => setDeleteConfirmation(false)}
                  className="rounded-md border border-slate-700 px-3 py-2 text-xs text-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={busy}
                  className="rounded-md bg-rose-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60"
                >
                  Confirm delete
                </button>
              </div>
            </section>
          )}

          {['queued', 'running'].includes(job?.status) && (
            <section className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/70 p-5">
              <p className="text-sm text-slate-200">
                Analysis {job.status}; progress {job.progress_percent}% · attempt {job.attempt_count}/{job.max_attempts}
              </p>
              <div
                role="progressbar"
                aria-label="Analysis progress"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={job.progress_percent}
                className="h-2 overflow-hidden rounded bg-slate-800"
              >
                <div
                  className="h-full bg-indigo-500 transition-all"
                  style={{ width: `${job.progress_percent}%` }}
                />
              </div>
            </section>
          )}
          {job?.error_category && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
              Analysis status: {job.error_category}
            </p>
          )}

          {detail.status === 'succeeded' && detail.summary && (
            <DriftFindingsSection
              healthState={aiProviderInfo ? 'connected' : 'disconnected'}
              baseCommit={detail.base_commit}
              headCommit={detail.head_commit}
              canCompare={false}
              driftLoading={false}
              driftError=""
              driftJob={job}
              driftCancelLoading={busy}
              onDismissDriftError={() => {}}
              driftResult={detail}
              driftStatusFilter="ALL"
              onDriftStatusFilterChange={() => {}}
              driftSeverityFilter="ALL"
              onDriftSeverityFilterChange={() => {}}
              expandedFindings={expandedFindings}
              onToggleFindingExpanded={toggleFindingExpanded}
              onAnalyzeDrift={() => {}}
              onCancelDrift={() => {}}
              aiProviderInfo={aiProviderInfo}
              selectedAiProvider={selectedAiProvider}
              onSelectAiProvider={setSelectedAiProvider}
              aiExplanationsById={aiExplanationsById}
              aiLoadingById={aiLoadingById}
              aiErrorById={aiErrorById}
              onDismissAiError={(findingId) => setAiErrorById((current) => ({ ...current, [findingId]: '' }))}
              aiFocusModeById={aiFocusModeById}
              onRequestFindingAI={handleRequestAI}
              copiedFindingId={copiedFindingId}
              onCopySuggestion={handleCopySuggestion}
            />
          )}
          {detail.status === 'succeeded' && !detail.summary && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
              The analysis completed but did not return a summary. No findings are available.
            </p>
          )}
        </>
      )}
    </div>
  );
}
