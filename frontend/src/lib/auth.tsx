import { useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { api, AuthSession, onUnauthorized, tokenStore, UserProfile } from './api';

type AuthStatus = 'loading' | 'authenticated' | 'anonymous';

interface AuthContextValue {
  status: AuthStatus;
  user: UserProfile | null;
  /** Set when the session ended because the server rejected the token. */
  sessionMessage: string | null;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  applySession: (session: AuthSession) => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [status, setStatus] = useState<AuthStatus>(() => (tokenStore.get() ? 'loading' : 'anonymous'));
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);

  const endSession = useCallback(
    (message: string | null) => {
      tokenStore.clear();
      setUser(null);
      setStatus('anonymous');
      setSessionMessage(message);
      queryClient.clear();
    },
    [queryClient],
  );

  const refreshProfile = useCallback(async () => {
    const profile = await api.me();
    setUser(profile);
    setStatus('authenticated');
  }, []);

  // Restore the session after a page refresh by validating the stored token.
  useEffect(() => {
    if (!tokenStore.get()) return;
    refreshProfile().catch(() => endSession('Your session has expired. Sign in again.'));
  }, [refreshProfile, endSession]);

  useEffect(
    () => onUnauthorized(() => endSession('Your session has expired or was signed out. Sign in again.')),
    [endSession],
  );

  const applySession = useCallback(
    async (session: AuthSession) => {
      queryClient.clear();
      tokenStore.set(session.access_token);
      setSessionMessage(null);
      await refreshProfile();
    },
    [queryClient, refreshProfile],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      sessionMessage,
      login: async (username, password) => applySession(await api.login(username, password)),
      register: async (username, password) => applySession(await api.register(username, password)),
      logout: async () => {
        try {
          await api.logout();
        } catch {
          // The token may already be invalid; the local session is cleared regardless.
        }
        endSession(null);
      },
      applySession,
      refreshProfile,
    }),
    [status, user, sessionMessage, applySession, refreshProfile, endSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
