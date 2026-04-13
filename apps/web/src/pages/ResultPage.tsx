import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Download, ArrowLeft, FileText, AlertTriangle, Globe, Trash2 } from 'lucide-react'
import VideoPlayer from '../components/VideoPlayer'
import MetricBar from '../components/MetricBar'
import GlowButton from '../components/GlowButton'
import PipelineTrack from '../components/PipelineTrack'
import { getMetrics, getProgress, getVideoUrl, getVideoDownloadUrl, getEvidenceReportUrl, getVariants, deleteJob, Variant } from '../api/client'
import { isDemoMode, getMockMetrics, getMockProgress } from '../api/mock'
import type { JobMetrics, JobProgress, StageProgress } from '../api/client'
import { STAGE_REGISTRY } from '../config/stages'

function ResultPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [metrics, setMetrics] = useState<JobMetrics | null>(null)
  const [progress, setProgress] = useState<JobProgress | null>(null)
  const [variants, setVariants] = useState<Variant[]>([])
  const [activeVariant, setActiveVariant] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const demo = isDemoMode()

  useEffect(() => {
    if (!jobId) return
    if (demo) {
      setMetrics(getMockMetrics())
      setProgress(getMockProgress() as JobProgress)
      return
    }
    Promise.all([getMetrics(jobId), getProgress(jobId), getVariants(jobId)])
      .then(([m, p, v]) => {
        setMetrics(m)
        setProgress(p)
        setVariants(v.length > 0 ? v : [])
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
  const evidenceUrl = getEvidenceReportUrl(jobId)

  // Use variants if available, fallback to default English
  const currentVariant = variants.length > 0 ? variants[activeVariant] : null
  const videoSrc = currentVariant
    ? `/api${currentVariant.video_url}`
    : getVideoUrl(jobId)
  const subtitlesSrc = currentVariant
    ? `/api${currentVariant.subtitles_url}`
    : getVideoUrl(jobId).replace('final.mp4', 'subtitles.vtt')
  const downloadHref = currentVariant
    ? `/api${currentVariant.download_url}`
    : getVideoDownloadUrl(jobId)

  // Build all-done stages array for PipelineTrack
  const allDoneStages: StageProgress[] = (
    progress.stages.length > 0
      ? progress.stages
      : Object.keys(STAGE_REGISTRY).map((name) => ({
          name,
          status: 'done' as const,
          started_at: null,
          finished_at: null,
          duration_s: null,
          detail: null,
          metrics: null,
        }))
  ).map((s) => ({ ...s, status: 'done' as const }))

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col gap-8 pt-8"
    >
      {/* Pipeline track - all done */}
      <PipelineTrack stages={allDoneStages} />

      {/* Header */}
      <motion.h1
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-2xl font-bold text-text-primary sm:text-3xl"
      >
        {variants.length > 1 ? (
          <>Your videos are <span className="gradient-text">ready</span></>
        ) : (
          <>Your video is <span className="gradient-text">ready</span></>
        )}
      </motion.h1>

      {/* Language tabs (only show if multiple variants) */}
      {variants.length > 1 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="flex gap-2 flex-wrap"
        >
          {variants.map((v, i) => (
            <button
              key={v.id}
              onClick={() => setActiveVariant(i)}
              className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-all ${
                i === activeVariant
                  ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/50'
                  : 'bg-surface text-text-secondary border border-border-subtle hover:border-border-active'
              }`}
            >
              <Globe className="h-4 w-4" />
              {v.lang}
            </button>
          ))}
        </motion.div>
      )}

      {/* Video player */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        key={activeVariant}
      >
        <VideoPlayer src={videoSrc} title={`${filename} — ${currentVariant?.lang || 'English'}`} subtitlesSrc={subtitlesSrc} />
      </motion.div>

      {/* Download buttons */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="flex flex-col gap-4 sm:flex-row"
      >
        <a
          href={downloadHref}
          download
          className="flex flex-1 items-center justify-center gap-3 rounded-2xl border border-border-subtle bg-surface px-6 py-4 text-lg font-medium text-text-primary backdrop-blur-xl transition-all duration-300 hover:border-border-active hover:bg-surface-hover"
        >
          <Download className="h-5 w-5 text-indigo-400" />
          Download {currentVariant?.lang || 'Video'}
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
            color="blue"
          />
        </div>

        {/* Summary stats */}
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-xl bg-[var(--color-surface)] px-4 py-3 text-center">
            <p className="text-sm text-text-secondary">Verifier</p>
            <p className="mt-1 text-base font-medium text-text-primary">
              {metrics.verifier_iterations} iterations &middot;{' '}
              {metrics.claims_pass} PASS &middot;{' '}
              {metrics.claims_rewrite} REWRITE
            </p>
          </div>
          <div className="rounded-xl bg-[var(--color-surface)] px-4 py-3 text-center">
            <p className="text-sm text-text-secondary">Knowledge Graph</p>
            <p className="mt-1 text-base font-medium text-text-primary">
              {metrics.graph_nodes} nodes &middot;{' '}
              {metrics.dual_provenance_pct.toFixed(0)}% dual-provenance
            </p>
          </div>
          <div className="rounded-xl bg-[var(--color-surface)] px-4 py-3 text-center">
            <p className="text-sm text-text-secondary">Duration</p>
            <p className="mt-1 text-base font-medium text-text-primary">
              {metrics.total_duration_s.toFixed(0)}s total &middot;{' '}
              {metrics.slide_count} slides
            </p>
          </div>
        </div>
      </motion.div>

      {/* Back + Delete */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="flex flex-col gap-4 sm:flex-row"
      >
        <GlowButton variant="secondary" onClick={() => navigate('/')}>
          <ArrowLeft className="h-5 w-5" />
          Transform another presentation
        </GlowButton>
        {!demo && (
          <button
            onClick={async () => {
              if (confirm('Delete this job and all its files? This cannot be undone.')) {
                await deleteJob(jobId)
                navigate('/')
              }
            }}
            className="flex items-center justify-center gap-2 rounded-2xl border border-red-500/30 bg-red-500/10 px-6 py-3 text-base font-medium text-red-400 transition-all hover:bg-red-500/20"
          >
            <Trash2 className="h-5 w-5" />
            Delete my data
          </button>
        )}
      </motion.div>
    </motion.div>
  )
}

export default ResultPage
