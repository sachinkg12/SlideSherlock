import type {
  Job,
  Evidence,
  Graph,
  Script,
  VerifyReport,
  Coverage,
  Timeline,
  ArtifactPaths,
} from '@slidesherlock/schemas';
import { DiagramUnderstanding, ScriptGenerator, Verifier, TimelineBuilder, type StorageClient } from '@slidesherlock/core';
import type { LLMProvider, TTSProvider, OCRProvider } from '@slidesherlock/providers';
import { Database } from './db.js';
import { randomUUID } from 'crypto';
import sharp from 'sharp';

export class Pipeline {
  constructor(
    private db: Database,
    private storage: StorageClient,
    private llmProvider: LLMProvider,
    private ttsProvider: TTSProvider,
    private ocrProvider: OCRProvider
  ) {}

  async process(jobId: string): Promise<void> {
    try {
      await this.db.updateJobStatus(jobId, 'EXTRACTING');

      // Stage 1: Extract
      const { extractedContent, slides, shapes, connectors } = await this.extract(jobId);
      const artifactPaths = this.getArtifactPaths(jobId);

      await this.db.updateJobStatus(jobId, 'DIAGRAM_ANALYSIS');

      // Stage 2: Build Evidence Index
      const evidenceIndex = await this.buildEvidenceIndex(jobId, extractedContent, shapes);

      // Stage 3: Diagram Understanding
      const graph = await this.analyzeDiagram(jobId, shapes, connectors, slides);

      await this.db.updateJobStatus(jobId, 'SCRIPT_GENERATION');

      // Stage 4: Script Generation
      const script = await this.generateScript(jobId, extractedContent, evidenceIndex, graph);

      await this.db.updateJobStatus(jobId, 'VERIFICATION');

      // Stage 5: Verification
      const { report, coverage, rewrittenScript } = await this.verify(jobId, script, evidenceIndex);

      await this.db.updateJobStatus(jobId, 'TIMELINE_BUILDING');

      // Stage 6: Timeline
      const timeline = await this.buildTimeline(jobId, rewrittenScript, graph);

      await this.db.updateJobStatus(jobId, 'RENDERING');

      // Stage 7: Render
      await this.render(jobId, rewrittenScript, timeline, slides);

      await this.db.updateJobStatus(jobId, 'COMPLETED');
    } catch (error) {
      await this.db.updateJobStatus(jobId, 'FAILED', String(error));
      throw error;
    }
  }

  private getArtifactPaths(jobId: string): ArtifactPaths {
    return {
      job_id: jobId,
      input_pptx: `jobs/${jobId}/input.pptx`,
      extracted_json: `jobs/${jobId}/extracted.json`,
      slides_png: `jobs/${jobId}/slides`,
      evidence_index: `jobs/${jobId}/evidence/index.json`,
      graph_native: `jobs/${jobId}/graph/native.json`,
      graph_vision: `jobs/${jobId}/graph/vision.json`,
      graph_unified: `jobs/${jobId}/graph/unified.json`,
      script: `jobs/${jobId}/script.json`,
      verify_report: `jobs/${jobId}/verify_report.json`,
      coverage: `jobs/${jobId}/coverage.json`,
      timeline: `jobs/${jobId}/timeline/timeline.json`,
      overlays: `jobs/${jobId}/overlays`,
      final_video: `jobs/${jobId}/final.mp4`,
    };
  }

  private async extract(jobId: string): Promise<{
    extractedContent: string;
    slides: Array<{ page: number; buffer: Buffer }>;
    shapes: Array<{ shape_id: string; type: string; geometry: { x: number; y: number; width: number; height: number; page: number }; text?: string }>;
    connectors: Array<{ connector_id: string; source_id: string; target_id: string; type: string }>;
  }> {
    // Download input PPTX
    const inputBuffer = await this.storage.get(`jobs/${jobId}/input.pptx`);

    // Simple extraction (in production, use a proper PPTX parser)
    // For now, return mock data
    const extractedContent = 'Sample presentation content extracted from PPTX';
    const slides: Array<{ page: number; buffer: Buffer }> = [];
    const shapes: Array<{ shape_id: string; type: string; geometry: { x: number; y: number; width: number; height: number; page: number }; text?: string }> = [];
    const connectors: Array<{ connector_id: string; source_id: string; target_id: string; type: string }> = [];

    // Save extracted content
    await this.storage.put(
      `jobs/${jobId}/extracted.json`,
      JSON.stringify({ content: extractedContent, slides: slides.length }, null, 2),
      'application/json'
    );

    return { extractedContent, slides, shapes, connectors };
  }

