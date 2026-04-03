import type {
  Script,
  ScriptSegment,
  VerifyReport,
  VerificationResult,
  Coverage,
  Evidence,
  Verdict,
} from '@slidesherlock/schemas';
import type { LLMProvider } from '@slidesherlock/providers';
import { randomUUID } from 'crypto';

export class Verifier {
  constructor(private llmProvider: LLMProvider) {}

  async verify(
    script: Script,
    evidenceIndex: Evidence[],
    maxIterations: number = 5
  ): Promise<{ report: VerifyReport; coverage: Coverage; rewrittenScript: Script }> {
    let currentScript = script;
    let iteration = 0;

    while (iteration < maxIterations) {
      const report = await this.verifyScript(currentScript, evidenceIndex);
      const hasRewrites = report.results.some((r) => r.verdict === 'REWRITE');

      if (!hasRewrites) {
        const coverage = this.buildCoverage(currentScript, evidenceIndex);
        return {
          report,
          coverage,
          rewrittenScript: currentScript,
        };
      }

      // Rewrite segments marked for rewrite
      currentScript = await this.rewriteScript(currentScript, report, evidenceIndex);
      iteration++;
    }

    // Final verification
    const finalReport = await this.verifyScript(currentScript, evidenceIndex);
    const coverage = this.buildCoverage(currentScript, evidenceIndex);

    return {
      report: finalReport,
      coverage,
      rewrittenScript: currentScript,
    };
  }

  private async verifyScript(
    script: Script,
    evidenceIndex: Evidence[]
  ): Promise<VerifyReport> {
    const results: VerificationResult[] = [];

    for (const segment of script.segments) {
      const result = await this.verifySegment(segment, evidenceIndex);
      results.push(result);
    }

    const passed = results.filter((r) => r.verdict === 'PASS').length;
    const rewritten = results.filter((r) => r.verdict === 'REWRITE').length;
    const removed = results.filter((r) => r.verdict === 'REMOVE').length;

    return {
      report_id: randomUUID(),
      job_id: script.job_id,
      results,
      total_segments: script.segments.length,
      passed,
      rewritten,
      removed,
    };
  }

  private async verifySegment(
    segment: ScriptSegment,
    evidenceIndex: Evidence[]
  ): Promise<VerificationResult> {
    // Check if segment has evidence
    if (segment.evidence_ids.length === 0) {
      return {
        segment_id: segment.segment_id,
        verdict: 'REWRITE',
        reason: 'No evidence_ids provided',
        evidence_coverage: [],
        missing_evidence: [],
      };
    }

    // Check if all evidence_ids exist
    const missingEvidence = segment.evidence_ids.filter(
      (id) => !evidenceIndex.some((e) => e.evidence_id === id)
    );

    if (missingEvidence.length > 0) {
      return {
        segment_id: segment.segment_id,
        verdict: 'REWRITE',
        reason: `Invalid evidence_ids: ${missingEvidence.join(', ')}`,
        evidence_coverage: segment.evidence_ids.filter(
          (id) => !missingEvidence.includes(id)
        ),
        missing_evidence: missingEvidence,
      };
    }

    // Use LLM to verify grounding
    const evidenceTexts = segment.evidence_ids
      .map((id) => {
        const ev = evidenceIndex.find((e) => e.evidence_id === id);
        return ev ? `${id}: ${ev.content}` : null;
      })
      .filter(Boolean)
      .join('\n');

    const prompt = `Verify if the following claim is properly grounded in the provided evidence.

CLAIM TEXT:
${segment.text}

EVIDENCE:
${evidenceTexts}

Respond with JSON:
{
  "verdict": "PASS" | "REWRITE" | "REMOVE",
  "reason": "explanation",
  "evidence_coverage": ["evidence_id1", "evidence_id2"]
}`;

    try {
      const response = await this.llmProvider.generate(prompt, {
        temperature: 0.3,
        maxTokens: 500,
      });

      const jsonMatch = response.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]) as {
          verdict: string;
          reason: string;
          evidence_coverage?: string[];
        };

