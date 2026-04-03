/**
 * Mock API responses for demo mode.
 * Activated when the backend is unreachable or via ?demo=true query param.
 * Simulates the full pipeline flow with realistic timing.
 */

import type { JobProgress, JobMetrics, EvidenceTrailResponse } from './client'

const STAGE_SEQUENCE: Array<{
  name: string
  duration_s: number
  detail: string
  metrics: Record<string, string | number>
}> = [
  {
    name: 'ingest',
    duration_s: 1.2,
    detail: '12 slides, 47 shapes, 8 images extracted',
    metrics: { slides: 12, shapes: 47, images: 8 },
  },
  {
    name: 'evidence',
    duration_s: 2.1,
    detail: '63 evidence items indexed',
    metrics: { 'TEXT_SPAN': 24, 'SHAPE_LABEL': 31, 'IMAGE_ASSET': 8 },
  },
  {
    name: 'render',
    duration_s: 4.3,
    detail: '12 slides rendered to PNG',
    metrics: { slides: 12, pdf_mb: 2.1 },
  },
  {
    name: 'graph',
    duration_s: 1.8,
    detail: '52 nodes unified (38 dual-provenance)',
    metrics: { native: 47, vision: 12, unified: 52, both: 38 },
  },
  {
    name: 'script',
    duration_s: 3.5,
    detail: '51 narration segments generated',
    metrics: { segments: 51, with_evidence: 50 },
  },
  {
    name: 'verify',
    duration_s: 2.8,
    detail: '48 PASS · 3 REWRITE · 0 REMOVE (2 iterations)',
    metrics: { pass: 48, rewrite: 3, remove: 0, iterations: 2 },
  },
  {
    name: 'audio',
    duration_s: 6.2,
    detail: '3:24 of narration generated',
    metrics: { duration: '3:24', slides: 12 },
  },
  {
    name: 'video',
    duration_s: 8.1,
    detail: 'Final video composed with overlays',
    metrics: { duration: '3:24', overlays: 47, subtitles: 51 },
  },
]

const MOCK_EVIDENCE: EvidenceTrailResponse = {
  entries: [
    {
      slide_index: 1,
      claim: 'This slide introduces the quarterly revenue overview for Q3 2025.',
      citations: [
        { kind: 'TEXT_SPAN', label: 'Speaker notes', confidence: 1.0 },
        { kind: 'SHAPE_LABEL', label: 'Q3 Revenue Overview', confidence: 1.0 },
      ],
      verdict: 'PASS',
      rewrite_reason: null,
    },
    {
      slide_index: 3,
      claim: 'Revenue grew 23% year-over-year, reaching $4.2 billion.',
      citations: [
        { kind: 'TEXT_SPAN', label: 'Notes: 23% YoY growth', confidence: 1.0 },
        { kind: 'SHAPE_LABEL', label: 'Revenue Chart', confidence: 1.0 },
      ],
      verdict: 'PASS',
      rewrite_reason: null,
    },
    {
      slide_index: 5,
      claim: 'The customer satisfaction score improved significantly.',
      citations: [
        { kind: 'SHAPE_LABEL', label: 'CSAT Score', confidence: 0.9 },
      ],
      verdict: 'REWRITE',
      rewrite_reason: 'Vague claim "significantly" not supported by evidence. Rewritten with specific number.',
    },
    {
      slide_index: 7,
      claim: 'The sequence diagram shows three actors communicating via REST APIs.',
      citations: [
        { kind: 'DIAGRAM_ENTITIES', label: 'User, API Gateway, Database', confidence: 0.85 },
        { kind: 'DIAGRAM_INTERACTIONS', label: '5 messages', confidence: 0.82 },
      ],
      verdict: 'PASS',
      rewrite_reason: null,
    },
    {
      slide_index: 9,
      claim: 'The photo appears to show the team at the annual offsite event.',
      citations: [
        { kind: 'IMAGE_OBJECTS', label: 'group of people, outdoor setting', confidence: 0.55 },
        { kind: 'IMAGE_CAPTION', label: 'Team photo at outdoor venue', confidence: 0.6 },
      ],
      verdict: 'REWRITE',
      rewrite_reason: 'Low confidence image evidence. Hedging language added.',
    },
    {
      slide_index: 11,
      claim: 'Looking ahead, the roadmap prioritizes three key initiatives.',
      citations: [
        { kind: 'TEXT_SPAN', label: 'Notes: 3 priorities for Q4', confidence: 1.0 },
        { kind: 'SHAPE_LABEL', label: 'Roadmap', confidence: 1.0 },
        { kind: 'SHAPE_LABEL', label: 'Initiative 1', confidence: 1.0 },
      ],
      verdict: 'PASS',
      rewrite_reason: null,
    },
  ],
}

