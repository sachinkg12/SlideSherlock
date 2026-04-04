import { motion } from 'framer-motion'

interface ProgressBarProps {
  percent: number
  size?: 'sm' | 'md'
  color?: 'indigo' | 'blue' | 'amber'
}

const colorMap = {
  indigo: {
    bg: 'bg-indigo-500/20',
    fill: 'from-indigo-500 to-violet-500',
    glow: 'shadow-indigo-500/30',
  },
  blue: {
    bg: 'bg-blue-500/20',
    fill: 'from-blue-500 to-blue-400',
    glow: 'shadow-blue-500/30',
  },
  amber: {
    bg: 'bg-amber-500/20',
    fill: 'from-amber-500 to-amber-400',
    glow: 'shadow-amber-500/30',
  },
}

function ProgressBar({ percent, size = 'md', color = 'indigo' }: ProgressBarProps) {
  const c = colorMap[color]
  const height = size === 'sm' ? 'h-2' : 'h-3'

  return (
    <div className={`w-full overflow-hidden rounded-full ${c.bg} ${height}`} role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
      <motion.div
        className={`${height} rounded-full bg-gradient-to-r ${c.fill} shadow-lg ${c.glow}`}
        initial={{ width: 0 }}
        animate={{ width: `${Math.min(percent, 100)}%` }}
        transition={{ type: 'spring', stiffness: 80, damping: 20 }}
      />
    </div>
  )
}

export default ProgressBar
