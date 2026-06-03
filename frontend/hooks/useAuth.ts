"use client";

import { create } from "zustand";
import Cookies from "js-cookie";
import { User } from "@/types";

function computeIsAdmin(user: User | null): boolean {
  if (!user) return false;
  return user.role === "super_admin" || user.role === "org_admin" || user.role === "admin";
}

interface AuthState {
  token:    string | null;
  user:     User | null;
  isAdmin:  boolean;
  setAuth:  (token: string, user: User) => void;
  clearAuth: () => void;
  hydrate:  () => void;
}

/**
 * Zustand auth store.
 *
 * - `setAuth`   : called after successful login; persists token in a cookie.
 * - `clearAuth` : called on logout; removes cookies and clears state.
 * - `hydrate`   : called on mount to restore state from cookies.
 */
export const useAuth = create<AuthState>((set) => ({
  token:   null,
  user:    null,
  isAdmin: false,

  setAuth(token, user) {
    Cookies.set("lumicams_token", token, { expires: 1, sameSite: "strict" });
    Cookies.set("lumicams_user",  JSON.stringify(user), { expires: 1, sameSite: "strict" });
    set({ token, user, isAdmin: computeIsAdmin(user) });
  },

  clearAuth() {
    Cookies.remove("lumicams_token");
    Cookies.remove("lumicams_user");
    set({ token: null, user: null, isAdmin: false });
  },

  hydrate() {
    const token = Cookies.get("lumicams_token");
    const raw   = Cookies.get("lumicams_user");
    if (token && raw) {
      try {
        const user: User = JSON.parse(raw);
        set({ token, user, isAdmin: computeIsAdmin(user) });
      } catch {
        /* ignore malformed cookie */
      }
    }
  },
}));
