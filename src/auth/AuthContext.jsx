import { createContext, useContext, useEffect, useMemo, useState } from 'react';

const AuthContext = createContext(undefined);

const envApiBase = import.meta?.env?.VITE_API_BASE_URL;
const apiBases = envApiBase
  ? [envApiBase]
  : ['http://127.0.0.1:8000', 'http://127.0.0.1:8001', 'http://127.0.0.1:8002'];

async function apiRequest(path, options = {}) {
  const method = options.method ?? 'GET';
  let lastError;

  for (const base of apiBases) {
    try {
      const response = await fetch(`${base}${path}`, {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
        },
        body: options.body ? JSON.stringify(options.body) : undefined,
      });

      if (!response.ok) {
        let detail = `Request failed (${response.status})`;
        try {
          const payload = await response.json();
          if (payload?.detail) {
            detail = payload.detail;
          }
        } catch {
          // ignore malformed error payload
        }
        throw new Error(detail);
      }

      return await response.json();
    } catch (error) {
      lastError = error;
    }
  }

  if (lastError instanceof Error) {
    throw lastError;
  }
  throw new Error('Unable to reach backend API');
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('retailpulse-token'));
  const [refreshToken, setRefreshToken] = useState(localStorage.getItem('retailpulse-refresh-token'));

  const logout = () => {
    localStorage.removeItem('retailpulse-token');
    localStorage.removeItem('retailpulse-refresh-token');
    setToken(null);
    setRefreshToken(null);
    setUser(null);
  };

  const persistAuth = (accessToken, refreshTokenValue, authUser) => {
    localStorage.setItem('retailpulse-token', accessToken);
    localStorage.setItem('retailpulse-refresh-token', refreshTokenValue);
    setToken(accessToken);
    setRefreshToken(refreshTokenValue);
    setUser(authUser);
  };

  useEffect(() => {
    const loadSession = async () => {
      const storedToken = localStorage.getItem('retailpulse-token');
      const storedRefreshToken = localStorage.getItem('retailpulse-refresh-token');

      if (!storedToken && !storedRefreshToken) {
        return;
      }

      if (storedToken) {
        try {
          const profile = await apiRequest('/auth/me', { method: 'GET', token: storedToken });
          setUser(profile);
          setToken(storedToken);
          return;
        } catch {
          // fall through to refresh attempt
        }
      }

      if (storedRefreshToken) {
        try {
          const response = await apiRequest('/auth/refresh', {
            method: 'POST',
            body: { refresh_token: storedRefreshToken },
          });
          const { access_token, refresh_token: nextRefreshToken, user: authUser } = response;
          persistAuth(access_token, nextRefreshToken, authUser);
        } catch {
          logout();
        }
      }
    };

    loadSession();
  }, []);

  const login = async (email, password) => {
    const response = await apiRequest('/auth/login', {
      method: 'POST',
      body: { email, password },
    });
    const { access_token, refresh_token: nextRefreshToken, user: authUser } = response;
    persistAuth(access_token, nextRefreshToken, authUser);
  };

  const register = async (payload) => {
    const response = await apiRequest('/auth/register', {
      method: 'POST',
      body: payload,
    });
    const { access_token, refresh_token: nextRefreshToken, user: authUser } = response;
    persistAuth(access_token, nextRefreshToken, authUser);
  };

  const value = useMemo(
    () => ({ user, token, isAuthenticated: Boolean(user && token), login, register, logout }),
    [user, token]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
