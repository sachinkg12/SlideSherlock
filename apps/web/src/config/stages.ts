import {
  FileInput,
  FileSearch,
  Image,
  Network,
  FileText,
  ShieldCheck,
  Languages,
  Volume2,
  Film,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export interface StageConfig {
  icon: LucideIcon
  label: string
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
    description: 'Parsing slides, extracting images',
  },
  evidence: {
    icon: FileSearch,
    label: 'Evidence',
    description: 'Building evidence index',
  },
  render: {
    icon: Image,
    label: 'Render',
    description: 'Converting slides to images',
  },
  graph: {
    icon: Network,
    label: 'Graph',
    description: 'Building knowledge graph',
  },
  script: {
    icon: FileText,
    label: 'Script',
    description: 'Generating narration',
  },
  verify: {
    icon: ShieldCheck,
    label: 'Verify',
    description: 'Checking evidence grounding',
  },
  translate: {
    icon: Languages,
    label: 'Translate',
    description: 'Translating to target language',
  },
  audio: {
    icon: Volume2,
    label: 'Audio',
    description: 'Generating speech',
  },
  video: {
    icon: Film,
    label: 'Video',
    description: 'Composing final video',
  },
}
