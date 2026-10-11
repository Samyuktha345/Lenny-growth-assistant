import React from 'react';
import { Plus, MessageSquare, LogOut } from 'lucide-react';

export default function Sidebar({
  sessions,
  currentSessionId,
  onSelectSession,
  onNewChat,
  loading,
  user,
  onLogout,
}) {
  return (
    <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col h-full shrink-0">
      {/* Brand header */}
      <div className="p-4 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold text-sm shadow">
            L
          </div>
          <span className="font-semibold text-slate-100 text-sm tracking-tight">
            Lenny Growth
          </span>
        </div>
      </div>

      {/* New chat action */}
      <div className="p-3">
        <button
          onClick={onNewChat}
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-sm transition shadow-sm disabled:opacity-50"
        >
          <Plus size={16} />
          <span>New Chat</span>
        </button>
      </div>

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto px-2 py-1 space-y-1">
        <div className="px-2 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Chat History
        </div>

        {sessions.length === 0 ? (
          <div className="text-center py-8 text-xs text-slate-400 px-3">
            No conversations yet. Start a new chat!
          </div>
        ) : (
          sessions.map((sess) => {
            const isActive = sess.id === currentSessionId;
            const dateStr = new Date(sess.created_at).toLocaleDateString(undefined, {
              month: 'short',
              day: 'numeric',
            });
            return (
              <button
                key={sess.id}
                onClick={() => onSelectSession(sess.id)}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2.5 transition group ${
                  isActive
                    ? 'bg-slate-800 text-slate-100 font-medium'
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                }`}
              >
                <MessageSquare
                  size={15}
                  className={isActive ? 'text-indigo-400' : 'text-slate-400 group-hover:text-slate-300'}
                />
                <span className="truncate flex-1">
                  {sess.user_name ? `${sess.user_name}'s Chat` : 'Session'}
                </span>
                <span className="text-[11px] text-slate-400">{dateStr}</span>
              </button>
            );
          })
        )}
      </div>

      {/* User profile & Log out button */}
      {user && (
        <div className="p-3 border-t border-slate-800 bg-slate-900/80 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-full bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-300 font-semibold text-xs shrink-0">
              {user.name ? user.name.charAt(0).toUpperCase() : 'U'}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-slate-200 truncate">{user.name}</p>
              <p className="text-[11px] text-slate-400 truncate">{user.email}</p>
            </div>
          </div>
          <button
            onClick={onLogout}
            title="Log out"
            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition shrink-0"
          >
            <LogOut size={16} />
          </button>
        </div>
      )}
    </aside>
  );
}
