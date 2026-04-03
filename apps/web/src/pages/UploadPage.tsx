import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Play } from 'lucide-react'
import DropZone from '../components/DropZone'
import PresetCard from '../components/PresetCard'
import GlowButton from '../components/GlowButton'
import { createQuickJob } from '../api/client'

type Preset = 'draft' | 'standard' | 'pro'

function UploadPage() {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [preset, setPreset] = useState<Preset>('standard')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (!file || isSubmitting) return
    setIsSubmitting(true)
    setError(null)
    try {
      const result = await createQuickJob(file, preset)
      navigate(`/jobs/${result.job_id}`)
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
          className="text-center text-base text-rose-400"
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
