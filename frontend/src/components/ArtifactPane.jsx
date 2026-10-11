import React, { useState } from 'react';
import { marked } from 'marked';
import {
  X,
  Copy,
  Check,
  Download,
  FileCode,
  FileText,
} from 'lucide-react';

export default function ArtifactPane({ artifact, onClose }) {
  const [copied, setCopied] = useState(false);

  if (!artifact) {
    return null;
  }

  const isMarkdown = artifact.type === 'markdown';

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(artifact.content || '');
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  const handleDownload = () => {
    const extension = isMarkdown ? 'md' : 'html';
    const filename = `${(artifact.title || 'artifact').toLowerCase().replace(/\s+/g, '-')}.${extension}`;
    const blob = new Blob([artifact.content || ''], {
      type: isMarkdown ? 'text/markdown;charset=utf-8' : 'text/html;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const markdownHtml = React.useMemo(() => {
    if (!isMarkdown) return '';
    try {
      return marked.parse(artifact.content || '');
    } catch {
      return artifact.content || '';
    }
  }, [artifact.content, isMarkdown]);

  return (
    <aside className="w-[460px] lg:w-[520px] bg-slate-900 border-l border-slate-800 flex flex-col h-full shrink-0 shadow-2xl z-10 animate-in slide-in-from-right duration-200">
      {/* Pane Header */}
      <div className="p-3.5 border-b border-slate-800 flex items-center justify-between bg-slate-900/90">
        <div className="flex items-center gap-2.5 min-w-0 pr-2">
          {isMarkdown ? (
            <FileText size={18} className="text-indigo-400 shrink-0" />
          ) : (
            <FileCode size={18} className="text-emerald-400 shrink-0" />
          )}
          <div className="truncate">
            <h3 className="text-sm font-semibold text-slate-100 truncate">
              {artifact.title || 'Artifact'}
            </h3>
            <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-medium">
              {artifact.type}
            </span>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={handleCopy}
            title="Copy content"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
          >
            {copied ? <Check size={16} className="text-emerald-400" /> : <Copy size={16} />}
          </button>
          <button
            onClick={handleDownload}
            title="Download file"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
          >
            <Download size={16} />
          </button>
          <button
            onClick={onClose}
            title="Close pane"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition ml-1"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Pane Content Viewer */}
      <div className="flex-1 overflow-y-auto p-5">
        {isMarkdown ? (
          <div
            className="markdown-content text-sm text-slate-200"
            dangerouslySetInnerHTML={{ __html: markdownHtml }}
          />
        ) : (
          <div className="w-full h-full min-h-[500px] rounded-lg overflow-hidden border border-slate-800 bg-white shadow-inner">
            <iframe
              title={artifact.title}
              srcDoc={artifact.content || ''}
              sandbox="allow-scripts"
              className="w-full h-full min-h-[500px] border-0"
            />
          </div>
        )}
      </div>
    </aside>
  );
}
