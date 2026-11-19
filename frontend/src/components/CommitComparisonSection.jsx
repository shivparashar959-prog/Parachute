const CHANGE_BADGE_STYLES = {
  added: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  modified: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  deleted: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  renamed: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
};

function DiffLinesView({ patch, isBinary }) {
  if (isBinary) {
    return (
      <div className="p-6 text-center text-xs text-slate-400 font-mono">
        Binary file changed — text diff preview is not available.
      </div>
    );
  }

  if (!patch || !patch.trim()) {
    return (
      <div className="p-6 text-center text-xs text-slate-400 font-mono">
        No line-level textual differences for this file (e.g., pure file rename or mode change).
      </div>
    );
  }

  const lines = patch.split('\n');

  return (
    <div className="overflow-x-auto font-mono text-xs leading-relaxed">
      {lines.map((line, index) => {
        const isAddition = line.startsWith('+') && !line.startsWith('+++');
        const isDeletion = line.startsWith('-') && !line.startsWith('---');
        const isHunkHeader = line.startsWith('@@');

        let rowClass = 'text-slate-300 hover:bg-slate-900/60';
        if (isAddition) {
          rowClass =
            'bg-emerald-500/15 text-emerald-200 border-l-2 border-emerald-400';
        } else if (isDeletion) {
          rowClass =
            'bg-rose-500/15 text-rose-200 border-l-2 border-rose-400';
        } else if (isHunkHeader) {
          rowClass = 'bg-indigo-500/10 text-indigo-300 font-semibold';
        }

        return (
          <div
            key={index}
            className={`px-4 py-0.5 whitespace-pre flex items-start gap-3 ${rowClass}`}
          >
            <span className="w-9 shrink-0 select-none text-right text-[10px] text-slate-500 pr-2 border-r border-slate-800/80">
              {index + 1}
            </span>
            <span className="flex-1">{line || ' '}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function CommitComparisonSection({
  compareResult,
  selectedFileIndex,
  onSelectFileIndex,
}) {
  if (!compareResult) return null;

  const selectedFile =
    compareResult.files && compareResult.files[selectedFileIndex]
      ? compareResult.files[selectedFileIndex]
      : null;

  return (
    <section
      aria-label="Commit Comparison Results"
      className="rounded-xl bg-slate-900/70 border border-slate-800 p-6 space-y-6"
    >
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h3 className="text-base font-semibold text-white">
            Commit Comparison & Diff Explorer
          </h3>
          <p className="text-xs text-slate-400 mt-0.5 font-mono">
            {compareResult.owner}/{compareResult.name}:{' '}
            <span className="text-indigo-300">
              {compareResult.base_commit.slice(0, 7)}
            </span>{' '}
            →{' '}
            <span className="text-emerald-300">
              {compareResult.head_commit.slice(0, 7)}
            </span>
          </p>
        </div>

        {/* Summary Stat Badges */}
        <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
          <span className="px-2.5 py-1 rounded-md bg-slate-800 text-slate-200 border border-slate-700">
            {compareResult.total_changed_files} changed files
          </span>
          <span className="px-2.5 py-1 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
            +{compareResult.total_additions} additions
          </span>
          <span className="px-2.5 py-1 rounded-md bg-rose-500/15 text-rose-300 border border-rose-500/30">
            -{compareResult.total_deletions} deletions
          </span>
          {compareResult.added_files.length > 0 && (
            <span className="px-2 py-1 rounded bg-emerald-500/10 text-emerald-300">
              {compareResult.added_files.length} added
            </span>
          )}
          {compareResult.modified_files.length > 0 && (
            <span className="px-2 py-1 rounded bg-amber-500/10 text-amber-300">
              {compareResult.modified_files.length} modified
            </span>
          )}
          {compareResult.deleted_files.length > 0 && (
            <span className="px-2 py-1 rounded bg-rose-500/10 text-rose-300">
              {compareResult.deleted_files.length} deleted
            </span>
          )}
          {compareResult.renamed_files.length > 0 && (
            <span className="px-2 py-1 rounded bg-cyan-500/10 text-cyan-300">
              {compareResult.renamed_files.length} renamed
            </span>
          )}
        </div>
      </div>

      {compareResult.diff_truncated && (
        <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs">
          Large diff detected: some patch contents were truncated to preserve browser responsiveness.
        </div>
      )}

      {compareResult.files.length === 0 ? (
        <div className="py-10 text-center text-sm text-slate-400">
          No file changes found between these two commits.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column: Changed Files List */}
          <div className="rounded-xl bg-slate-950 border border-slate-800 overflow-hidden flex flex-col max-h-[540px]">
            <div className="px-4 py-3 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Changed Files ({compareResult.files.length})
              </span>
            </div>
            <ul className="divide-y divide-slate-800/70 overflow-y-auto">
              {compareResult.files.map((file, idx) => {
                const isSelected = idx === selectedFileIndex;
                const badgeClass =
                  CHANGE_BADGE_STYLES[file.change_type] ||
                  CHANGE_BADGE_STYLES.modified;

                return (
                  <li key={`${file.file_path}-${idx}`}>
                    <button
                      type="button"
                      onClick={() => onSelectFileIndex(idx)}
                      className={`w-full text-left px-4 py-3 transition-colors flex items-start justify-between gap-2 cursor-pointer ${
                        isSelected
                          ? 'bg-indigo-600/15 border-l-2 border-indigo-400'
                          : 'hover:bg-slate-900/60'
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-mono text-slate-200 break-all">
                          {file.previous_path
                            ? `${file.previous_path} → ${file.file_path}`
                            : file.file_path}
                        </p>
                        <div className="mt-1.5 flex items-center gap-2">
                          <span
                            className={`text-[10px] uppercase font-mono px-1.5 py-0.5 rounded border ${badgeClass}`}
                          >
                            {file.change_type}
                          </span>
                          <span className="text-[11px] font-mono text-emerald-400">
                            +{file.additions}
                          </span>
                          <span className="text-[11px] font-mono text-rose-400">
                            -{file.deletions}
                          </span>
                        </div>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* Right 2 columns: Unified Diff Patch Preview */}
          <div className="lg:col-span-2 rounded-xl bg-slate-950 border border-slate-800 overflow-hidden flex flex-col max-h-[540px]">
            {selectedFile && (
              <>
                <div className="px-4 py-3 bg-slate-900/90 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className={`text-[10px] uppercase font-mono px-2 py-0.5 rounded border ${
                        CHANGE_BADGE_STYLES[selectedFile.change_type] ||
                        CHANGE_BADGE_STYLES.modified
                      }`}
                    >
                      {selectedFile.change_type}
                    </span>
                    <span className="text-xs font-mono text-white truncate">
                      {selectedFile.previous_path
                        ? `${selectedFile.previous_path} → ${selectedFile.file_path}`
                        : selectedFile.file_path}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs font-mono">
                    <span className="text-emerald-400">
                      +{selectedFile.additions}
                    </span>
                    <span className="text-rose-400">
                      -{selectedFile.deletions}
                    </span>
                  </div>
                </div>

                <div className="overflow-y-auto flex-1 py-2">
                  <DiffLinesView
                    patch={selectedFile.patch}
                    isBinary={selectedFile.is_binary}
                  />
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
