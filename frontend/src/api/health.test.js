import assert from 'node:assert/strict';
import test from 'node:test';

import {
  analyzeDocumentationDrift,
  cancelAnalysis,
  fetchAnalysisStatus,
  generateFindingAIExplanations,
  fetchBackendHealth,
  isRequestCancelledError,
} from './health.js';

function responseWithAbortableBody(signal) {
  return {
    ok: true,
    json() {
      return new Promise((resolve, reject) => {
        signal.addEventListener(
          'abort',
          () => {
            const error = new Error('The response body was aborted.');
            error.name = 'AbortError';
            reject(error);
          },
          { once: true }
        );
      });
    },
  };
}

test('request timeout remains active while parsing the response body', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (_url, options) =>
    responseWithAbortableBody(options.signal);

  try {
    await assert.rejects(fetchBackendHealth({ timeoutMs: 20 }), (error) => {
      assert.equal(error.name, 'TimeoutError');
      assert.equal(error.isTimeout, true);
      assert.equal(isRequestCancelledError(error), false);
      return true;
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('caller cancellation aborts response-body parsing', async () => {
  const originalFetch = globalThis.fetch;
  const caller = new AbortController();
  globalThis.fetch = async (_url, options) =>
    responseWithAbortableBody(options.signal);

  try {
    const request = fetchBackendHealth({
      signal: caller.signal,
      timeoutMs: 1000,
    });
    setTimeout(() => caller.abort(), 20);

    await assert.rejects(request, (error) => {
      assert.equal(error.name, 'AbortError');
      assert.equal(error.isCancelled, true);
      assert.equal(isRequestCancelledError(error), true);
      return true;
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('AI explanation request sends analysis and finding IDs, not client findings', async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl;
  let requestOptions;
  globalThis.fetch = async (url, options) => {
    requestUrl = url;
    requestOptions = options;
    return { ok: true, json: async () => ({}) };
  };

  try {
    await generateFindingAIExplanations({
      analysisId: 'analysis-123',
      provider: 'gemini',
      findingIds: ['finding-1'],
    });

    assert.equal(requestUrl, '/api/analyze/explanations');
    assert.deepEqual(JSON.parse(requestOptions.body), {
      analysis_id: 'analysis-123',
      provider: 'gemini',
      finding_ids: ['finding-1'],
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('analysis requests enqueue, poll, and cancel by persisted analysis ID', async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return { ok: true, json: async () => ({ status: 'queued' }) };
  };

  try {
    await analyzeDocumentationDrift({
      githubRepositoryId: 123,
      baseCommit: 'a'.repeat(40),
      headCommit: 'b'.repeat(40),
      idempotencyKey: 'frontend-idempotency-key-01',
    });
    await fetchAnalysisStatus('analysis/123');
    await cancelAnalysis('analysis/123');

    assert.equal(requests[0].url, '/api/analyses');
    assert.equal(requests[0].options.headers['Idempotency-Key'], 'frontend-idempotency-key-01');
    assert.equal(requests[1].url, '/api/analyses/analysis%2F123/status');
    assert.equal(requests[2].url, '/api/analyses/analysis%2F123/cancel');
    assert.equal(requests[2].options.method, 'POST');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
