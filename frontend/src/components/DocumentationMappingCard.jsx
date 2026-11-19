const CONFIDENCE_BADGE_STYLES = {
  HIGH: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  MEDIUM: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  LOW: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
};

const MAPPING_STATUS_STYLES = {
  MAPPED: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  AMBIGUOUS: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  UNMAPPED: 'bg-slate-800 text-slate-400 border-slate-700',
};

export default function DocumentationMappingCard({
  item,
  expanded,
  onToggle,
}) {
  const statusBadge =
    MAPPING_STATUS_STYLES[item.mapping_status] || MAPPING_STATUS_STYLES.UNMAPPED;

  return (
    <div className="p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1 min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border ${statusBadge}`}
            >
              {item.mapping_status}
            </span>
            {item.highest_confidence && (
              <span
                className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border ${
                  CONFIDENCE_BADGE_STYLES[item.highest_confidence] || ''
                }`}
              >
                {item.highest_confidence} CONFIDENCE
              </span>
            )}
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
              {item.unit_type}
            </span>
            <span className="text-xs font-mono text-cyan-300">
              {item.documentation_file} (L{item.start_line}–L{item.end_line})
            </span>
          </div>

          {item.heading_hierarchy && item.heading_hierarchy.length > 0 && (
            <p className="text-xs font-semibold text-white">
              Section: {item.heading_hierarchy.join(' › ')}
            </p>
          )}

          <p className="text-xs text-slate-300 line-clamp-2 font-mono bg-slate-900/60 px-3 py-1.5 rounded border border-slate-800/70">
            {item.documentation_text}
          </p>
        </div>

        <button
          type="button"
          onClick={onToggle}
          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-800 shrink-0 cursor-pointer"
        >
          {expanded ? 'Collapse' : 'Inspect Mapping'}
        </button>
      </div>

      {item.related_symbols.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="text-[11px] text-slate-400">
            Linked Python Symbol(s):
          </span>
          {item.related_symbols.map((sym, sIdx) => (
            <span
              key={`${item.mapping_id}-${sym.source_file}-${sym.qualified_name}-${sIdx}`}
              className="inline-flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-md bg-indigo-500/10 text-indigo-300 border border-indigo-500/30"
            >
              <strong>{sym.qualified_name}</strong>
              <span className="text-slate-400">
                ({sym.source_file}:L{sym.line_start}–L{sym.line_end})
              </span>
            </span>
          ))}
        </div>
      )}

      {expanded && (
        <div className="mt-3 pt-3 border-t border-slate-800/80 space-y-3 text-xs">
          <div className="p-3 rounded-lg bg-slate-900 border border-slate-800">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
              Full Extracted Documentation Statement ({item.documentation_file}:L{item.start_line}–L{item.end_line})
            </span>
            <pre className="whitespace-pre-wrap font-mono text-xs text-slate-200 leading-relaxed">
              {item.documentation_text}
            </pre>
          </div>

          {item.related_symbols.length === 0 ? (
            <p className="text-xs text-slate-400 italic">
              No matching Python AST symbol found for this documentation unit.
            </p>
          ) : (
            <div className="space-y-2.5">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block">
                Mapped Python AST Symbols & Evidence ({item.related_symbols.length})
              </span>
              {item.related_symbols.map((sym, sIdx) => (
                <div
                  key={`detail-${item.mapping_id}-${sIdx}`}
                  className="p-3.5 rounded-lg bg-slate-900/90 border border-slate-800 space-y-2"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span
                        className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border ${
                          CONFIDENCE_BADGE_STYLES[sym.confidence] || ''
                        }`}
                      >
                        {sym.confidence}
                      </span>
                      <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-950 text-slate-300 border border-slate-800">
                        {sym.symbol_type}
                      </span>
                      <span className="font-mono font-semibold text-white">
                        {sym.qualified_name}
                      </span>
                    </div>
                    <span className="font-mono text-indigo-300">
                      {sym.source_file} (lines {sym.line_start}–{sym.line_end})
                    </span>
                  </div>

                  <div className="p-2 rounded bg-slate-950 border border-slate-800 font-mono text-emerald-300 overflow-x-auto">
                    <code>{sym.signature}</code>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-1">
                    <div>
                      <span className="text-[10px] uppercase tracking-wider text-slate-400 block mb-1">
                        Matching Reasons
                      </span>
                      <ul className="list-disc list-inside text-slate-300 space-y-0.5">
                        {sym.matching_reasons.map((reason, reasonIndex) => (
                          <li key={reasonIndex}>{reason}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <span className="text-[10px] uppercase tracking-wider text-slate-400 block mb-1">
                        Supporting Evidence
                      </span>
                      <ul className="list-disc list-inside text-slate-300 space-y-0.5">
                        {sym.evidence.map((evidence, evidenceIndex) => (
                          <li key={evidenceIndex}>{evidence}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
