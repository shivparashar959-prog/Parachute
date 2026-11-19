/**
 * Frontend API Service for DocGuard Backend communication.
 * Uses Vite's development proxy (/api -> http://127.0.0.1:8000) by default,
 * with optional override via VITE_API_BASE_URL.
 *
 * Includes AbortController-based request timeouts and caller cancellation
 * support to prevent stale responses from overwriting state after repository
 * or commit selection changes.
 */

const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL || '';
export const DEFAULT_API_TIMEOUT_MS = 120_000;
export const HEALTH_API_TIMEOUT_MS = 15_000;

/**
 * Returns true if an error resulted from an intentional request cancellation
 * (e.g., when a user selects a new repository or commit while a previous request
 * was in flight), as opposed to a request timeout or server error.
 * @param {unknown} err
 * @returns {boolean}
 */
export function isRequestCancelledError(err) {
  if (!err || typeof err !== 'object') return false;
  if (err.isTimeout) return false;
  return err.isCancelled === true || err.name === 'AbortError';
}

export const isAbortError = isRequestCancelledError;

function createTimeoutError(endpoint, timeoutMs) {
  const seconds = Math.max(1, Math.round(timeoutMs / 1000));
  const error = new Error(
    `Request to ${endpoint} timed out after ${seconds}s. The operation took too long to respond.`
  );
  error.name = 'TimeoutError';
  error.isTimeout = true;
  return error;
}

function createCancelledError(endpoint) {
  const error = new Error(`Request to ${endpoint} was cancelled.`);
  error.name = 'AbortError';
  error.isCancelled = true;
  return error;
}

/**
 * Shared HTTP helper with AbortController-based timeout, external AbortSignal
 * chaining, consistent JSON parsing, and FastAPI error extraction.
 * @param {string} endpoint
 * @param {RequestInit & { timeoutMs?: number }} [options]
 */
async function apiRequest(endpoint, options = {}) {
  const {
    timeoutMs = DEFAULT_API_TIMEOUT_MS,
    signal: externalSignal,
    ...fetchOptions
  } = options;

  const controller = new AbortController();
  let timedOut = false;
  let externallyCancelled = false;

  const handleExternalAbort = () => {
    externallyCancelled = true;
    controller.abort();
  };

  if (externalSignal) {
    if (externalSignal.aborted) {
      externallyCancelled = true;
      controller.abort();
    } else {
      externalSignal.addEventListener('abort', handleExternalAbort, {
        once: true,
      });
    }
  }

  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(fetchOptions.body ? { 'Content-Type': 'application/json' } : {}),
        ...(fetchOptions.headers || {}),
      },
    });

    let payload = null;
    try {
      payload = await response.json();
    } catch (err) {
      if (timedOut || externallyCancelled || err?.name === 'AbortError') {
        throw err;
      }
      payload = null;
    }

    if (!response.ok) {
      const detail =
        payload && typeof payload.detail === 'string'
          ? payload.detail
          : Array.isArray(payload?.detail)
          ? payload.detail.map((d) => d.msg).join(', ')
          : `HTTP ${response.status}: ${response.statusText}`;
      throw new Error(detail);
    }

    return payload;
  } catch (err) {
    if (timedOut) {
      throw createTimeoutError(endpoint, timeoutMs);
    }
    if (externallyCancelled || err?.name === 'AbortError') {
      throw createCancelledError(endpoint);
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
    if (externalSignal) {
      externalSignal.removeEventListener('abort', handleExternalAbort);
    }
  }
}

/**
 * Fetches backend health status from GET /api/health.
 * @param {{ signal?: AbortSignal, timeoutMs?: number }} [reqOptions]
 * @returns {Promise<{status: string, application: string, version: string}>}
 */
export async function fetchBackendHealth(reqOptions = {}) {
  return apiRequest('/api/health', {
    method: 'GET',
    timeoutMs: reqOptions.timeoutMs ?? HEALTH_API_TIMEOUT_MS,
    signal: reqOptions.signal,
  });
}

/**
 * Inspects a public HTTPS GitHub repository and returns metadata + recent commits.
 * Calls POST /api/repositories/inspect.
 * @param {string} repositoryUrl
 * @param {{ signal?: AbortSignal, timeoutMs?: number }} [reqOptions]
 */
export async function inspectRepository(repositoryUrl, reqOptions = {}) {
  return apiRequest('/api/repositories/inspect', {
    method: 'POST',
    body: JSON.stringify({ repository_url: repositoryUrl }),
    timeoutMs: reqOptions.timeoutMs ?? DEFAULT_API_TIMEOUT_MS,
    signal: reqOptions.signal,
  });
}

