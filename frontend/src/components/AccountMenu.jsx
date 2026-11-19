import { useState } from 'react';
import { deleteAccount, exportAccountData } from '../api/auth.js';

export default function AccountMenu({ session, loading, error, onSignOut }) {
  const [privacyLoading, setPrivacyLoading] = useState(false);
  const [privacyError, setPrivacyError] = useState('');

  const handleExport = async () => {
    setPrivacyLoading(true);
    setPrivacyError('');
    try {
      const data = await exportAccountData();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'docguard-export.json';
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (exportError) {
      setPrivacyError(
        exportError instanceof Error ? exportError.message : 'Could not export account data.'
      );
    } finally {
      setPrivacyLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Delete this DocGuard account and workspace? This cannot be undone.')) {
      return;
    }
    setPrivacyLoading(true);
    setPrivacyError('');
    try {
      await deleteAccount();
      window.location.assign('/');
    } catch (deleteError) {
      setPrivacyError(
        deleteError instanceof Error ? deleteError.message : 'Could not delete account.'
      );
    } finally {
      setPrivacyLoading(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="text-right">
        <p className="text-sm font-medium text-slate-200">
          {session.user.display_name}
        </p>
        <p className="text-xs text-slate-400">
          {session.workspace.name} · {session.workspace.role}
        </p>
      </div>
      <button
        type="button"
        onClick={onSignOut}
        disabled={loading}
        className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading ? 'Signing out...' : 'Sign out'}
      </button>
      <button
        type="button"
        onClick={handleExport}
        disabled={privacyLoading}
        className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-60"
      >
        Export data
      </button>
      <button
        type="button"
        onClick={handleDelete}
        disabled={privacyLoading}
        className="rounded-lg border border-rose-800 px-3 py-1.5 text-xs text-rose-300 hover:bg-rose-950 disabled:opacity-60"
      >
        Delete account
      </button>
      {error && (
        <p role="alert" className="w-full text-right text-xs text-rose-300">
          {error}
        </p>
      )}
      {privacyError && (
        <p role="alert" className="w-full text-right text-xs text-rose-300">
          {privacyError}
        </p>
      )}
    </div>
  );
}
