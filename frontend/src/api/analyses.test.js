import assert from 'node:assert/strict';
import test from 'node:test';

import {
  deleteAnalysis,
  fetchAnalysisHistory,
  retryAnalysis,
} from './analyses.js';

test('analysis history is paginated through the authenticated API client', async () => {
  const originalFetch = globalThis.fetch;
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => ({ items: [], total_count: 0 }) };
  };

  try {
    await fetchAnalysisHistory({ limit: 10, offset: 20 });
    assert.equal(request.url, '/api/analyses?limit=10&offset=20');
    assert.equal(request.options.method, 'GET');
    assert.equal(request.options.credentials, 'include');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('retry and delete use analysis IDs and cookie-authenticated state changes', async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return { ok: true, json: async () => ({ analysis_id: 'new-job' }) };
  };

  try {
    await retryAnalysis('private/id');
    await deleteAnalysis('private/id');
    assert.equal(
      requests[0].url,
      '/api/analyses/private%2Fid/retry'
    );
    assert.equal(requests[0].options.method, 'POST');
    assert.equal(requests[1].url, '/api/analyses/private%2Fid');
    assert.equal(requests[1].options.method, 'DELETE');
    assert.equal(requests[1].options.credentials, 'include');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('a protected API 401 broadcasts session expiry', async () => {
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  const events = [];
  globalThis.window = {
    dispatchEvent(event) {
      events.push(event.type);
    },
  };
  globalThis.fetch = async () => ({
    ok: false,
    status: 401,
    statusText: 'Unauthorized',
    json: async () => ({ detail: 'Authentication required.' }),
  });

  try {
    await assert.rejects(fetchAnalysisHistory(), (error) => {
      assert.equal(error.status, 401);
      return true;
    });
    assert.deepEqual(events, ['docguard:session-expired']);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});
