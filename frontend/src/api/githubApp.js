import { apiRequest, DEFAULT_API_TIMEOUT_MS } from './health.js';

export function fetchGitHubAppStatus(reqOptions = {}) {
  return apiRequest('/api/github/status', {
    method: 'GET',
    timeoutMs: reqOptions.timeoutMs ?? DEFAULT_API_TIMEOUT_MS,
    signal: reqOptions.signal,
  });
}

export function fetchAuthorizedRepositories(reqOptions = {}) {
  return apiRequest('/api/github/repositories', {
    method: 'GET',
    timeoutMs: reqOptions.timeoutMs ?? DEFAULT_API_TIMEOUT_MS,
    signal: reqOptions.signal,
  });
}

export function fetchRepositoryPullRequests(
  githubRepositoryId,
  reqOptions = {}
) {
  return apiRequest(
    `/api/github/repositories/${encodeURIComponent(githubRepositoryId)}/pull-requests`,
    {
      method: 'GET',
      timeoutMs: reqOptions.timeoutMs ?? DEFAULT_API_TIMEOUT_MS,
      signal: reqOptions.signal,
    }
  );
}

export function createGitHubAppInstallation(reqOptions = {}) {
  return apiRequest('/api/github/installations/start', {
    method: 'POST',
    timeoutMs: reqOptions.timeoutMs ?? DEFAULT_API_TIMEOUT_MS,
    signal: reqOptions.signal,
  });
}
