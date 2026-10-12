import React, { useState, useEffect, useRef } from 'react';
import { Send, Sparkles, AlertCircle, Loader2 } from 'lucide-react';
import {
  fetchHealth,
  createSession,
  fetchSessions,
  fetchMessages,
  sendChatMessageStream,
  getStoredUser,
  setStoredUser,
} from './api';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import ChatMessage from './components/ChatMessage';
import ArtifactPane from './components/ArtifactPane';
import SignIn from './components/SignIn';

export default function App() {
  const [currentUser, setCurrentUser] = useState(() => getStoredUser());
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [health, setHealth] = useState(null);
  const [activeArtifact, setActiveArtifact] = useState(null);
  const [isArtifactOpen, setIsArtifactOpen] = useState(false);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [lastFailedMessage, setLastFailedMessage] = useState(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState(null);

  const messagesEndRef = useRef(null);

  // Scroll to bottom on new messages
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  useEffect(() => {
    let timer;
    if (loading) {
      setElapsedSeconds(0);
      timer = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      setElapsedSeconds(0);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [loading]);

  // Initial data loading when user is signed in
  useEffect(() => {
    if (!currentUser) {
      setInitialLoading(false);
      return;
    }

    async function init() {
      setInitialLoading(true);
      setError(null);
      try {
        // 1. Fetch health
        try {
          const healthData = await fetchHealth();
          setHealth(healthData);
        } catch {
          setHealth({ status: 'offline', provider: 'offline', model: 'none' });
        }

        // 2. Fetch sessions
        const sessList = await fetchSessions();
        setSessions(sessList);

        if (sessList.length > 0) {
          const firstId = sessList[0].id;
          setCurrentSessionId(firstId);
          const msgs = await fetchMessages(firstId);
          setMessages(msgs);
        } else {
          // Create initial session for this user
          const newSess = await createSession(currentUser.name);
          setSessions([newSess]);
          setCurrentSessionId(newSess.id);
          setMessages([]);
        }
      } catch (err) {
        if (err.status === 401) {
          // Invalid or expired user ID
          setStoredUser(null);
          setCurrentUser(null);
        } else {
          setError(err.message || 'Failed to initialize app.');
        }
      } finally {
        setInitialLoading(false);
      }
    }

    init();
  }, [currentUser]);

  // Handle Logout
  const handleLogout = () => {
    setStoredUser(null);
    setCurrentUser(null);
    setSessions([]);
    setCurrentSessionId(null);
    setMessages([]);
    setActiveArtifact(null);
    setIsArtifactOpen(false);
    setError(null);
  };

  // Switch session
  const handleSelectSession = async (sessionId) => {
    if (sessionId === currentSessionId) return;
    setError(null);
    setCurrentSessionId(sessionId);
    try {
      const msgs = await fetchMessages(sessionId);
      setMessages(msgs);
      // If there are artifacts in the conversation, preview the latest one
      const allArtifacts = msgs.flatMap((m) => m.artifacts || []);
      if (allArtifacts.length > 0) {
        setActiveArtifact(allArtifacts[allArtifacts.length - 1]);
      }
    } catch (err) {
      if (err.status === 401) {
        handleLogout();
      } else {
        setError(err.message || 'Failed to load conversation history.');
      }
    }
  };

  // Create new chat
  const handleNewChat = async () => {
    setError(null);
    try {
      const newSess = await createSession(currentUser?.name || 'Operator');
      setSessions([newSess, ...sessions]);
      setCurrentSessionId(newSess.id);
      setMessages([]);
      setActiveArtifact(null);
      setIsArtifactOpen(false);
    } catch (err) {
      if (err.status === 401) {
        handleLogout();
      } else {
        setError(err.message || 'Failed to create new chat session.');
      }
    }
  };

  // Send message
  const handleSend = async (customText = null) => {
    const textToSend = customText || inputText;
    if (!textToSend.trim() || loading || !currentSessionId) return;

    setError(null);
    setLastFailedMessage(null);
    setInputText('');
    setLoading(true);

    // Optimistic user message
    const tempUserMsg = {
      id: Date.now(),
      session_id: currentSessionId,
      role: 'user',
      content: textToSend,
      created_at: new Date().toISOString(),
    };

    const tempAssistantId = Date.now() + 1;
    const tempAssistantMsg = {
      id: tempAssistantId,
      session_id: currentSessionId,
      role: 'assistant',
      content: '',
      sources: [],
      artifacts: [],
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, tempUserMsg, tempAssistantMsg]);

    try {
      await sendChatMessageStream(currentSessionId, textToSend, {
        onToken: (token, accumulated) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === tempAssistantId ? { ...m, content: accumulated } : m
            )
          );
        },
        onSources: (sources) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === tempAssistantId ? { ...m, sources } : m
            )
          );
        },
        onArtifact: (art) => {
          setActiveArtifact(art);
          setIsArtifactOpen(true);
        },
        onDone: ({ reply, sources, artifacts }) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === tempAssistantId
                ? {
                    ...m,
                    content: reply || m.content,
                    sources: sources && sources.length > 0 ? sources : m.sources,
                    artifacts: artifacts && artifacts.length > 0 ? artifacts : m.artifacts,
                  }
                : m
            )
          );
          if (artifacts && artifacts.length > 0) {
            setActiveArtifact(artifacts[0]);
            setIsArtifactOpen(true);
          }
          setLoading(false);
        },
        onError: (err) => {
          setLastFailedMessage(textToSend);
          if (err.status === 401) {
            handleLogout();
          } else {
            setError(err.message || 'Unable to retrieve answer.');
          }
          setLoading(false);
        },
      });
    } catch (err) {
      setLastFailedMessage(textToSend);
      if (err.status === 401) {
        handleLogout();
      } else {
        setError(err.message || 'Unable to retrieve answer.');
      }
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Quick Action: Write Ship 30 essay
  const handleWriteEssay = (answerText) => {
    handleSend('Please write a comprehensive Ship 30 for 30 essay based on this answer and the transcripts.');
  };

  // Select artifact to display
  const handleSelectArtifact = (art) => {
    setActiveArtifact(art);
    setIsArtifactOpen(true);
  };

  // If no user is authenticated, render the SignIn page
  if (!currentUser) {
    return <SignIn onLoginSuccess={(user) => setCurrentUser(user)} />;
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100 font-sans">
      {/* Sidebar */}
      <Sidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        loading={loading}
        user={currentUser}
        onLogout={handleLogout}
      />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-full min-w-0">
        <Header
          health={health}
          hasActiveArtifact={Boolean(activeArtifact)}
          isArtifactOpen={isArtifactOpen}
          onToggleArtifact={() => setIsArtifactOpen(!isArtifactOpen)}
        />

        {/* Error notification banner */}
        {error && (
          <div className="bg-rose-950/70 border-b border-rose-800/80 px-5 py-2.5 flex items-center justify-between text-xs text-rose-200">
            <div className="flex items-center gap-2">
              <AlertCircle size={15} className="text-rose-400 shrink-0" />
              <span>{error}</span>
            </div>
            <div className="flex items-center gap-2">
              {lastFailedMessage && (
                <button
                  onClick={() => {
                    const msg = lastFailedMessage;
                    setError(null);
                    setLastFailedMessage(null);
                    handleSend(msg);
                  }}
                  className="bg-rose-800 hover:bg-rose-700 text-white font-medium px-2.5 py-1 rounded text-xs transition"
                >
                  Retry
                </button>
              )}
              <button
                onClick={() => setError(null)}
                className="text-rose-400 hover:text-rose-200 font-bold px-2 py-0.5"
              >
                ✕
              </button>
            </div>
          </div>
        )}

        {/* Messages Stream */}
        <div className="flex-1 overflow-y-auto">
          {initialLoading ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-3">
              <Loader2 size={28} className="animate-spin text-indigo-500" />
              <span className="text-sm">Connecting to Lenny Growth Assistant...</span>
            </div>
          ) : messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full max-w-lg mx-auto text-center px-4 space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shadow-inner">
                <Sparkles size={24} />
              </div>
              <h2 className="text-lg font-semibold text-slate-100">
                Welcome, {currentUser.name}! What insight are you looking for?
              </h2>
              <p className="text-xs text-slate-400 leading-relaxed">
                Ask about finding PMF, retention strategies, pricing models, founder mode, or growth loops grounded strictly in Lenny's Podcast transcripts.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 w-full">
                {[
                  'What is founder mode according to Brian Chesky?',
                  'How should early-stage startups measure retention?',
                  'What are Elena Verna’s core product-led growth loops?',
                  'Write a Ship 30 essay on finding product-market fit',
                ].map((prompt, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(prompt)}
                    className="p-3 text-left rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-300 hover:border-slate-700 hover:bg-slate-800/60 transition"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="divide-y divide-slate-800/40">
              {messages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  onWriteEssay={handleWriteEssay}
                  onSelectArtifact={handleSelectArtifact}
                  activeArtifactId={activeArtifact?.id}
                />
              ))}

              {loading && (
                <div className="py-5 px-6 flex gap-4 bg-slate-900/60">
                  <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center text-white shrink-0 shadow">
                    <Loader2 size={16} className="animate-spin" />
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-400 pt-1.5">
                    <span>Thinking... ({elapsedSeconds}s)</span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Chat Input Bar */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/80 shrink-0">
          <div className="max-w-4xl mx-auto flex items-end gap-2 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 focus-within:border-indigo-500/80 transition shadow-lg">
            <textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              placeholder="Ask a question about product, growth, or strategy... (Shift + Enter for newline)"
              rows={1}
              className="flex-1 bg-transparent border-0 resize-none text-sm text-slate-100 placeholder-slate-400 focus:outline-none max-h-32 leading-relaxed"
            />
            <button
              onClick={() => handleSend()}
              disabled={!inputText.trim() || loading}
              className="p-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 text-white transition shrink-0"
            >
              <Send size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* Artifact Pane */}
      {isArtifactOpen && activeArtifact && (
        <ArtifactPane
          artifact={activeArtifact}
          onClose={() => setIsArtifactOpen(false)}
        />
      )}
    </div>
  );
}
