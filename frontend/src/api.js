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

  try {
    const res = await fetch(url, {
      ...options,
      headers,
    });

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

export async function deleteSession(sessionId) {
  return request(`/sessions/${sessionId}`, {
    method: 'DELETE',
  });
}

export async function fetchArtifact(artifactId) {
  return request(`/artifacts/${artifactId}`);
}
