import DocumentationMappingCard from './DocumentationMappingCard';

const DOC_FILTER_TABS = [
  { id: 'ALL', label: 'All Mappings' },
  { id: 'HIGH', label: 'High Confidence' },
  { id: 'MEDIUM', label: 'Medium Confidence' },
  { id: 'LOW', label: 'Low Confidence' },
  { id: 'AMBIGUOUS', label: 'Ambiguous' },
  { id: 'UNMAPPED', label: 'Unmapped' },
];

export default function DocumentationMapSection({
  repoInfo,
  headCommit,
  canAnalyzeDocs,
  docLoading,
  docError,
  onDismissDocError,
  docResult,
  docFilter,
  onDocFilterChange,
  expandedMappings,
  onToggleMappingExpanded,
  onAnalyzeDocumentation,
}) {
  const filteredDocMappings = (docResult?.mappings || []).filter((m) => {
    if (docFilter === 'ALL') return true;
    if (docFilter === 'UNMAPPED') return m.mapping_status === 'UNMAPPED';
    if (docFilter === 'AMBIGUOUS') return m.mapping_status === 'AMBIGUOUS';
    if (docFilter === 'HIGH') return m.highest_confidence === 'HIGH';
    if (docFilter === 'MEDIUM') return m.highest_confidence === 'MEDIUM';
    if (docFilter === 'LOW') return m.highest_confidence === 'LOW';
    return true;
  });

  return (
    <section
      aria-label="DOCUMENTATION MAP"
      className="rounded-xl bg-slate-900/70 border border-slate-800 p-6 space-y-6"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2.5">
            <h3 className="text-base font-bold tracking-wide uppercase text-white">
              DOCUMENTATION MAP
            </h3>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
              Milestone 4 Doc-to-Code Engine
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Discovers Markdown documentation at HEAD commit, extracts structured statements, and maps them to Python AST symbols with confidence and evidence.
          </p>
        </div>

        <button
          type="button"
          onClick={onAnalyzeDocumentation}
          disabled={!canAnalyzeDocs}
          className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-xs shadow-lg shadow-cyan-600/20 transition-colors cursor-pointer shrink-0 flex items-center gap-2"
        >
          {docLoading ? (
            <>
              <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
              <span>Parsing & Mapping Docs...</span>
            </>
          ) : (
            <span>Analyze Documentation</span>
          )}
        </button>
      </div>

      {/* 1. Loading Progress State */}
      {docLoading && (
        <div className="py-10 px-4 text-center space-y-3">
          <div className="mx-auto h-8 w-8 rounded-full border-2 border-cyan-400 border-t-transparent animate-spin" />
          <p className="text-sm font-medium text-cyan-300">
            Discovering Markdown files, extracting documentation statements, and mapping against Python AST symbols at Head (
            {headCommit ? headCommit.slice(0, 7) : 'HEAD'})...
          </p>
          <p className="text-xs text-slate-400">
            Static parsing only — documentation code blocks and repository files are never executed.
          </p>
        </div>
      )}

      {/* 2. API Error State */}
      {!docLoading && docError && (
        <div
          role="alert"
          className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs flex items-start justify-between gap-4"
        >
          <div>
            <p className="font-semibold text-rose-300">
              Documentation Parsing & Mapping Failed
            </p>
            <p className="mt-1 leading-relaxed">{docError}</p>
          </div>
          <button
            type="button"
            onClick={onDismissDocError}
            className="text-rose-300 hover:text-white underline shrink-0 cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* 3. Initial Idle Prompt */}
      {!docLoading && !docError && !docResult && (
        <div className="py-8 px-4 text-center max-w-lg mx-auto">
          <p className="text-sm font-medium text-slate-300">
            {repoInfo
              ? 'Ready to discover Markdown documentation and map sections to Python symbols.'
              : 'Connect a GitHub repository above to run Documentation Parsing and Code Mapping.'}
          </p>
          <p className="mt-1.5 text-xs text-slate-400">
            Click &ldquo;Analyze Documentation&rdquo; to extract headings, paragraphs, lists, API references, and code blocks and inspect their mapped Python functions, classes, and methods.
          </p>
        </div>
      )}

      {/* 4. Documentation Mapping Results */}
      {!docLoading && docResult && (
        <div className="space-y-6">
          {/* Outcome Banner Distinguishing Zero Mappings vs Mapped Results */}
          {docResult.summary.discovered_doc_files_count === 0 ? (
            <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-slate-300 text-xs">
              <p className="font-semibold text-white">
                Documentation Scan Complete — No Markdown Files Discovered
              </p>
              <p className="mt-1 text-slate-400">
                No `.md` documentation files were found in the repository at commit {docResult.commit_sha.slice(0, 7)} ({docResult.summary.extracted_python_symbols_count} Python symbols indexed).
              </p>
            </div>
          ) : docResult.summary.mapped_units_count === 0 &&
            docResult.summary.ambiguous_units_count === 0 ? (
            <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-slate-300 text-xs">
              <p className="font-semibold text-white">
                Documentation Scan Complete — 0 Symbol Mappings Found
              </p>
              <p className="mt-1 text-slate-400">
                Parsed {docResult.summary.discovered_doc_files_count} Markdown file(s) and extracted {docResult.summary.extracted_units_count} documentation unit(s), but none referenced the {docResult.summary.extracted_python_symbols_count} Python symbol(s) in the repository.
              </p>
            </div>
          ) : (
            <div className="p-4 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-200 text-xs">
              <p className="font-semibold text-cyan-300">
                Documentation Mapping Complete — {docResult.summary.mapped_units_count} Mapped Unit(s), {docResult.summary.ambiguous_units_count} Ambiguous, {docResult.summary.unmapped_units_count} Unmapped
              </p>
              <p className="mt-1">
                Parsed {docResult.summary.discovered_doc_files_count} Markdown file(s) ({docResult.summary.extracted_units_count} documentation units) against {docResult.summary.extracted_python_symbols_count} Python AST symbol(s) at commit {docResult.commit_sha.slice(0, 7)}.
              </p>
            </div>
          )}

          {/* Summary Metric Tiles */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Doc Files
              </span>
              <span className="mt-1 text-lg font-bold text-white block">
                {docResult.summary.discovered_doc_files_count}
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Extracted Units
              </span>
              <span className="mt-1 text-lg font-bold text-white block">
                {docResult.summary.extracted_units_count}
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Mapped Units
              </span>
              <span className="mt-1 text-lg font-bold text-emerald-400 block">
                {docResult.summary.mapped_units_count}
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Ambiguous
              </span>
              <span className="mt-1 text-lg font-bold text-amber-300 block">
                {docResult.summary.ambiguous_units_count}
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Unmapped
              </span>
              <span className="mt-1 text-lg font-bold text-slate-300 block">
                {docResult.summary.unmapped_units_count}
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-[11px] uppercase tracking-wider text-slate-400 block">
                Python Symbols
              </span>
              <span className="mt-1 text-lg font-bold text-indigo-300 block">
                {docResult.summary.extracted_python_symbols_count}
              </span>
            </div>
          </div>

          {/* Discovered Documentation Files & Skipped Files */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300 mb-3">
                Discovered Documentation Files ({docResult.documentation_files.length})
              </h4>
              {docResult.documentation_files.length === 0 ? (
                <p className="text-xs text-slate-500">No Markdown files discovered.</p>
              ) : (
                <ul className="space-y-2 max-h-44 overflow-y-auto text-xs font-mono">
                  {docResult.documentation_files.map((df) => (
                    <li
                      key={df.file_path}
                      className="flex items-center justify-between gap-2 pb-1.5 border-b border-slate-800/80 last:border-b-0"
                    >
                      <span className="text-cyan-300 truncate">{df.file_path}</span>
                      <span className="text-slate-400 shrink-0">
                        {df.sections_count} sec • {df.extracted_units_count} units • {df.mapped_units_count} mapped
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300 mb-3">
                Skipped Documentation Files ({docResult.skipped_files.length})
              </h4>
              {docResult.skipped_files.length === 0 ? (
                <p className="text-xs text-slate-500">No documentation files were skipped.</p>
              ) : (
                <ul className="space-y-2 max-h-44 overflow-y-auto text-xs font-mono">
                  {docResult.skipped_files.map((sf, idx) => (
                    <li
                      key={`${sf.file_path}-${idx}`}
                      className="flex items-center justify-between gap-2 pb-1.5 border-b border-slate-800/80 last:border-b-0"
                    >
                      <span className="text-slate-300 truncate">{sf.file_path}</span>
                      <span className="text-slate-500 shrink-0">{sf.reason}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Filter Tabs (All, High, Medium, Low, Ambiguous, Unmapped) */}
          {docResult.mappings.length > 0 && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                  Documentation-to-Code Mappings ({filteredDocMappings.length} shown)
                </h4>
                <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Mapping Filters">
                  {DOC_FILTER_TABS.map((tab) => {
                    const isActive = docFilter === tab.id;
                    return (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => onDocFilterChange(tab.id)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors cursor-pointer ${
                          isActive
                            ? 'bg-cyan-500/20 text-cyan-200 border-cyan-500/40'
                            : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200 hover:bg-slate-900'
                        }`}
                      >
                        {tab.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {filteredDocMappings.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-400 bg-slate-950 rounded-xl border border-slate-800">
                  No documentation units match the selected filter ({docFilter}).
                </div>
              ) : (
                <div className="divide-y divide-slate-800 rounded-xl bg-slate-950 border border-slate-800 overflow-hidden">
                  {filteredDocMappings.map((item) => (
                    <DocumentationMappingCard
                      key={item.mapping_id}
                      item={item}
                      expanded={Boolean(expandedMappings[item.mapping_id])}
                      onToggle={() =>
                        onToggleMappingExpanded(item.mapping_id)
                      }
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
