import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import axios from 'axios';

interface User {
  id: number;
  name: string;
  email: string;
  role: string;
  company: string;
  lastLogin: string;
  accountStatus: string;
}

interface RegisterPayload {
  companyName: string;
  industry: string;
  companyEmail: string;
  companyAddress: string;
  companyPhone: string;
  ownerName: string;
  ownerEmail: string;
  password: string;
  confirmPassword: string;
}

interface AuthContextValue {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const api = axios.create({ baseURL: 'http://127.0.0.1:8000' });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem('retailpulse-token'));
  const [refreshToken, setRefreshToken] = useState<string | null>(localStorage.getItem('retailpulse-refresh-token'));

  const logout = () => {
    localStorage.removeItem('retailpulse-token');
    localStorage.removeItem('retailpulse-refresh-token');
    delete api.defaults.headers.common.Authorization;
    setToken(null);
    setRefreshToken(null);
    setUser(null);
  };

  const persistAuth = (accessToken: string, refreshTokenValue: string, authUser: User) => {
    localStorage.setItem('retailpulse-token', accessToken);
    localStorage.setItem('retailpulse-refresh-token', refreshTokenValue);
    setToken(accessToken);
    setRefreshToken(refreshTokenValue);
    setUser(authUser);
    api.defaults.headers.common.Authorization = `Bearer ${accessToken}`;
  };

  useEffect(() => {
    const loadSession = async () => {
      const storedToken = localStorage.getItem('retailpulse-token');
      const storedRefreshToken = localStorage.getItem('retailpulse-refresh-token');

      if (!storedToken && !storedRefreshToken) {
        return;
      }

      if (storedToken) {
        api.defaults.headers.common.Authorization = `Bearer ${storedToken}`;
        try {
          const response = await api.get('/auth/me');
          setUser(response.data);
          setToken(storedToken);
          return;
        } catch {
          // fall through to refresh attempt
        }
      }

      if (storedRefreshToken) {
        try {
          const response = await api.post('/auth/refresh', { refresh_token: storedRefreshToken });
          const { access_token, refresh_token: nextRefreshToken, user: authUser } = response.data;
          persistAuth(access_token, nextRefreshToken, authUser);
        } catch {
          logout();
        }
      }
    };

    loadSession();
  }, []);

  const login = async (email: string, password: string) => {
    const response = await api.post('/auth/login', { email, password });
    const { access_token, refresh_token: nextRefreshToken, user: authUser } = response.data;
    persistAuth(access_token, nextRefreshToken, authUser);
  };

  const register = async (payload: RegisterPayload) => {
    const response = await api.post('/auth/register', payload);
    const { access_token, refresh_token: nextRefreshToken, user: authUser } = response.data;
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