  private async buildEvidenceIndex(
    jobId: string,
    content: string,
    shapes: Array<{ shape_id: string; text?: string; geometry: { x: number; y: number; width: number; height: number; page: number } }>
  ): Promise<Evidence[]> {
    const evidence: Evidence[] = [];

    // Extract evidence from text content
    const sentences = content.split(/[.!?]+/).filter((s) => s.trim().length > 0);
    sentences.forEach((sentence, idx) => {
      evidence.push({
        evidence_id: `ev-text-${idx}`,
        source_ref: {
          type: 'page_char',
          page: 0,
          char_start: content.indexOf(sentence),
          char_end: content.indexOf(sentence) + sentence.length,
        },
        content: sentence.trim(),
      });
    });

    // Extract evidence from shapes
    shapes.forEach((shape, idx) => {
      if (shape.text) {
        evidence.push({
          evidence_id: `ev-shape-${idx}`,
          source_ref: {
            type: 'ppt_shape',
            ppt_shape_id: shape.shape_id,
            bbox: shape.geometry,
          },
          content: shape.text,
        });
      }
    });

    // Save to storage
    await this.storage.put(
      `jobs/${jobId}/evidence/index.json`,
      JSON.stringify(evidence, null, 2),
      'application/json'
    );

    // Save to DB
    await this.db.saveEvidence(
      evidence.map((ev) => ({
        evidence_id: ev.evidence_id,
        job_id: jobId,
        source_ref: ev.source_ref,
        content: ev.content,
        metadata: ev.metadata,
      }))
    );

    return evidence;
  }

  private async analyzeDiagram(
    jobId: string,
    shapes: Array<{ shape_id: string; type: string; geometry: { x: number; y: number; width: number; height: number; page: number }; text?: string }>,
    connectors: Array<{ connector_id: string; source_id: string; target_id: string; type: string }>,
    slides: Array<{ page: number; buffer: Buffer }>
  ): Promise<Graph> {
    const diagramUnderstanding = new DiagramUnderstanding();

    // Build G_native
    const gNative = diagramUnderstanding.buildNativeGraph(shapes, connectors);

    // Save G_native
    await this.storage.put(
      `jobs/${jobId}/graph/native.json`,
      JSON.stringify(gNative, null, 2),
      'application/json'
    );

    // Optionally build G_vision from slides
    let gVision: Graph | undefined;
    if (slides.length > 0) {
      const visionGraphs = await Promise.all(
        slides.map((slide) =>
          diagramUnderstanding.buildVisionGraph(slide.buffer, slide.page, this.ocrProvider)
        )
      );

      // Merge vision graphs from all slides
      if (visionGraphs.length > 0) {
        gVision = visionGraphs.reduce((acc, g) => {
          return diagramUnderstanding.mergeGraphs(acc, g);
        });
      }

      if (gVision) {
        await this.storage.put(
          `jobs/${jobId}/graph/vision.json`,
          JSON.stringify(gVision, null, 2),
          'application/json'
        );
      }
    }

    // Merge to G_unified
    const gUnified = diagramUnderstanding.mergeGraphs(gNative, gVision);

    // Save G_unified
    await this.storage.put(
      `jobs/${jobId}/graph/unified.json`,
      JSON.stringify(gUnified, null, 2),
      'application/json'
    );

    return gUnified;
  }

  private async generateScript(
    jobId: string,
    content: string,
    evidenceIndex: Evidence[],
    graph: Graph
  ): Promise<Script> {
    const generator = new ScriptGenerator(this.llmProvider);
    const script = await generator.generate(jobId, content, evidenceIndex, graph);

    // Save script
    await this.storage.put(
      `jobs/${jobId}/script.json`,
      JSON.stringify(script, null, 2),
      'application/json'
    );

    return script;
  }

