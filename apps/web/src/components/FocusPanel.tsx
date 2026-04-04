import { motion, AnimatePresence } from 'framer-motion'
import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react'
import type { StageProgress } from '../api/client'
import { STAGE_REGISTRY } from '../config/stages'

interface FocusPanelProps {
  stage: StageProgress | null
  allStages: StageProgress[]
}

function FocusPanel({ stage, allStages }: FocusPanelProps) {
  const allDone = allStages.length > 0 && allStages.every((s) => s.status === 'done')
  const hasFailed = allStages.some((s) => s.status === 'failed')
  const failedStage = allStages.find((s) => s.status === 'failed')
  const hasStarted = allStages.some((s) => s.status !== 'pending')

  // Determine what to show
  let viewKey: string
  if (allDone) {
    viewKey = 'complete'
  } else if (hasFailed) {
    viewKey = `failed-${failedStage?.name}`
  } else if (stage && stage.status === 'running') {
    viewKey = `running-${stage.name}`
  } else {
    viewKey = 'preparing'
  }

  return (
    <div className="glass-card flex min-h-[16rem] flex-col items-center justify-center p-8 text-center">
      <AnimatePresence mode="wait">
        {allDone ? (
          <CompletedView key="complete" />
        ) : hasFailed && failedStage ? (
          <FailedView key={viewKey} stage={failedStage} />
        ) : stage && stage.status === 'running' ? (
          <RunningView key={viewKey} stage={stage} />
        ) : (
          <PreparingView key="preparing" hasStarted={hasStarted} />
        )}
      </AnimatePresence>
    </div>
  )
}

function RunningView({ stage }: { stage: StageProgress }) {
  const config = STAGE_REGISTRY[stage.name.toLowerCase()]
  const StageIcon = config?.icon
  const label = config?.label ?? stage.name
  const description = config?.description ?? ''

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col items-center gap-4"
    >
      {/* Large rotating icon */}
      {StageIcon && (
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 8, repeat: Infinity, ease: 'linear' }}
          className="flex h-20 w-20 items-center justify-center rounded-2xl bg-status-active/10"
        >
          <StageIcon className="h-10 w-10 text-status-active" />
        </motion.div>
      )}

      {/* Stage name */}
      <h2 className="text-2xl font-bold text-text-primary">{label}</h2>

      {/* Description */}
      <motion.p
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="text-sm text-text-secondary"
      >
        {description}
      </motion.p>

      {/* Detail text */}
      {stage.detail && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="max-w-md text-sm text-text-secondary/70 italic"
        >
          {stage.detail}
        </motion.p>
      )}

      {/* Progress dots */}
      <div className="mt-2 flex gap-1.5">
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            className="h-2 w-2 rounded-full bg-status-active"
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{
              duration: 1.2,
              repeat: Infinity,
              delay: i * 0.3,
              ease: 'easeInOut',
            }}
          />
        ))}
      </div>
    </motion.div>
  )
}

function CompletedView() {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ duration: 0.4, type: 'spring' }}
      className="flex flex-col items-center gap-4"
    >
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.1, type: 'spring', stiffness: 200 }}
        className="flex h-20 w-20 items-center justify-center rounded-full bg-emerald-500/10"
      >
        <CheckCircle2 className="h-10 w-10 text-emerald-400" />
      </motion.div>

      <h2 className="text-3xl font-bold gradient-text">Pipeline Complete</h2>

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
        className="text-sm text-text-secondary"
      >
        All stages finished successfully.
      </motion.p>
    </motion.div>
  )
}

function FailedView({ stage }: { stage: StageProgress }) {
  const config = STAGE_REGISTRY[stage.name.toLowerCase()]
  const label = config?.label ?? stage.name

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col items-center gap-4"
    >
      <motion.div
        animate={{ rotate: [0, -5, 5, -5, 0] }}
        transition={{ duration: 0.5, delay: 0.2 }}
        className="flex h-20 w-20 items-center justify-center rounded-2xl bg-status-warning/10"
      >
        <AlertTriangle className="h-10 w-10 text-status-warning" />
      </motion.div>

      <h2 className="text-2xl font-bold text-status-warning">
        {label} Failed
      </h2>

      {stage.detail && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="max-w-md text-sm text-text-secondary"
        >
          {stage.detail}
        </motion.p>
      )}
    </motion.div>
  )
}

function PreparingView({ hasStarted }: { hasStarted: boolean }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="flex flex-col items-center gap-4"
    >
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
        className="flex h-16 w-16 items-center justify-center"
      >
        <Loader2 className="h-8 w-8 text-text-secondary/50" />
      </motion.div>
      <p className="text-sm text-text-secondary">
        {hasStarted ? 'Waiting for next stage...' : 'Preparing pipeline...'}
      </p>
    </motion.div>
  )
}

export default FocusPanel
