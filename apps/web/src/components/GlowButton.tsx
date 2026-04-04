import { motion } from 'framer-motion'
import { ReactNode } from 'react'

interface GlowButtonProps {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  variant?: 'primary' | 'secondary'
  className?: string
  type?: 'button' | 'submit'
}

function GlowButton({
  children,
  onClick,
  disabled = false,
  variant = 'primary',
  className = '',
  type = 'button',
}: GlowButtonProps) {
  const isPrimary = variant === 'primary'

  return (
    <motion.button
      type={type}
      onClick={onClick}
      disabled={disabled}
      whileHover={disabled ? {} : { scale: 1.02 }}
      whileTap={disabled ? {} : { scale: 0.98 }}
      className={`
        relative w-full rounded-2xl px-8 py-5 text-lg font-semibold
        transition-all duration-300 cursor-pointer
        ${
          isPrimary
            ? disabled
              ? 'bg-gradient-to-r from-indigo-500/30 to-violet-500/30 text-[var(--color-text-primary)]/40 cursor-not-allowed'
              : 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40'
            : 'glass-card-hover text-text-primary'
        }
        ${className}
      `}
    >
      {!disabled && isPrimary && (
        <motion.div
          className="absolute inset-0 rounded-2xl bg-gradient-to-r from-indigo-500 to-violet-500 opacity-0"
          animate={{ opacity: [0, 0.3, 0] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
      <span className="relative z-10 flex items-center justify-center gap-3">
        {children}
      </span>
    </motion.button>
  )
}

export default GlowButton
