import { Verifier } from '../verifier.js';
import type { Script, Evidence } from '@slidesherlock/schemas';
import { NoOpLLMProvider } from '@slidesherlock/providers';

// Jest globals
declare const describe: (name: string, fn: () => void) => void;
declare const it: (name: string, fn: () => void | Promise<void>) => void;
declare const expect: (value: unknown) => {
  toBe: (expected: unknown) => void;
  toContain: (item: unknown) => void;
  toEqual: (expected: unknown) => void;
};

describe('Verifier', () => {
  const llmProvider = new NoOpLLMProvider();
  const verifier = new Verifier(llmProvider);

  describe('verifySegment', () => {
    it('should mark segment as REWRITE if no evidence_ids', async () => {
      const segment = {
        segment_id: 'seg-1',
        claim_id: 'claim-1',
        evidence_ids: [],
        entity_ids: [],
        text: 'Some claim without evidence',
      };

      const evidenceIndex: Evidence[] = [];

      // Access private method via type assertion (in real test, make it public or use a test helper)
      const result = await (verifier as any).verifySegment(segment, evidenceIndex);

      expect(result.verdict).toBe('REWRITE');
      expect(result.reason).toContain('No evidence_ids');
    });

    it('should mark segment as REWRITE if evidence_ids are invalid', async () => {
      const segment = {
        segment_id: 'seg-1',
        claim_id: 'claim-1',
        evidence_ids: ['invalid-ev-1'],
        entity_ids: [],
        text: 'Some claim',
      };

      const evidenceIndex: Evidence[] = [
        {
          evidence_id: 'ev-1',
          source_ref: { type: 'page_char', page: 0, char_start: 0, char_end: 10 },
          content: 'Valid evidence',
        },
      ];

      const result = await (verifier as any).verifySegment(segment, evidenceIndex);

      expect(result.verdict).toBe('REWRITE');
      expect(result.reason).toContain('Invalid evidence_ids');
    });
  });

  describe('buildCoverage', () => {
    it('should build coverage map correctly', () => {
      const script: Script = {
        script_id: 'script-1',
        job_id: 'job-1',
        segments: [
          {
            segment_id: 'seg-1',
            claim_id: 'claim-1',
            evidence_ids: ['ev-1', 'ev-2'],
            entity_ids: ['entity-1'],
            text: 'Segment 1',
          },
          {
            segment_id: 'seg-2',
            claim_id: 'claim-2',
            evidence_ids: ['ev-2'],
            entity_ids: ['entity-2'],
            text: 'Segment 2',
          },
        ],
      };

      const evidenceIndex: Evidence[] = [
        {
          evidence_id: 'ev-1',
          source_ref: { type: 'page_char', page: 0, char_start: 0, char_end: 10 },
          content: 'Evidence 1',
        },
        {
          evidence_id: 'ev-2',
          source_ref: { type: 'page_char', page: 0, char_start: 10, char_end: 20 },
          content: 'Evidence 2',
        },
        {
          evidence_id: 'ev-3',
          source_ref: { type: 'page_char', page: 0, char_start: 20, char_end: 30 },
          content: 'Evidence 3',
        },
      ];

      const coverage = (verifier as any).buildCoverage(script, evidenceIndex);

      expect(coverage.evidence_coverage['ev-1']).toEqual(['seg-1']);
      expect(coverage.evidence_coverage['ev-2']).toEqual(['seg-1', 'seg-2']);
      expect(coverage.evidence_coverage['ev-3']).toEqual([]);
      expect(coverage.gaps).toContain('Evidence ev-3 not covered');
    });
  });
});
