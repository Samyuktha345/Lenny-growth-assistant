import React, { useState } from 'react';
import { Sparkles, ArrowRight, AlertCircle, Loader2, User, Mail } from 'lucide-react';
import { loginUser, setStoredUser } from '../api';

export default function SignIn({ onLoginSuccess }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e?.preventDefault();
    if (!name.trim() || !email.trim()) {
      setError('Please provide both your name and email address.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const user = await loginUser(name.trim(), email.trim());
      setStoredUser(user);
      onLoginSuccess(user);
    } catch (err) {
      setError(err.message || 'Failed to sign in. Please ensure the backend is running.');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickDemo = (demoName, demoEmail) => {
    setName(demoName);
    setEmail(demoEmail);
    // Submit with demo credentials
    setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const user = await loginUser(demoName, demoEmail);
        setStoredUser(user);
        onLoginSuccess(user);
      } catch (err) {
        setError(err.message || 'Failed to sign in.');
      } finally {
        setLoading(false);
      }
    }, 50);
  };

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-slate-950 px-4 text-slate-100 font-sans">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/90 p-8 shadow-2xl backdrop-blur-sm">
        {/* Logo and title */}
        <div className="flex flex-col items-center text-center space-y-3 mb-6">
          <div className="w-12 h-12 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shadow-inner">
            <Sparkles size={24} />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-100">
              The Lenny Growth Assistant
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Sign in to access personalized growth frameworks and session history.
            </p>
          </div>
        </div>

        {/* Error notification */}
        {error && (
          <div className="mb-5 flex items-center gap-2 rounded-xl bg-rose-950/70 border border-rose-800/80 px-3.5 py-2.5 text-xs text-rose-300">
            <AlertCircle size={15} className="shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        {/* Sign in form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              Full Name
            </label>
            <div className="relative">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-500">
                <User size={15} />
              </div>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Alice Operator"
                disabled={loading}
                required
                className="w-full rounded-xl border border-slate-800 bg-slate-950 py-2.5 pl-9 pr-3 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none transition"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              Email Address
            </label>
            <div className="relative">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-500">
                <Mail size={15} />
              </div>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="e.g. alice@example.com"
                disabled={loading}
                required
                className="w-full rounded-xl border border-slate-800 bg-slate-950 py-2.5 pl-9 pr-3 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none transition"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 flex items-center justify-center gap-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 py-2.5 px-4 text-sm font-semibold text-white transition shadow-md"
          >
            {loading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                <span>Signing in...</span>
              </>
            ) : (
              <>
                <span>Continue to Chat</span>
                <ArrowRight size={15} />
              </>
            )}
          </button>
        </form>

        {/* Quick demo pills */}
        <div className="mt-6 pt-5 border-t border-slate-800/80">
          <p className="text-[11px] font-medium text-slate-400 uppercase tracking-wider text-center mb-2.5">
            Quick Demo Accounts
          </p>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => handleQuickDemo('Alice Operator', 'alice@growth.co')}
              className="px-2.5 py-1.5 rounded-lg border border-slate-800 bg-slate-950 text-left hover:border-slate-700 hover:bg-slate-800/50 transition"
            >
              <div className="text-xs font-medium text-slate-200">Alice (User A)</div>
              <div className="text-[10px] text-slate-400 truncate">alice@growth.co</div>
            </button>
            <button
              type="button"
              onClick={() => handleQuickDemo('Bob Founder', 'bob@startup.io')}
              className="px-2.5 py-1.5 rounded-lg border border-slate-800 bg-slate-950 text-left hover:border-slate-700 hover:bg-slate-800/50 transition"
            >
              <div className="text-xs font-medium text-slate-200">Bob (User B)</div>
              <div className="text-[10px] text-slate-400 truncate">bob@startup.io</div>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
