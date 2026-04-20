import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Play, Sparkles, Globe, X } from 'lucide-react'
import DropZone from '../components/DropZone'
import PresetCard from '../components/PresetCard'
import GlowButton from '../components/GlowButton'
import { createQuickJob, getLanguages, Language } from '../api/client'
import { isDemoMode, startMockJob } from '../api/mock'

type Preset = 'draft' | 'standard' | 'pro'

function UploadPage() {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [preset, setPreset] = useState<Preset>('standard')
  const [aiNarration, setAiNarration] = useState(false)
  const [selectedLangs, setSelectedLangs] = useState<string[]>([])
  const [languages, setLanguages] = useState<Language[]>([{ name: 'English', code: 'en-US' }])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getLanguages().then(setLanguages)
  }, [])

  const addLanguage = (code: string) => {
    if (code && code !== 'en-US' && !selectedLangs.includes(code)) {
      setSelectedLangs([...selectedLangs, code])
    }
  }

  const removeLanguage = (code: string) => {
    setSelectedLangs(selectedLangs.filter(l => l !== code))
  }

  const langName = (code: string) => languages.find(l => l.code === code)?.name || code

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
          const result = await createQuickJob(file, preset, aiNarration, selectedLangs.join(','))
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
      {/* Privacy + legal disclaimer */}
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-center text-xs text-amber-700 dark:text-amber-300/90 leading-relaxed">
        <strong>Research demonstration.</strong> Uploaded files are processed via OpenAI API and automatically deleted within 30 minutes.
        Do not upload confidential, sensitive, or personally identifiable information.
        Provided &ldquo;as is&rdquo; under Apache 2.0 &mdash; no warranties. By uploading, you agree to these terms.
      </div>

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

      {/* Language selector */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.24 }}
        className="rounded-2xl border border-border-subtle bg-surface px-5 py-4 backdrop-blur-xl"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Globe className={`h-5 w-5 ${selectedLangs.length > 0 ? 'text-blue-400' : 'text-text-secondary'}`} />
            <div>
              <p className="text-base font-medium text-text-primary">Narration Language</p>
              <p className="text-sm text-text-secondary">
                English is always included. Add more languages below.
              </p>
            </div>
          </div>
          <select
            value=""
            onChange={(e) => { addLanguage(e.target.value); e.target.value = '' }}
            className="rounded-lg border border-border-subtle bg-[var(--color-bg)] px-3 py-2 text-sm text-text-primary focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            aria-label="Add narration language"
          >
            <option value="">+ Add language</option>
            {languages
              .filter(l => l.code !== 'en-US' && !selectedLangs.includes(l.code))
              .map((lang) => (
                <option key={lang.code} value={lang.code}>{lang.name}</option>
              ))}
          </select>
        </div>
        {selectedLangs.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="inline-flex items-center gap-1 rounded-full bg-indigo-500/20 px-3 py-1 text-sm text-indigo-700 dark:text-indigo-300">
              English (default)
            </span>
            {selectedLangs.map(code => (
              <span
                key={code}
                className="inline-flex items-center gap-1 rounded-full bg-blue-500/20 px-3 py-1 text-sm text-blue-700 dark:text-blue-300"
              >
                {langName(code)}
                <button
                  onClick={() => removeLanguage(code)}
                  className="ml-1 rounded-full hover:bg-blue-500/30 p-0.5"
                  aria-label={`Remove ${langName(code)}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}
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
