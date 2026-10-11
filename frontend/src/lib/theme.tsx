import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';

const THEME_KEY = 'nyaya-theme';
const ThemeContext = createContext<{ dark: boolean; toggle: () => void }>({ dark: false, toggle: () => undefined });

function initialTheme(): boolean {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    if (stored) return stored === 'dark';
  } catch {
    // Fall through to the system preference.
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [dark, setDark] = useState(initialTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  }, [dark]);
  const toggle = () =>
    setDark((current) => {
      try {
        window.localStorage.setItem(THEME_KEY, current ? 'light' : 'dark');
      } catch {
        // Preference is kept for this session only.
      }
      return !current;
    });
  return (
    <ThemeContext.Provider value={{ dark, toggle }}>
      <div className={dark ? 'theme-root dark-mode' : 'theme-root'}>{children}</div>
    </ThemeContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeContext);
