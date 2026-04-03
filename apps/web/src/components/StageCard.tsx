import { motion } from 'framer-motion'
import {
  CheckCircle2,
  Loader2,
  Circle,
  XCircle,
  FileInput,
  FileSearch,
  Image,
  Network,
  FileText,
  ShieldCheck,
  Volume2,
  Film,
} from 'lucide-react'
import type { StageProgress } from '../api/client'
import ProgressBar from './ProgressBar'

interface StageCardProps {
  stage: StageProgress
  index: number
}

const stageIcons: Record<string, typeof FileInput> = {
  ingest: FileInput,
  evidence: FileSearch,
  render: Image,
  graph: Network,
  script: FileText,
  verify: ShieldCheck,
  audio: Volume2,
  video: Film,
}

const stageLabels: Record<string, string> = {
  ingest: 'Ingest',
  evidence: 'Evidence',
  render: 'Render',
  graph: 'Graph',
  script: 'Script',
  verify: 'Verify',
  audio: 'Audio',
  video: 'Video',
}

function StageCard({ stage, index }: StageCardProps) {
  const status = stage.status
  const StageIcon = stageIcons[stage.name.toLowerCase()] ?? Circle
  const label = stageLabels[stage.name.toLowerCase()] ?? stage.name

  const statusIcon = {
    done: <CheckCircle2 className="h-6 w-6 text-emerald-400" />,
    running: (
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
      >
        <Loader2 className="h-6 w-6 text-indigo-400" />
      </motion.div>
    ),
    pending: <Circle className="h-6 w-6 text-text-secondary/40" />,
    failed: <XCircle className="h-6 w-6 text-rose-400" />,
  }[status]

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, type: 'spring', stiffness: 200, damping: 25 }}
      className={`
        relative overflow-hidden rounded-2xl border px-5 py-4 backdrop-blur-xl
        transition-all duration-500
        ${
          status === 'done'
            ? 'border-emerald-500/20 bg-surface'
            : status === 'running'
              ? 'border-indigo-500/30 bg-indigo-500/5'
              : status === 'failed'
                ? 'border-rose-500/30 bg-rose-500/5'
                : 'border-border-subtle/50 bg-surface/50'
        }
      `}
    >
      {/* Active glow animation */}
      {status === 'running' && (
        <motion.div
          className="pointer-events-none absolute inset-0 rounded-2xl"
          animate={{
            boxShadow: [
              '0 0 20px rgba(99, 102, 241, 0.1)',
              '0 0 40px rgba(99, 102, 241, 0.25)',
              '0 0 20px rgba(99, 102, 241, 0.1)',
            ],
          }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}

      {/* Left accent bar for completed */}
      {status === 'done' && (
        <motion.div
          initial={{ scaleY: 0 }}
          animate={{ scaleY: 1 }}
          className="absolute left-0 top-0 bottom-0 w-1 origin-top rounded-l-2xl bg-emerald-400"
        />
      )}

      {/* Failed accent bar */}
      {status === 'failed' && (
        <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l-2xl bg-rose-400" />
      )}

      <div className="flex items-center gap-4">
        <div className="flex-shrink-0">{statusIcon}</div>

        <div className="flex flex-1 items-center gap-3 min-w-0">
          <StageIcon
            className={`h-5 w-5 flex-shrink-0 ${
              status === 'pending' ? 'text-text-secondary/30' : 'text-text-secondary'
            }`}
          />
          <span
            className={`text-lg font-medium ${
              status === 'pending' ? 'text-text-secondary/40' : 'text-text-primary'
            }`}
          >
            {label}
          </span>
        </div>

        <div className="flex-shrink-0 text-right">
          {status === 'done' && stage.duration_s != null && (
            <span className="text-sm text-text-secondary">
              {stage.duration_s.toFixed(1)}s
            </span>
          )}
          {status === 'running' && (
            <span className="text-sm text-indigo-400">processing...</span>
          )}
          {status === 'pending' && (
            <span className="text-sm text-text-secondary/40">waiting...</span>
          )}
          {status === 'failed' && (
            <span className="text-sm text-rose-400">failed</span>
          )}
        </div>
      </div>

      {/* Detail text */}
      {stage.detail && status !== 'pending' && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-2 ml-10 text-sm text-text-secondary"
        >
          {stage.detail}
        </motion.p>
      )}

      {/* Metrics tags */}
      {stage.metrics && status === 'done' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="mt-2 ml-10 flex flex-wrap gap-2"
        >
          {Object.entries(stage.metrics).map(([key, value]) => (
            <span
              key={key}
              className="rounded-full bg-white/5 px-3 py-0.5 text-xs text-text-secondary"
            >
              {key}: {value}
            </span>
          ))}
        </motion.div>
      )}

      {/* Running progress bar */}
      {status === 'running' && (
        <div className="mt-3 ml-10">
          <ProgressBar percent={50} size="sm" />
        </div>
      )}
    </motion.div>
  )
}

export default StageCard
