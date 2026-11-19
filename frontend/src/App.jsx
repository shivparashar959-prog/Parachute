import { useEffect, useState, useCallback } from 'react';
import {
  fetchBackendHealth,
  inspectRepository,
  compareRepositoryCommits,
  analyzePythonCodeChanges,
  analyzeRepositoryDocumentation,
  analyzeDocumentationDrift,
  fetchAIProviderStatus,
  generateFindingAIExplanations,
  isRequestCancelledError,
} from './api/health';
import { useRequestGuard } from './hooks/useRequestGuard';
import Sidebar from './components/Sidebar';
import RepositoryConnectionSection from './components/RepositoryConnectionSection';
import CommitComparisonSection from './components/CommitComparisonSection';
import PythonAstAnalysisSection from './components/PythonAstAnalysisSection';
import DocumentationMapSection from './components/DocumentationMapSection';
import DriftFindingsSection from './components/DriftFindingsSection';

export default function App() {
  // Live backend health state ('checking' | 'connected' | 'disconnected')
  const [healthState, setHealthState] = useState('checking');
  const [healthData, setHealthData] = useState(null);
  const [healthError, setHealthError] = useState('');
  const [lastChecked, setLastChecked] = useState(null);

  // Milestone 2: Repository Inspection State
  const [repoUrl, setRepoUrl] = useState('https://github.com/pallets/flask');
  const [inspectLoading, setInspectLoading] = useState(false);
  const [inspectError, setInspectError] = useState('');
  const [repoInfo, setRepoInfo] = useState(null);

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
  const [driftResult, setDriftResult] = useState(null);
  const [driftStatusFilter, setDriftStatusFilter] = useState('ALL');
  const [driftSeverityFilter, setDriftSeverityFilter] = useState('ALL');
  const [expandedFindings, setExpandedFindings] = useState({});

  // Milestone 6: AI Explanations & Documentation Fix Suggestions State
  const [aiProviderInfo, setAiProviderInfo] = useState(null);
  const [selectedAiProvider, setSelectedAiProvider] = useState('mock');
  const [aiExplanationsById, setAiExplanationsById] = useState({});
  const [aiLoadingById, setAiLoadingById] = useState({});
  const [aiErrorById, setAiErrorById] = useState({});
  const [aiFocusModeById, setAiFocusModeById] = useState({});
  const [copiedFindingId, setCopiedFindingId] = useState(null);

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Reusable request guard hook cancelling superseded requests and preventing stale responses
  const requestGuard = useRequestGuard();

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
    setDriftResult(null);
    setExpandedFindings({});

    setAiExplanationsById({});
    setAiLoadingById({});
    setAiErrorById({});
    setAiFocusModeById({});
  }, []);

  const checkBackendHealth = useCallback(async () => {
    const request = requestGuard.start('health');
    setHealthState('checking');
    setHealthError('');
    try {
      const data = await fetchBackendHealth({ signal: request.signal });
      if (!request.isCurrent()) return;

      if (data && data.status === 'ok') {
        setHealthData(data);
        setHealthState('connected');
        try {
          const provStatus = await fetchAIProviderStatus({
            signal: request.signal,
          });
          if (!request.isCurrent()) return;
          setAiProviderInfo(provStatus);
          if (provStatus?.active_default_provider) {
            setSelectedAiProvider(provStatus.active_default_provider);
          }
        } catch (provErr) {
          if (isRequestCancelledError(provErr) || !request.isCurrent()) return;
          setAiProviderInfo(null);
        }
      } else {
        setHealthData(data);
        setHealthState('disconnected');
        setHealthError('Unexpected response format from /api/health');
      }
    } catch (err) {
      if (isRequestCancelledError(err) || !request.isCurrent()) return;
      setHealthData(null);
      setHealthState('disconnected');
      setHealthError(
        err instanceof Error
          ? err.message
          : 'Unable to reach FastAPI server at /api/health'
      );
    } finally {
      if (request.isCurrent()) {
        setLastChecked(new Date().toLocaleTimeString());
      }
      request.finish();
    }
  }, [requestGuard]);

  useEffect(() => {
    checkBackendHealth();
  }, [checkBackendHealth]);

  const handleSelectPresetUrl = (presetUrl) => {
    setRepoUrl(presetUrl);
    setInspectError('');
  };

  const handleBaseCommitChange = (newBaseSha) => {
    setBaseCommit(newBaseSha);
    requestGuard.cancelAnalysis();
    resetAnalysisStates();
  };

  const handleHeadCommitChange = (newHeadSha) => {
    setHeadCommit(newHeadSha);
    requestGuard.cancelAnalysis();
    resetAnalysisStates();
  };

  const handleConnectRepository = async (event) => {
    event.preventDefault();
    const trimmedUrl = repoUrl.trim();
    if (!trimmedUrl) {
      setInspectError('Please enter a public HTTPS GitHub repository URL.');
      return;
    }

    // Cancel all in-flight repository/analysis requests before inspecting new repository
    requestGuard.cancelAll();
    resetAnalysisStates();

    const request = requestGuard.start('inspect');
    setInspectLoading(true);
    setInspectError('');

    try {
      const data = await inspectRepository(trimmedUrl, {
        signal: request.signal,
      });
      if (!request.isCurrent()) return;

      setRepoInfo(data);
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
          : 'Failed to inspect repository. Ensure the URL points to a valid public GitHub repository.'
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
        repositoryUrl: repoInfo.repository_url || repoUrl.trim(),
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
        repositoryUrl: repoInfo.repository_url || repoUrl.trim(),
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
        repositoryUrl: repoInfo.repository_url || repoUrl.trim(),
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
    setDriftResult(null);
    setExpandedFindings({});
    setAiExplanationsById({});
    setAiLoadingById({});
    setAiErrorById({});

    try {
      const result = await analyzeDocumentationDrift({
        repositoryUrl: repoInfo.repository_url || repoUrl.trim(),
        baseCommit,
        headCommit,
        signal: request.signal,
      });
      if (!request.isCurrent()) return;
      setDriftResult(result);
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
        repositoryUrl:
          driftResult.repository_url ||
          repoInfo?.repository_url ||
          repoUrl.trim(),
        baseCommit: driftResult.base_commit || baseCommit,
        headCommit: driftResult.head_commit || headCommit,
        provider: selectedAiProvider,
        findingIds: [fid],
        findings: [finding],
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
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col lg:flex-row">
      <Sidebar
        mobileMenuOpen={mobileMenuOpen}
        setMobileMenuOpen={setMobileMenuOpen}
        healthState={healthState}
        healthData={healthData}
        healthError={healthError}
        lastChecked={lastChecked}
        onRefreshHealth={checkBackendHealth}
      />

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto">
        {/* Top Utility Header */}
        <div className="border-b border-slate-800 bg-slate-900/40 px-6 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              Documentation Drift Dashboard
            </h2>
            <p className="text-sm text-slate-400">
              Connect a public GitHub repository, inspect commits, and analyze actual code diffs.
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
                  : 'Enter a GitHub URL below'}
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
                  : 'Milestone 2 Git Integration'}
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
            repoUrl={repoUrl}
            onRepoUrlChange={setRepoUrl}
            onSelectPresetUrl={handleSelectPresetUrl}
            inspectLoading={inspectLoading}
            inspectError={inspectError}
            onDismissInspectError={() => setInspectError('')}
            onConnectRepository={handleConnectRepository}
            repoInfo={repoInfo}
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
            onDismissDriftError={() => setDriftError('')}
            driftResult={driftResult}
            driftStatusFilter={driftStatusFilter}
            onDriftStatusFilterChange={setDriftStatusFilter}
            driftSeverityFilter={driftSeverityFilter}
            onDriftSeverityFilterChange={setDriftSeverityFilter}
            expandedFindings={expandedFindings}
            onToggleFindingExpanded={toggleFindingExpanded}
            onAnalyzeDrift={handleAnalyzeDrift}
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
      </main>
    </div>
  );
}
