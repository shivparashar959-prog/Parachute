import { useState, useCallback, useEffect } from 'react';
import {
  BrowserRouter,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import {
  fetchBackendHealth,
  fetchAIProviderStatus,
  isRequestCancelledError,
} from './api/health.js';
import {
  registerAccount,
  signInWithPassword,
  startGitHubSignIn,
} from './api/auth.js';
import AnalysisPage from './AnalysisPage.jsx';
import AnalysisHistoryPage from './pages/AnalysisHistoryPage.jsx';
import AnalysisDetailPage from './pages/AnalysisDetailPage.jsx';
import { AuthProvider, useAuth } from './auth/AuthContext.jsx';
import AccountMenu from './components/AccountMenu.jsx';
import SignInScreen from './components/SignInScreen.jsx';
import Sidebar from './components/Sidebar.jsx';

function SessionLoading() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 p-6 text-slate-100">
      <p role="status" className="text-sm text-slate-300">
        Checking your secure session...
      </p>
    </main>
  );
}

function PublicLandingPage() {
  const {
    loading,
    session,
    signInEnabled,
    githubOAuthEnabled,
    error,
    refresh,
  } = useAuth();

  if (loading) return <SessionLoading />;
  if (session) return <Navigate to="/dashboard/analyze" replace />;

  return (
    <SignInScreen
      loading={false}
      signInEnabled={signInEnabled}
      githubOAuthEnabled={githubOAuthEnabled}
      error={error}
      onAuthenticate={async (mode, credentials) => {
        if (mode === 'register') await registerAccount(credentials);
        else await signInWithPassword(credentials);
        await refresh();
      }}
      onGitHubSignIn={startGitHubSignIn}
      onRetry={() => refresh()}
    />
  );
}

function RequireSession() {
  const { loading, session } = useAuth();
  const location = useLocation();
  if (loading) return <SessionLoading />;
  if (!session) {
    return (
      <Navigate
        to="/signin"
        replace
        state={{ from: location }}
      />
    );
  }
  return <Outlet />;
}

function DashboardLayout() {
  const {
    session,
    signOut,
    signOutLoading,
    error: authError,
  } = useAuth();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [healthState, setHealthState] = useState('checking');
  const [healthData, setHealthData] = useState(null);
  const [healthError, setHealthError] = useState('');
  const [lastChecked, setLastChecked] = useState(null);
  const [aiProviderInfo, setAiProviderInfo] = useState(null);
  const [healthRequestLoading, setHealthRequestLoading] = useState(false);

  const checkBackendHealth = useCallback(async () => {
    setHealthRequestLoading(true);
    setHealthState('checking');
    setHealthError('');
    try {
      const data = await fetchBackendHealth();
      setHealthData(data);
      if (data?.status !== 'ok') {
        throw new Error('Unexpected response from the backend health endpoint.');
      }
      setHealthState('connected');
      try {
        setAiProviderInfo(await fetchAIProviderStatus());
      } catch {
        setAiProviderInfo(null);
      }
    } catch (requestError) {
      if (!isRequestCancelledError(requestError)) {
        setHealthState('disconnected');
        setHealthError(
          requestError instanceof Error
            ? requestError.message
            : 'Unable to reach the backend.'
        );
      }
    } finally {
      setLastChecked(new Date().toLocaleTimeString());
      setHealthRequestLoading(false);
    }
  }, []);

  useEffect(() => {
    checkBackendHealth();
  }, [checkBackendHealth]);

  const handleSignOut = async () => {
    if (await signOut()) navigate('/signin', { replace: true });
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 lg:flex">
      <Sidebar
        mobileMenuOpen={mobileMenuOpen}
        setMobileMenuOpen={setMobileMenuOpen}
        healthState={healthState}
        healthData={healthData}
        healthError={healthError}
        lastChecked={lastChecked}
        onRefreshHealth={checkBackendHealth}
      />
      <main className="min-w-0 flex-1">
        <header className="flex flex-col gap-4 border-b border-slate-800 bg-slate-900/40 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="min-w-0">
            <h1 className="text-lg font-bold tracking-tight text-white">
              DocGuard dashboard
            </h1>
            <p className="text-xs text-slate-400">
              Evidence-based documentation drift analysis
              {healthRequestLoading ? ' · Checking services...' : ''}
            </p>
          </div>
          <AccountMenu
            session={session}
            loading={signOutLoading}
            error={authError}
            onSignOut={handleSignOut}
          />
        </header>
        <Outlet
          context={{
            healthState,
            healthData,
            healthError,
            checkBackendHealth,
            aiProviderInfo,
          }}
        />
      </main>
    </div>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<PublicLandingPage />} />
      <Route path="/signin" element={<PublicLandingPage />} />
      <Route element={<RequireSession />}>
        <Route path="/dashboard" element={<DashboardLayout />}>
          <Route index element={<Navigate to="analyze" replace />} />
          <Route path="analyze" element={<AnalysisPage />} />
          <Route path="history" element={<AnalysisHistoryPage />} />
          <Route
            path="history/:analysisId"
            element={<AnalysisDetailPage />}
          />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