  private async verify(
    jobId: string,
    script: Script,
    evidenceIndex: Evidence[]
  ): Promise<{ report: VerifyReport; coverage: Coverage; rewrittenScript: Script }> {
    const verifier = new Verifier(this.llmProvider);
    const { report, coverage, rewrittenScript } = await verifier.verify(script, evidenceIndex);

    // Save verify report
    await this.storage.put(
      `jobs/${jobId}/verify_report.json`,
      JSON.stringify(report, null, 2),
      'application/json'
    );

    // Save coverage
    await this.storage.put(
      `jobs/${jobId}/coverage.json`,
      JSON.stringify(coverage, null, 2),
      'application/json'
    );

    // Save rewritten script
    await this.storage.put(
      `jobs/${jobId}/script.json`,
      JSON.stringify(rewrittenScript, null, 2),
      'application/json'
    );

    return { report, coverage, rewrittenScript };
  }

  private async buildTimeline(
    jobId: string,
    script: Script,
    graph: Graph
  ): Promise<Timeline> {
    const builder = new TimelineBuilder();
    const timeline = await builder.build(script, graph);

    // Save timeline
    await this.storage.put(
      `jobs/${jobId}/timeline/timeline.json`,
      JSON.stringify(timeline, null, 2),
      'application/json'
    );

    return timeline;
  }

  private async render(
    jobId: string,
    script: Script,
    timeline: Timeline,
    slides: Array<{ page: number; buffer: Buffer }>
  ): Promise<void> {
    // Generate audio for each segment
    const audioFiles: string[] = [];
    for (const segment of script.segments) {
      const audio = await this.ttsProvider.synthesize(segment.text);
      const audioPath = `jobs/${jobId}/audio/${segment.segment_id}.wav`;
      await this.storage.put(audioPath, audio, 'audio/wav');
      audioFiles.push(audioPath);
    }

    // Generate overlays
    const overlayFiles: string[] = [];
    for (const action of timeline.actions) {
      if (action.action_type !== 'NONE' && action.geometry) {
        const overlay = await this.generateOverlay(action, slides[action.geometry.page]?.buffer);
        const overlayPath = `jobs/${jobId}/overlays/${action.action_id}.png`;
        await this.storage.put(overlayPath, overlay, 'image/png');
        overlayFiles.push(overlayPath);
      }
    }

    // Compose final video with FFmpeg
    // This is a simplified version - in production, use fluent-ffmpeg properly
    await this.composeVideo(jobId, slides, audioFiles, timeline);
  }

  private async generateOverlay(
    action: { action_type: string; geometry?: { x: number; y: number; width: number; height: number } },
    slideBuffer?: Buffer
  ): Promise<Buffer> {
    // Generate overlay image with highlight/trace/zoom
    // For now, create a simple colored rectangle
    const { geometry } = action;
    if (!geometry) {
      return Buffer.from([]);
    }

    const overlay = await sharp({
      create: {
        width: geometry.width + 20,
        height: geometry.height + 20,
        channels: 4,
        background: { r: 255, g: 255, b: 0, alpha: 0.5 },
      },
    })
      .png()
      .toBuffer();

    return overlay;
  }

  private async composeVideo(
    jobId: string,
    slides: Array<{ page: number; buffer: Buffer }>,
    audioFiles: string[],
    timeline: Timeline
  ): Promise<void> {
    // This would use fluent-ffmpeg to compose the final video
    // In production, this would:
    // 1. Combine audio files in sequence
    // 2. Create video from slides with appropriate timing
    // 3. Overlay visual actions (highlight/trace/zoom) at correct timestamps
    // 4. Combine everything into final.mp4
    
    // For now, create a placeholder
    // In a real implementation, you would use fluent-ffmpeg:
    /*
    const ffmpeg = require('fluent-ffmpeg');
    const { Readable } = require('stream');
    
    // Create video from slides with audio
    // This is a simplified example - actual implementation would be more complex
    */
    
    const placeholder = Buffer.from('placeholder video - FFmpeg composition not yet implemented');
    await this.storage.put(`jobs/${jobId}/final.mp4`, placeholder, 'video/mp4');
  }
}
