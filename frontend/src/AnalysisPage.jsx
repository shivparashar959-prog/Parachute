import { useEffect, useState, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  inspectRepository,
  compareRepositoryCommits,
  analyzePythonCodeChanges,
  analyzeRepositoryDocumentation,
  analyzeDocumentationDrift,
  fetchAnalysisStatus,
  fetchAnalysisDetail,
  cancelAnalysis,
  generateFindingAIExplanations,
  isRequestCancelledError,
} from './api/health';
import {
  createGitHubAppInstallation,
  fetchAuthorizedRepositories,
  fetchGitHubAppStatus,
  fetchRepositoryPullRequests,
  fetchPullRequestAutomation,
  updatePullRequestAutomation,
} from './api/githubApp';
import { useAuth } from './auth/AuthContext';
import { useRequestGuard } from './hooks/useRequestGuard';
import RepositoryConnectionSection from './components/RepositoryConnectionSection';
import CommitComparisonSection from './components/CommitComparisonSection';
import PythonAstAnalysisSection from './components/PythonAstAnalysisSection';
import DocumentationMapSection from './components/DocumentationMapSection';
import DriftFindingsSection from './components/DriftFindingsSection';

function waitForPollingInterval(delayMs, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      const error = new Error('Analysis status polling was cancelled.');
      error.name = 'AbortError';
      reject(error);
      return;
    }

    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', handleAbort);
      resolve();
    }, delayMs);
    const handleAbort = () => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', handleAbort);
      const error = new Error('Analysis status polling was cancelled.');
      error.name = 'AbortError';
      reject(error);
    };
    signal?.addEventListener('abort', handleAbort, { once: true });
  });
}

