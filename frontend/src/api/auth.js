import {
  apiRequest,
  getApiUrl,
  HEALTH_API_TIMEOUT_MS,
} from './health.js';

export function fetchAuthStatus(reqOptions = {}) {
  return apiRequest('/api/auth/status', {
    method: 'GET',
    timeoutMs: reqOptions.timeoutMs ?? HEALTH_API_TIMEOUT_MS,
    signal: reqOptions.signal,
  });
}

export function fetchCurrentSession(reqOptions = {}) {
  return apiRequest('/api/auth/me', {
    method: 'GET',
    timeoutMs: reqOptions.timeoutMs ?? HEALTH_API_TIMEOUT_MS,
    signal: reqOptions.signal,
  });
}

export function logout(reqOptions = {}) {
  return apiRequest('/api/auth/logout', {
    method: 'POST',
    timeoutMs: reqOptions.timeoutMs ?? HEALTH_API_TIMEOUT_MS,
    signal: reqOptions.signal,
  });
}

export function exportAccountData(reqOptions = {}) {
  return apiRequest('/api/auth/export', {
    method: 'GET',
    timeoutMs: reqOptions.timeoutMs ?? HEALTH_API_TIMEOUT_MS,
    signal: reqOptions.signal,
  });
}

export function deleteAccount(reqOptions = {}) {
  return apiRequest('/api/auth/account', {
    method: 'DELETE',
    timeoutMs: reqOptions.timeoutMs ?? HEALTH_API_TIMEOUT_MS,
    signal: reqOptions.signal,
  });
}

export function startGitHubSignIn() {
  if (typeof window === 'undefined') return;
  window.location.assign(getApiUrl('/api/auth/login'));
}