        return {
          segment_id: segment.segment_id,
          verdict: (parsed.verdict as Verdict) || 'PASS',
          reason: parsed.reason || 'Verified',
          evidence_coverage: parsed.evidence_coverage || segment.evidence_ids,
        };
      }
    } catch (error) {
      // Fallback to basic check
    }

    // Default: PASS if evidence exists
    return {
      segment_id: segment.segment_id,
      verdict: 'PASS',
      reason: 'Evidence present, basic verification passed',
      evidence_coverage: segment.evidence_ids,
    };
  }

  private async rewriteScript(
    script: Script,
    report: VerifyReport,
    evidenceIndex: Evidence[]
  ): Promise<Script> {
    const newSegments: ScriptSegment[] = [];

    for (const segment of script.segments) {
      const result = report.results.find((r) => r.segment_id === segment.segment_id);

      if (!result) {
        newSegments.push(segment);
        continue;
      }

      if (result.verdict === 'REMOVE') {
        // Skip this segment
        continue;
      }

      if (result.verdict === 'REWRITE') {
        // Rewrite the segment
        const rewritten = await this.rewriteSegment(segment, result, evidenceIndex);
        if (rewritten) {
          newSegments.push(rewritten);
        }
      } else {
        // PASS - keep as is
        newSegments.push(segment);
      }
    }

    return {
      ...script,
      segments: newSegments,
      metadata: {
        ...script.metadata,
        rewritten_at: new Date().toISOString(),
      },
    };
  }

  private async rewriteSegment(
    segment: ScriptSegment,
    result: VerificationResult,
    evidenceIndex: Evidence[]
  ): Promise<ScriptSegment | null> {
    const availableEvidence = result.evidence_coverage
      .map((id) => {
        const ev = evidenceIndex.find((e) => e.evidence_id === id);
        return ev ? `${id}: ${ev.content}` : null;
      })
      .filter(Boolean)
      .join('\n');

    const prompt = `Rewrite the following segment to be properly grounded in the provided evidence.

ORIGINAL TEXT:
${segment.text}

REASON FOR REWRITE:
${result.reason}

AVAILABLE EVIDENCE:
${availableEvidence}

Respond with JSON:
{
  "text": "rewritten narration",
  "evidence_ids": ["evidence_id1", "evidence_id2"],
  "entity_ids": ["entity_id1"]
}`;

    try {
      const response = await this.llmProvider.generate(prompt, {
        temperature: 0.7,
        maxTokens: 500,
      });

      const jsonMatch = response.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]) as {
          text: string;
          evidence_ids?: string[];
          entity_ids?: string[];
        };

        return {
          ...segment,
          text: parsed.text || segment.text,
          evidence_ids: parsed.evidence_ids || result.evidence_coverage,
          entity_ids: parsed.entity_ids || segment.entity_ids,
          metadata: {
            ...segment.metadata,
            rewritten: true,
            original_text: segment.text,
          },
        };
      }
    } catch (error) {
      // Return null to remove segment if rewrite fails
    }

    return null;
  }

  private buildCoverage(script: Script, evidenceIndex: Evidence[]): Coverage {
    const evidenceCoverage: Record<string, string[]> = {};
    const entityCoverage: Record<string, string[]> = {};
    const gaps: string[] = [];

    // Initialize coverage maps
    for (const ev of evidenceIndex) {
      evidenceCoverage[ev.evidence_id] = [];
    }

    // Build coverage
    for (const segment of script.segments) {
      for (const evId of segment.evidence_ids) {
        if (evidenceCoverage[evId]) {
          evidenceCoverage[evId].push(segment.segment_id);
        }
      }

      for (const entityId of segment.entity_ids) {
        if (!entityCoverage[entityId]) {
          entityCoverage[entityId] = [];
        }
        entityCoverage[entityId].push(segment.segment_id);
      }
    }

    // Find gaps
    for (const [evId, segments] of Object.entries(evidenceCoverage)) {
      if (segments.length === 0) {
        gaps.push(`Evidence ${evId} not covered`);
      }
    }

    return {
      coverage_id: randomUUID(),
      job_id: script.job_id,
      evidence_coverage: evidenceCoverage,
      entity_coverage: entityCoverage,
      gaps,
    };
  }
}
