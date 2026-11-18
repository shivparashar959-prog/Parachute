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
} from './api/health';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard Overview', badge: 'Active', active: true },
  { id: 'analysis', label: 'Repository Diff', badge: 'Active (M2)', active: true },
  { id: 'ast', label: 'Python AST Analysis', badge: 'Active (M3)', active: true },
  { id: 'docs', label: 'Documentation Map', badge: 'Active (M4)', active: true },
  { id: 'findings', label: 'Drift Findings', badge: 'Active (M5)', active: true },
  { id: 'ai', label: 'AI Explanations', badge: 'Active (M6)', active: true },
];

const DRIFT_STATUS_TABS = [
  { id: 'ALL', label: 'All Findings' },
  { id: 'CONFIRMED_DRIFT', label: 'Confirmed Drift' },
  { id: 'POTENTIAL_DRIFT', label: 'Potential Drift' },
  { id: 'UNCERTAIN', label: 'Uncertain' },
  { id: 'RESOLVED', label: 'Resolved' },
];

const DRIFT_SEVERITY_OPTIONS = [
  { id: 'ALL', label: 'All Severities' },
  { id: 'CRITICAL', label: 'Critical' },
  { id: 'HIGH', label: 'High' },
  { id: 'MEDIUM', label: 'Medium' },
  { id: 'LOW', label: 'Low' },
];

const DRIFT_STATUS_STYLES = {
  CONFIRMED_DRIFT: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
  POTENTIAL_DRIFT: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  UNCERTAIN: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/40',
  RESOLVED: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  UNCHANGED: 'bg-slate-800 text-slate-400 border-slate-700',
};

const DRIFT_SEVERITY_STYLES = {
  CRITICAL: 'bg-rose-600/20 text-rose-200 border-rose-500/50',
  HIGH: 'bg-amber-500/20 text-amber-200 border-amber-500/40',
  MEDIUM: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  LOW: 'bg-slate-800 text-slate-300 border-slate-700',
};

const DOC_FILTER_TABS = [
  { id: 'ALL', label: 'All Mappings' },
  { id: 'HIGH', label: 'High Confidence' },
  { id: 'MEDIUM', label: 'Medium Confidence' },
  { id: 'LOW', label: 'Low Confidence' },
  { id: 'AMBIGUOUS', label: 'Ambiguous' },
  { id: 'UNMAPPED', label: 'Unmapped' },
];

const CONFIDENCE_BADGE_STYLES = {
  HIGH: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  MEDIUM: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  LOW: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
};

const MAPPING_STATUS_STYLES = {
  MAPPED: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  AMBIGUOUS: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  UNMAPPED: 'bg-slate-800 text-slate-400 border-slate-700',
};

const CHANGE_BADGE_STYLES = {
  added: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  modified: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  deleted: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  renamed: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
};

function getAstChangeBadgeStyle(changeType) {
  if (!changeType) return 'bg-slate-800 text-slate-300 border-slate-700';
  if (changeType.endsWith('_ADDED')) {
    return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
  }
  if (changeType.endsWith('_REMOVED')) {
    return 'bg-rose-500/15 text-rose-300 border-rose-500/30';
  }
  if (changeType.endsWith('_RENAMED') || changeType.endsWith('_REORDERED')) {
    return 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30';
  }
  return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
}

function formatCommitTimestamp(isoString) {
  if (!isoString) return '';
  try {
    const dt = new Date(isoString);
    return dt.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoString;
  }
}

