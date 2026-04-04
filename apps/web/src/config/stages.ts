import {
  FileInput,
  FileSearch,
  Image,
  Network,
  FileText,
  ShieldCheck,
  Languages,
  Sparkles,
  Volume2,
  Film,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export interface StageConfig {
  icon: LucideIcon
  label: string
  shortLabel: string
  description: string
}

/**
 * Stage registry: add a new pipeline stage here — no component changes needed.
 * Key must match the `stage.name` returned by the API.
 */
export const STAGE_REGISTRY: Record<string, StageConfig> = {
  ingest: {
    icon: FileInput,
    label: 'Ingest',
    shortLabel: 'ING',
    description: 'Parsing slides, extracting images',
  },
  evidence: {
    icon: FileSearch,
    label: 'Evidence',
    shortLabel: 'EVD',
    description: 'Building evidence index',
  },
  render: {
    icon: Image,
    label: 'Render',
    shortLabel: 'RND',
    description: 'Converting slides to images',
  },
  graph: {
    icon: Network,
    label: 'Graph',
    shortLabel: 'GRF',
    description: 'Building knowledge graph',
  },
  script: {
    icon: FileText,
    label: 'Script',
    shortLabel: 'SCR',
    description: 'Generating narration',
  },
  verify: {
    icon: ShieldCheck,
    label: 'Verify',
    shortLabel: 'VFY',
    description: 'Checking evidence grounding',
  },
  translate: {
    icon: Languages,
    label: 'Translate',
    shortLabel: 'TRN',
    description: 'Translating to target language',
  },
  narrate: {
    icon: Sparkles,
    label: 'AI Narrate',
    shortLabel: 'NAR',
    description: 'Rewriting narration for natural delivery',
  },
  audio: {
    icon: Volume2,
    label: 'Audio',
    shortLabel: 'AUD',
    description: 'Generating speech',
  },
  video: {
    icon: Film,
    label: 'Video',
    shortLabel: 'VID',
    description: 'Composing final video',
  },
}
