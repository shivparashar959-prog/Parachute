import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createGitHubAppInstallation,
  fetchAuthorizedRepositories,
  fetchGitHubAppStatus,
  fetchRepositoryPullRequests,
} from './githubApp.js';

test('GitHub App APIs use credentialed same-origin requests', async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true,
      json: async () => (url.endsWith('/installations/start')
        ? { installation_url: 'https://github.com/apps/docguard/installations/new' }
        : {}),
    };
  };

  try {
    await fetchGitHubAppStatus();
    await fetchAuthorizedRepositories();
    await fetchRepositoryPullRequests(123);
    await createGitHubAppInstallation();
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(
    requests.map(({ url }) => url),
    [
      '/api/github/status',
      '/api/github/repositories',
      '/api/github/repositories/123/pull-requests',
      '/api/github/installations/start',
    ]
  );
  assert.ok(requests.every(({ options }) => options.credentials === 'include'));
  assert.equal(requests[3].options.method, 'POST');
  assert.equal('body' in requests[3].options, false);
});