export default function AnalysisPage() {
  const { session: authSession } = useAuth();
  const {
    healthState,
    healthData,
    healthError,
    checkBackendHealth,
    aiProviderInfo,
  } = useOutletContext();

  // Authorized repository catalog and repository inspection state
  const [githubAppStatus, setGitHubAppStatus] = useState(null);
  const [authorizedRepositories, setAuthorizedRepositories] = useState([]);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState('');
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [githubAppError, setGitHubAppError] = useState('');
  const [installLoading, setInstallLoading] = useState(false);
  const [inspectLoading, setInspectLoading] = useState(false);
  const [inspectError, setInspectError] = useState('');
  const [repoInfo, setRepoInfo] = useState(null);
  const [pullRequests, setPullRequests] = useState([]);
  const [pullRequestsLoading, setPullRequestsLoading] = useState(false);
  const [pullRequestsError, setPullRequestsError] = useState('');
  const [selectedPullRequest, setSelectedPullRequest] = useState('');
  const [pullRequestAutomationEnabled, setPullRequestAutomationEnabled] = useState(false);
  const [pullRequestAutomationLoading, setPullRequestAutomationLoading] = useState(false);
  const [pullRequestAutomationError, setPullRequestAutomationError] = useState('');

  // Milestone 2: Commit Selection & Comparison State
  const [baseCommit, setBaseCommit] = useState('');
  const [headCommit, setHeadCommit] = useState('');
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState('');
  const [compareResult, setCompareResult] = useState(null);
  const [selectedFileIndex, setSelectedFileIndex] = useState(0);

  // Milestone 3: Python AST Code Analysis State
  const [astLoading, setAstLoading] = useState(false);
  const [astError, setAstError] = useState('');
  const [astResult, setAstResult] = useState(null);

  // Milestone 4: Documentation Parsing & Code Mapping State
  const [docLoading, setDocLoading] = useState(false);
  const [docError, setDocError] = useState('');
  const [docResult, setDocResult] = useState(null);
  const [docFilter, setDocFilter] = useState('ALL');
  const [expandedMappings, setExpandedMappings] = useState({});

  // Milestone 5: Documentation Drift Detection State
  const [driftLoading, setDriftLoading] = useState(false);
  const [driftError, setDriftError] = useState('');
  const [driftJob, setDriftJob] = useState(null);
  const [driftCancelLoading, setDriftCancelLoading] = useState(false);
  const [driftResult, setDriftResult] = useState(null);
  const [driftStatusFilter, setDriftStatusFilter] = useState('ALL');
  const [driftSeverityFilter, setDriftSeverityFilter] = useState('ALL');
  const [expandedFindings, setExpandedFindings] = useState({});

  // AI explanation and documentation-fix suggestion state
  const [selectedAiProvider, setSelectedAiProvider] = useState('mock');
  const [aiExplanationsById, setAiExplanationsById] = useState({});
  const [aiLoadingById, setAiLoadingById] = useState({});
  const [aiErrorById, setAiErrorById] = useState({});
  const [aiFocusModeById, setAiFocusModeById] = useState({});
  const [copiedFindingId, setCopiedFindingId] = useState(null);

  // Reusable request guard hook cancelling superseded requests and preventing stale responses
  const requestGuard = useRequestGuard();

  useEffect(() => {
    if (!authSession) {
      setGitHubAppStatus(null);
      setAuthorizedRepositories([]);
      setSelectedRepositoryId('');
      setGitHubAppError('');
      setCatalogLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    const loadGitHubAppCatalog = async () => {
      setCatalogLoading(true);
      setGitHubAppError('');
      try {
        const status = await fetchGitHubAppStatus({
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setGitHubAppStatus(status);
        if (status.configured && status.connected) {
          const catalog = await fetchAuthorizedRepositories({
            signal: controller.signal,
          });
          if (controller.signal.aborted) return;
          setAuthorizedRepositories(catalog.repositories || []);
        } else {
          setAuthorizedRepositories([]);
          setSelectedRepositoryId('');
        }
      } catch (error) {
        if (error?.name === 'AbortError') return;
        setGitHubAppError(
          error instanceof Error
            ? error.message
            : 'Could not load authorized GitHub repositories.'
        );
      } finally {
        if (!controller.signal.aborted) setCatalogLoading(false);
      }
    };

    loadGitHubAppCatalog();
    return () => controller.abort();
  }, [authSession]);

  useEffect(() => {
    if (!repoInfo || !selectedRepositoryId) {
      setPullRequests([]);
      setPullRequestsLoading(false);
      setPullRequestsError('');
      setSelectedPullRequest('');
      return undefined;
    }

    const controller = new AbortController();
    setPullRequestsLoading(true);
    setPullRequestsError('');
    fetchRepositoryPullRequests(Number(selectedRepositoryId), {
      signal: controller.signal,
    })
      .then((response) => {
        if (!controller.signal.aborted) {
          setPullRequests(response.pull_requests || []);
        }
      })
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError' && !controller.signal.aborted) {
          setPullRequests([]);
          setPullRequestsError(
            requestError?.status === 429
              ? 'GitHub rate limit reached. Pull requests could not be refreshed yet.'
              : requestError instanceof Error
                ? requestError.message
                : 'Could not load authorized pull requests.'
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setPullRequestsLoading(false);
      });

    return () => controller.abort();
  }, [repoInfo, selectedRepositoryId]);

  const resetAnalysisStates = useCallback(() => {
    setCompareLoading(false);
    setCompareError('');
    setCompareResult(null);
    setSelectedFileIndex(0);

    setAstLoading(false);
    setAstError('');
    setAstResult(null);

    setDocLoading(false);
    setDocError('');
    setDocResult(null);
    setExpandedMappings({});

    setDriftLoading(false);
    setDriftError('');
    setDriftJob(null);
    setDriftCancelLoading(false);
    setDriftResult(null);
    setExpandedFindings({});

    setAiExplanationsById({});
    setAiLoadingById({});
    setAiErrorById({});
    setAiFocusModeById({});
  }, []);

  useEffect(() => {
    if (aiProviderInfo?.active_default_provider) {
      setSelectedAiProvider(aiProviderInfo.active_default_provider);
    }
  }, [aiProviderInfo]);

  const handleSelectRepositoryId = (repositoryId) => {
    requestGuard.cancelAll();
    resetAnalysisStates();
    setSelectedRepositoryId(repositoryId);
    setRepoInfo(null);
    setPullRequests([]);
    setSelectedPullRequest('');
    setInspectError('');
  };

  useEffect(() => {
    const repositoryId = Number(selectedRepositoryId);
    if (!Number.isSafeInteger(repositoryId) || repositoryId <= 0) {
      setPullRequestAutomationEnabled(false);
      setPullRequestAutomationError('');
      return;
    }
    const controller = new AbortController();
    setPullRequestAutomationLoading(true);
    setPullRequestAutomationError('');
    fetchPullRequestAutomation(repositoryId, { signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) {
          setPullRequestAutomationEnabled(result.enabled === true);
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setPullRequestAutomationError(
            error instanceof Error ? error.message : 'Could not load PR automation status.'
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setPullRequestAutomationLoading(false);
      });
    return () => controller.abort();
  }, [selectedRepositoryId]);

  const handlePullRequestAutomationChange = async (enabled) => {
    const repositoryId = Number(selectedRepositoryId);
    if (!Number.isSafeInteger(repositoryId) || repositoryId <= 0) return;
    setPullRequestAutomationLoading(true);
    setPullRequestAutomationError('');
    try {
      const result = await updatePullRequestAutomation(repositoryId, enabled);
      setPullRequestAutomationEnabled(result.enabled === true);
    } catch (error) {
      setPullRequestAutomationError(
        error instanceof Error ? error.message : 'Could not update PR automation.'
      );
    } finally {
      setPullRequestAutomationLoading(false);
    }
  };

  const handleConnectGitHubApp = async () => {
    setInstallLoading(true);
    setGitHubAppError('');
    try {
      const response = await createGitHubAppInstallation();
      const target = new URL(response.installation_url);
      if (target.origin !== 'https://github.com') {
        throw new Error('GitHub returned an unsafe installation destination.');
      }
      window.location.assign(target.href);
    } catch (error) {
      setGitHubAppError(
        error instanceof Error
          ? error.message
          : 'Could not start GitHub App installation.'
      );
    } finally {
      setInstallLoading(false);
    }
  };

  const handleBaseCommitChange = (newBaseSha) => {
    setBaseCommit(newBaseSha);
    setSelectedPullRequest('');
    requestGuard.cancelAnalysis();
    resetAnalysisStates();
  };

  const handleHeadCommitChange = (newHeadSha) => {
    setHeadCommit(newHeadSha);
    setSelectedPullRequest('');
    requestGuard.cancelAnalysis();
    resetAnalysisStates();
  };

  const handleSelectPullRequest = (pullRequestNumber) => {
    setSelectedPullRequest(pullRequestNumber);
    if (!pullRequestNumber) return;
    const pullRequest = pullRequests.find(
      (item) => String(item.number) === pullRequestNumber
    );
    if (!pullRequest) return;
    requestGuard.cancelAnalysis();
    resetAnalysisStates();
    setBaseCommit(pullRequest.base_sha);
    setHeadCommit(pullRequest.head_sha);
  };

  const handleConnectRepository = async (event) => {
    event.preventDefault();
    const githubRepositoryId = Number(selectedRepositoryId);
    if (!Number.isSafeInteger(githubRepositoryId) || githubRepositoryId <= 0) {
      setInspectError('Select a repository authorized for this workspace.');
      return;
    }

    // Cancel all in-flight repository/analysis requests before inspecting new repository
    requestGuard.cancelAll();
    resetAnalysisStates();

    const request = requestGuard.start('inspect');
    setInspectLoading(true);
    setInspectError('');

    try {
      const data = await inspectRepository(githubRepositoryId, {
        signal: request.signal,
      });
      if (!request.isCurrent()) return;

      setRepoInfo(data);
      setSelectedPullRequest('');
      if (Array.isArray(data.commits) && data.commits.length >= 2) {
        setHeadCommit(data.commits[0].sha);
        setBaseCommit(data.commits[1].sha);
      } else if (Array.isArray(data.commits) && data.commits.length === 1) {
        setHeadCommit(data.commits[0].sha);
        setBaseCommit(data.commits[0].sha);
      } else {
        setHeadCommit('');
        setBaseCommit('');
      }
    } catch (err) {
      if (isRequestCancelledError(err) || !request.isCurrent()) return;
      setRepoInfo(null);
      setBaseCommit('');
      setHeadCommit('');
      setInspectError(
        err instanceof Error
          ? err.message
          : 'Failed to inspect the authorized repository.'
      );
    } finally {
      if (request.isCurrent()) {
        setInspectLoading(false);
      }
      request.finish();
    }
  };

  const canCompare =
    Boolean(repoInfo) &&
    Boolean(selectedRepositoryId) &&
    Boolean(baseCommit) &&
    Boolean(headCommit) &&
    baseCommit !== headCommit &&
    !compareLoading &&
    !astLoading &&
    !docLoading &&
    !driftLoading &&
    !inspectLoading;

  const canAnalyzeDocs =
    Boolean(repoInfo) &&
    Boolean(selectedRepositoryId) &&
    Boolean(headCommit) &&
    !compareLoading &&
    !astLoading &&
    !docLoading &&
    !driftLoading &&
    !inspectLoading;

  const handleCompareCommits = async (event) => {
    event.preventDefault();
    if (!canCompare) return;

    const request = requestGuard.start('compare');
    setCompareLoading(true);
    setCompareError('');
    setCompareResult(null);
    setSelectedFileIndex(0);

    try {
      const result = await compareRepositoryCommits({
        githubRepositoryId: Number(selectedRepositoryId),
        baseCommit,
        headCommit,
        signal: request.signal,
      });
      if (!request.isCurrent()) return;
      setCompareResult(result);
      setSelectedFileIndex(0);
    } catch (err) {
      if (isRequestCancelledError(err) || !request.isCurrent()) return;
      setCompareResult(null);
      setCompareError(
        err instanceof Error
          ? err.message
          : 'Failed to compare the selected commits.'
      );
    } finally {
      if (request.isCurrent()) {
        setCompareLoading(false);
      }
      request.finish();
    }
  };

  const handleAnalyzePythonChanges = async () => {
    if (!canCompare) return;

    const request = requestGuard.start('ast');
    setAstLoading(true);
    setAstError('');
    setAstResult(null);

    try {
      const result = await analyzePythonCodeChanges({
        githubRepositoryId: Number(selectedRepositoryId),
        baseCommit,
        headCommit,
        signal: request.signal,
      });
      if (!request.isCurrent()) return;
      setAstResult(result);
    } catch (err) {
      if (isRequestCancelledError(err) || !request.isCurrent()) return;
      setAstResult(null);
      setAstError(
        err instanceof Error
          ? err.message
          : 'Failed to analyze Python AST changes between the selected commits.'
      );
    } finally {
      if (request.isCurrent()) {
        setAstLoading(false);
      }
      request.finish();
    }
  };

  const handleAnalyzeDocumentation = async () => {
    if (!canAnalyzeDocs) return;

    const request = requestGuard.start('docs');
    setDocLoading(true);
    setDocError('');
    setDocResult(null);
    setExpandedMappings({});

    try {
      const result = await analyzeRepositoryDocumentation({
        githubRepositoryId: Number(selectedRepositoryId),
        baseCommit,
        headCommit,
        signal: request.signal,
      });
      if (!request.isCurrent()) return;
      setDocResult(result);
    } catch (err) {
      if (isRequestCancelledError(err) || !request.isCurrent()) return;
      setDocResult(null);
      setDocError(
        err instanceof Error
          ? err.message
          : 'Failed to parse and map repository documentation.'
      );
    } finally {
      if (request.isCurrent()) {
        setDocLoading(false);
      }
      request.finish();
    }
  };

  const toggleMappingExpanded = (mappingId) => {
    setExpandedMappings((prev) => ({
      ...prev,
      [mappingId]: !prev[mappingId],
    }));
  };

  const handleAnalyzeDrift = async () => {
    if (!canCompare) return;

    const request = requestGuard.start('drift');
    setDriftLoading(true);
    setDriftError('');
    setDriftJob(null);
    setDriftResult(null);
    setExpandedFindings({});
    setAiExplanationsById({});
    setAiLoadingById({});
    setAiErrorById({});

    try {
      const result = await analyzeDocumentationDrift({
        githubRepositoryId: Number(selectedRepositoryId),
        baseCommit,
        headCommit,
        idempotencyKey: globalThis.crypto?.randomUUID?.(),
        signal: request.signal,
      });
      if (!request.isCurrent()) return;
      setDriftJob(result);

      let job = result;
      while (job.status === 'queued' || job.status === 'running') {
        await waitForPollingInterval(1500, request.signal);
        job = await fetchAnalysisStatus(job.analysis_id, {
          signal: request.signal,
        });
        if (!request.isCurrent()) return;
        setDriftJob(job);
      }

      if (job.status === 'succeeded') {
        const detail = await fetchAnalysisDetail(job.analysis_id, {
          signal: request.signal,
        });
        if (!request.isCurrent()) return;
        setDriftResult(detail);
      } else if (job.status === 'failed') {
        setDriftError(
          `Analysis failed (${job.error_category || 'analysis_failed'}).`
        );
      } else if (job.status === 'cancelled') {
        setDriftError('Analysis was cancelled.');
      }
    } catch (err) {
      if (isRequestCancelledError(err) || !request.isCurrent()) return;
      setDriftResult(null);
      setDriftError(
        err instanceof Error
          ? err.message
          : 'Failed to run documentation drift detection.'
      );
    } finally {
      if (request.isCurrent()) {
        setDriftLoading(false);
      }
      request.finish();
    }
  };

  const handleCancelDrift = async () => {
    if (!driftJob?.analysis_id || driftCancelLoading) return;
    setDriftCancelLoading(true);
    setDriftError('');
    try {
      const job = await cancelAnalysis(driftJob.analysis_id);
      setDriftJob(job);
      if (job.status === 'cancelled') {
        setDriftLoading(false);
        setDriftError('Analysis was cancelled.');
      }
    } catch (error) {
      setDriftError(
        error instanceof Error
          ? error.message
          : 'Could not request analysis cancellation.'
      );
    } finally {
      setDriftCancelLoading(false);
    }
  };

  const toggleFindingExpanded = (findingId) => {
    setExpandedFindings((prev) => ({
      ...prev,
      [findingId]: !prev[findingId],
    }));
  };

  const handleRequestFindingAI = async (finding, focusMode = 'explain') => {
    if (!finding || !driftResult) return;
    const fid = finding.finding_id;
    const request = requestGuard.start(`ai:${fid}`);

    setAiFocusModeById((prev) => ({ ...prev, [fid]: focusMode }));
    setAiLoadingById((prev) => ({ ...prev, [fid]: true }));
    setAiErrorById((prev) => ({ ...prev, [fid]: '' }));

    try {
      const response = await generateFindingAIExplanations({
        analysisId: driftResult.analysis_id,
        provider: selectedAiProvider,
        findingIds: [fid],
        signal: request.signal,
      });
      if (!request.isCurrent()) return;

      const generated = response?.explanations?.[0];
      if (generated) {
        setAiExplanationsById((prev) => ({ ...prev, [fid]: generated }));
      } else {
        setAiErrorById((prev) => ({
          ...prev,
          [fid]: 'No explanation was returned for this finding.',
        }));
      }
    } catch (err) {
      if (isRequestCancelledError(err) || !request.isCurrent()) return;
      setAiErrorById((prev) => ({
        ...prev,
        [fid]:
          err instanceof Error
            ? err.message
            : 'AI provider failed to generate explanation.',
      }));
    } finally {
      if (request.isCurrent()) {
        setAiLoadingById((prev) => ({ ...prev, [fid]: false }));
      }
      request.finish();
    }
  };

  const handleDismissAiError = (findingId) => {
    setAiErrorById((prev) => ({ ...prev, [findingId]: '' }));
  };

  const handleCopySuggestion = async (findingId, text) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopiedFindingId(findingId);
      setTimeout(() => {
        setCopiedFindingId((prev) => (prev === findingId ? null : prev));
      }, 2000);
    } catch {
      setCopiedFindingId(null);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 text-slate-100 sm:p-6">
      <header className="flex flex-col gap-3 border-b border-slate-800 pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-white">
            Repository analysis
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Compare authorized repository commits and review persisted drift findings.
          </p>
        </div>
        <button
          type="button"
          onClick={checkBackendHealth}
          className="self-start rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-700 sm:self-auto"
        >
          Refresh service status
        </button>
      </header>

      <p className="rounded-lg border border-indigo-500/20 bg-indigo-500/5 p-3 text-xs leading-relaxed text-slate-300" role="note">
        Analysis reads repository source without executing it. Only bounded evidence
        is persisted; selected evidence is sent to Google Gemini only when you
        explicitly request a Gemini explanation.
      </p>

          {/* Dashboard Overview Cards */}
          <section
            aria-label="Dashboard Overview"
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
          >
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
              <p className="mt-1 text-xs text-slate-400 font-mono">GET /api/health</p>
            </div>

            <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                Connected Repository
              </p>
              <p className="mt-2 text-lg font-bold text-white truncate">
                {repoInfo ? `${repoInfo.owner}/${repoInfo.name}` : 'None connected'}
              </p>
              <p className="mt-1 text-xs text-slate-400 font-mono">
                {repoInfo
                  ? `Branch: ${repoInfo.default_branch} (${repoInfo.commits.length} commits)`
                  : 'Select from the authorized repository catalog'}
              </p>
            </div>

            <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                Comparison Status
              </p>
              <p className="mt-2 text-lg font-bold text-indigo-300">
                {compareLoading
                  ? 'Comparing...'
                  : compareResult
                  ? `${compareResult.total_changed_files} Files Changed`
                  : inspectLoading
                  ? 'Inspecting Repo...'
                  : repoInfo
                  ? 'Ready to Compare'
                  : 'Idle'}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                {compareResult
                  ? `+${compareResult.total_additions} / -${compareResult.total_deletions} lines`
                  : 'Workspace-authorized GitHub access'}
              </p>
            </div>

            <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                Python AST Analysis
              </p>
              <p className="mt-2 text-lg font-bold text-white">
                {astLoading
                  ? 'Analyzing AST...'
                  : astResult
                  ? `${astResult.summary.total_symbol_changes} Symbol Changes`
                  : 'Not Run Yet'}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                {astResult
                  ? `${astResult.summary.analyzed_python_files_count} Python files analyzed`
                  : 'Milestone 3 Static AST Engine'}
              </p>
            </div>
          </section>

          {/* 1. Repository Connection & Commit Selection */}
          <RepositoryConnectionSection
            repositories={authorizedRepositories}
            selectedRepositoryId={selectedRepositoryId}
            onSelectRepositoryId={handleSelectRepositoryId}
            catalogLoading={catalogLoading}
            githubAppConfigured={githubAppStatus?.configured === true}
            githubAppConnected={githubAppStatus?.connected === true}
            githubAppError={githubAppError}
            onConnectGitHubApp={handleConnectGitHubApp}
            installLoading={installLoading}
            inspectLoading={inspectLoading}
            inspectError={inspectError}
            onDismissInspectError={() => setInspectError('')}
            onConnectRepository={handleConnectRepository}
            repoInfo={repoInfo}
            pullRequests={pullRequests}
            pullRequestsLoading={pullRequestsLoading}
            pullRequestsError={pullRequestsError}
            pullRequestAutomationEnabled={pullRequestAutomationEnabled}
            pullRequestAutomationLoading={pullRequestAutomationLoading}
            pullRequestAutomationError={pullRequestAutomationError}
            onPullRequestAutomationChange={handlePullRequestAutomationChange}
            selectedPullRequest={selectedPullRequest}
            onSelectPullRequest={handleSelectPullRequest}
            baseCommit={baseCommit}
            headCommit={headCommit}
            onBaseCommitChange={handleBaseCommitChange}
            onHeadCommitChange={handleHeadCommitChange}
            canCompare={canCompare}
            canAnalyzeDocs={canAnalyzeDocs}
            compareLoading={compareLoading}
            compareError={compareError}
            onDismissCompareError={() => setCompareError('')}
            compareResult={compareResult}
            astLoading={astLoading}
            docLoading={docLoading}
            driftLoading={driftLoading}
            onCompareCommits={handleCompareCommits}
            onAnalyzePythonChanges={handleAnalyzePythonChanges}
            onAnalyzeDocumentation={handleAnalyzeDocumentation}
            onAnalyzeDrift={handleAnalyzeDrift}
            healthState={healthState}
            healthData={healthData}
            healthError={healthError}
          />

          {/* 2. Commit Comparison & Diff Viewer */}
          <CommitComparisonSection
            compareResult={compareResult}
            selectedFileIndex={selectedFileIndex}
            onSelectFileIndex={setSelectedFileIndex}
          />

          {/* 3. Python AST Code Analysis */}
          <PythonAstAnalysisSection
            repoInfo={repoInfo}
            baseCommit={baseCommit}
            headCommit={headCommit}
            canCompare={canCompare}
            astLoading={astLoading}
            astError={astError}
            onDismissAstError={() => setAstError('')}
            astResult={astResult}
            onAnalyzePythonChanges={handleAnalyzePythonChanges}
          />

          {/* 4. Documentation Map */}
          <DocumentationMapSection
            repoInfo={repoInfo}
            headCommit={headCommit}
            canAnalyzeDocs={canAnalyzeDocs}
            docLoading={docLoading}
            docError={docError}
            onDismissDocError={() => setDocError('')}
            docResult={docResult}
            docFilter={docFilter}
            onDocFilterChange={setDocFilter}
            expandedMappings={expandedMappings}
            onToggleMappingExpanded={toggleMappingExpanded}
            onAnalyzeDocumentation={handleAnalyzeDocumentation}
          />

          {/* 5. Documentation Drift Findings & AI Explanations */}
          <DriftFindingsSection
            healthState={healthState}
            baseCommit={baseCommit}
            headCommit={headCommit}
            canCompare={canCompare}
            driftLoading={driftLoading}
            driftError={driftError}
            driftJob={driftJob}
            driftCancelLoading={driftCancelLoading}
            onDismissDriftError={() => setDriftError('')}
            driftResult={driftResult}
            driftStatusFilter={driftStatusFilter}
            onDriftStatusFilterChange={setDriftStatusFilter}
            driftSeverityFilter={driftSeverityFilter}
            onDriftSeverityFilterChange={setDriftSeverityFilter}
            expandedFindings={expandedFindings}
            onToggleFindingExpanded={toggleFindingExpanded}
            onAnalyzeDrift={handleAnalyzeDrift}
            onCancelDrift={handleCancelDrift}
            aiProviderInfo={aiProviderInfo}
            selectedAiProvider={selectedAiProvider}
            onSelectAiProvider={setSelectedAiProvider}
            aiExplanationsById={aiExplanationsById}
            aiLoadingById={aiLoadingById}
            aiErrorById={aiErrorById}
            onDismissAiError={handleDismissAiError}
            aiFocusModeById={aiFocusModeById}
            onRequestFindingAI={handleRequestFindingAI}
            copiedFindingId={copiedFindingId}
            onCopySuggestion={handleCopySuggestion}
          />
    </div>
  );
}
