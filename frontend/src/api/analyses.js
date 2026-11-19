import { apiRequest, DEFAULT_API_TIMEOUT_MS } from './health.js';

export function fetchAnalysisHistory({
  limit = 20,
  offset = 0,
  signal,
} = {}) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiRequest(`/api/analyses?${query}`, {
    method: 'GET',
    signal,
  });
}

export function retryAnalysis(analysisId, reqOptions = {}) {
  return apiRequest(
    `/api/analyses/${encodeURIComponent(analysisId)}/retry`,
    {
      method: 'POST',
      signal: reqOptions.signal,
      timeoutMs: reqOptions.timeoutMs ?? DEFAULT_API_TIMEOUT_MS,
    }
  );
}

export function deleteAnalysis(analysisId, reqOptions = {}) {
  return apiRequest(`/api/analyses/${encodeURIComponent(analysisId)}`, {
    method: 'DELETE',
    signal: reqOptions.signal,
    timeoutMs: reqOptions.timeoutMs ?? DEFAULT_API_TIMEOUT_MS,
  });
}
