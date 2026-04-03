import { TimelineBuilder } from '../timeline.js';
import type { Script, Graph } from '@slidesherlock/schemas';

// Jest globals
declare const describe: (name: string, fn: () => void) => void;
declare const it: (name: string, fn: () => void | Promise<void>) => void;
declare const expect: (value: unknown) => {
  toBe: (expected: unknown) => void;
  toHaveLength: (length: number) => void;
  toBeGreaterThan: (value: number) => void;
  toBeGreaterThanOrEqual: (value: number) => void;
};

describe('TimelineBuilder', () => {
  const builder = new TimelineBuilder();

  describe('build', () => {
    it('should generate timeline with actions', async () => {
      const script: Script = {
        script_id: 'script-1',
        job_id: 'job-1',
        segments: [
          {
            segment_id: 'seg-1',
            claim_id: 'claim-1',
            evidence_ids: ['ev-1'],
            entity_ids: ['entity-1'],
            text: 'This is a test segment with some words',
          },
        ],
      };

      const graph: Graph = {
        graph_id: 'graph-1',
        nodes: [
          {
            node_id: 'entity-1',
            label: 'Entity 1',
            type: 'rectangle',
            geometry: { x: 10, y: 10, width: 100, height: 50, page: 0 },
            confidence: 1.0,
            provenance: 'NATIVE',
            needs_review: false,
          },
        ],
        edges: [],
      };

      const timeline = await builder.build(script, graph, 150);

      expect(timeline.actions).toHaveLength(1);
      expect(timeline.actions[0].action_type).not.toBe('NONE');
      expect(timeline.actions[0].entity_id).toBe('entity-1');
      expect(timeline.actions[0].start_time).toBeGreaterThanOrEqual(0);
      expect(timeline.actions[0].end_time).toBeGreaterThan(timeline.actions[0].start_time);
    });

    it('should handle segments without entities', async () => {
      const script: Script = {
        script_id: 'script-1',
        job_id: 'job-1',
        segments: [
          {
            segment_id: 'seg-1',
            claim_id: 'claim-1',
            evidence_ids: ['ev-1'],
            entity_ids: [],
            text: 'Segment without entities',
          },
        ],
      };

      const graph: Graph = {
        graph_id: 'graph-1',
        nodes: [],
        edges: [],
      };

      const timeline = await builder.build(script, graph);

      expect(timeline.actions).toHaveLength(1);
      expect(timeline.actions[0].action_type).toBe('NONE');
    });
  });

  describe('determineActionType', () => {
    it('should return ZOOM for large entities', () => {
      const segment = {
        segment_id: 'seg-1',
        claim_id: 'claim-1',
        evidence_ids: [],
        entity_ids: ['entity-1'],
        text: 'Test',
      };

      const graph: Graph = {
        graph_id: 'graph-1',
        nodes: [
          {
            node_id: 'entity-1',
            label: 'Large Entity',
            type: 'rectangle',
            geometry: { x: 10, y: 10, width: 300, height: 200, page: 0 },
            confidence: 1.0,
            provenance: 'NATIVE',
            needs_review: false,
          },
        ],
        edges: [],
      };

      const actionType = (builder as any).determineActionType(segment, graph);
      expect(actionType).toBe('ZOOM');
    });

    it('should return TRACE for connected entities', () => {
      const segment = {
        segment_id: 'seg-1',
        claim_id: 'claim-1',
        evidence_ids: [],
        entity_ids: ['entity-1'],
        text: 'Test',
      };

      const graph: Graph = {
        graph_id: 'graph-1',
        nodes: [
          {
            node_id: 'entity-1',
            label: 'Entity 1',
            type: 'rectangle',
            geometry: { x: 10, y: 10, width: 100, height: 50, page: 0 },
            confidence: 1.0,
            provenance: 'NATIVE',
            needs_review: false,
          },
        ],
        edges: [
          {
            edge_id: 'edge-1',
            source_id: 'entity-1',
            target_id: 'entity-2',
            type: 'arrow',
            confidence: 1.0,
            provenance: 'NATIVE',
            needs_review: false,
          },
        ],
      };

      const actionType = (builder as any).determineActionType(segment, graph);
      expect(actionType).toBe('TRACE');
    });
  });
});
