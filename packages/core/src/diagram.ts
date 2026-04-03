import type { Graph, Node, Edge, Provenance } from '@slidesherlock/schemas';
import type { OCRProvider, OCRResult } from '@slidesherlock/providers';

export interface PPTShape {
  shape_id: string;
  type: string;
  geometry: {
    x: number;
    y: number;
    width: number;
    height: number;
    page: number;
  };
  text?: string;
  metadata?: Record<string, unknown>;
}

export interface PPTConnector {
  connector_id: string;
  source_id: string;
  target_id: string;
  type: string;
  metadata?: Record<string, unknown>;
}

export interface PPTGroup {
  group_id: string;
  shape_ids: string[];
  metadata?: Record<string, unknown>;
}

export class DiagramUnderstanding {
  /**
   * Build G_native from PPT objects
   */
  buildNativeGraph(
    shapes: PPTShape[],
    connectors: PPTConnector[],
    groups: PPTGroup[] = []
  ): Graph {
    const nodes: Node[] = shapes.map((shape) => ({
      node_id: shape.shape_id,
      label: shape.text || shape.type,
      type: shape.type,
      geometry: shape.geometry,
      confidence: 1.0,
      provenance: 'NATIVE' as Provenance,
      needs_review: false,
      metadata: shape.metadata,
    }));

    const edges: Edge[] = connectors.map((connector) => ({
      edge_id: connector.connector_id,
      source_id: connector.source_id,
      target_id: connector.target_id,
      label: connector.type,
      type: connector.type,
      confidence: 1.0,
      provenance: 'NATIVE' as Provenance,
      needs_review: false,
      metadata: connector.metadata,
    }));

    return {
      graph_id: `native-${Date.now()}`,
      nodes,
      edges,
      metadata: {
        groups: groups.map((g) => ({
          group_id: g.group_id,
          shape_ids: g.shape_ids,
        })),
      },
    };
  }

  /**
   * Build G_vision from PNG + OCR
   */
  async buildVisionGraph(
    imageBuffer: Buffer,
    page: number,
    ocrProvider: OCRProvider
  ): Promise<Graph> {
    const ocrResult = await ocrProvider.recognize(imageBuffer);

    const nodes: Node[] = ocrResult.words.map((word, idx) => ({
      node_id: `vision-word-${page}-${idx}`,
      label: word.text,
      type: 'text',
      geometry: {
        ...word.bbox,
        page,
      },
      confidence: word.confidence,
      provenance: 'VISION' as Provenance,
      needs_review: word.confidence < 0.7,
      metadata: {},
    }));

    // Simple edge detection based on proximity
    const edges: Edge[] = [];
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const n1 = nodes[i];
        const n2 = nodes[j];
        const distance = Math.sqrt(
          Math.pow(n1.geometry.x - n2.geometry.x, 2) +
          Math.pow(n1.geometry.y - n2.geometry.y, 2)
        );
        if (distance < 100) {
          edges.push({
            edge_id: `vision-edge-${page}-${i}-${j}`,
            source_id: n1.node_id,
            target_id: n2.node_id,
            type: 'proximity',
            confidence: 0.5,
            provenance: 'VISION' as Provenance,
            needs_review: true,
            metadata: { distance },
          });
        }
      }
    }

    return {
      graph_id: `vision-${page}-${Date.now()}`,
      nodes,
      edges,
      metadata: {
        page,
        ocr_text: ocrResult.text,
      },
    };
  }

  /**
   * Merge G_native and G_vision to G_unified
   */
  mergeGraphs(native: Graph, vision?: Graph): Graph {
    const nodeMap = new Map<string, Node>();
    const edgeMap = new Map<string, Edge>();

    // Add native nodes
    for (const node of native.nodes) {
      nodeMap.set(node.node_id, { ...node });
    }

    // Add native edges
    for (const edge of native.edges) {
      edgeMap.set(edge.edge_id, { ...edge });
    }

    // Merge vision nodes
    if (vision) {
      for (const visionNode of vision.nodes) {
        const existing = nodeMap.get(visionNode.node_id);
        if (existing) {
          // Both sources agree
          existing.provenance = 'BOTH';
          existing.confidence = Math.max(existing.confidence, visionNode.confidence);
          existing.needs_review = existing.needs_review || visionNode.needs_review;
        } else {
          // Only vision
          nodeMap.set(visionNode.node_id, { ...visionNode });
        }
      }

      // Merge vision edges
      for (const visionEdge of vision.edges) {
        const existing = edgeMap.get(visionEdge.edge_id);
        if (existing) {
          existing.provenance = 'BOTH';
          existing.confidence = Math.max(existing.confidence, visionEdge.confidence);
          existing.needs_review = existing.needs_review || visionEdge.needs_review;
        } else {
          edgeMap.set(visionEdge.edge_id, { ...visionEdge });
        }
      }
    }

    return {
      graph_id: `unified-${Date.now()}`,
      nodes: Array.from(nodeMap.values()),
      edges: Array.from(edgeMap.values()),
      metadata: {
        ...native.metadata,
        merged_at: new Date().toISOString(),
        has_vision: !!vision,
      },
    };
  }
}
