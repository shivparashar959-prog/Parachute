import { useEffect, useRef } from 'react';
import { createRequestGuardState } from './requestGuardState.js';

/**
 * Guards async requests against stale responses and provides per-key and
 * group-level AbortController cancellation.
 *
 * `start(key)` aborts any in-flight request that used the same key and returns:
 *   - signal:    pass to the API call so the HTTP request is cancelled on abort
 *   - isCurrent: false once this request was superseded, cancelled, or `cancelAll()` ran
 *   - finish:    releases the request's bookkeeping
 *
 * `cancelAnalysis()` aborts all in-flight analysis requests (`compare`, `ast`,
 * `docs`, `drift`, `ai:*`) when the user changes Base or Head commit selection.
 *
 * `cancelAll()` aborts everything in flight, e.g. when the user connects a
 * different repository or unmounts the component.
 */
export function useRequestGuard() {
  const guardRef = useRef(null);
  if (guardRef.current === null) {
    guardRef.current = createRequestGuardState();
  }

  const guard = guardRef.current;
  useEffect(() => guard.cancelAll, [guard]);

  return guard;
}
