import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Download, ArrowLeft, FileText, AlertTriangle } from 'lucide-react'
import VideoPlayer from '../components/VideoPlayer'
import MetricBar from '../components/MetricBar'
import GlowButton from '../components/GlowButton'
import { getMetrics, getProgress, getVideoUrl, getEvidenceReportUrl } from '../api/client'
import { isDemoMode, getMockMetrics, getMockProgress } from '../api/mock'
import type { JobMetrics, JobProgress } from '../api/client'

function ResultPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [metrics, setMetrics] = useState<JobMetrics | null>(null)
  const [progress, setProgress] = useState<JobProgress | null>(null)
  const [error, setError] = useState<string | null>(null)

  const demo = isDemoMode()

  useEffect(() => {
    if (!jobId) return
    if (demo) {
      setMetrics(getMockMetrics())
      setProgress(getMockProgress() as JobProgress)
      return
    }
    Promise.all([getMetrics(jobId), getProgress(jobId)])
      .then(([m, p]) => {
        setMetrics(m)
        setProgress(p)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to load results')
      })
  }, [jobId, demo])

  if (error) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex flex-col items-center gap-4 pt-24"
      >
        <AlertTriangle className="h-12 w-12 text-rose-400" />
        <p className="text-xl text-text-primary">Could not load results</p>
        <p className="text-base text-text-secondary">{error}</p>
      </motion.div>
    )
  }

  if (!metrics || !progress || !jobId) {
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

  const filename = progress.filename ?? 'Presentation'
  const videoUrl = getVideoUrl(jobId)
  const evidenceUrl = getEvidenceReportUrl(jobId)

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col gap-8 pt-8"
    >
      {/* Header */}
      <motion.h1
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-2xl font-bold text-text-primary sm:text-3xl"
      >
        Your video is{' '}
        <span className="gradient-text">ready</span>
      </motion.h1>

      {/* Video player */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <VideoPlayer src={videoUrl} title={filename} />
      </motion.div>

      {/* Download buttons */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="flex flex-col gap-4 sm:flex-row"
      >
        <a
          href={videoUrl}
          download
          className="flex flex-1 items-center justify-center gap-3 rounded-2xl border border-border-subtle bg-surface px-6 py-4 text-lg font-medium text-text-primary backdrop-blur-xl transition-all duration-300 hover:border-border-active hover:bg-surface-hover"
        >
          <Download className="h-5 w-5 text-indigo-400" />
          Download Video
        </a>
        <a
          href={evidenceUrl}
          download
          className="flex flex-1 items-center justify-center gap-3 rounded-2xl border border-border-subtle bg-surface px-6 py-4 text-lg font-medium text-text-primary backdrop-blur-xl transition-all duration-300 hover:border-border-active hover:bg-surface-hover"
        >
          <FileText className="h-5 w-5 text-violet-400" />
          Evidence Report
        </a>
      </motion.div>

      {/* Pipeline report */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="glass-card px-6 py-6"
      >
        <h2 className="mb-6 text-xl font-semibold text-text-primary">
          Pipeline Report
        </h2>

        <div className="space-y-6">
          <MetricBar
            label="Evidence Coverage"
            value={metrics.evidence_coverage}
            color="indigo"
          />
          <MetricBar
            label="Verification Pass Rate"
            value={metrics.verification_pass_rate}
            color="emerald"
          />
        </div>

        {/* Summary stats */}
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-xl bg-white/5 px-4 py-3 text-center">
            <p className="text-sm text-text-secondary">Verifier</p>
            <p className="mt-1 text-base font-medium text-text-primary">
              {metrics.verifier_iterations} iterations &middot;{' '}
              {metrics.claims_pass} PASS &middot;{' '}
              {metrics.claims_rewrite} REWRITE
            </p>
          </div>
          <div className="rounded-xl bg-white/5 px-4 py-3 text-center">
            <p className="text-sm text-text-secondary">Knowledge Graph</p>
            <p className="mt-1 text-base font-medium text-text-primary">
              {metrics.graph_nodes} nodes &middot;{' '}
              {metrics.dual_provenance_pct.toFixed(0)}% dual-provenance
            </p>
          </div>
          <div className="rounded-xl bg-white/5 px-4 py-3 text-center">
            <p className="text-sm text-text-secondary">Duration</p>
            <p className="mt-1 text-base font-medium text-text-primary">
              {metrics.total_duration_s.toFixed(0)}s total &middot;{' '}
              {metrics.slide_count} slides
            </p>
          </div>
        </div>
      </motion.div>

      {/* Back to upload */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
      >
        <GlowButton variant="secondary" onClick={() => navigate('/')}>
          <ArrowLeft className="h-5 w-5" />
          Transform another presentation
        </GlowButton>
      </motion.div>
    </motion.div>
  )
}

export default ResultPage
