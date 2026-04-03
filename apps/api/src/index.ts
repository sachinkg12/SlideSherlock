import express from 'express';
import multer from 'multer';
import { Database, JobRecord } from './db.js';
import { MinIOStorageClient } from '@slidesherlock/core';
import Redis from 'ioredis';
import { randomUUID } from 'crypto';

const app = express();
app.use(express.json());

const db = new Database(
  process.env.DATABASE_URL || 'postgresql://slidesherlock:slidesherlock@localhost:5432/slidesherlock'
);

const storage = new MinIOStorageClient(
  process.env.MINIO_ENDPOINT || 'http://localhost:9000',
  process.env.MINIO_ACCESS_KEY || 'minioadmin',
  process.env.MINIO_SECRET_KEY || 'minioadmin',
  process.env.MINIO_BUCKET || 'slidesherlock'
);

const redis = new Redis(process.env.REDIS_URL || 'redis://localhost:6379');

const upload = multer({ storage: multer.memoryStorage() });

// Initialize database
db.init().catch(console.error);

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

// Submit job
app.post('/jobs', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No file uploaded' });
    }

    const jobId = randomUUID();
    const inputPath = `jobs/${jobId}/input.pptx`;

    // Upload file to storage
    await storage.put(inputPath, req.file.buffer, 'application/vnd.openxmlformats-officedocument.presentationml.presentation');

    // Create job record
    const job: JobRecord = {
      job_id: jobId,
      status: 'PENDING',
      input_path: inputPath,
      created_at: new Date(),
      updated_at: new Date(),
    };

    await db.createJob(job);

    // Queue job
    await redis.lpush('jobs:queue', jobId);

    res.json({
      job_id: jobId,
      status: job.status,
      message: 'Job submitted successfully',
    });
  } catch (error) {
    console.error('Error submitting job:', error);
    res.status(500).json({ error: String(error) });
  }
});

// Get job status
app.get('/jobs/:jobId', async (req, res) => {
  try {
    const job = await db.getJob(req.params.jobId);
    if (!job) {
      return res.status(404).json({ error: 'Job not found' });
    }

    res.json(job);
  } catch (error) {
    console.error('Error getting job:', error);
    res.status(500).json({ error: String(error) });
  }
});

// Get job artifacts
app.get('/jobs/:jobId/artifacts/:artifact', async (req, res) => {
  try {
    const { jobId, artifact } = req.params;
    const artifactPaths: Record<string, string> = {
      script: `jobs/${jobId}/script.json`,
      verify_report: `jobs/${jobId}/verify_report.json`,
      coverage: `jobs/${jobId}/coverage.json`,
      timeline: `jobs/${jobId}/timeline/timeline.json`,
      evidence: `jobs/${jobId}/evidence/index.json`,
      graph_unified: `jobs/${jobId}/graph/unified.json`,
      final_video: `jobs/${jobId}/final.mp4`,
    };

    const path = artifactPaths[artifact];
    if (!path) {
      return res.status(400).json({ error: 'Invalid artifact name' });
    }

    if (!(await storage.exists(path))) {
      return res.status(404).json({ error: 'Artifact not found' });
    }

    const data = await storage.get(path);
    const contentType = artifact === 'final_video' ? 'video/mp4' : 'application/json';
    res.setHeader('Content-Type', contentType);
    res.send(data);
  } catch (error) {
    console.error('Error getting artifact:', error);
    res.status(500).json({ error: String(error) });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`API server listening on port ${PORT}`);
});
