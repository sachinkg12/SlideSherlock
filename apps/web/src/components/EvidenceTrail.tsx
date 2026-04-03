import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle2, RefreshCw, Trash2, Paperclip } from 'lucide-react'
import type { EvidenceEntry } from '../api/client'

interface EvidenceTrailProps {
  entries: EvidenceEntry[]
}

const verdictConfig = {
  PASS: {
    icon: <CheckCircle2 className="h-5 w-5 text-emerald-400" />,
    label: 'PASS — grounded in evidence',
    color: 'text-emerald-400',
    border: 'border-emerald-500/20',
  },
  REWRITE: {
    icon: <RefreshCw className="h-5 w-5 text-amber-400" />,
    label: 'REWRITE',
    color: 'text-amber-400',
    border: 'border-amber-500/20',
  },
  REMOVE: {
    icon: <Trash2 className="h-5 w-5 text-rose-400" />,
    label: 'REMOVE — ungrounded claim',
    color: 'text-rose-400',
    border: 'border-rose-500/20',
  },
}

function EvidenceTrail({ entries }: EvidenceTrailProps) {
  if (entries.length === 0) return null

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-8"
    >
      <h3 className="mb-4 text-lg font-semibold text-text-primary">
        Evidence Trail
      </h3>

      <div className="space-y-3 max-h-96 overflow-y-auto pr-2">
        <AnimatePresence>
          {entries.map((entry, i) => {
            const verdict = verdictConfig[entry.verdict]
            return (
              <motion.div
                key={`${entry.slide_index}-${i}`}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                className={`glass-card border-l-2 ${verdict.border} px-5 py-4`}
              >
                <p className="text-sm text-text-secondary">
                  Slide {entry.slide_index + 1}
                </p>
                <p className="mt-1 text-base text-text-primary leading-relaxed">
                  &ldquo;{entry.claim}&rdquo;
                </p>

                {/* Citations */}
                <div className="mt-3 space-y-1.5">
                  {entry.citations.map((cite, ci) => (
                    <div
                      key={ci}
                      className="flex items-center gap-2 text-sm text-text-secondary"
                    >
                      <Paperclip className="h-3.5 w-3.5 flex-shrink-0 text-text-secondary/60" />
                      <span>{cite.kind}</span>
                      {cite.label && (
                        <span className="text-text-secondary/60">
                          ({cite.label})
                        </span>
                      )}
                      <span className="ml-auto text-xs opacity-60">
                        {(cite.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
                </div>

                {/* Verdict */}
                <div className={`mt-3 flex items-center gap-2 text-sm ${verdict.color}`}>
                  {verdict.icon}
                  <span>{verdict.label}</span>
                </div>

                {entry.rewrite_reason && (
                  <p className="mt-1 ml-7 text-xs text-text-secondary italic">
                    {entry.rewrite_reason}
                  </p>
                )}
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}

export default EvidenceTrail
