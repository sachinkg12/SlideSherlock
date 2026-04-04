import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

type Theme = 'dark' | 'light'

interface ThemeContextValue {
  theme: Theme
  toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)

const STORAGE_KEY = 'ss-theme'

function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'dark'
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return 'dark'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(getInitialTheme)

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') {
      root.classList.add('dark')
      root.classList.remove('light')
    } else {
      root.classList.remove('dark')
      root.classList.add('light')
    }
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  // Set initial class on mount
  useEffect(() => {
    const root = document.documentElement
    if (getInitialTheme() === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
      root.classList.add('light')
    }
  }, [])

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'))
  }

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return ctx
}
