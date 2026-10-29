import { createContext, type ReactNode, useContext, useEffect, useState } from "react";
import type { Account, AccountSession } from "../api/client";

const SESSION_STORAGE_KEY = "gettogether_session";

type StoredSession = {
  accessToken: string;
  expiresAt: number;
  user: Account;
};

type AuthContextValue = {
  user: Account | null;
  saveSession: (session: AccountSession) => void;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function loadSession(): StoredSession | null {
  const stored = localStorage.getItem(SESSION_STORAGE_KEY);
  if (!stored) return null;
  try {
    const session = JSON.parse(stored) as StoredSession;
    if (
      typeof session.accessToken === "string" &&
      typeof session.expiresAt === "number" &&
      session.expiresAt > Date.now() &&
      session.user &&
      typeof session.user.email === "string"
    ) {
      return session;
    }
  } catch {
    localStorage.removeItem(SESSION_STORAGE_KEY);
    return null;
  }
  localStorage.removeItem(SESSION_STORAGE_KEY);
  return null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<StoredSession | null>(loadSession);

  useEffect(() => {
    function synchronizeSession(event: StorageEvent) {
      if (event.key === SESSION_STORAGE_KEY) setSession(loadSession());
    }
    window.addEventListener("storage", synchronizeSession);
    return () => window.removeEventListener("storage", synchronizeSession);
  }, []);

  useEffect(() => {
    if (!session) return;
    const timeout = window.setTimeout(() => setSession(loadSession()), Math.max(0, session.expiresAt - Date.now()));
    return () => window.clearTimeout(timeout);
  }, [session]);

  function saveSession(response: AccountSession) {
    const nextSession: StoredSession = {
      accessToken: response.access_token,
      expiresAt: Date.now() + response.expires_in * 1000,
      user: response.user,
    };
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(nextSession));
    setSession(nextSession);
  }

  function signOut() {
    localStorage.removeItem(SESSION_STORAGE_KEY);
    setSession(null);
  }

  return <AuthContext.Provider value={{ user: session?.user ?? null, saveSession, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
