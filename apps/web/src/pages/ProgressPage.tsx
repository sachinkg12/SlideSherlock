import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { AlertTriangle } from 'lucide-react'
import PipelineTrack from '../components/PipelineTrack'
import FocusPanel from '../components/FocusPanel'
import ActivityFeed from '../components/ActivityFeed'
import ProgressBar from '../components/ProgressBar'
import { getProgress, getEvidenceTrail } from '../api/client'
import { isDemoMode, getMockProgress, getMockEvidenceTrail } from '../api/mock'
import { spawnConfetti } from '../utils/confetti'
import type { JobProgress, EvidenceEntry } from '../api/client'

function ProgressPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [progress, setProgress] = useState<JobProgress | null>(null)
  const [evidence, setEvidence] = useState<EvidenceEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const doneHandled = useRef(false)

  const demo = isDemoMode()

  const pollProgress = useCallback(async () => {
    if (!jobId) return
    try {
      let data: JobProgress
      if (demo) {
        data = getMockProgress()
      } else {
        data = await getProgress(jobId)
      }
      setProgress(data)

      // Fetch evidence trail if verify stage is running or done
      const verifyStage = data.stages?.find(
        (s) => s.name.toLowerCase() === 'verify',
      )
      if (verifyStage && verifyStage.status !== 'pending') {
        try {
          const trail = demo ? getMockEvidenceTrail() : await getEvidenceTrail(jobId)
          setEvidence(trail.entries ?? [])
        } catch {
          // Evidence trail might not be available yet
        }
      }

      if (data.status === 'done' && !doneHandled.current) {
        doneHandled.current = true
        spawnConfetti()
        const suffix = demo ? '?demo=true' : ''
        setTimeout(() => navigate(`/jobs/${jobId}/result${suffix}`), 2000)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load progress')
    }
  }, [jobId, navigate, demo])

  useEffect(() => {
    pollProgress()
    const interval = setInterval(pollProgress, 2000)
    return () => clearInterval(interval)
  }, [pollProgress])

  if (error) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex flex-col items-center gap-4 pt-24"
      >
        <AlertTriangle className="h-12 w-12 text-status-error" />
        <p className="text-xl text-text-primary">Something went wrong</p>
        <p className="text-base text-text-secondary">{error}</p>
      </motion.div>
    )
  }

  if (!progress) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex items-center justify-center pt-32"
      >
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </motion.div>
    )
  }

  // Find the currently running stage
  const currentStage = progress.stages.find((s) => s.status === 'running') ?? null

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col gap-6 pt-8"
    >
      {/* Header */}
      <div>
        <motion.h1
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-2xl font-bold text-text-primary sm:text-3xl"
        >
          Processing:{' '}
          <span className="gradient-text">{progress.filename}</span>
        </motion.h1>
      </div>

      {/* Pipeline track - horizontal dots */}
      <PipelineTrack stages={progress.stages} />

      {/* Two-panel layout: FocusPanel (60%) | ActivityFeed (40%) */}
      <div className="flex flex-col lg:flex-row gap-6">
        <div className="lg:w-3/5">
          <FocusPanel stage={currentStage} allStages={progress.stages} />
        </div>
        <div className="lg:w-2/5">
          <ActivityFeed stages={progress.stages} evidence={evidence} />
        </div>
      </div>

      {/* Error banner */}
      {progress.status === 'failed' && progress.error && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card border-status-error/30 bg-status-error/5 px-6 py-4"
        >
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-6 w-6 flex-shrink-0 text-status-error" />
            <div>
              <p className="text-base font-medium text-status-error">
                Pipeline failed
              </p>
              <p className="mt-1 text-sm text-text-secondary">
                {progress.error}
              </p>
            </div>
          </div>
        </motion.div>
      )}

      {/* Overall progress bar + percentage */}
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <ProgressBar percent={progress.percent} />
        </div>
        <span className="text-lg font-bold tabular-nums text-indigo-400 min-w-[4ch]">
          {Math.round(progress.percent)}%
        </span>
      </div>
    </motion.div>
  )
}

export default ProgressPage