const MOCK_METRICS: JobMetrics = {
  evidence_coverage: 98.4,
  verification_pass_rate: 94.1,
  verifier_iterations: 2,
  claims_pass: 48,
  claims_rewrite: 3,
  claims_remove: 0,
  graph_nodes: 52,
  dual_provenance_pct: 73.1,
  total_duration_s: 29.9,
  slide_count: 12,
}

let mockStartTime: number | null = null
let mockFilename: string = 'presentation.pptx'

export function startMockJob(filename: string): string {
  mockStartTime = Date.now()
  mockFilename = filename
  return 'demo-job-' + Math.random().toString(36).slice(2, 10)
}

export function getMockProgress(): JobProgress {
  if (!mockStartTime) {
    return {
      job_id: 'demo',
      status: 'queued',
      filename: mockFilename,
      preset: 'standard',
      percent: 0,
      stages: STAGE_SEQUENCE.map((s) => ({
        name: s.name,
        status: 'pending' as const,
        started_at: null,
        finished_at: null,
        duration_s: null,
        detail: null,
        metrics: null,
      })),
      error: null,
    }
  }

  const elapsed = (Date.now() - mockStartTime) / 1000
  let cumulative = 0
  const stages: JobProgress['stages'] = []

  for (const def of STAGE_SEQUENCE) {
    const stageStart = cumulative
    const stageEnd = cumulative + def.duration_s
    cumulative = stageEnd

    if (elapsed >= stageEnd) {
      stages.push({
        name: def.name,
        status: 'done',
        started_at: new Date(mockStartTime + stageStart * 1000).toISOString(),
        finished_at: new Date(mockStartTime + stageEnd * 1000).toISOString(),
        duration_s: def.duration_s,
        detail: def.detail,
        metrics: def.metrics,
      })
    } else if (elapsed >= stageStart) {
      stages.push({
        name: def.name,
        status: 'running',
        started_at: new Date(mockStartTime + stageStart * 1000).toISOString(),
        finished_at: null,
        duration_s: null,
        detail: 'Processing...',
        metrics: null,
      })
    } else {
      stages.push({
        name: def.name,
        status: 'pending',
        started_at: null,
        finished_at: null,
        duration_s: null,
        detail: null,
        metrics: null,
      })
    }
  }

  const totalTime = STAGE_SEQUENCE.reduce((sum, s) => sum + s.duration_s, 0)
  const percent = Math.min((elapsed / totalTime) * 100, 100)
  const done = elapsed >= totalTime

  return {
    job_id: 'demo',
    status: done ? 'done' : 'running',
    filename: mockFilename,
    preset: 'standard',
    percent,
    stages,
    error: null,
  }
}

export function getMockEvidenceTrail(): EvidenceTrailResponse {
  if (!mockStartTime) return { entries: [] }

  const elapsed = (Date.now() - mockStartTime) / 1000
  // Evidence trail appears after verify stage starts (~13s in)
  const verifyStart = STAGE_SEQUENCE.slice(0, 5).reduce((s, d) => s + d.duration_s, 0)
  if (elapsed < verifyStart) return { entries: [] }

  // Reveal entries progressively
  const verifyElapsed = elapsed - verifyStart
  const entriesCount = Math.min(
    Math.floor(verifyElapsed / 0.8) + 1,
    MOCK_EVIDENCE.entries.length,
  )
  return { entries: MOCK_EVIDENCE.entries.slice(0, entriesCount) }
}

export function getMockMetrics(): JobMetrics {
  return MOCK_METRICS
}

export function isDemoMode(): boolean {
  if (typeof window !== 'undefined') {
    return new URLSearchParams(window.location.search).get('demo') === 'true'
  }
  return false
}
