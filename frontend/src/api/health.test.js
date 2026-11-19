import assert from 'node:assert/strict';
import test from 'node:test';

import {
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
