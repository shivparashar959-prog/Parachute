import assert from 'node:assert/strict';
import test from 'node:test';

import { fetchAuthStatus, fetchCurrentSession, logout, startGitHubSignIn } from './auth.js';

test('session requests send credentialed cookies', async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      async json() {
        return { sign_in_enabled: true };
      },
    };
  };

  try {
    await fetchAuthStatus();
    await fetchCurrentSession();
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls.length, 2);
  assert.equal(calls[0].options.credentials, 'include');
  assert.equal(calls[1].options.credentials, 'include');
  assert.equal(calls[0].url, '/api/auth/status');
  assert.equal(calls[1].url, '/api/auth/me');
});

test('logout is a credentialed POST and sign-in navigates to the backend OAuth route', async () => {
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  let call;
  let navigatedTo;
  globalThis.fetch = async (url, options) => {
    call = { url, options };
    return { ok: true, async json() { return null; } };
  };
  globalThis.window = {
    location: {
      assign(url) {
        navigatedTo = url;
      },
    },
  };

  try {
    await logout();
    startGitHubSignIn();
  } finally {
    globalThis.fetch = originalFetch;
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
  }

  assert.equal(call.url, '/api/auth/logout');
  assert.equal(call.options.method, 'POST');
  assert.equal(call.options.credentials, 'include');
  assert.equal(navigatedTo, '/api/auth/login');
});
