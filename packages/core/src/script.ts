import type { Script, ScriptSegment, Evidence } from '@slidesherlock/schemas';
import type { LLMProvider } from '@slidesherlock/providers';
import { v4 as uuidv4 } from 'uuid';

export class ScriptGenerator {
  constructor(private llmProvider: LLMProvider) {}

  async generate(
    jobId: string,
    extractedContent: string,
    evidenceIndex: Evidence[],
    graph: { nodes: Array<{ node_id: string; label: string }>; edges: Array<{ edge_id: string }> }
  ): Promise<Script> {
    const prompt = this.buildPrompt(extractedContent, evidenceIndex, graph);
    
    const llmResponse = await this.llmProvider.generate(prompt, {
      temperature: 0.7,
      maxTokens: 3000,
    });

    const segments = this.parseLLMResponse(llmResponse, evidenceIndex, graph);

    return {
      script_id: randomUUID(),
      job_id: jobId,
      segments,
      metadata: {
        generated_at: new Date().toISOString(),
        llm_provider: 'configured',
      },
    };
  }

  private buildPrompt(
    content: string,
    evidence: Evidence[],
    graph: { nodes: Array<{ node_id: string; label: string }>; edges: Array<{ edge_id: string }> }
  ): string {
    const evidenceList = evidence
      .map((e, idx) => `${idx + 1}. [${e.evidence_id}] ${e.content}`)
      .join('\n');

    const entities = graph.nodes.map((n) => n.node_id).join(', ');

    return `Generate a narrated explainer script for a presentation slide.

CONTENT:
${content}

AVAILABLE EVIDENCE:
${evidenceList}

AVAILABLE ENTITIES (from diagram):
${entities}

Generate a script with multiple segments. Each segment should:
1. Have a clear claim
2. Reference specific evidence_ids that support the claim
3. Reference entity_ids from the diagram when relevant
4. Be natural and engaging

Format your response as JSON array:
[
  {
    "text": "The narration text",
    "claim": "What this segment claims",
    "evidence_ids": ["ev-1", "ev-2"],
    "entity_ids": ["entity-1"]
  }
]`;
  }

  private parseLLMResponse(
    response: string,
    evidenceIndex: Evidence[],
    graph: { nodes: Array<{ node_id: string }>; edges: Array<{ edge_id: string }> }
  ): ScriptSegment[] {
    try {
      // Try to extract JSON from response
      const jsonMatch = response.match(/\[[\s\S]*\]/);
      if (!jsonMatch) {
        throw new Error('No JSON array found in response');
      }

      const rawSegments = JSON.parse(jsonMatch[0]) as Array<{
        text: string;
        claim: string;
        evidence_ids?: string[];
        entity_ids?: string[];
      }>;

      return rawSegments.map((raw, idx) => {
        const segmentId = randomUUID();
        const claimId = randomUUID();

        // Validate evidence_ids exist
        const validEvidenceIds = (raw.evidence_ids || []).filter((id) =>
          evidenceIndex.some((e) => e.evidence_id === id)
        );

        // Validate entity_ids exist
        const validEntityIds = (raw.entity_ids || []).filter((id) =>
          graph.nodes.some((n) => n.node_id === id) ||
          graph.edges.some((e) => e.edge_id === id)
        );

        return {
          segment_id: segmentId,
          claim_id: claimId,
          evidence_ids: validEvidenceIds,
          entity_ids: validEntityIds,
          text: raw.text,
          metadata: {
            original_claim: raw.claim,
            segment_index: idx,
          },
        };
      });
    } catch (error) {
      // Fallback: create a single segment
      return [
        {
          segment_id: randomUUID(),
          claim_id: randomUUID(),
          evidence_ids: [],
          entity_ids: [],
          text: response.substring(0, 500),
          metadata: {
            fallback: true,
            error: String(error),
          },
        },
      ];
    }
  }
}
