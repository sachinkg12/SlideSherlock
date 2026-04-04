import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Play, Sparkles } from 'lucide-react'
import DropZone from '../components/DropZone'
import PresetCard from '../components/PresetCard'
import GlowButton from '../components/GlowButton'
import { createQuickJob } from '../api/client'
import { isDemoMode, startMockJob } from '../api/mock'

type Preset = 'draft' | 'standard' | 'pro'

function UploadPage() {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [preset, setPreset] = useState<Preset>('standard')
  const [aiNarration, setAiNarration] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (!file || isSubmitting) return
    setIsSubmitting(true)
    setError(null)
    try {
      // Try real API first; fall back to demo mode if unreachable
      let jobId: string
      if (isDemoMode()) {
        jobId = startMockJob(file.name)
      } else {
        try {
          const result = await createQuickJob(file, preset, aiNarration)
          jobId = result.job_id
        } catch {
          // Backend unreachable — enter demo mode
          const url = new URL(window.location.href)
          url.searchParams.set('demo', 'true')
          window.history.replaceState({}, '', url.toString())
          jobId = startMockJob(file.name)
        }
      }
      navigate(`/jobs/${jobId}${isDemoMode() ? '?demo=true' : ''}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
      setIsSubmitting(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col gap-8 pt-8 sm:pt-16"
    >
      {/* Hero area */}
      <div className="text-center">
        <motion.h1
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="text-3xl font-bold tracking-tight text-text-primary sm:text-4xl"
        >
          Transform slides into
          <span className="gradient-text"> narrated videos</span>
        </motion.h1>
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="mt-3 text-lg text-text-secondary"
        >
          Upload a PowerPoint, choose your quality, watch the magic.
        </motion.p>
      </div>

      {/* Drop zone */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
      >
        <DropZone file={file} onFileSelect={setFile} />
      </motion.div>

      {/* Preset selector */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="flex flex-col gap-4 sm:flex-row"
      >
        {(['draft', 'standard', 'pro'] as const).map((p) => (
          <PresetCard
            key={p}
            preset={p}
            selected={preset === p}
            onSelect={() => setPreset(p)}
          />
        ))}
      </motion.div>

      {/* AI Narration toggle */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.22 }}
        className="flex items-center justify-between rounded-2xl border border-border-subtle bg-surface px-5 py-4 backdrop-blur-xl"
      >
        <div className="flex items-center gap-3">
          <Sparkles className={`h-5 w-5 ${aiNarration ? 'text-amber-400' : 'text-text-secondary'}`} />
          <div>
            <p className="text-base font-medium text-text-primary">AI Narration</p>
            <p className="text-sm text-text-secondary">
              {aiNarration
                ? 'GPT-4o explains slides naturally, like a human presenter'
                : 'Template narration from slide text and notes'}
            </p>
          </div>
        </div>
        <button
          onClick={() => setAiNarration(!aiNarration)}
          className={`relative inline-flex h-7 w-12 flex-shrink-0 cursor-pointer rounded-full transition-colors duration-200 ${
            aiNarration
              ? 'bg-gradient-to-r from-amber-500 to-orange-500'
              : 'bg-[var(--color-surface)]'
          }`}
          role="switch"
          aria-checked={aiNarration}
          aria-label="Toggle AI narration"
        >
          <span
            className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-lg transition-transform duration-200 mt-1 ${
              aiNarration ? 'translate-x-6 ml-0' : 'translate-x-1'
            }`}
          />
        </button>
      </motion.div>

      {/* Submit button */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25 }}
      >
        <GlowButton
          onClick={handleSubmit}
          disabled={!file || isSubmitting}
        >
          <Play className="h-5 w-5" />
          {isSubmitting ? 'Starting...' : 'Transform into Video'}
        </GlowButton>
      </motion.div>

      {/* Error message */}
      {error && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center text-base text-status-error"
        >
          {error}
        </motion.p>
      )}

      {/* Tagline */}
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.5 }}
        transition={{ delay: 0.8, duration: 1 }}
        className="text-center text-base text-text-secondary italic"
      >
        No hallucinations. Every word traced to your slides.
      </motion.p>
    </motion.div>
  )
}

export default UploadPage
