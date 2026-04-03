import { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Search } from 'lucide-react'

interface LayoutProps {
  children: ReactNode
}

function Layout({ children }: LayoutProps) {
  return (
    <div className="relative min-h-screen bg-dark overflow-hidden">
      {/* Ambient background glow */}
      <div
        className="pointer-events-none fixed inset-0"
        style={{
          background:
            'radial-gradient(ellipse 60% 40% at 50% 0%, rgba(99, 102, 241, 0.08) 0%, transparent 70%)',
        }}
      />

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-6 py-5 sm:px-10">
        <Link to="/" className="flex items-center gap-3 group">
          <motion.div
            whileHover={{ rotate: 15, scale: 1.1 }}
            transition={{ type: 'spring', stiffness: 300 }}
          >
            <Search className="h-7 w-7 text-indigo-400" />
          </motion.div>
          <span className="text-xl font-bold tracking-tight text-text-primary">
            Slide<span className="gradient-text">Sherlock</span>
          </span>
        </Link>
      </header>

      {/* Main content */}
      <main className="relative z-10 mx-auto max-w-4xl px-4 pb-16 sm:px-6">
        {children}
      </main>
    </div>
  )
}

export default Layout
