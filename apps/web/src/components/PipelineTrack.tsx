import { motion } from 'framer-motion'
import { Check, X, Loader2 } from 'lucide-react'
import type { StageProgress } from '../api/client'
import { STAGE_REGISTRY } from '../config/stages'

interface PipelineTrackProps {
  stages: StageProgress[]
}

function PipelineTrack({ stages }: PipelineTrackProps) {
  return (
    <div className="w-full overflow-x-auto py-4 px-2">
      <div className="flex items-start justify-center min-w-max gap-0">
        {stages.map((stage, i) => {
          const config = STAGE_REGISTRY[stage.name.toLowerCase()]
          const label = config?.label ?? stage.name
          const status = stage.status

          return (
            <motion.div
              key={stage.name}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06, type: 'spring', stiffness: 200, damping: 25 }}
              className="flex items-start"
            >
              {/* Connecting line before this dot (skip for first) */}
              {i > 0 && (
                <div className="flex items-center h-10 pt-0.5">
                  <ConnectingLine
                    prevStatus={stages[i - 1].status}
                    currentStatus={status}
                  />
                </div>
              )}

              {/* Dot + label column */}
              <div className="flex flex-col items-center min-w-[4.5rem]">
                <StageDot status={status} index={i} />
                <span
                  className={`mt-2 text-xs font-medium text-center leading-tight ${
                    status === 'pending'
                      ? 'text-text-secondary/40'
                      : status === 'failed'
                        ? 'text-status-warning'
                        : status === 'running'
                          ? 'text-indigo-300'
                          : 'text-text-secondary'
                  }`}
                >
                  {label}
                </span>
              </div>
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}

function StageDot({ status, index }: { status: StageProgress['status']; index: number }) {
  if (status === 'done') {
    return (
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: index * 0.06 + 0.1, type: 'spring', stiffness: 300 }}
        className="relative flex h-10 w-10 items-center justify-center rounded-full bg-status-done"
      >
        <Check className="h-5 w-5 text-white" strokeWidth={3} />
      </motion.div>
    )
  }

  if (status === 'running') {
    return (
      <div className="relative flex h-10 w-10 items-center justify-center">
        {/* Glow ring */}
        <motion.div
          className="absolute inset-0 rounded-full bg-indigo-500/20"
          animate={{ scale: [1, 1.6, 1], opacity: [0.5, 0, 0.5] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />
        <motion.div
          className="relative flex h-10 w-10 items-center justify-center rounded-full bg-status-active"
          animate={{ scale: [1, 1.05, 1] }}
          transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
        >
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
          >
            <Loader2 className="h-5 w-5 text-white" />
          </motion.div>
        </motion.div>
      </div>
    )
  }

  if (status === 'failed') {
    return (
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        className="relative flex h-10 w-10 items-center justify-center rounded-full bg-status-warning"
      >
        <X className="h-5 w-5 text-white" strokeWidth={3} />
      </motion.div>
    )
  }

  // pending
  return (
    <div className="flex h-10 w-10 items-center justify-center rounded-full border-2 border-status-pending/50 bg-transparent">
      <div className="h-2 w-2 rounded-full bg-status-pending/30" />
    </div>
  )
}

function ConnectingLine({
  prevStatus,
  currentStatus,
}: {
  prevStatus: StageProgress['status']
  currentStatus: StageProgress['status']
}) {
  const bothDone = prevStatus === 'done' && currentStatus === 'done'
  const prevDoneCurrentActive = prevStatus === 'done' && currentStatus === 'running'
  const isActive = prevDoneCurrentActive

  if (bothDone) {
    return (
      <motion.div
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        className="h-0.5 w-8 origin-left bg-status-done"
      />
    )
  }

  if (isActive) {
    return (
      <div className="relative h-0.5 w-8 overflow-hidden rounded-full bg-status-pending/30">
        <motion.div
          className="absolute inset-y-0 left-0 w-full bg-gradient-to-r from-status-done to-status-active"
          animate={{ x: ['-100%', '100%'] }}
          transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
        />
      </div>
    )
  }

  // pending or after failed
  return (
    <div
      className="h-0.5 w-8"
      style={{
        backgroundImage:
          'repeating-linear-gradient(90deg, rgb(75 85 99 / 0.4) 0px, rgb(75 85 99 / 0.4) 4px, transparent 4px, transparent 8px)',
      }}
    />
  )
}

export default PipelineTrack
