const API_BASE = 'http://localhost:8000';

export function getStoredUser() {
  try {
    const raw = localStorage.getItem('lenny_user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setStoredUser(user) {
  if (user) {
    localStorage.setItem('lenny_user', JSON.stringify(user));
  } else {
    localStorage.removeItem('lenny_user');
  }
}

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const user = getStoredUser();
  const headers = {
    'Content-Type': 'application/json',
    ...(user?.id ? { 'X-User-Id': user.id } : {}),
    ...(options.headers || {}),
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90000);

  try {
    const res = await fetch(url, {
      ...options,
      headers,
      signal: options.signal || controller.signal,
    });
    clearTimeout(timeoutId);

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (res.status === 401 && endpoint !== '/users/login') {
        setStoredUser(null);
      }
      const errorMsg = data?.error?.message || data?.detail || `HTTP Error ${res.status}`;
      const err = new Error(errorMsg);
      err.status = res.status;
      err.code = data?.error?.code;
      throw err;
    }
    return data;
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      const timeoutErr = new Error('Request timed out after 90 seconds.');
      timeoutErr.status = 408;
      throw timeoutErr;
    }
    if (err.message && err.message.includes('Failed to fetch')) {
      const connErr = new Error('Unable to connect to Lenny Assistant server.');
      throw connErr;
    }
    throw err;
  }
}

export async function loginUser(name, email) {
  return request('/users/login', {
    method: 'POST',
    body: JSON.stringify({ name, email }),
  });
}

export async function fetchHealth() {
  return request('/health');
}

export async function createSession(userName = null) {
  return request('/sessions', {
    method: 'POST',
    body: JSON.stringify({ user_name: userName }),
  });
}

export async function fetchSessions() {
  return request('/sessions');
}

export async function fetchMessages(sessionId) {
  return request(`/sessions/${sessionId}/messages`);
}

export async function sendChatMessage(sessionId, message) {
  return request(`/sessions/${sessionId}/chat`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

export async function sendChatMessageStream(sessionId, message, callbacks = {}) {
  const { onToken, onSources, onArtifact, onDone, onError } = callbacks;
  const url = `${API_BASE}/sessions/${sessionId}/chat`;
  const user = getStoredUser();

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90000);

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(user?.id ? { 'X-User-Id': user.id } : {}),
      },
      body: JSON.stringify({ message, stream: true }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      const msg = errData?.error?.message || errData?.detail || `Server error (${res.status})`;
      const err = new Error(msg);
      err.status = res.status;
      err.code = errData?.error?.code;
      throw err;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let accumulatedReply = '';
    let currentSources = [];
    let currentArtifacts = [];
    let doneCalled = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data:')) continue;

        const jsonStr = trimmed.slice(5).trim();
        if (!jsonStr) continue;

        try {
          const payload = JSON.parse(jsonStr);
          if (payload.type === 'sources') {
            currentSources = payload.sources || [];
            if (onSources) onSources(currentSources);
          } else if (payload.type === 'token') {
            const token = payload.token || '';
            accumulatedReply += token;
            if (onToken) onToken(token, accumulatedReply);
          } else if (payload.type === 'artifact') {
            if (payload.artifact) {
              currentArtifacts.push(payload.artifact);
              if (onArtifact) onArtifact(payload.artifact);
            }
          } else if (payload.type === 'done') {
            doneCalled = true;
            if (payload.reply) accumulatedReply = payload.reply;
            if (payload.sources) currentSources = payload.sources;
            if (payload.artifacts) currentArtifacts = payload.artifacts;
            if (onDone) {
              onDone({
                reply: accumulatedReply,
                sources: currentSources,
                artifacts: currentArtifacts,
              });
            }
          } else if (payload.type === 'error') {
            throw new Error(payload.message || 'Stream error occurred');
          }
        } catch (parseErr) {
          console.warn('Failed to parse SSE chunk:', jsonStr, parseErr);
        }
      }
    }

    if (!doneCalled && onDone) {
      onDone({
        reply: accumulatedReply,
        sources: currentSources,
        artifacts: currentArtifacts,
      });
    }
  } catch (err) {
    clearTimeout(timeoutId);
    let friendlyMessage = err.message;
    if (err.name === 'AbortError') {
      friendlyMessage = 'The request took longer than 90 seconds to respond.';
    } else if (friendlyMessage && friendlyMessage.includes('Failed to fetch')) {
      friendlyMessage = 'Unable to connect to Lenny Assistant server.';
    }
    const finalErr = new Error(friendlyMessage);
    finalErr.status = err.status;
    finalErr.code = err.code;
    if (onError) onError(finalErr);
    else throw finalErr;
  }
}

export async function deleteSession(sessionId) {
  return request(`/sessions/${sessionId}`, {
    method: 'DELETE',
  });
}

export async function fetchArtifact(artifactId) {
  return request(`/artifacts/${artifactId}`);
}
