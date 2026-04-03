import { z } from 'zod';

// ============================================================================
// Evidence Index
// ============================================================================

export const SourceRefSchema = z.object({
  type: z.enum(['bbox', 'ppt_shape', 'page_char']),
  bbox: z.object({
    x: z.number(),
    y: z.number(),
    width: z.number(),
    height: z.number(),
    page: z.number().optional(),
  }).optional(),
  ppt_shape_id: z.string().optional(),
  page: z.number().optional(),
  char_start: z.number().optional(),
  char_end: z.number().optional(),
});

export type SourceRef = z.infer<typeof SourceRefSchema>;

export const EvidenceSchema = z.object({
  evidence_id: z.string(),
  source_ref: SourceRefSchema,
  content: z.string(),
  metadata: z.record(z.unknown()).optional(),
});

export type Evidence = z.infer<typeof EvidenceSchema>;

export const EvidenceIndexSchema = z.object({
  evidence_id: z.string(),
  source_ref: SourceRefSchema,
  content: z.string(),
  metadata: z.record(z.unknown()).optional(),
});

export type EvidenceIndex = z.infer<typeof EvidenceIndexSchema>;

// ============================================================================
// Diagram Understanding
// ============================================================================

export const ProvenanceSchema = z.enum(['NATIVE', 'VISION', 'BOTH']);

export type Provenance = z.infer<typeof ProvenanceSchema>;

export const NodeSchema = z.object({
  node_id: z.string(),
  label: z.string(),
  type: z.string(),
  geometry: z.object({
    x: z.number(),
    y: z.number(),
    width: z.number(),
    height: z.number(),
    page: z.number(),
  }),
  confidence: z.number().min(0).max(1),
  provenance: ProvenanceSchema,
  needs_review: z.boolean(),
  metadata: z.record(z.unknown()).optional(),
});

export type Node = z.infer<typeof NodeSchema>;

export const EdgeSchema = z.object({
  edge_id: z.string(),
  source_id: z.string(),
  target_id: z.string(),
  label: z.string().optional(),
  type: z.string(),
  confidence: z.number().min(0).max(1),
  provenance: ProvenanceSchema,
  needs_review: z.boolean(),
  metadata: z.record(z.unknown()).optional(),
});

export type Edge = z.infer<typeof EdgeSchema>;

export const GraphSchema = z.object({
  graph_id: z.string(),
  nodes: z.array(NodeSchema),
  edges: z.array(EdgeSchema),
  metadata: z.record(z.unknown()).optional(),
});

export type Graph = z.infer<typeof GraphSchema>;

// ============================================================================
// Script Generation
// ============================================================================

export const ScriptSegmentSchema = z.object({
  segment_id: z.string(),
  claim_id: z.string(),
  evidence_ids: z.array(z.string()),
  entity_ids: z.array(z.string()),
  text: z.string(),
  start_time: z.number().optional(),
  end_time: z.number().optional(),
  metadata: z.record(z.unknown()).optional(),
});

export type ScriptSegment = z.infer<typeof ScriptSegmentSchema>;

export const ScriptSchema = z.object({
  script_id: z.string(),
  job_id: z.string(),
  segments: z.array(ScriptSegmentSchema),
  metadata: z.record(z.unknown()).optional(),
});

export type Script = z.infer<typeof ScriptSchema>;

// ============================================================================
// Verification
// ============================================================================

export const VerdictSchema = z.enum(['PASS', 'REWRITE', 'REMOVE']);

export type Verdict = z.infer<typeof VerdictSchema>;

export const VerificationResultSchema = z.object({
  segment_id: z.string(),
  verdict: VerdictSchema,
  reason: z.string(),
  evidence_coverage: z.array(z.string()),
  missing_evidence: z.array(z.string()).optional(),
});

export type VerificationResult = z.infer<typeof VerificationResultSchema>;

export const VerifyReportSchema = z.object({
  report_id: z.string(),
  job_id: z.string(),
  results: z.array(VerificationResultSchema),
  total_segments: z.number(),
  passed: z.number(),
  rewritten: z.number(),
  removed: z.number(),
});

export type VerifyReport = z.infer<typeof VerifyReportSchema>;

export const CoverageSchema = z.object({
  coverage_id: z.string(),
  job_id: z.string(),
  evidence_coverage: z.record(z.array(z.string())), // evidence_id -> segment_ids
  entity_coverage: z.record(z.array(z.string())), // entity_id -> segment_ids
  gaps: z.array(z.string()),
});

export type Coverage = z.infer<typeof CoverageSchema>;

// ============================================================================
// Timeline
// ============================================================================

export const ActionTypeSchema = z.enum(['HIGHLIGHT', 'TRACE', 'ZOOM', 'NONE']);

export type ActionType = z.infer<typeof ActionTypeSchema>;

export const TimelineActionSchema = z.object({
  action_id: z.string(),
  segment_id: z.string(),
  action_type: ActionTypeSchema,
  entity_id: z.string().optional(),
  geometry: z.object({
    x: z.number(),
    y: z.number(),
    width: z.number(),
    height: z.number(),
    page: z.number(),
  }).optional(),
  start_time: z.number(),
  end_time: z.number(),
  metadata: z.record(z.unknown()).optional(),
});

export type TimelineAction = z.infer<typeof TimelineActionSchema>;

export const TimelineSchema = z.object({
  timeline_id: z.string(),
  job_id: z.string(),
  actions: z.array(TimelineActionSchema),
  total_duration: z.number(),
  metadata: z.record(z.unknown()).optional(),
});

export type Timeline = z.infer<typeof TimelineSchema>;

// ============================================================================
// Job Management
// ============================================================================

export const JobStatusSchema = z.enum([
  'PENDING',
  'EXTRACTING',
  'DIAGRAM_ANALYSIS',
  'SCRIPT_GENERATION',
  'VERIFICATION',
  'TIMELINE_BUILDING',
  'RENDERING',
  'COMPLETED',
  'FAILED',
]);

export type JobStatus = z.infer<typeof JobStatusSchema>;

export const JobSchema = z.object({
  job_id: z.string(),
  status: JobStatusSchema,
  input_path: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  error: z.string().optional(),
  metadata: z.record(z.unknown()).optional(),
});

export type Job = z.infer<typeof JobSchema>;

// ============================================================================
// Artifact Paths
// ============================================================================

export const ArtifactPathsSchema = z.object({
  job_id: z.string(),
  input_pptx: z.string(),
  extracted_json: z.string(),
  slides_png: z.string(),
  evidence_index: z.string(),
  graph_native: z.string(),
  graph_vision: z.string().optional(),
  graph_unified: z.string(),
  script: z.string(),
  verify_report: z.string(),
  coverage: z.string(),
  timeline: z.string(),
  overlays: z.string(),
  final_video: z.string(),
});

export type ArtifactPaths = z.infer<typeof ArtifactPathsSchema>;
