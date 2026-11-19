import assert from 'node:assert/strict';
import test from 'node:test';

import { createRequestGuardState } from './requestGuardState.js';

test('superseded requests cannot apply a stale response', () => {
  const guard = createRequestGuardState();
  const first = guard.start('docs');
  const second = guard.start('docs');

  assert.equal(first.signal.aborted, true);
  assert.equal(first.isCurrent(), false);
  assert.equal(second.isCurrent(), true);

  first.finish();
  assert.equal(second.isCurrent(), true);
});

test('cancelAnalysis invalidates analysis requests but preserves health requests', () => {
  const guard = createRequestGuardState();
  const health = guard.start('health');
  const analysis = guard.start('drift');

  guard.cancelAnalysis();

  assert.equal(analysis.signal.aborted, true);
  assert.equal(analysis.isCurrent(), false);
  assert.equal(health.isCurrent(), true);
});
