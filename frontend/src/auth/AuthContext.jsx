import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  fetchAuthStatus,
  fetchCurrentSession,
  logout as logoutRequest,
} from '../api/auth.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [loading, setLoading] = useState(true);
  const [session, setSession] = useState(null);
  const [signInEnabled, setSignInEnabled] = useState(false);
  const [error, setError] = useState('');
  const [signOutLoading, setSignOutLoading] = useState(false);

  const refresh = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    let statusError = '';
    try {
      const status = await fetchAuthStatus({ signal });
      setSignInEnabled(status?.sign_in_enabled === true);
    } catch (requestError) {
      if (requestError?.name === 'AbortError') return;
      statusError =
        requestError instanceof Error
          ? requestError.message
          : 'Could not check sign-in availability.';
      setSignInEnabled(false);
    }

    try {
      const currentSession = await fetchCurrentSession({ signal });
      if (signal?.aborted) return;
      setSession(currentSession);
      setError('');
    } catch (requestError) {
      if (requestError?.name === 'AbortError') return;
      setSession(null);
      setError(
        requestError?.status === 401
          ? statusError
          : requestError instanceof Error
            ? requestError.message
            : 'Could not load the current account session.'
      );
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const handleSessionExpired = () => {
      setSession(null);
      setError('Your session expired. Sign in again to continue.');
    };
    window.addEventListener('docguard:session-expired', handleSessionExpired);
    refresh(controller.signal);
    return () => {
      controller.abort();
      window.removeEventListener(
        'docguard:session-expired',
        handleSessionExpired
      );
    };
  }, [refresh]);

  const signOut = useCallback(async () => {
    setSignOutLoading(true);
    setError('');
    try {
      await logoutRequest();
      setSession(null);
      return true;
    } catch (requestError) {
      if (requestError?.status === 401) {
        setSession(null);
        return true;
      }
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Could not sign out.'
      );
      return false;
    } finally {
      setSignOutLoading(false);
    }
  }, []);

  const value = useMemo(
    () => ({
      loading,
      session,
      signInEnabled,
      error,
      signOutLoading,
      refresh,
      signOut,
    }),
    [loading, session, signInEnabled, error, signOutLoading, refresh, signOut]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuth must be used within AuthProvider.');
  }
  return value;
}
