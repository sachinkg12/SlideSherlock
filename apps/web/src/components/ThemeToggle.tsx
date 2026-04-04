import { motion } from 'framer-motion'
import { Sun, Moon } from 'lucide-react'
import { useTheme } from '../contexts/ThemeContext'

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <motion.button
      onClick={toggleTheme}
      whileHover={{ scale: 1.1 }}
      whileTap={{ scale: 0.9 }}
      className="flex h-9 w-9 items-center justify-center rounded-full border border-border-subtle bg-surface backdrop-blur-sm transition-colors hover:bg-surface-hover"
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      <motion.div
        key={theme}
        initial={{ rotate: -90, opacity: 0 }}
        animate={{ rotate: 0, opacity: 1 }}
        exit={{ rotate: 90, opacity: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
      >
        {isDark ? (
          <Moon className="h-4 w-4 text-text-secondary" />
        ) : (
          <Sun className="h-4 w-4 text-amber-400" />
        )}
      </motion.div>
    </motion.button>
  )
}

export default ThemeToggle
