import React, { useState } from 'react';
import { marked } from 'marked';
import {
  FileText,
  ChevronDown,
  ChevronUp,
  Sparkles,
  BookOpen,
  User,
  Bot,
} from 'lucide-react';

export default function ChatMessage({
  message,
  onWriteEssay,
  onSelectArtifact,
  activeArtifactId,
}) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const isUser = message.role === 'user';
  const sources = message.sources || [];
  const artifacts = message.artifacts || [];

  const rawHtml = React.useMemo(() => {
    try {
      return marked.parse(message.content || '');
    } catch {
      return message.content || '';
    }
  }, [message.content]);

  if (!isUser && !message.content) {
    return null;
  }

  return (
    <div
      className={`py-5 px-6 flex gap-4 transition ${
        isUser ? 'bg-slate-900/40' : 'bg-slate-900/80 border-y border-slate-800/40'
      }`}
    >
      {/* Role Avatar */}
      <div className="shrink-0 mt-0.5">
        {isUser ? (
          <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-slate-300">
            <User size={16} />
          </div>
        ) : (
          <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center text-white shadow">
            <Bot size={16} />
          </div>
        )}
      </div>

      {/* Message Body */}
      <div className="flex-1 min-w-0 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-300">
            {isUser ? 'You' : 'Lenny Growth Assistant'}
          </span>
          <span className="text-[11px] text-slate-400">
            {new Date(message.created_at).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>

        {/* Markdown Rendered Content */}
        <div
          className="markdown-content text-sm text-slate-200"
          dangerouslySetInnerHTML={{ __html: rawHtml }}
        />

        {/* Attached Artifacts Chips */}
        {artifacts.length > 0 && (
          <div className="pt-2 flex flex-wrap gap-2">
            {artifacts.map((art) => {
              const isSelected = art.id === activeArtifactId;
              return (
                <button
                  key={art.id}
                  onClick={() => onSelectArtifact(art)}
                  className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border transition ${
                    isSelected
                      ? 'bg-indigo-600/30 border-indigo-500 text-indigo-200 shadow-sm'
                      : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
                  }`}
                >
                  <FileText size={14} className="text-indigo-400" />
                  <span>{art.title}</span>
                  <span className="uppercase text-[10px] px-1 py-0.2 rounded bg-slate-700/60 text-slate-400">
                    {art.type}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {/* Assistant Footer Actions: Citations & Write Ship 30 Essay Button */}
        {!isUser && (
          <div className="pt-2 flex flex-col gap-2.5">
            <div className="flex items-center gap-3">
              {/* Quick Action: Write Ship 30 Essay */}
              <button
                onClick={() => onWriteEssay(message.content)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-950/80 hover:bg-indigo-900 border border-indigo-800/80 text-indigo-300 text-xs font-medium transition shadow-sm"
              >
                <Sparkles size={13} className="text-indigo-400" />
                <span>Write Ship 30 essay from this answer</span>
              </button>

              {/* Citations Toggle */}
              {sources.length > 0 && (
                <button
                  onClick={() => setSourcesOpen(!sourcesOpen)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
                >
                  <BookOpen size={13} />
                  <span>
                    {sources.length} {sources.length === 1 ? 'Source' : 'Sources'}
                  </span>
                  {sourcesOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                </button>
              )}
            </div>

            {/* Citations List Accordion */}
            {sources.length > 0 && sourcesOpen && (
              <div className="mt-1 p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-2.5 text-xs">
                <div className="font-semibold text-slate-300 uppercase tracking-wider text-[11px]">
                  Transcript Citations
                </div>
                <div className="grid gap-2">
                  {sources.map((src, idx) => (
                    <div
                      key={idx}
                      className="p-2.5 rounded bg-slate-900/80 border border-slate-800/80 text-slate-300 space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-indigo-300">
                          [{src.id || idx + 1}] {src.guest} - {src.episode_title}
                        </span>
                        {src.similarity_score && (
                          <span className="text-[10px] text-slate-400">
                            Score: {(src.similarity_score * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                      {src.text && (
                        <p className="text-slate-400 text-[11px] line-clamp-3 italic">
                          "{src.text.trim()}"
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
