import React from 'react';
import { Sparkles, FileText, Cpu } from 'lucide-react';

export default function Header({
  health,
  hasActiveArtifact,
  isArtifactOpen,
  onToggleArtifact,
}) {
  const isHealthy = health?.status === 'ok';
  const provider = health?.provider || 'offline';
  const model = health?.model || 'unknown';

  return (
    <header className="h-14 border-b border-slate-800 bg-slate-900/60 backdrop-blur px-5 flex items-center justify-between shrink-0">
      <div className="flex items-center gap-3">
        <h1 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
          <span>The Lenny Growth Assistant</span>
          <span className="text-xs font-normal text-slate-400">RAG Chat</span>
        </h1>
      </div>

      <div className="flex items-center gap-3">
        {/* Active Provider & Model Badge */}
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-slate-800/80 border border-slate-700/60 text-xs">
          <span className="relative flex h-2 w-2">
            {isHealthy ? (
              <>
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </>
            ) : (
              <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
            )}
          </span>
          <Cpu size={13} className="text-slate-400" />
          <span className="font-medium text-slate-300 capitalize">{provider}</span>
          <span className="text-slate-400">/</span>
          <span className="text-slate-400 font-mono text-[11px] truncate max-w-[140px]">
            {model}
          </span>
        </div>

        {/* Artifact Toggle Button */}
        {hasActiveArtifact && (
          <button
            onClick={onToggleArtifact}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium border transition ${
              isArtifactOpen
                ? 'bg-indigo-600/20 border-indigo-500/50 text-indigo-300'
                : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
            }`}
          >
            <FileText size={13} />
            <span>{isArtifactOpen ? 'Hide Artifact' : 'View Artifact'}</span>
          </button>
        )}
      </div>
    </header>
  );
}
