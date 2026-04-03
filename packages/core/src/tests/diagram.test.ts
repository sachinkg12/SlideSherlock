import { DiagramUnderstanding } from '../diagram.js';
import type { Graph } from '@slidesherlock/schemas';
import { NoOpOCRProvider } from '@slidesherlock/providers';

// Jest globals
declare const describe: (name: string, fn: () => void) => void;
declare const it: (name: string, fn: () => void | Promise<void>) => void;
declare const expect: (value: unknown) => {
  toBe: (expected: unknown) => void;
  toHaveLength: (length: number) => void;
  toContain: (item: unknown) => void;
  toBeGreaterThan: (value: number) => void;
  toBeGreaterThanOrEqual: (value: number) => void;
};

describe('DiagramUnderstanding', () => {
  const diagramUnderstanding = new DiagramUnderstanding();
  const ocrProvider = new NoOpOCRProvider();

  describe('buildNativeGraph', () => {
    it('should build graph from PPT shapes and connectors', () => {
      const shapes = [
        {
          shape_id: 'shape-1',
          type: 'rectangle',
          geometry: { x: 10, y: 10, width: 100, height: 50, page: 0 },
          text: 'Node 1',
        },
        {
          shape_id: 'shape-2',
          type: 'rectangle',
          geometry: { x: 150, y: 10, width: 100, height: 50, page: 0 },
          text: 'Node 2',
        },
      ];

      const connectors = [
        {
          connector_id: 'conn-1',
          source_id: 'shape-1',
          target_id: 'shape-2',
          type: 'arrow',
        },
      ];

      const graph = diagramUnderstanding.buildNativeGraph(shapes, connectors);

      expect(graph.nodes).toHaveLength(2);
      expect(graph.edges).toHaveLength(1);
      expect(graph.nodes[0].provenance).toBe('NATIVE');
      expect(graph.nodes[0].confidence).toBe(1.0);
      expect(graph.edges[0].source_id).toBe('shape-1');
      expect(graph.edges[0].target_id).toBe('shape-2');
    });
  });

  describe('mergeGraphs', () => {
    it('should merge native and vision graphs', () => {
      const native: Graph = {
        graph_id: 'native-1',
        nodes: [
          {
            node_id: 'node-1',
            label: 'Node 1',
            type: 'rectangle',
            geometry: { x: 10, y: 10, width: 100, height: 50, page: 0 },
            confidence: 1.0,
            provenance: 'NATIVE',
            needs_review: false,
          },
        ],
        edges: [],
      };

      const vision: Graph = {
        graph_id: 'vision-1',
        nodes: [
          {
            node_id: 'node-1',
            label: 'Node 1',
            type: 'rectangle',
            geometry: { x: 10, y: 10, width: 100, height: 50, page: 0 },
            confidence: 0.9,
            provenance: 'VISION',
            needs_review: false,
          },
          {
            node_id: 'node-2',
            label: 'Node 2',
            type: 'text',
            geometry: { x: 150, y: 10, width: 50, height: 20, page: 0 },
            confidence: 0.8,
            provenance: 'VISION',
            needs_review: true,
          },
        ],
        edges: [],
      };

      const merged = diagramUnderstanding.mergeGraphs(native, vision);

      expect(merged.nodes).toHaveLength(2);
      const node1 = merged.nodes.find((n) => n.node_id === 'node-1');
      expect(node1?.provenance).toBe('BOTH');
      expect(node1?.confidence).toBe(1.0); // Max of 1.0 and 0.9

      const node2 = merged.nodes.find((n) => n.node_id === 'node-2');
      expect(node2?.provenance).toBe('VISION');
    });

    it('should handle native-only graph', () => {
      const native: Graph = {
        graph_id: 'native-1',
        nodes: [
          {
            node_id: 'node-1',
            label: 'Node 1',
            type: 'rectangle',
            geometry: { x: 10, y: 10, width: 100, height: 50, page: 0 },
            confidence: 1.0,
            provenance: 'NATIVE',
            needs_review: false,
          },
        ],
        edges: [],
      };

      const merged = diagramUnderstanding.mergeGraphs(native);
      expect(merged.nodes).toHaveLength(1);
      expect(merged.nodes[0].provenance).toBe('NATIVE');
    });
  });
});