function DiffLinesView({ patch, isBinary }) {
  if (isBinary) {
    return (
      <div className="p-6 text-center text-xs text-slate-400 font-mono">
        Binary file changed — text diff preview is not available.
      </div>
    );
  }

  if (!patch || !patch.trim()) {
    return (
      <div className="p-6 text-center text-xs text-slate-400 font-mono">
        No line-level textual differences for this file (e.g., pure file rename or mode change).
      </div>
    );
  }

  const lines = patch.split('\n');

  return (
    <div className="overflow-x-auto font-mono text-xs leading-relaxed">
      {lines.map((line, index) => {
        const isAddition = line.startsWith('+') && !line.startsWith('+++');
        const isDeletion = line.startsWith('-') && !line.startsWith('---');
        const isHunkHeader = line.startsWith('@@');

        let rowClass = 'text-slate-300 hover:bg-slate-900/60';
        if (isAddition) {
          rowClass =
            'bg-emerald-500/15 text-emerald-200 border-l-2 border-emerald-400';
        } else if (isDeletion) {
          rowClass =
            'bg-rose-500/15 text-rose-200 border-l-2 border-rose-400';
        } else if (isHunkHeader) {
          rowClass = 'bg-indigo-500/10 text-indigo-300 font-semibold';
        }

        return (
          <div
            key={index}
            className={`px-4 py-0.5 whitespace-pre flex items-start gap-3 ${rowClass}`}
          >
            <span className="w-9 shrink-0 select-none text-right text-[10px] text-slate-500 pr-2 border-r border-slate-800/80">
              {index + 1}
            </span>
            <span className="flex-1">{line || ' '}</span>
          </div>
        );
      })}
    </div>
  );
}

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

  const checkBackendHealth = useCallback(async () => {
    setHealthState('checking');
    setHealthError('');
    try {
      const data = await fetchBackendHealth();
      if (data && data.status === 'ok') {
        setHealthData(data);
        setHealthState('connected');
        try {
          const provStatus = await fetchAIProviderStatus();
          setAiProviderInfo(provStatus);
          if (provStatus?.active_default_provider) {
            setSelectedAiProvider(provStatus.active_default_provider);
          }
        } catch {
          setAiProviderInfo(null);
        }
      } else {
        setHealthData(data);
        setHealthState('disconnected');
        setHealthError('Unexpected response format from /api/health');
      }
    } catch (err) {
      setHealthData(null);
      setHealthState('disconnected');
      setHealthError(
        err instanceof Error
          ? err.message
          : 'Unable to reach FastAPI server at /api/health'
      );
    } finally {
      setLastChecked(new Date().toLocaleTimeString());
    }
  }, []);

  useEffect(() => {
    checkBackendHealth();
  }, [checkBackendHealth]);

  const handleConnectRepository = async (event) => {
    event.preventDefault();
    const trimmedUrl = repoUrl.trim();
    if (!trimmedUrl) {
      setInspectError('Please enter a public HTTPS GitHub repository URL.');
      return;
    }

    setInspectLoading(true);
    setInspectError('');
    setCompareError('');
    setCompareResult(null);
    setAstError('');
    setAstResult(null);
    setDocError('');
    setDocResult(null);
    setExpandedMappings({});
    setDriftError('');
    setDriftResult(null);
    setExpandedFindings({});
    setAiExplanationsById({});
    setAiLoadingById({});
    setAiErrorById({});
    setSelectedFileIndex(0);

    try {
      const data = await inspectRepository(trimmedUrl);
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
      setRepoInfo(null);
      setBaseCommit('');
      setHeadCommit('');
      setInspectError(
        err instanceof Error
          ? err.message
          : 'Failed to inspect repository. Ensure the URL points to a valid public GitHub repository.'
      );
    } finally {
      setInspectLoading(false);
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

    setCompareLoading(true);
    setCompareError('');
    setCompareResult(null);
    setSelectedFileIndex(0);

    try {
      const result = await compareRepositoryCommits({
        repositoryUrl: repoInfo.repository_url || repoUrl.trim(),
        baseCommit,
        headCommit,
      });
      setCompareResult(result);
      setSelectedFileIndex(0);
    } catch (err) {
      setCompareResult(null);
      setCompareError(
        err instanceof Error
          ? err.message
          : 'Failed to compare the selected commits.'
      );
    } finally {
      setCompareLoading(false);
    }
  };

  const handleAnalyzePythonChanges = async () => {
    if (!canCompare) return;

    setAstLoading(true);
    setAstError('');
    setAstResult(null);

    try {
      const result = await analyzePythonCodeChanges({
        repositoryUrl: repoInfo.repository_url || repoUrl.trim(),
        baseCommit,
        headCommit,
      });
      setAstResult(result);
    } catch (err) {
      setAstResult(null);
      setAstError(
        err instanceof Error
          ? err.message
          : 'Failed to analyze Python AST changes between the selected commits.'
      );
    } finally {
      setAstLoading(false);
    }
  };

  const handleAnalyzeDocumentation = async () => {
    if (!canAnalyzeDocs) return;

    setDocLoading(true);
    setDocError('');
    setDocResult(null);
    setExpandedMappings({});

    try {
      const result = await analyzeRepositoryDocumentation({
        repositoryUrl: repoInfo.repository_url || repoUrl.trim(),
        baseCommit,
        headCommit,
      });
      setDocResult(result);
    } catch (err) {
      setDocResult(null);
      setDocError(
        err instanceof Error
          ? err.message
          : 'Failed to parse and map repository documentation.'
      );
    } finally {
      setDocLoading(false);
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
      });
      setDriftResult(result);
    } catch (err) {
      setDriftResult(null);
      setDriftError(
        err instanceof Error
          ? err.message
          : 'Failed to run documentation drift detection.'
      );
    } finally {
      setDriftLoading(false);
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

    setAiFocusModeById((prev) => ({ ...prev, [fid]: focusMode }));
    setAiLoadingById((prev) => ({ ...prev, [fid]: true }));
    setAiErrorById((prev) => ({ ...prev, [fid]: '' }));

    try {
      const response = await generateFindingAIExplanations({
        repositoryUrl: driftResult.repository_url || repoInfo?.repository_url || repoUrl.trim(),
        baseCommit: driftResult.base_commit || baseCommit,
        headCommit: driftResult.head_commit || headCommit,
        provider: selectedAiProvider,
        findingIds: [fid],
        findings: [finding],
      });

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
      setAiErrorById((prev) => ({
        ...prev,
        [fid]:
          err instanceof Error
            ? err.message
            : 'AI provider failed to generate explanation.',
      }));
    } finally {
      setAiLoadingById((prev) => ({ ...prev, [fid]: false }));
    }
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
      // Fallback if clipboard API is restricted
      setCopiedFindingId(null);
    }
  };

  const filteredDriftFindings = (driftResult?.findings || []).filter((f) => {
    if (driftStatusFilter !== 'ALL' && f.status !== driftStatusFilter) {
      return false;
    }
    if (driftSeverityFilter !== 'ALL' && f.severity !== driftSeverityFilter) {
      return false;
    }
    return true;
  });

  const filteredDocMappings = (docResult?.mappings || []).filter((m) => {
    if (docFilter === 'ALL') return true;
    if (docFilter === 'UNMAPPED') return m.mapping_status === 'UNMAPPED';
    if (docFilter === 'AMBIGUOUS') return m.mapping_status === 'AMBIGUOUS';
    if (docFilter === 'HIGH') return m.highest_confidence === 'HIGH';
    if (docFilter === 'MEDIUM') return m.highest_confidence === 'MEDIUM';
    if (docFilter === 'LOW') return m.highest_confidence === 'LOW';
    return true;
  });

  const selectedFile =
    compareResult?.files && compareResult.files[selectedFileIndex]
      ? compareResult.files[selectedFileIndex]
      : null;

  const selectedBaseCommitObj = repoInfo?.commits?.find(
    (c) => c.sha === baseCommit
  );
  const selectedHeadCommitObj = repoInfo?.commits?.find(
    (c) => c.sha === headCommit
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col lg:flex-row">
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
              onClick={checkBackendHealth}
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

          {/* Main Grid: Step 1 (Connect Repo) + Step 2 (Select & Compare Commits) & Status */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Repository Connection & Commit Comparison Panel (2 columns) */}
            <section className="lg:col-span-2 rounded-xl bg-slate-900/70 border border-slate-800 p-6 space-y-6">
              <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                <div>
                  <h3 className="text-base font-semibold text-white">
                    GitHub Repository Connection & Commit Comparison
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Connect a public HTTPS GitHub repository to retrieve live commit history and inspect code diffs.
                  </p>
                </div>
                <span className="text-xs px-2.5 py-1 rounded-md bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 font-mono">
                  Milestone 2 Live
                </span>
              </div>

              {/* Step 1: Connect Repository Form */}
              <form onSubmit={handleConnectRepository} className="space-y-3">
                <label
                  htmlFor="repo-url"
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-300"
                >
                  1. Public GitHub Repository URL
                </label>
                <div className="flex flex-col sm:flex-row gap-3">
                  <input
                    id="repo-url"
                    type="url"
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    disabled={inspectLoading}
                    placeholder="https://github.com/pallets/flask"
                    className="flex-1 rounded-lg bg-slate-950 border border-slate-800 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono disabled:opacity-60"
                  />
                  <button
                    type="submit"
                    disabled={inspectLoading || !repoUrl.trim()}
                    className="px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-sm shadow-lg shadow-indigo-600/20 transition-colors cursor-pointer shrink-0 flex items-center justify-center gap-2"
                  >
                    {inspectLoading ? (
                      <>
                        <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                        <span>Connecting...</span>
                      </>
                    ) : (
                      <span>Connect Repository</span>
                    )}
                  </button>
                </div>

                {/* Quick-Select Preset Buttons for Hackathon Demo & Real-World Testing */}
                <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
                  <span className="text-slate-400">Quick Presets:</span>
                  <button
                    type="button"
                    disabled={inspectLoading}
                    onClick={() =>
                      setRepoUrl('https://github.com/docguard-demo/billing-api')
                    }
                    className="px-2.5 py-1 rounded-md bg-indigo-500/15 hover:bg-indigo-500/25 text-indigo-300 border border-indigo-500/30 font-mono text-[11px] cursor-pointer"
                  >
                    Controlled Demo (docguard-demo/billing-api)
                  </button>
                  <button
                    type="button"
                    disabled={inspectLoading}
                    onClick={() =>
                      setRepoUrl('https://github.com/pallets/flask')
                    }
                    className="px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 font-mono text-[11px] cursor-pointer"
                  >
                    Real GitHub (pallets/flask)
                  </button>
                </div>
              </form>

              {/* Inspect Error Banner */}
              {inspectError && (
                <div
                  role="alert"
                  className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start justify-between gap-4"
                >
                  <div>
                    <p className="font-semibold text-rose-300">
                      Repository Connection Failed
                    </p>
                    <p className="mt-1 leading-relaxed">{inspectError}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setInspectError('')}
                    className="text-rose-300 hover:text-white underline shrink-0 cursor-pointer"
                  >
                    Dismiss
                  </button>
                </div>
              )}

              {/* Step 2: Repository Metadata & Commit Dropdowns */}
              {repoInfo && (
                <div className="pt-4 border-t border-slate-800 space-y-5">
                  {/* Repository Details Pill Bar */}
                  <div className="p-4 rounded-xl bg-slate-950/90 border border-slate-800 grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div>
                      <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                        Owner / Repository
                      </span>
                      <a
                        href={repoInfo.repository_url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-1 text-sm font-semibold text-indigo-300 hover:text-indigo-200 font-mono inline-flex items-center gap-1"
                      >
                        {repoInfo.owner}/{repoInfo.name}
                      </a>
                    </div>
                    <div>
                      <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                        Default Branch
                      </span>
                      <span className="mt-1 inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-mono bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                        {repoInfo.default_branch}
                      </span>
                    </div>
                    <div>
                      <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                        Recent Commits Loaded
                      </span>
                      <span className="mt-1 text-sm font-semibold text-white block">
                        {repoInfo.commits.length} commits
                      </span>
                    </div>
                  </div>

                  {/* Base & Head Commit Selectors */}
                  <form onSubmit={handleCompareCommits} className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label
                          htmlFor="base-commit-select"
                          className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-2"
                        >
                          2. Base Commit (Older / Starting Point)
                        </label>
                        <select
                          id="base-commit-select"
                          value={baseCommit}
                          onChange={(e) => setBaseCommit(e.target.value)}
                          disabled={compareLoading}
                          className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono"
                        >
                          <option value="">-- Select Base Commit --</option>
                          {repoInfo.commits.map((commit) => (
                            <option key={`base-${commit.sha}`} value={commit.sha}>
                              [{commit.short_sha}] {commit.message.slice(0, 55)} ({commit.author})
                            </option>
                          ))}
                        </select>
                        {selectedBaseCommitObj && (
                          <p className="mt-1.5 text-[11px] text-slate-400 truncate">
                            Author: <span className="text-slate-300">{selectedBaseCommitObj.author}</span> •{' '}
                            {formatCommitTimestamp(selectedBaseCommitObj.timestamp)}
                          </p>
                        )}
                      </div>

                      <div>
                        <label
                          htmlFor="head-commit-select"
                          className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-2"
                        >
                          3. Head Commit (Newer / Target Point)
                        </label>
                        <select
                          id="head-commit-select"
                          value={headCommit}
                          onChange={(e) => setHeadCommit(e.target.value)}
                          disabled={compareLoading}
                          className="w-full rounded-lg bg-slate-950 border border-slate-800 px-3 py-2.5 text-xs text-slate-100 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono"
                        >
                          <option value="">-- Select Head Commit --</option>
                          {repoInfo.commits.map((commit) => (
                            <option key={`head-${commit.sha}`} value={commit.sha}>
                              [{commit.short_sha}] {commit.message.slice(0, 55)} ({commit.author})
                            </option>
                          ))}
                        </select>
                        {selectedHeadCommitObj && (
                          <p className="mt-1.5 text-[11px] text-slate-400 truncate">
                            Author: <span className="text-slate-300">{selectedHeadCommitObj.author}</span> •{' '}
                            {formatCommitTimestamp(selectedHeadCommitObj.timestamp)}
                          </p>
                        )}
                      </div>
                    </div>

                    {baseCommit && headCommit && baseCommit === headCommit && (
                      <p className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
                        Base commit and head commit must be different to perform a comparison.
                      </p>
                    )}

                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pt-1">
                      <p className="text-xs text-slate-400">
                        Compare Git diffs or perform static Python AST symbol change analysis between Base ({baseCommit ? baseCommit.slice(0, 7) : 'none'}) and Head ({headCommit ? headCommit.slice(0, 7) : 'none'}).
                      </p>
                      <div className="flex flex-wrap items-center gap-3 shrink-0">
                        <button
                          type="submit"
                          disabled={!canCompare}
                          className="px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-sm shadow-lg shadow-emerald-600/20 transition-colors cursor-pointer flex items-center justify-center gap-2"
                        >
                          {compareLoading ? (
                            <>
                              <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                              <span>Comparing Commits...</span>
                            </>
                          ) : (
                            <span>Compare Commits</span>
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={handleAnalyzePythonChanges}
                          disabled={!canCompare}
                          className="px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-sm shadow-lg shadow-indigo-600/20 transition-colors cursor-pointer flex items-center justify-center gap-2"
                        >
                          {astLoading ? (
                            <>
                              <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                              <span>Analyzing Python AST...</span>
                            </>
                          ) : (
                            <span>Analyze Python Changes</span>
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={handleAnalyzeDocumentation}
                          disabled={!canAnalyzeDocs}
                          className="px-4 py-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-sm shadow-lg shadow-cyan-600/20 transition-colors cursor-pointer flex items-center justify-center gap-2"
                        >
                          {docLoading ? (
                            <>
                              <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                              <span>Mapping Docs...</span>
                            </>
                          ) : (
                            <span>Analyze Documentation</span>
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={handleAnalyzeDrift}
                          disabled={!canCompare}
                          className="px-4 py-2.5 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-semibold text-sm shadow-lg shadow-rose-600/25 transition-colors cursor-pointer flex items-center justify-center gap-2"
                        >
                          {driftLoading ? (
                            <>
                              <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                              <span>Detecting Drift...</span>
                            </>
                          ) : (
                            <span>ANALYZE DOCUMENTATION DRIFT</span>
                          )}
                        </button>
                      </div>
                    </div>
                  </form>
                </div>
              )}

              {/* Compare Error Banner */}
              {compareError && (
                <div
                  role="alert"
                  className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start justify-between gap-4"
                >
                  <div>
                    <p className="font-semibold text-rose-300">
                      Commit Comparison Failed
                    </p>
                    <p className="mt-1 leading-relaxed">{compareError}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setCompareError('')}
                    className="text-rose-300 hover:text-white underline shrink-0 cursor-pointer"
                  >
                    Dismiss
                  </button>
                </div>
              )}
            </section>

            {/* Analysis Status & Recent Commit Feed (1 column) */}
            <section className="rounded-xl bg-slate-900/70 border border-slate-800 p-6 flex flex-col justify-between">
              <div>
                <div className="pb-4 mb-4 border-b border-slate-800">
                  <h3 className="text-base font-semibold text-white">Analysis Status</h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Real-time repository and backend connection telemetry.
                  </p>
                </div>

                <div className="space-y-4 text-sm">
                  <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-xs text-slate-400 block">Pipeline State</span>
                    <span className="text-sm font-semibold text-slate-200 mt-0.5 block">
                      {inspectLoading
                        ? 'Cloning & Inspecting Repository...'
                        : compareLoading
                        ? 'Computing Git Commit Diff...'
                        : compareResult
                        ? `Diff Complete (${compareResult.total_changed_files} files)`
                        : repoInfo
                        ? `Connected to ${repoInfo.owner}/${repoInfo.name}`
                        : 'Standby — Awaiting Repository'}
                    </span>
                  </div>

                  <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-xs text-slate-400 block">
                      FastAPI Health Endpoint
                    </span>
                    {healthState === 'connected' ? (
                      <div className="mt-1">
                        <span className="text-sm font-semibold text-emerald-400 block">
                          Backend connected
                        </span>
                        <code className="mt-1.5 block text-[11px] text-slate-400 font-mono bg-slate-900 p-2 rounded border border-slate-800">
                          {JSON.stringify(healthData)}
                        </code>
                      </div>
                    ) : healthState === 'checking' ? (
                      <span className="text-sm font-semibold text-amber-300 mt-1 block">
                        Querying GET /api/health...
                      </span>
                    ) : (
                      <div className="mt-1">
                        <span className="text-sm font-semibold text-rose-400 block">
                          Backend disconnected
                        </span>
                        <span className="text-xs text-rose-300/90 mt-1 block">
                          {healthError}
                        </span>
                      </div>
                    )}
                  </div>

                  {repoInfo && (
                    <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800">
                      <span className="text-xs text-slate-400 block mb-2">
                        Latest Commits ({repoInfo.default_branch})
                      </span>
                      <ul className="space-y-2 max-h-48 overflow-y-auto pr-1">
                        {repoInfo.commits.slice(0, 6).map((c) => (
                          <li
                            key={c.sha}
                            className="text-xs border-b border-slate-800/80 pb-1.5 last:border-b-0"
                          >
                            <div className="flex items-center justify-between font-mono text-[11px] text-indigo-300">
                              <span>{c.short_sha}</span>
                              <span className="text-slate-500">
                                {formatCommitTimestamp(c.timestamp)}
                              </span>
                            </div>
                            <p className="text-slate-300 truncate mt-0.5">{c.message}</p>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-6 pt-4 border-t border-slate-800 text-xs text-slate-500">
                Repositories are inspected in isolated temporary directories and cleaned up immediately.
              </div>
            </section>
          </div>

          {/* Changed Files & Unified Diff Viewer Section (Shown when comparison completes) */}
          {compareResult && (
            <section
              aria-label="Commit Comparison Results"
              className="rounded-xl bg-slate-900/70 border border-slate-800 p-6 space-y-6"
            >
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-4 border-b border-slate-800">
                <div>
                  <h3 className="text-base font-semibold text-white">
                    Commit Comparison & Diff Explorer
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5 font-mono">
                    {compareResult.owner}/{compareResult.name}:{' '}
                    <span className="text-indigo-300">
                      {compareResult.base_commit.slice(0, 7)}
                    </span>{' '}
                    →{' '}
                    <span className="text-emerald-300">
                      {compareResult.head_commit.slice(0, 7)}
                    </span>
                  </p>
                </div>

                {/* Summary Stat Badges */}
                <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
                  <span className="px-2.5 py-1 rounded-md bg-slate-800 text-slate-200 border border-slate-700">
                    {compareResult.total_changed_files} changed files
                  </span>
                  <span className="px-2.5 py-1 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                    +{compareResult.total_additions} additions
                  </span>
                  <span className="px-2.5 py-1 rounded-md bg-rose-500/15 text-rose-300 border border-rose-500/30">
                    -{compareResult.total_deletions} deletions
                  </span>
                  {compareResult.added_files.length > 0 && (
                    <span className="px-2 py-1 rounded bg-emerald-500/10 text-emerald-300">
                      {compareResult.added_files.length} added
                    </span>
                  )}
                  {compareResult.modified_files.length > 0 && (
                    <span className="px-2 py-1 rounded bg-amber-500/10 text-amber-300">
                      {compareResult.modified_files.length} modified
                    </span>
                  )}
                  {compareResult.deleted_files.length > 0 && (
                    <span className="px-2 py-1 rounded bg-rose-500/10 text-rose-300">
                      {compareResult.deleted_files.length} deleted
                    </span>
                  )}
                  {compareResult.renamed_files.length > 0 && (
                    <span className="px-2 py-1 rounded bg-cyan-500/10 text-cyan-300">
                      {compareResult.renamed_files.length} renamed
                    </span>
                  )}
                </div>
              </div>

              {compareResult.diff_truncated && (
                <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs">
                  Large diff detected: some patch contents were truncated to preserve browser responsiveness.
                </div>
              )}

              {compareResult.files.length === 0 ? (
                <div className="py-10 text-center text-sm text-slate-400">
                  No file changes found between these two commits.
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  {/* Left column: Changed Files List */}
                  <div className="rounded-xl bg-slate-950 border border-slate-800 overflow-hidden flex flex-col max-h-[540px]">
                    <div className="px-4 py-3 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
                      <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                        Changed Files ({compareResult.files.length})
                      </span>
                    </div>
                    <ul className="divide-y divide-slate-800/70 overflow-y-auto">
                      {compareResult.files.map((file, idx) => {
                        const isSelected = idx === selectedFileIndex;
                        const badgeClass =
                          CHANGE_BADGE_STYLES[file.change_type] ||
                          CHANGE_BADGE_STYLES.modified;

                        return (
                          <li key={`${file.file_path}-${idx}`}>
                            <button
                              type="button"
                              onClick={() => setSelectedFileIndex(idx)}
                              className={`w-full text-left px-4 py-3 transition-colors flex items-start justify-between gap-2 cursor-pointer ${
                                isSelected
                                  ? 'bg-indigo-600/15 border-l-2 border-indigo-400'
                                  : 'hover:bg-slate-900/60'
                              }`}
                            >
                              <div className="min-w-0 flex-1">
                                <p className="text-xs font-mono text-slate-200 break-all">
                                  {file.previous_path
                                    ? `${file.previous_path} → ${file.file_path}`
                                    : file.file_path}
                                </p>
                                <div className="mt-1.5 flex items-center gap-2">
                                  <span
                                    className={`text-[10px] uppercase font-mono px-1.5 py-0.5 rounded border ${badgeClass}`}
                                  >
                                    {file.change_type}
                                  </span>
                                  <span className="text-[11px] font-mono text-emerald-400">
                                    +{file.additions}
                                  </span>
                                  <span className="text-[11px] font-mono text-rose-400">
                                    -{file.deletions}
                                  </span>
                                </div>
                              </div>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>

                  {/* Right 2 columns: Unified Diff Patch Preview */}
                  <div className="lg:col-span-2 rounded-xl bg-slate-950 border border-slate-800 overflow-hidden flex flex-col max-h-[540px]">
                    {selectedFile && (
                      <>
                        <div className="px-4 py-3 bg-slate-900/90 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <span
                              className={`text-[10px] uppercase font-mono px-2 py-0.5 rounded border ${
                                CHANGE_BADGE_STYLES[selectedFile.change_type] ||
                                CHANGE_BADGE_STYLES.modified
                              }`}
                            >
                              {selectedFile.change_type}
                            </span>
                            <span className="text-xs font-mono text-white truncate">
                              {selectedFile.previous_path
                                ? `${selectedFile.previous_path} → ${selectedFile.file_path}`
                                : selectedFile.file_path}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 text-xs font-mono">
                            <span className="text-emerald-400">
                              +{selectedFile.additions}
                            </span>
                            <span className="text-rose-400">
                              -{selectedFile.deletions}
                            </span>
                          </div>
                        </div>

                        <div className="overflow-y-auto flex-1 py-2">
                          <DiffLinesView
                            patch={selectedFile.patch}
                            isBinary={selectedFile.is_binary}
                          />
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}
            </section>
          )}

          {/* MILESTONE 3: PYTHON CODE ANALYSIS SECTION */}
          <section
            aria-label="PYTHON CODE ANALYSIS"
            className="rounded-xl bg-slate-900/70 border border-slate-800 p-6 space-y-6"
          >
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
              <div>
                <div className="flex items-center gap-2.5">
                  <h3 className="text-base font-bold tracking-wide uppercase text-white">
                    PYTHON CODE ANALYSIS
                  </h3>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                    Milestone 3 Static AST
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Static Python AST structural comparison detecting function, class, method, parameter, annotation, and async changes without executing code.
                </p>
              </div>

              <button
                type="button"
                onClick={handleAnalyzePythonChanges}
                disabled={!canCompare}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-xs shadow-lg shadow-indigo-600/20 transition-colors cursor-pointer shrink-0 flex items-center gap-2"
              >
                {astLoading ? (
                  <>
                    <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                    <span>Running AST Analysis...</span>
                  </>
                ) : (
                  <span>Analyze Python Changes</span>
                )}
              </button>
            </div>

            {/* 1. Loading Progress State */}
            {astLoading && (
              <div className="py-10 px-4 text-center space-y-3">
                <div className="mx-auto h-8 w-8 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin" />
                <p className="text-sm font-medium text-indigo-300">
                  Retrieving Python blobs and parsing AST trees for Base ({baseCommit.slice(0, 7)}) → Head ({headCommit.slice(0, 7)})...
                </p>
                <p className="text-xs text-slate-400">
                  Static analysis only — repository code is never executed or imported.
                </p>
              </div>
            )}

            {/* 2. Failed Analysis Error State */}
            {!astLoading && astError && (
              <div
                role="alert"
                className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start justify-between gap-4"
              >
                <div>
                  <p className="font-semibold text-rose-300">
                    Python AST Code Analysis Failed
                  </p>
                  <p className="mt-1 leading-relaxed">{astError}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setAstError('')}
                  className="text-rose-300 hover:text-white underline shrink-0 cursor-pointer"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* 3. Initial Idle Prompt before Analysis is Triggered */}
            {!astLoading && !astError && !astResult && (
              <div className="py-8 px-4 text-center max-w-lg mx-auto">
                <p className="text-sm font-medium text-slate-300">
                  {repoInfo
                    ? 'Ready to analyze Python AST changes between the selected commits.'
                    : 'Connect a GitHub repository and select Base and Head commits above to run Python AST analysis.'}
                </p>
                <p className="mt-1.5 text-xs text-slate-400">
                  Click &ldquo;Analyze Python Changes&rdquo; to inspect added, removed, modified, and renamed Python functions, classes, methods, parameters, default values, and type annotations.
                </p>
              </div>
            )}

            {/* 4. AST Analysis Results */}
            {!astLoading && astResult && (
              <div className="space-y-6">
                {/* Status Banner Distinguishing Analysis Outcomes */}
                {astResult.summary.parse_errors_count > 0 ? (
                  <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs">
                    <p className="font-semibold text-amber-300">
                      Partial Analysis Completed with Syntax Parse Errors ({astResult.summary.parse_errors_count})
                    </p>
                    <p className="mt-1">
                      Analyzed {astResult.summary.analyzed_python_files_count} Python file(s) and detected {astResult.summary.total_symbol_changes} symbol change(s), while {astResult.summary.parse_errors_count} file version(s) contained invalid Python syntax.
                    </p>
                  </div>
                ) : astResult.summary.total_symbol_changes > 0 ? (
                  <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 text-xs">
                    <p className="font-semibold text-emerald-300">
                      AST Analysis Complete — {astResult.summary.total_symbol_changes} Symbol Change(s) Detected
                    </p>
                    <p className="mt-1">
                      Inspected {astResult.summary.analyzed_python_files_count} changed Python file(s) between {astResult.base_commit.slice(0, 7)} and {astResult.head_commit.slice(0, 7)}.
                    </p>
                  </div>
                ) : (
                  <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-slate-300 text-xs">
                    <p className="font-semibold text-white">
                      AST Analysis Complete — No Python Symbol Changes Detected
                    </p>
                    <p className="mt-1 text-slate-400">
                      {astResult.summary.analyzed_python_files_count > 0
                        ? `Inspected ${astResult.summary.analyzed_python_files_count} changed Python file(s); no function, class, method, or parameter signature/body changes were found.`
                        : `No changed Python (.py) files were present between ${astResult.base_commit.slice(0, 7)} and ${astResult.head_commit.slice(0, 7)}.`}
                    </p>
                  </div>
                )}

                {/* Summary Metric Tiles */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Python Files Analyzed
                    </span>
                    <span className="mt-1 text-xl font-bold text-white block">
                      {astResult.summary.analyzed_python_files_count}
                    </span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Changed Symbols
                    </span>
                    <span className="mt-1 text-xl font-bold text-indigo-300 block">
                      {astResult.summary.total_symbol_changes}
                    </span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Skipped Files
                    </span>
                    <span className="mt-1 text-xl font-bold text-slate-300 block">
                      {astResult.summary.skipped_files_count}
                    </span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Parse Errors
                    </span>
                    <span
                      className={`mt-1 text-xl font-bold block ${
                        astResult.summary.parse_errors_count > 0
                          ? 'text-amber-300'
                          : 'text-emerald-400'
                      }`}
                    >
                      {astResult.summary.parse_errors_count}
                    </span>
                  </div>
                </div>

                {/* Counts by Change Type */}
                {Object.keys(astResult.summary.counts_by_change_type).length > 0 && (
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 block mb-3">
                      Counts by Change Type
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(astResult.summary.counts_by_change_type).map(
                        ([cType, count]) => (
                          <span
                            key={cType}
                            className={`text-xs font-mono px-2.5 py-1 rounded-md border ${getAstChangeBadgeStyle(
                              cType
                            )}`}
                          >
                            {cType}: <strong>{count}</strong>
                          </span>
                        )
                      )}
                    </div>
                  </div>
                )}

                {/* Detailed List of Detected Symbol Changes */}
                {astResult.changed_symbols.length > 0 && (
                  <div className="space-y-3">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                      Detected Symbol Changes ({astResult.changed_symbols.length})
                    </h4>
                    <div className="divide-y divide-slate-800 rounded-xl bg-slate-950 border border-slate-800 overflow-hidden">
                      {astResult.changed_symbols.map((change, idx) => (
                        <div key={`${change.file_path}-${change.qualified_name}-${change.change_type}-${idx}`} className="p-4 space-y-2.5">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <span
                                className={`text-[11px] font-mono px-2 py-0.5 rounded border ${getAstChangeBadgeStyle(
                                  change.change_type
                                )}`}
                              >
                                {change.change_type}
                              </span>
                              <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-800">
                                {change.symbol_type}
                              </span>
                              <span className="text-sm font-semibold font-mono text-white">
                                {change.qualified_name}
                              </span>
                            </div>
                            <div className="text-xs font-mono text-slate-400">
                              <span className="text-indigo-300">{change.file_path}</span>
                              {change.old_line && change.new_line ? (
                                <span className="ml-2">
                                  (L{change.old_line} → L{change.new_line})
                                </span>
                              ) : change.new_line ? (
                                <span className="ml-2 text-emerald-400">
                                  (New L{change.new_line})
                                </span>
                              ) : change.old_line ? (
                                <span className="ml-2 text-rose-400">
                                  (Old L{change.old_line})
                                </span>
                              ) : null}
                            </div>
                          </div>

                          <p className="text-xs text-slate-300">{change.summary}</p>

                          {(change.old_signature || change.new_signature) && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-1 font-mono text-xs">
                              {change.old_signature && (
                                <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/25 text-rose-200 overflow-x-auto">
                                  <span className="text-[10px] uppercase tracking-wider text-rose-400 block mb-0.5">
                                    Base Signature {change.old_line ? `(line ${change.old_line})` : ''}
                                  </span>
                                  <code>{change.old_signature}</code>
                                </div>
                              )}
                              {change.new_signature && (
                                <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/25 text-emerald-200 overflow-x-auto">
                                  <span className="text-[10px] uppercase tracking-wider text-emerald-400 block mb-0.5">
                                    Head Signature {change.new_line ? `(line ${change.new_line})` : ''}
                                  </span>
                                  <code>{change.new_signature}</code>
                                </div>
                              )}
                            </div>
                          )}

                          {change.details && Object.keys(change.details).length > 0 && (
                            <div className="text-[11px] font-mono text-slate-400 bg-slate-900/80 px-3 py-1.5 rounded border border-slate-800/80 overflow-x-auto">
                              Details: {JSON.stringify(change.details)}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Parse Errors Section */}
                {astResult.parse_errors.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-amber-300">
                      Syntax / Parse Errors ({astResult.parse_errors.length})
                    </h4>
                    <div className="divide-y divide-amber-500/20 rounded-xl bg-amber-500/10 border border-amber-500/30 overflow-hidden">
                      {astResult.parse_errors.map((err, idx) => (
                        <div key={`${err.file_path}-${err.version}-${idx}`} className="p-3.5 text-xs text-amber-200 font-mono">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-semibold text-amber-300">
                              {err.file_path} ({err.version} commit)
                            </span>
                            <span>
                              {err.error_type}
                              {err.line ? ` at line ${err.line}` : ''}
                              {err.column ? `, col ${err.column}` : ''}
                            </span>
                          </div>
                          <p className="mt-1 text-amber-100/90">{err.message}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Analyzed Python Files & Skipped Files Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300 mb-3">
                      Analyzed Python Files ({astResult.analyzed_files.length})
                    </h4>
                    {astResult.analyzed_files.length === 0 ? (
                      <p className="text-xs text-slate-500">No Python (.py) files in commit range.</p>
                    ) : (
                      <ul className="space-y-2 max-h-48 overflow-y-auto text-xs font-mono">
                        {astResult.analyzed_files.map((af) => (
                          <li
                            key={af.file_path}
                            className="flex items-center justify-between gap-2 pb-1.5 border-b border-slate-800/80 last:border-b-0"
                          >
                            <span className="text-slate-200 truncate">{af.file_path}</span>
                            <span className="text-slate-400 shrink-0">
                              {af.changes_count} change(s) ({af.base_symbol_count}→{af.head_symbol_count} symbols)
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300 mb-3">
                      Skipped Files ({astResult.skipped_files.length})
                    </h4>
                    {astResult.skipped_files.length === 0 ? (
                      <p className="text-xs text-slate-500">No files were skipped.</p>
                    ) : (
                      <ul className="space-y-2 max-h-48 overflow-y-auto text-xs font-mono">
                        {astResult.skipped_files.map((sf, idx) => (
                          <li
                            key={`${sf.file_path}-${idx}`}
                            className="flex items-center justify-between gap-2 pb-1.5 border-b border-slate-800/80 last:border-b-0"
                          >
                            <span className="text-slate-300 truncate">{sf.file_path}</span>
                            <span className="text-slate-500 shrink-0">{sf.reason}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* MILESTONE 4: DOCUMENTATION MAP SECTION */}
          <section
            aria-label="DOCUMENTATION MAP"
            className="rounded-xl bg-slate-900/70 border border-slate-800 p-6 space-y-6"
          >
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
              <div>
                <div className="flex items-center gap-2.5">
                  <h3 className="text-base font-bold tracking-wide uppercase text-white">
                    DOCUMENTATION MAP
                  </h3>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                    Milestone 4 Doc-to-Code Engine
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Discovers Markdown documentation at HEAD commit, extracts structured statements, and maps them to Python AST symbols with confidence and evidence.
                </p>
              </div>

              <button
                type="button"
                onClick={handleAnalyzeDocumentation}
                disabled={!canAnalyzeDocs}
                className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-xs shadow-lg shadow-cyan-600/20 transition-colors cursor-pointer shrink-0 flex items-center gap-2"
              >
                {docLoading ? (
                  <>
                    <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                    <span>Parsing & Mapping Docs...</span>
                  </>
                ) : (
                  <span>Analyze Documentation</span>
                )}
              </button>
            </div>

            {/* 1. Loading Progress State */}
            {docLoading && (
              <div className="py-10 px-4 text-center space-y-3">
                <div className="mx-auto h-8 w-8 rounded-full border-2 border-cyan-400 border-t-transparent animate-spin" />
                <p className="text-sm font-medium text-cyan-300">
                  Discovering Markdown files, extracting documentation statements, and mapping against Python AST symbols at Head ({headCommit ? headCommit.slice(0, 7) : 'HEAD'})...
                </p>
                <p className="text-xs text-slate-400">
                  Static parsing only — documentation code blocks and repository files are never executed.
                </p>
              </div>
            )}

            {/* 2. API Error State */}
            {!docLoading && docError && (
              <div
                role="alert"
                className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start justify-between gap-4"
              >
                <div>
                  <p className="font-semibold text-rose-300">
                    Documentation Parsing & Mapping Failed
                  </p>
                  <p className="mt-1 leading-relaxed">{docError}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setDocError('')}
                  className="text-rose-300 hover:text-white underline shrink-0 cursor-pointer"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* 3. Initial Idle Prompt */}
            {!docLoading && !docError && !docResult && (
              <div className="py-8 px-4 text-center max-w-lg mx-auto">
                <p className="text-sm font-medium text-slate-300">
                  {repoInfo
                    ? 'Ready to discover Markdown documentation and map sections to Python symbols.'
                    : 'Connect a GitHub repository above to run Documentation Parsing and Code Mapping.'}
                </p>
                <p className="mt-1.5 text-xs text-slate-400">
                  Click &ldquo;Analyze Documentation&rdquo; to extract headings, paragraphs, lists, API references, and code blocks and inspect their mapped Python functions, classes, and methods.
                </p>
              </div>
            )}

            {/* 4. Documentation Mapping Results */}
            {!docLoading && docResult && (
              <div className="space-y-6">
                {/* Outcome Banner Distinguishing Zero Mappings vs Mapped Results */}
                {docResult.summary.discovered_doc_files_count === 0 ? (
                  <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-slate-300 text-xs">
                    <p className="font-semibold text-white">
                      Documentation Scan Complete — No Markdown Files Discovered
                    </p>
                    <p className="mt-1 text-slate-400">
                      No `.md` documentation files were found in the repository at commit {docResult.commit_sha.slice(0, 7)} ({docResult.summary.extracted_python_symbols_count} Python symbols indexed).
                    </p>
                  </div>
                ) : docResult.summary.mapped_units_count === 0 && docResult.summary.ambiguous_units_count === 0 ? (
                  <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-slate-300 text-xs">
                    <p className="font-semibold text-white">
                      Documentation Scan Complete — 0 Symbol Mappings Found
                    </p>
                    <p className="mt-1 text-slate-400">
                      Parsed {docResult.summary.discovered_doc_files_count} Markdown file(s) and extracted {docResult.summary.extracted_units_count} documentation unit(s), but none referenced the {docResult.summary.extracted_python_symbols_count} Python symbol(s) in the repository.
                    </p>
                  </div>
                ) : (
                  <div className="p-4 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-200 text-xs">
                    <p className="font-semibold text-cyan-300">
                      Documentation Mapping Complete — {docResult.summary.mapped_units_count} Mapped Unit(s), {docResult.summary.ambiguous_units_count} Ambiguous, {docResult.summary.unmapped_units_count} Unmapped
                    </p>
                    <p className="mt-1">
                      Parsed {docResult.summary.discovered_doc_files_count} Markdown file(s) ({docResult.summary.extracted_units_count} documentation units) against {docResult.summary.extracted_python_symbols_count} Python AST symbol(s) at commit {docResult.commit_sha.slice(0, 7)}.
                    </p>
                  </div>
                )}

                {/* Summary Metric Tiles */}
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Doc Files
                    </span>
                    <span className="mt-1 text-lg font-bold text-white block">
                      {docResult.summary.discovered_doc_files_count}
                    </span>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Extracted Units
                    </span>
                    <span className="mt-1 text-lg font-bold text-white block">
                      {docResult.summary.extracted_units_count}
                    </span>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Mapped Units
                    </span>
                    <span className="mt-1 text-lg font-bold text-emerald-400 block">
                      {docResult.summary.mapped_units_count}
                    </span>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Ambiguous
                    </span>
                    <span className="mt-1 text-lg font-bold text-amber-300 block">
                      {docResult.summary.ambiguous_units_count}
                    </span>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Unmapped
                    </span>
                    <span className="mt-1 text-lg font-bold text-slate-300 block">
                      {docResult.summary.unmapped_units_count}
                    </span>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Python Symbols
                    </span>
                    <span className="mt-1 text-lg font-bold text-indigo-300 block">
                      {docResult.summary.extracted_python_symbols_count}
                    </span>
                  </div>
                </div>

                {/* Discovered Documentation Files & Skipped Files */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300 mb-3">
                      Discovered Documentation Files ({docResult.documentation_files.length})
                    </h4>
                    {docResult.documentation_files.length === 0 ? (
                      <p className="text-xs text-slate-500">No Markdown files discovered.</p>
                    ) : (
                      <ul className="space-y-2 max-h-44 overflow-y-auto text-xs font-mono">
                        {docResult.documentation_files.map((df) => (
                          <li
                            key={df.file_path}
                            className="flex items-center justify-between gap-2 pb-1.5 border-b border-slate-800/80 last:border-b-0"
                          >
                            <span className="text-cyan-300 truncate">{df.file_path}</span>
                            <span className="text-slate-400 shrink-0">
                              {df.sections_count} sec • {df.extracted_units_count} units • {df.mapped_units_count} mapped
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300 mb-3">
                      Skipped Documentation Files ({docResult.skipped_files.length})
                    </h4>
                    {docResult.skipped_files.length === 0 ? (
                      <p className="text-xs text-slate-500">No documentation files were skipped.</p>
                    ) : (
                      <ul className="space-y-2 max-h-44 overflow-y-auto text-xs font-mono">
                        {docResult.skipped_files.map((sf, idx) => (
                          <li
                            key={`${sf.file_path}-${idx}`}
                            className="flex items-center justify-between gap-2 pb-1.5 border-b border-slate-800/80 last:border-b-0"
                          >
                            <span className="text-slate-300 truncate">{sf.file_path}</span>
                            <span className="text-slate-500 shrink-0">{sf.reason}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>

                {/* Filter Tabs (All, High, Medium, Low, Ambiguous, Unmapped) */}
                {docResult.mappings.length > 0 && (
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                        Documentation-to-Code Mappings ({filteredDocMappings.length} shown)
                      </h4>
                      <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Mapping Filters">
                        {DOC_FILTER_TABS.map((tab) => {
                          const isActive = docFilter === tab.id;
                          return (
                            <button
                              key={tab.id}
                              type="button"
                              onClick={() => setDocFilter(tab.id)}
                              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors cursor-pointer ${
                                isActive
                                  ? 'bg-cyan-500/20 text-cyan-200 border-cyan-500/40'
                                  : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200 hover:bg-slate-900'
                              }`}
                            >
                              {tab.label}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    {filteredDocMappings.length === 0 ? (
                      <div className="py-8 text-center text-xs text-slate-400 bg-slate-950 rounded-xl border border-slate-800">
                        No documentation units match the selected filter ({docFilter}).
                      </div>
                    ) : (
                      <div className="divide-y divide-slate-800 rounded-xl bg-slate-950 border border-slate-800 overflow-hidden">
                        {filteredDocMappings.map((item) => {
                          const isExpanded = Boolean(expandedMappings[item.mapping_id]);
                          const statusBadge =
                            MAPPING_STATUS_STYLES[item.mapping_status] ||
                            MAPPING_STATUS_STYLES.UNMAPPED;

                          return (
                            <div key={item.mapping_id} className="p-4 space-y-3">
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div className="space-y-1 min-w-0 flex-1">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span
                                      className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border ${statusBadge}`}
                                    >
                                      {item.mapping_status}
                                    </span>
                                    {item.highest_confidence && (
                                      <span
                                        className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border ${
                                          CONFIDENCE_BADGE_STYLES[item.highest_confidence] || ''
                                        }`}
                                      >
                                        {item.highest_confidence} CONFIDENCE
                                      </span>
                                    )}
                                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                                      {item.unit_type}
                                    </span>
                                    <span className="text-xs font-mono text-cyan-300">
                                      {item.documentation_file} (L{item.start_line}–L{item.end_line})
                                    </span>
                                  </div>

                                  {item.heading_hierarchy && item.heading_hierarchy.length > 0 && (
                                    <p className="text-xs font-semibold text-white">
                                      Section: {item.heading_hierarchy.join(' › ')}
                                    </p>
                                  )}

                                  <p className="text-xs text-slate-300 line-clamp-2 font-mono bg-slate-900/60 px-3 py-1.5 rounded border border-slate-800/70">
                                    {item.documentation_text}
                                  </p>
                                </div>

                                <button
                                  type="button"
                                  onClick={() => toggleMappingExpanded(item.mapping_id)}
                                  className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-800 shrink-0 cursor-pointer"
                                >
                                  {isExpanded ? 'Collapse' : 'Inspect Mapping'}
                                </button>
                              </div>

                              {/* Quick Summary of Linked Code Symbols */}
                              {item.related_symbols.length > 0 && (
                                <div className="flex flex-wrap items-center gap-2 pt-1">
                                  <span className="text-[11px] text-slate-400">
                                    Linked Python Symbol(s):
                                  </span>
                                  {item.related_symbols.map((sym, sIdx) => (
                                    <span
                                      key={`${item.mapping_id}-${sym.source_file}-${sym.qualified_name}-${sIdx}`}
                                      className="inline-flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-md bg-indigo-500/10 text-indigo-300 border border-indigo-500/30"
                                    >
                                      <strong>{sym.qualified_name}</strong>
                                      <span className="text-slate-400">
                                        ({sym.source_file}:L{sym.line_start}–L{sym.line_end})
                                      </span>
                                    </span>
                                  ))}
                                </div>
                              )}

                              {/* Expanded View: Full Documentation Text, Code Signatures, Matching Reasons & Evidence */}
                              {isExpanded && (
                                <div className="mt-3 pt-3 border-t border-slate-800/80 space-y-3 text-xs">
                                  <div className="p-3 rounded-lg bg-slate-900 border border-slate-800">
                                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                                      Full Extracted Documentation Statement ({item.documentation_file}:L{item.start_line}–L{item.end_line})
                                    </span>
                                    <pre className="whitespace-pre-wrap font-mono text-xs text-slate-200 leading-relaxed">
                                      {item.documentation_text}
                                    </pre>
                                  </div>

                                  {item.related_symbols.length === 0 ? (
                                    <p className="text-xs text-slate-400 italic">
                                      No matching Python AST symbol found for this documentation unit.
                                    </p>
                                  ) : (
                                    <div className="space-y-2.5">
                                      <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block">
                                        Mapped Python AST Symbols & Evidence ({item.related_symbols.length})
                                      </span>
                                      {item.related_symbols.map((sym, sIdx) => (
                                        <div
                                          key={`detail-${item.mapping_id}-${sIdx}`}
                                          className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800 space-y-2"
                                        >
                                          <div className="flex flex-wrap items-center justify-between gap-2">
                                            <div className="flex items-center gap-2">
                                              <span
                                                className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border ${
                                                  CONFIDENCE_BADGE_STYLES[sym.confidence] || ''
                                                }`}
                                              >
                                                {sym.confidence}
                                              </span>
                                              <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-950 text-slate-300 border border-slate-800">
                                                {sym.symbol_type}
                                              </span>
                                              <span className="font-mono font-semibold text-white">
                                                {sym.qualified_name}
                                              </span>
                                            </div>
                                            <span className="font-mono text-indigo-300">
                                              {sym.source_file} (lines {sym.line_start}–{sym.line_end})
                                            </span>
                                          </div>

                                          <div className="p-2 rounded bg-slate-950 border border-slate-800 font-mono text-emerald-300 overflow-x-auto">
                                            <code>{sym.signature}</code>
                                          </div>

                                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-1">
                                            <div>
                                              <span className="text-[10px] uppercase tracking-wider text-slate-400 block mb-1">
                                                Matching Reasons
                                              </span>
                                              <ul className="list-disc list-inside text-slate-300 space-y-0.5">
                                                {sym.matching_reasons.map((r, rIdx) => (
                                                  <li key={rIdx}>{r}</li>
                                                ))}
                                              </ul>
                                            </div>
                                            <div>
                                              <span className="text-[10px] uppercase tracking-wider text-slate-400 block mb-1">
                                                Supporting Evidence
                                              </span>
                                              <ul className="list-disc list-inside text-slate-300 space-y-0.5">
                                                {sym.evidence.map((ev, eIdx) => (
                                                  <li key={eIdx}>{ev}</li>
                                                ))}
                                              </ul>
                                            </div>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </section>

          {/* MILESTONE 5: DOCUMENTATION DRIFT DETECTION SECTION */}
          <section
            aria-label="DOCUMENTATION DRIFT FINDINGS"
            className="rounded-xl bg-slate-900/70 border border-slate-800 p-6 space-y-6"
          >
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
              <div>
                <div className="flex items-center gap-2.5">
                  <h3 className="text-base font-bold tracking-wide uppercase text-white">
                    Documentation Drift Findings
                  </h3>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30">
                    Milestone 5 Drift Engine
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Deterministic, evidence-based verification connecting Python AST code changes between Base and Head commits to mapped Markdown documentation claims.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                {/* Active AI Provider Selector & Status Indicator */}
                <div className="flex items-center gap-2 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800 text-xs">
                  <span className="text-slate-400">AI Provider:</span>
                  <select
                    aria-label="Select AI Provider"
                    value={selectedAiProvider}
                    onChange={(e) => setSelectedAiProvider(e.target.value)}
                    disabled={healthState !== 'connected'}
                    className="bg-slate-900 text-slate-100 font-mono text-xs px-2 py-0.5 rounded border border-slate-700 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="mock">Mock (Offline Deterministic)</option>
                    <option value="gemini">
                      Gemini ({aiProviderInfo?.gemini_configured ? aiProviderInfo.gemini_model : 'API Key Not Configured'})
                    </option>
                  </select>
                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                      healthState !== 'connected'
                        ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                        : selectedAiProvider === 'gemini' && aiProviderInfo?.gemini_configured
                        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                        : selectedAiProvider === 'gemini' && !aiProviderInfo?.gemini_configured
                        ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                        : 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30'
                    }`}
                  >
                    {healthState !== 'connected'
                      ? 'Unavailable'
                      : selectedAiProvider === 'gemini'
                      ? aiProviderInfo?.gemini_configured
                        ? 'Gemini Ready'
                        : 'Gemini Unconfigured'
                      : 'Mock Active'}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={handleAnalyzeDrift}
                  disabled={!canCompare}
                  className="px-4 py-2.5 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-semibold text-xs shadow-lg shadow-rose-600/25 transition-colors cursor-pointer shrink-0 flex items-center gap-2"
                >
                  {driftLoading ? (
                    <>
                      <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                      <span>Running Drift Detection...</span>
                    </>
                  ) : (
                    <span>ANALYZE DOCUMENTATION DRIFT</span>
                  )}
                </button>
              </div>
            </div>

            {/* 1. Loading State */}
            {driftLoading && (
              <div className="py-10 px-4 text-center space-y-3">
                <div className="mx-auto h-8 w-8 rounded-full border-2 border-rose-400 border-t-transparent animate-spin" />
                <p className="text-sm font-medium text-rose-300">
                  Analyzing AST code changes, mapping Base & Head documentation, and evaluating Drift Rules A–I for Base ({baseCommit ? baseCommit.slice(0, 7) : ''}) → Head ({headCommit ? headCommit.slice(0, 7) : ''})...
                </p>
                <p className="text-xs text-slate-400">
                  Deterministic static rule evaluation only — repository code and Markdown snippets are never executed.
                </p>
              </div>
            )}

            {/* 2. Failed Analysis Error State */}
            {!driftLoading && driftError && (
              <div
                role="alert"
                className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start justify-between gap-4"
              >
                <div>
                  <p className="font-semibold text-rose-300">
                    Documentation Drift Analysis Failed
                  </p>
                  <p className="mt-1 leading-relaxed">{driftError}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setDriftError('')}
                  className="text-rose-300 hover:text-white underline shrink-0 cursor-pointer"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* 3. Initial Idle State before Drift Analysis is Triggered */}
            {!driftLoading && !driftError && !driftResult && (
              <div className="py-10 px-4 text-center max-w-md mx-auto">
                <div className="mx-auto h-12 w-12 rounded-full bg-slate-800/80 border border-slate-700 flex items-center justify-center text-slate-400 mb-4">
                  <svg
                    className="w-6 h-6"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.75}
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>
                </div>
                <h4 className="text-base font-semibold text-white">
                  No drift analysis has been performed yet
                </h4>
                <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                  Connect a repository, select two different Base and Head commits, and click &ldquo;ANALYZE DOCUMENTATION DRIFT&rdquo; to detect outdated parameters, defaults, return contracts, removed/renamed functions, and deleted source files.
                </p>
              </div>
            )}

            {/* 4. Drift Analysis Results */}
            {!driftLoading && driftResult && (
              <div className="space-y-6">
                {/* Outcome Status Banner Distinguishing Partial, Findings, and Zero-Drift Results */}
                {driftResult.summary.parse_errors_count > 0 ? (
                  <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs">
                    <p className="font-semibold text-amber-300">
                      Partial Drift Analysis Completed ({driftResult.summary.parse_errors_count} syntax parse error(s))
                    </p>
                    <p className="mt-1">
                      Analyzed {driftResult.summary.python_files_analyzed} Python file(s) and {driftResult.summary.documentation_files_analyzed} documentation file(s) with {driftResult.summary.total_findings} finding(s), while {driftResult.summary.parse_errors_count} file(s) could not be parsed.
                    </p>
                  </div>
                ) : driftResult.summary.confirmed_drift_count > 0 || driftResult.summary.potential_drift_count > 0 ? (
                  <div className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs">
                    <p className="font-semibold text-rose-300">
                      Documentation Drift Detected — {driftResult.summary.confirmed_drift_count} Confirmed, {driftResult.summary.potential_drift_count} Potential
                    </p>
                    <p className="mt-1">
                      Evaluated {driftResult.summary.code_changes_count} AST code change(s) across {driftResult.summary.python_files_analyzed} Python file(s) and {driftResult.summary.documentation_files_analyzed} Markdown file(s) between {driftResult.base_commit.slice(0, 7)} and {driftResult.head_commit.slice(0, 7)}.
                    </p>
                  </div>
                ) : (
                  <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 text-xs">
                    <p className="font-semibold text-emerald-300">
                      Analysis Successful — No Unresolved Documentation Drift Detected
                    </p>
                    <p className="mt-1">
                      Evaluated {driftResult.summary.code_changes_count} AST code change(s) across {driftResult.summary.python_files_analyzed} Python file(s) and {driftResult.summary.documentation_files_analyzed} Markdown file(s). No outdated documentation claims were identified ({driftResult.summary.resolved_count} resolved, {driftResult.summary.uncertain_count} uncertain).
                    </p>
                  </div>
                )}

                {/* Summary Metric Tiles */}
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Total Drift Findings
                    </span>
                    <span className="mt-1 text-xl font-bold text-white block">
                      {driftResult.summary.total_findings}
                    </span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Confirmed Drift
                    </span>
                    <span className="mt-1 text-xl font-bold text-rose-400 block">
                      {driftResult.summary.confirmed_drift_count}
                    </span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Potential Drift
                    </span>
                    <span className="mt-1 text-xl font-bold text-amber-300 block">
                      {driftResult.summary.potential_drift_count}
                    </span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Uncertain Findings
                    </span>
                    <span className="mt-1 text-xl font-bold text-indigo-300 block">
                      {driftResult.summary.uncertain_count}
                    </span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                      Resolved Findings
                    </span>
                    <span className="mt-1 text-xl font-bold text-emerald-400 block">
                      {driftResult.summary.resolved_count}
                    </span>
                  </div>
                </div>

                {/* Filters Bar (Status Tabs + Severity Dropdown) */}
                {driftResult.findings.length > 0 && (
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Drift Status Filters">
                        {DRIFT_STATUS_TABS.map((tab) => {
                          const isActive = driftStatusFilter === tab.id;
                          return (
                            <button
                              key={tab.id}
                              type="button"
                              onClick={() => setDriftStatusFilter(tab.id)}
                              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors cursor-pointer ${
                                isActive
                                  ? 'bg-rose-500/20 text-rose-200 border-rose-500/40'
                                  : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200 hover:bg-slate-900'
                              }`}
                            >
                              {tab.label}
                            </button>
                          );
                        })}
                      </div>

                      <div className="flex items-center gap-2">
                        <label
                          htmlFor="drift-severity-filter"
                          className="text-xs text-slate-400"
                        >
                          Severity:
                        </label>
                        <select
                          id="drift-severity-filter"
                          value={driftSeverityFilter}
                          onChange={(e) => setDriftSeverityFilter(e.target.value)}
                          className="rounded-lg bg-slate-950 border border-slate-800 px-3 py-1.5 text-xs text-slate-200 font-mono focus:outline-none focus:border-rose-500"
                        >
                          {DRIFT_SEVERITY_OPTIONS.map((opt) => (
                            <option key={opt.id} value={opt.id}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    {filteredDriftFindings.length === 0 ? (
                      <div className="py-8 text-center text-xs text-slate-400 bg-slate-950 rounded-xl border border-slate-800">
                        No findings match the selected Status ({driftStatusFilter}) and Severity ({driftSeverityFilter}) filters.
                      </div>
                    ) : (
                      <div className="divide-y divide-slate-800 rounded-xl bg-slate-950 border border-slate-800 overflow-hidden">
                        {filteredDriftFindings.map((finding) => {
                          const isExpanded = Boolean(expandedFindings[finding.finding_id]);
                          const statusStyle =
                            DRIFT_STATUS_STYLES[finding.status] ||
                            DRIFT_STATUS_STYLES.UNCHANGED;
                          const sevStyle =
                            DRIFT_SEVERITY_STYLES[finding.severity] ||
                            DRIFT_SEVERITY_STYLES.LOW;

                          return (
                            <div key={finding.finding_id} className="p-4 space-y-3">
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div className="space-y-1.5 min-w-0 flex-1">
                                  {/* Badges Row */}
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span
                                      className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border font-semibold ${statusStyle}`}
                                    >
                                      {finding.status}
                                    </span>
                                    <span
                                      className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border ${sevStyle}`}
                                    >
                                      {finding.severity} SEVERITY
                                    </span>
                                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-800">
                                      Confidence: {(finding.confidence * 100).toFixed(0)}% ({finding.confidence})
                                    </span>
                                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">
                                      {finding.finding_type}
                                    </span>
                                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                                      {finding.rule_id}
                                    </span>
                                  </div>

                                  {/* File & Symbol Row */}
                                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono">
                                    <span className="text-cyan-300">
                                      Doc: <strong>{finding.documentation_file}</strong> (L{finding.documentation_line}
                                      {finding.documentation_end_line > finding.documentation_line
                                        ? `–L${finding.documentation_end_line}`
                                        : ''}
                                      )
                                    </span>
                                    <span className="text-indigo-300">
                                      Symbol: <strong>{finding.qualified_symbol}</strong> in{' '}
                                      {finding.source_file}
                                      {finding.source_line ? `:L${finding.source_line}` : ''}
                                    </span>
                                  </div>

                                  {/* Detection Reason */}
                                  <p className="text-xs text-slate-200 leading-relaxed">
                                    {finding.reason}
                                  </p>
                                </div>

                                <div className="flex flex-wrap items-center gap-2 shrink-0">
                                  <button
                                    type="button"
                                    onClick={() =>
                                      handleRequestFindingAI(finding, 'explain')
                                    }
                                    disabled={Boolean(aiLoadingById[finding.finding_id])}
                                    className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white shadow shadow-indigo-600/20 cursor-pointer"
                                  >
                                    {aiLoadingById[finding.finding_id] &&
                                    aiFocusModeById[finding.finding_id] === 'explain'
                                      ? 'Explaining...'
                                      : 'EXPLAIN WITH AI'}
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      handleRequestFindingAI(finding, 'suggest')
                                    }
                                    disabled={Boolean(aiLoadingById[finding.finding_id])}
                                    className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 disabled:text-slate-500 text-white shadow shadow-emerald-600/20 cursor-pointer"
                                  >
                                    {aiLoadingById[finding.finding_id] &&
                                    aiFocusModeById[finding.finding_id] === 'suggest'
                                      ? 'Suggesting...'
                                      : 'SUGGEST DOCUMENTATION FIX'}
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      toggleFindingExpanded(finding.finding_id)
                                    }
                                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-800 cursor-pointer"
                                  >
                                    {isExpanded ? 'Hide Evidence' : 'Inspect Evidence'}
                                  </button>
                                </div>
                              </div>

                              {/* Milestone 6: AI Loading Indicator for this Finding */}
                              {aiLoadingById[finding.finding_id] && (
                                <div className="mt-2 p-3 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-200 text-xs flex items-center gap-2.5">
                                  <span className="h-3.5 w-3.5 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin shrink-0" />
                                  <span>
                                    Generating evidence-based AI explanation and documentation suggestion via{' '}
                                    <strong className="uppercase">{selectedAiProvider}</strong> provider...
                                  </span>
                                </div>
                              )}

                              {/* Milestone 6: AI Provider Error Banner for this Finding */}
                              {!aiLoadingById[finding.finding_id] &&
                                aiErrorById[finding.finding_id] && (
                                  <div
                                    role="alert"
                                    className="mt-2 p-3.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start justify-between gap-3"
                                  >
                                    <div>
                                      <p className="font-semibold text-rose-300">
                                        AI Provider ({selectedAiProvider.toUpperCase()}) Error
                                      </p>
                                      <p className="mt-1">
                                        {aiErrorById[finding.finding_id]}
                                      </p>
                                    </div>
                                    <button
                                      type="button"
                                      onClick={() =>
                                        setAiErrorById((prev) => ({
                                          ...prev,
                                          [finding.finding_id]: '',
                                        }))
                                      }
                                      className="text-rose-300 hover:text-white underline shrink-0 cursor-pointer"
                                    >
                                      Dismiss
                                    </button>
                                  </div>
                                )}

                              {/* Milestone 6: AI Explanation & Documentation Correction Panel */}
                              {!aiLoadingById[finding.finding_id] &&
                                aiExplanationsById[finding.finding_id] && (
                                  <div className="mt-3 p-4 rounded-xl bg-slate-900/95 border border-indigo-500/30 space-y-4 text-xs">
                                    <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-slate-800">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-200 border border-indigo-500/40 font-semibold">
                                          AI-Generated Explanation
                                        </span>
                                        <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-slate-950 text-cyan-300 border border-slate-800">
                                          Provider: {aiExplanationsById[finding.finding_id].provider.toUpperCase()} ({aiExplanationsById[finding.finding_id].model_name})
                                        </span>
                                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-950 text-slate-400 border border-slate-800">
                                          Deterministic Status Preserved: {aiExplanationsById[finding.finding_id].original_status}
                                        </span>
                                      </div>
                                      <span className="text-[11px] text-slate-400 italic">
                                        Advisory AI analysis — deterministic engine remains source of truth
                                      </span>
                                    </div>

                                    {/* Explanation & Code/Doc Breakdown */}
                                    <div className="space-y-2.5">
                                      <div>
                                        <span className="text-[10px] font-semibold uppercase tracking-wider text-indigo-300 block mb-1">
                                          Detailed Explanation
                                        </span>
                                        <p className="text-slate-200 leading-relaxed">
                                          {aiExplanationsById[finding.finding_id].explanation}
                                        </p>
                                      </div>

                                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                                        <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                                          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                                            Code Change Summary
                                          </span>
                                          <p className="text-slate-300">
                                            {aiExplanationsById[finding.finding_id].code_change_summary}
                                          </p>
                                        </div>
                                        <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                                          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                                            Documentation Issue
                                          </span>
                                          <p className="text-slate-300">
                                            {aiExplanationsById[finding.finding_id].documentation_issue}
                                          </p>
                                        </div>
                                      </div>
                                    </div>

                                    {/* AI-Generated Correction Suggestion vs Insufficient Evidence Warning */}
                                    <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
                                      <div className="flex flex-wrap items-center justify-between gap-2">
                                        <div className="flex items-center gap-2">
                                          <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-semibold">
                                            AI-Generated Correction Suggestion
                                          </span>
                                          <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-800">
                                            {aiExplanationsById[finding.finding_id].correction_status}
                                          </span>
                                        </div>

                                        {aiExplanationsById[finding.finding_id]
                                          .correction_available &&
                                          aiExplanationsById[finding.finding_id]
                                            .suggested_correction && (
                                            <button
                                              type="button"
                                              onClick={() =>
                                                handleCopySuggestion(
                                                  finding.finding_id,
                                                  aiExplanationsById[finding.finding_id]
                                                    .suggested_correction
                                                )
                                              }
                                              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-[11px] font-mono cursor-pointer"
                                            >
                                              {copiedFindingId === finding.finding_id
                                                ? 'Copied!'
                                                : 'Copy Suggestion'}
                                            </button>
                                          )}
                                      </div>

                                      {aiExplanationsById[finding.finding_id]
                                        .insufficient_evidence ||
                                      !aiExplanationsById[finding.finding_id]
                                        .correction_available ? (
                                        <div className="p-2.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs">
                                          <strong>Insufficient Evidence Warning:</strong> An automated documentation replacement cannot be safely proposed from the available static evidence. Manual author review is required.
                                        </div>
                                      ) : (
                                        <div className="space-y-1.5">
                                          <pre className="p-3 rounded bg-emerald-950/30 border border-emerald-500/30 font-mono text-xs text-emerald-200 whitespace-pre-wrap">
                                            {
                                              aiExplanationsById[finding.finding_id]
                                                .suggested_correction
                                            }
                                          </pre>
                                          <p className="text-[11px] text-slate-400">
                                            Proposal only — review manually before editing `{finding.documentation_file}`. DocGuard never modifies repository files automatically.
                                          </p>
                                        </div>
                                      )}
                                    </div>

                                    {/* Evidence Used & Limitations */}
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                      <div>
                                        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                                          Repository Evidence Referenced by AI
                                        </span>
                                        <ul className="list-disc list-inside text-slate-300 space-y-0.5 font-mono text-[11px]">
                                          {aiExplanationsById[
                                            finding.finding_id
                                          ].evidence_used.map((ev, idx) => (
                                            <li key={idx}>{ev}</li>
                                          ))}
                                        </ul>
                                      </div>
                                      {aiExplanationsById[finding.finding_id]
                                        .limitations?.length > 0 && (
                                        <div>
                                          <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-400 block mb-1">
                                            Notes & Limitations
                                          </span>
                                          <ul className="list-disc list-inside text-slate-300 space-y-0.5 text-[11px]">
                                            {aiExplanationsById[
                                              finding.finding_id
                                            ].limitations.map((lim, idx) => (
                                              <li key={idx}>{lim}</li>
                                            ))}
                                          </ul>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                )}

                              {/* Expanded Evidence View */}
                              {isExpanded && (
                                <div className="mt-3 pt-3 border-t border-slate-800/80 space-y-3 text-xs">
                                  {/* Original Documentation Text */}
                                  <div className="p-3 rounded-lg bg-slate-900 border border-slate-800">
                                    <span className="text-[10px] font-semibold uppercase tracking-wider text-cyan-400 block mb-1">
                                      Documentation Statement — {finding.documentation_file}:L{finding.documentation_line}
                                      {finding.documentation_section
                                        ? ` (Section: ${finding.documentation_section})`
                                        : ''}
                                    </span>
                                    <pre className="whitespace-pre-wrap font-mono text-xs text-slate-200 leading-relaxed">
                                      {finding.documentation_text}
                                    </pre>
                                    {finding.previous_documentation_text && (
                                      <div className="mt-2 pt-2 border-t border-slate-800">
                                        <span className="text-[10px] uppercase tracking-wider text-slate-400 block mb-0.5">
                                          Previous Base Commit Documentation Text:
                                        </span>
                                        <pre className="whitespace-pre-wrap font-mono text-xs text-slate-400">
                                          {finding.previous_documentation_text}
                                        </pre>
                                      </div>
                                    )}
                                  </div>

                                  {/* Old and New Code Evidence */}
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 font-mono">
                                    <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/25 text-rose-200 overflow-x-auto">
                                      <span className="text-[10px] font-semibold uppercase tracking-wider text-rose-400 block mb-1">
                                        Base Commit Code Evidence ({finding.source_file}
                                        {finding.old_source_line ? `:L${finding.old_source_line}` : ''})
                                      </span>
                                      <pre className="whitespace-pre-wrap text-xs">
                                        {finding.old_code_evidence}
                                      </pre>
                                    </div>
                                    <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/25 text-emerald-200 overflow-x-auto">
                                      <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400 block mb-1">
                                        Head Commit Code Evidence ({finding.source_file}
                                        {finding.source_line ? `:L${finding.source_line}` : ''})
                                      </span>
                                      <pre className="whitespace-pre-wrap text-xs">
                                        {finding.new_code_evidence}
                                      </pre>
                                    </div>
                                  </div>

                                  {/* Mapping Evidence & Suggested Action */}
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                    <div className="p-3 rounded-lg bg-slate-900/90 border border-slate-800">
                                      <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                                        Doc-to-Code Mapping Evidence
                                      </span>
                                      <ul className="list-disc list-inside text-slate-300 space-y-0.5">
                                        {finding.mapping_evidence.map((ev, idx) => (
                                          <li key={idx}>{ev}</li>
                                        ))}
                                      </ul>
                                    </div>
                                    <div className="p-3 rounded-lg bg-slate-900/90 border border-slate-800">
                                      <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-400 block mb-1">
                                        Recommended Action
                                      </span>
                                      <p className="text-slate-200">{finding.suggested_action}</p>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
