import { useEffect, useState, useRef } from 'react'
import { motion } from 'framer-motion'

interface MetricBarProps {
  label: string
  value: number
  maxValue?: number
  suffix?: string
  color?: 'indigo' | 'emerald' | 'amber'
}

const colorMap = {
  indigo: {
    fill: 'from-indigo-500 to-violet-500',
    glow: 'shadow-indigo-500/20',
    text: 'text-indigo-400',
  },
  emerald: {
    fill: 'from-emerald-500 to-emerald-400',
    glow: 'shadow-emerald-500/20',
    text: 'text-emerald-400',
  },
  amber: {
    fill: 'from-amber-500 to-amber-400',
    glow: 'shadow-amber-500/20',
    text: 'text-amber-400',
  },
}

function MetricBar({
  label,
  value,
  maxValue = 100,
  suffix = '%',
  color = 'indigo',
}: MetricBarProps) {
  const [displayValue, setDisplayValue] = useState(0)
  const animRef = useRef<number | null>(null)
  const startTime = useRef<number | null>(null)
  const c = colorMap[color]

  useEffect(() => {
    const duration = 1500
    const animate = (timestamp: number) => {
      if (!startTime.current) startTime.current = timestamp
      const elapsed = timestamp - startTime.current
      const progress = Math.min(elapsed / duration, 1)
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplayValue(eased * value)
      if (progress < 1) {
        animRef.current = requestAnimationFrame(animate)
      }
    }
    animRef.current = requestAnimationFrame(animate)
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current)
    }
  }, [value])

  const percent = (value / maxValue) * 100

  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-base text-text-primary">{label}</span>
        <span className={`text-lg font-bold tabular-nums ${c.text}`}>
          {displayValue.toFixed(1)}{suffix}
        </span>
      </div>
      <div className="h-3 w-full overflow-hidden rounded-full bg-white/5">
        <motion.div
          className={`h-full rounded-full bg-gradient-to-r ${c.fill} shadow-lg ${c.glow}`}
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 1.5, ease: [0.33, 1, 0.68, 1] }}
        />
      </div>
    </div>
  )
}

export default MetricBar
