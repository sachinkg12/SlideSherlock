import { motion } from 'framer-motion'
import { Zap, Sparkles, Rocket } from 'lucide-react'
import { ReactNode } from 'react'

interface PresetCardProps {
  preset: 'draft' | 'standard' | 'pro'
  selected: boolean
  onSelect: () => void
}

const presetConfig: Record<
  string,
  { icon: ReactNode; label: string; description: string; accent: string }
> = {
  draft: {
    icon: <Zap className="h-7 w-7" />,
    label: 'Draft',
    description: 'Fast, silent preview',
    accent: 'text-amber-600 dark:text-amber-400',
  },
  standard: {
    icon: <Sparkles className="h-7 w-7" />,
    label: 'Standard',
    description: 'Narration + subtitles',
    accent: 'text-indigo-600 dark:text-indigo-400',
  },
  pro: {
    icon: <Rocket className="h-7 w-7" />,
    label: 'Pro',
    description: 'Vision AI + full polish',
    accent: 'text-violet-600 dark:text-violet-400',
  },
}

function PresetCard({ preset, selected, onSelect }: PresetCardProps) {
  const config = presetConfig[preset]

  return (
    <motion.button
      onClick={onSelect}
      whileHover={{ y: -4 }}
      whileTap={{ scale: 0.97 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      className={`
        relative flex flex-1 cursor-pointer flex-col items-center gap-3 rounded-2xl
        border p-6 text-center backdrop-blur-xl transition-all duration-300
        ${
          selected
            ? 'border-indigo-500/40 bg-indigo-500/10 shadow-lg shadow-indigo-500/10'
            : 'border-border-subtle bg-surface hover:border-border-active hover:bg-surface-hover'
        }
      `}
      aria-label={`Select ${config.label} preset: ${config.description}`}
      aria-pressed={selected}
    >
      {/* Glow effect for selected */}
      {selected && (
        <motion.div
          layoutId="preset-glow"
          className="absolute inset-0 rounded-2xl"
          style={{
            boxShadow: '0 0 30px rgba(99, 102, 241, 0.15)',
          }}
          transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        />
      )}

      <span className={`relative ${config.accent}`}>{config.icon}</span>
      <span className="relative text-lg font-semibold text-text-primary">
        {config.label}
      </span>
      <span className="relative text-sm text-text-secondary leading-snug">
        {config.description}
      </span>

      {/* Selection indicator */}
      <motion.div
        className="mt-1 h-2 w-2 rounded-full"
        animate={{
          backgroundColor: selected ? 'rgb(99, 102, 241)' : 'rgba(128,128,128,0.3)',
          scale: selected ? 1 : 0.8,
        }}
        transition={{ type: 'spring', stiffness: 500 }}
      />
    </motion.button>
  )
}

export default PresetCard
