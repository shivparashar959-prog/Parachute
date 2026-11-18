/**
 * Frontend API Service for DocGuard Backend communication.
 * Uses Vite's development proxy (/api -> http://127.0.0.1:8000) by default,
 * with optional override via VITE_API_BASE_URL.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

/**
 * Fetches backend health status from GET /api/health.
 * @returns {Promise<{status: string, application: string, version: string}>}
 */
export async function fetchBackendHealth() {
  const response = await fetch(`${API_BASE_URL}/api/health`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}
