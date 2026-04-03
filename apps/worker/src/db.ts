import pg from 'pg';
const { Pool } = pg;

export interface JobRecord {
  job_id: string;
  status: string;
  input_path: string;
  created_at: Date;
  updated_at: Date;
  error?: string;
  metadata?: Record<string, unknown>;
}

export class Database {
  private pool: pg.Pool;

  constructor(connectionString: string) {
    this.pool = new Pool({ connectionString });
  }

  async init() {
    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS jobs (
        job_id VARCHAR(255) PRIMARY KEY,
        status VARCHAR(50) NOT NULL,
        input_path TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        error TEXT,
        metadata JSONB
      );

      CREATE TABLE IF NOT EXISTS evidence (
        evidence_id VARCHAR(255) PRIMARY KEY,
        job_id VARCHAR(255) NOT NULL,
        source_ref JSONB NOT NULL,
        content TEXT NOT NULL,
        metadata JSONB,
        created_at TIMESTAMP DEFAULT NOW(),
        FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
      );

      CREATE INDEX IF NOT EXISTS idx_evidence_job_id ON evidence(job_id);
    `);
  }

  async createJob(job: JobRecord): Promise<void> {
    await this.pool.query(
      `INSERT INTO jobs (job_id, status, input_path, created_at, updated_at, error, metadata)
       VALUES ($1, $2, $3, $4, $5, $6, $7)
       ON CONFLICT (job_id) DO UPDATE SET
         status = EXCLUDED.status,
         updated_at = EXCLUDED.updated_at,
         error = EXCLUDED.error,
         metadata = EXCLUDED.metadata`,
      [
        job.job_id,
        job.status,
        job.input_path,
        job.created_at,
        job.updated_at,
        job.error || null,
        job.metadata ? JSON.stringify(job.metadata) : null,
      ]
    );
  }

  async updateJobStatus(jobId: string, status: string, error?: string): Promise<void> {
    await this.pool.query(
      `UPDATE jobs SET status = $1, updated_at = NOW(), error = $2 WHERE job_id = $3`,
      [status, error || null, jobId]
    );
  }

  async getJob(jobId: string): Promise<JobRecord | null> {
    const result = await this.pool.query(
      `SELECT * FROM jobs WHERE job_id = $1`,
      [jobId]
    );
    if (result.rows.length === 0) {
      return null;
    }
    const row = result.rows[0];
    return {
      job_id: row.job_id,
      status: row.status,
      input_path: row.input_path,
      created_at: row.created_at,
      updated_at: row.updated_at,
      error: row.error,
      metadata: row.metadata,
    };
  }

  async saveEvidence(evidence: Array<{ evidence_id: string; job_id: string; source_ref: unknown; content: string; metadata?: unknown }>): Promise<void> {
    for (const ev of evidence) {
      await this.pool.query(
        `INSERT INTO evidence (evidence_id, job_id, source_ref, content, metadata)
         VALUES ($1, $2, $3, $4, $5)
         ON CONFLICT (evidence_id) DO UPDATE SET
           source_ref = EXCLUDED.source_ref,
           content = EXCLUDED.content,
           metadata = EXCLUDED.metadata`,
        [
          ev.evidence_id,
          ev.job_id,
          JSON.stringify(ev.source_ref),
          ev.content,
          ev.metadata ? JSON.stringify(ev.metadata) : null,
        ]
      );
    }
  }

  async close() {
    await this.pool.end();
  }
}
