import assert from 'node:assert/strict';
import test from 'node:test';

import {
  deleteAccount,
  exportAccountData,
  fetchAuthStatus,
  fetchCurrentSession,
  logout,
  registerAccount,
  signInWithPassword,
  startGitHubSignIn,
} from './auth.js';

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

test('export and account deletion use credentialed privacy endpoints', async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      async json() {
        return {};
      },
    };
  };

  try {
    await exportAccountData();
    await deleteAccount();
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls[0].url, '/api/auth/export');
  assert.equal(calls[0].options.method, 'GET');
  assert.equal(calls[0].options.credentials, 'include');
  assert.equal(calls[1].url, '/api/auth/account');
  assert.equal(calls[1].options.method, 'DELETE');
  assert.equal(calls[1].options.credentials, 'include');
});

test('local registration and password sign-in send credentialed JSON requests', async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, async json() { return { ok: true }; } };
  };

  try {
    await registerAccount({
      name: 'Local User',
      email: 'local@example.com',
      password: 'a-very-strong-password',
    });
    await signInWithPassword({
      email: 'local@example.com',
      password: 'a-very-strong-password',
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls[0].url, '/api/auth/register');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.credentials, 'include');
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    name: 'Local User',
    email: 'local@example.com',
    password: 'a-very-strong-password',
  });
  assert.equal(calls[1].url, '/api/auth/login');
  assert.equal(calls[1].options.method, 'POST');
  assert.equal(calls[1].options.credentials, 'include');
});
