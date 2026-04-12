const BASE = '/api'

export interface QuickJobResponse {
  job_id: string
}

export interface StageProgress {
  name: string
  status: 'pending' | 'running' | 'done' | 'failed'
  started_at: string | null
  finished_at: string | null
  duration_s: number | null
  detail: string | null
  metrics: Record<string, string | number> | null
}

export interface JobProgress {
  job_id: string
  status: 'queued' | 'running' | 'done' | 'failed'
  filename: string
  preset: string
  percent: number
  stages: StageProgress[]
  error: string | null
}

export interface EvidenceEntry {
  slide_index: number
  claim: string
  citations: {
    kind: string
    label: string
    confidence: number
  }[]
  verdict: 'PASS' | 'REWRITE' | 'REMOVE'
  rewrite_reason: string | null
}

export interface EvidenceTrailResponse {
  entries: EvidenceEntry[]
}

export interface JobMetrics {
  evidence_coverage: number
  verification_pass_rate: number
  verifier_iterations: number
  claims_pass: number
  claims_rewrite: number
  claims_remove: number
  graph_nodes: number
  dual_provenance_pct: number
  total_duration_s: number
  slide_count: number
}

export async function createQuickJob(file: File, preset: string, aiNarration: boolean = false): Promise<QuickJobResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('preset', preset)
  const name = file.name.replace(/\.pptx$/i, '')
  const params = new URLSearchParams({ name })
  if (aiNarration) params.set('ai_narration', 'true')
  const res = await fetch(`${BASE}/jobs/quick?${params.toString()}`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getProgress(jobId: string): Promise<JobProgress> {
  const res = await fetch(`${BASE}/jobs/${jobId}/progress`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getMetrics(jobId: string): Promise<JobMetrics> {
  const res = await fetch(`${BASE}/jobs/${jobId}/metrics`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getEvidenceTrail(jobId: string): Promise<EvidenceTrailResponse> {
  const res = await fetch(`${BASE}/jobs/${jobId}/evidence-trail`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export function getVideoUrl(jobId: string): string {
  return `${BASE}/jobs/${jobId}/output/en/final.mp4`
}

export function getSubtitlesUrl(jobId: string): string {
  return `${BASE}/jobs/${jobId}/output/en/subtitles.vtt`
}

export function getEvidenceReportUrl(jobId: string): string {
  return `${BASE}/jobs/${jobId}/output/evidence-report.json`
}
