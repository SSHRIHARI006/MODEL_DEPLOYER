import { create } from 'zustand';
import { api } from './api';

interface WalletData {
  credit_balance: string;
  lifetime_earned: string;
  lifetime_spent: string;
}

interface UniversalKey {
  id: string;
  name: string;
  prefix: string;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
}

interface AppState {
  token: string | null;
  username: string | null;

  wallet: WalletData | null;
  keys: UniversalKey[];
  theme: 'light' | 'dark';

  setAuth: (token: string | null, username: string | null) => void;
  logout: () => void;
  fetchWallet: () => Promise<void>;
  fetchKeys: () => Promise<void>;
  toggleTheme: () => void;
}

export const useStore = create<AppState>((set) => ({
  token: localStorage.getItem('token'),
  username: localStorage.getItem('username'),

  wallet: null,
  keys: [],
  theme: (localStorage.getItem('theme') as 'light' | 'dark') || 'light',

  setAuth: (token, username) => {
    if (token && username) {
      localStorage.setItem('token', token);
      localStorage.setItem('username', username);
    }
    set({ token, username });
  },

  toggleTheme: () => set((state) => {
    const newTheme = state.theme === 'light' ? 'dark' : 'light';
    localStorage.setItem('theme', newTheme);
    return { theme: newTheme };
  }),

  logout: () => {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    set({ token: null, username: null, wallet: null, keys: [] });
  },

  fetchWallet: async () => {
    try {
      const data = await api.get<{ wallet: WalletData }>('/wallet/');
      set({ wallet: data.wallet });
    } catch { /* ignore if not logged in */ }
  },

  fetchKeys: async () => {
    try {
      const data = await api.get<UniversalKey[]>('/keys/universal/');
      set({ keys: data });
    } catch { /* ignore */ }
  },
}));
