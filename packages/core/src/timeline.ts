import type {
  Script,
  Timeline,
  TimelineAction,
  ActionType,
  Graph,
} from '@slidesherlock/schemas';
import { randomUUID } from 'crypto';

export class TimelineBuilder {
  /**
   * Generate timeline actions from verified script + alignment
   */
  async build(
    script: Script,
    graph: Graph,
    wordsPerMinute: number = 150
  ): Promise<Timeline> {
    const actions: TimelineAction[] = [];
    let currentTime = 0;

    for (const segment of script.segments) {
      // Estimate duration based on word count
      const wordCount = segment.text.split(/\s+/).length;
      const duration = (wordCount / wordsPerMinute) * 60; // seconds

      // Determine action type based on entity_ids
      const actionType = this.determineActionType(segment, graph);

      if (actionType !== 'NONE' && segment.entity_ids.length > 0) {
        // Get geometry from first entity
        const entityId = segment.entity_ids[0];
        const entity = graph.nodes.find((n) => n.node_id === entityId);

        if (entity) {
          actions.push({
            action_id: randomUUID(),
            segment_id: segment.segment_id,
            action_type: actionType,
            entity_id: entityId,
            geometry: entity.geometry,
            start_time: currentTime,
            end_time: currentTime + duration,
            metadata: {
              text: segment.text,
            },
          });
        }
      } else {
        // No visual action, just narration
        actions.push({
          action_id: randomUUID(),
          segment_id: segment.segment_id,
          action_type: 'NONE',
          start_time: currentTime,
          end_time: currentTime + duration,
          metadata: {
            text: segment.text,
          },
        });
      }

      // Update segment timing
      segment.start_time = currentTime;
      segment.end_time = currentTime + duration;

      currentTime += duration;
    }

    return {
      timeline_id: randomUUID(),
      job_id: script.job_id,
      actions,
      total_duration: currentTime,
      metadata: {
        words_per_minute: wordsPerMinute,
        generated_at: new Date().toISOString(),
      },
    };
  }

  private determineActionType(segment: ScriptSegment, graph: Graph): ActionType {
    if (segment.entity_ids.length === 0) {
      return 'NONE';
    }

    // Simple heuristic: use HIGHLIGHT for most cases
    // Could be enhanced with LLM-based decision
    const entity = graph.nodes.find((n) => n.node_id === segment.entity_ids[0]);
    
    if (!entity) {
      return 'NONE';
    }

    // If entity is large, use ZOOM
    const area = entity.geometry.width * entity.geometry.height;
    if (area > 50000) {
      return 'ZOOM';
    }

    // If entity is connected, use TRACE
    const hasConnections = graph.edges.some(
      (e) => e.source_id === entity.node_id || e.target_id === entity.node_id
    );
    if (hasConnections) {
      return 'TRACE';
    }

    // Default to HIGHLIGHT
    return 'HIGHLIGHT';
  }
}