/**
 * Compares two commits in a public HTTPS GitHub repository.
 * Calls POST /api/repositories/compare.
 * @param {{ repositoryUrl: string, baseCommit: string, headCommit: string, signal?: AbortSignal, timeoutMs?: number }} params
 */
export async function compareRepositoryCommits({
  repositoryUrl,
  baseCommit,
  headCommit,
  signal,
  timeoutMs,
}) {
  return apiRequest('/api/repositories/compare', {
    method: 'POST',
    body: JSON.stringify({
      repository_url: repositoryUrl,
      base_commit: baseCommit,
      head_commit: headCommit,
    }),
    signal,
    timeoutMs: timeoutMs ?? DEFAULT_API_TIMEOUT_MS,
  });
}

/**
 * Performs static Python AST code change analysis between two commits.
 * Calls POST /api/analyze/code.
 * @param {{ repositoryUrl: string, baseCommit: string, headCommit: string, signal?: AbortSignal, timeoutMs?: number }} params
 */
export async function analyzePythonCodeChanges({
  repositoryUrl,
  baseCommit,
  headCommit,
  signal,
  timeoutMs,
}) {
  return apiRequest('/api/analyze/code', {
    method: 'POST',
    body: JSON.stringify({
      repository_url: repositoryUrl,
      base_commit: baseCommit,
      head_commit: headCommit,
    }),
    signal,
    timeoutMs: timeoutMs ?? DEFAULT_API_TIMEOUT_MS,
  });
}

/**
 * Discovers, parses, and maps repository Markdown documentation to Python AST symbols.
 * Calls POST /api/analyze/documentation.
 * @param {{ repositoryUrl: string, baseCommit?: string, headCommit: string, signal?: AbortSignal, timeoutMs?: number }} params
 */
export async function analyzeRepositoryDocumentation({
  repositoryUrl,
  baseCommit,
  headCommit,
  signal,
  timeoutMs,
}) {
  return apiRequest('/api/analyze/documentation', {
    method: 'POST',
    body: JSON.stringify({
      repository_url: repositoryUrl,
      base_commit: baseCommit || null,
      head_commit: headCommit,
    }),
    signal,
    timeoutMs: timeoutMs ?? DEFAULT_API_TIMEOUT_MS,
  });
}

/**
 * Performs deterministic, evidence-based documentation drift detection between two commits.
 * Calls POST /api/analyze/drift.
 * @param {{ repositoryUrl: string, baseCommit: string, headCommit: string, signal?: AbortSignal, timeoutMs?: number }} params
 */
export async function analyzeDocumentationDrift({
  repositoryUrl,
  baseCommit,
  headCommit,
  signal,
  timeoutMs,
}) {
  return apiRequest('/api/analyze/drift', {
    method: 'POST',
    body: JSON.stringify({
      repository_url: repositoryUrl,
      base_commit: baseCommit,
      head_commit: headCommit,
    }),
    signal,
    timeoutMs: timeoutMs ?? DEFAULT_API_TIMEOUT_MS,
  });
}

/**
 * Fetches AI provider configuration status (Gemini vs Mock) from GET /api/analyze/explanations/providers.
 * @param {{ signal?: AbortSignal, timeoutMs?: number }} [reqOptions]
 */
export async function fetchAIProviderStatus(reqOptions = {}) {
  return apiRequest('/api/analyze/explanations/providers', {
    method: 'GET',
    timeoutMs: reqOptions.timeoutMs ?? HEALTH_API_TIMEOUT_MS,
    signal: reqOptions.signal,
  });
}

/**
 * Generates AI explanations and documentation fix suggestions for drift findings.
 * Calls POST /api/analyze/explanations.
 * @param {{
 *   repositoryUrl: string,
 *   baseCommit: string,
 *   headCommit: string,
 *   provider: 'mock' | 'gemini',
 *   findingIds?: string[],
 *   findings?: object[],
 *   signal?: AbortSignal,
 *   timeoutMs?: number
 * }} params
 */
export async function generateFindingAIExplanations({
  repositoryUrl,
  baseCommit,
  headCommit,
  provider = 'mock',
  findingIds = null,
  findings = null,
  signal,
  timeoutMs,
}) {
  return apiRequest('/api/analyze/explanations', {
    method: 'POST',
    body: JSON.stringify({
      repository_url: repositoryUrl,
      base_commit: baseCommit,
      head_commit: headCommit,
      provider,
      finding_ids: findingIds,
      findings,
    }),
    signal,
    timeoutMs: timeoutMs ?? DEFAULT_API_TIMEOUT_MS,
  });
}
