import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  CheckCircle2,
  PlayCircle,
  XCircle,
  Clock,
  CircleCheck,
  Diamond,
  TriangleAlert,
} from 'lucide-react'
import type { StageProgress, EvidenceEntry } from '../api/client'
import { STAGE_REGISTRY } from '../config/stages'

interface ActivityFeedProps {
  stages: StageProgress[]
  evidence: EvidenceEntry[]
}

interface FeedEvent {
  id: string
  timestamp: string | null
  type: 'stage' | 'evidence'
  icon: React.ReactNode
  summary: string
  colorClass: string
}

function buildFeedEvents(stages: StageProgress[], evidence: EvidenceEntry[]): FeedEvent[] {
  const events: FeedEvent[] = []

  // Stage events: done, running, failed
  for (const stage of stages) {
    const config = STAGE_REGISTRY[stage.name.toLowerCase()]
    const label = config?.label ?? stage.name

    if (stage.status === 'done') {
      const durationStr = stage.duration_s != null ? ` (${stage.duration_s.toFixed(1)}s)` : ''
      events.push({
        id: `stage-done-${stage.name}`,
        timestamp: stage.finished_at,
        type: 'stage',
        icon: <CheckCircle2 className="h-4 w-4 text-status-done" />,
        summary: `${label} completed${durationStr}`,
        colorClass: 'text-text-primary',
      })
    }

    if (stage.status === 'running') {
      events.push({
        id: `stage-running-${stage.name}`,
        timestamp: stage.started_at,
        type: 'stage',
        icon: <PlayCircle className="h-4 w-4 text-status-active" />,
        summary: `${label} started`,
        colorClass: 'text-indigo-300',
      })
    }

    if (stage.status === 'failed') {
      events.push({
        id: `stage-failed-${stage.name}`,
        timestamp: stage.finished_at ?? stage.started_at,
        type: 'stage',
        icon: <XCircle className="h-4 w-4 text-status-error" />,
        summary: `${label} failed`,
        colorClass: 'text-status-warning',
      })
    }
  }

  // Evidence events
  for (const entry of evidence) {
    const slideNum = entry.slide_index + 1
    const claim =
      entry.claim.length > 50 ? entry.claim.slice(0, 47) + '...' : entry.claim

    let icon: React.ReactNode
    let summary: string
    let colorClass: string

    if (entry.verdict === 'PASS') {
      // Blue circle with check -- shape: circle
      icon = <CircleCheck className="h-4 w-4 text-status-done" />
      summary = `Slide ${slideNum}: PASS - '${claim}'`
      colorClass = 'text-text-secondary'
    } else if (entry.verdict === 'REWRITE') {
      // Orange diamond -- shape: diamond
      icon = <Diamond className="h-4 w-4 text-status-warning" />
      summary = `Slide ${slideNum}: REWRITE - ${entry.rewrite_reason ?? 'needs hedging'}`
      colorClass = 'text-status-warning/80'
    } else {
      // Red triangle with X -- shape: triangle
      icon = <TriangleAlert className="h-4 w-4 text-status-error" />
      summary = `Slide ${slideNum}: REMOVE - '${claim}'`
      colorClass = 'text-status-error/80'
    }

    events.push({
      id: `evidence-${entry.slide_index}-${entry.verdict}-${entry.claim.slice(0, 20)}`,
      timestamp: null, // evidence entries don't have timestamps
      type: 'evidence',
      icon,
      summary,
      colorClass,
    })
  }

  // Sort: stage events with timestamps first (chronological), then evidence
  events.sort((a, b) => {
    if (a.timestamp && b.timestamp) {
      return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    }
    if (a.timestamp && !b.timestamp) return -1
    if (!a.timestamp && b.timestamp) return 1
    return 0
  })

  return events
}

function formatRelativeTime(ts: string | null): string {
  if (!ts) return ''
  try {
    const diff = Date.now() - new Date(ts).getTime()
    const seconds = Math.floor(diff / 1000)
    if (seconds < 5) return 'just now'
    if (seconds < 60) return `${seconds}s ago`
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ago`
    return `${Math.floor(minutes / 60)}h ago`
  } catch {
    return ''
  }
}

function ActivityFeed({ stages, evidence }: ActivityFeedProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const events = buildFeedEvents(stages, evidence)

  // Auto-scroll to bottom on new events
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [events.length])

  return (
    <div className="glass-card flex flex-col overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border-subtle px-4 py-3">
        <Clock className="h-4 w-4 text-text-secondary" />
        <h3 className="text-sm font-semibold text-text-primary">Activity</h3>
        {events.length > 0 && (
          <span className="ml-auto rounded-full bg-white/5 px-2 py-0.5 text-xs text-text-secondary">
            {events.length}
          </span>
        )}
      </div>

      <div
        ref={scrollRef}
        className="max-h-[28rem] overflow-y-auto scroll-smooth px-4 py-2"
      >
        {events.length === 0 ? (
          <p className="py-8 text-center text-sm text-text-secondary/50">
            No events yet...
          </p>
        ) : (
          <AnimatePresence initial={false}>
            {events.map((event) => (
              <motion.div
                key={event.id}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.25, ease: 'easeOut' }}
                className="flex items-start gap-3 border-b border-border-subtle/50 py-2.5 last:border-b-0"
              >
                <div className="mt-0.5 flex-shrink-0">{event.icon}</div>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm leading-snug ${event.colorClass}`}>
                    {event.summary}
                  </p>
                </div>
                {event.timestamp && (
                  <span className="flex-shrink-0 text-xs text-text-secondary/50 tabular-nums">
                    {formatRelativeTime(event.timestamp)}
                  </span>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        )}
      </div>
    </div>
  )
}

export default ActivityFeed
