/**
 * Frontend API Service for DocGuard Backend communication.
 * Uses Vite's development proxy (/api -> http://127.0.0.1:8000) by default,
 * with optional override via VITE_API_BASE_URL.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

/**
 * Shared HTTP helper with consistent JSON parsing and FastAPI error extraction.
 * @param {string} endpoint
 * @param {RequestInit} [options]
 */
async function apiRequest(endpoint, options = {}) {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
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
}

/**
 * Fetches backend health status from GET /api/health.
 * @returns {Promise<{status: string, application: string, version: string}>}
 */
export async function fetchBackendHealth() {
  return apiRequest('/api/health', { method: 'GET' });
}

/**
 * Inspects a public HTTPS GitHub repository and returns metadata + recent commits.
 * Calls POST /api/repositories/inspect.
 * @param {string} repositoryUrl
 */
export async function inspectRepository(repositoryUrl) {
  return apiRequest('/api/repositories/inspect', {
    method: 'POST',
    body: JSON.stringify({ repository_url: repositoryUrl }),
  });
}

/**
 * Compares two commits in a public HTTPS GitHub repository.
 * Calls POST /api/repositories/compare.
 * @param {{ repositoryUrl: string, baseCommit: string, headCommit: string }} params
 */
export async function compareRepositoryCommits({
  repositoryUrl,
  baseCommit,
  headCommit,
}) {
  return apiRequest('/api/repositories/compare', {
    method: 'POST',
    body: JSON.stringify({
      repository_url: repositoryUrl,
      base_commit: baseCommit,
      head_commit: headCommit,
    }),
  });
}

/**
 * Performs static Python AST code change analysis between two commits.
 * Calls POST /api/analyze/code.
 * @param {{ repositoryUrl: string, baseCommit: string, headCommit: string }} params
 */
export async function analyzePythonCodeChanges({
  repositoryUrl,
  baseCommit,
  headCommit,
}) {
  return apiRequest('/api/analyze/code', {
    method: 'POST',
    body: JSON.stringify({
      repository_url: repositoryUrl,
      base_commit: baseCommit,
      head_commit: headCommit,
    }),
  });
}

/**
 * Discovers, parses, and maps repository Markdown documentation to Python AST symbols.
 * Calls POST /api/analyze/documentation.
 * @param {{ repositoryUrl: string, baseCommit?: string, headCommit: string }} params
 */
export async function analyzeRepositoryDocumentation({
  repositoryUrl,
  baseCommit,
  headCommit,
}) {
  return apiRequest('/api/analyze/documentation', {
    method: 'POST',
    body: JSON.stringify({
      repository_url: repositoryUrl,
      base_commit: baseCommit || null,
      head_commit: headCommit,
    }),
  });
}

/**
 * Performs deterministic, evidence-based documentation drift detection between two commits.
 * Calls POST /api/analyze/drift.
 * @param {{ repositoryUrl: string, baseCommit: string, headCommit: string }} params
 */
export async function analyzeDocumentationDrift({
  repositoryUrl,
  baseCommit,
  headCommit,
}) {
  return apiRequest('/api/analyze/drift', {
    method: 'POST',
    body: JSON.stringify({
      repository_url: repositoryUrl,
      base_commit: baseCommit,
      head_commit: headCommit,
    }),
  });
}

/**
 * Fetches AI provider configuration status (Gemini vs Mock) from GET /api/analyze/explanations/providers.
 */
export async function fetchAIProviderStatus() {
  return apiRequest('/api/analyze/explanations/providers', {
    method: 'GET',
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
 *   findings?: object[]
 * }} params
 */
export async function generateFindingAIExplanations({
  repositoryUrl,
  baseCommit,
  headCommit,
  provider = 'mock',
  findingIds = null,
  findings = null,
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
  });
}
