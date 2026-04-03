import { Database } from './db.js';
import { Pipeline } from './pipeline.js';
import { MinIOStorageClient } from '@slidesherlock/core';
import {
  NoOpLLMProvider,
  NoOpTTSProvider,
  NoOpOCRProvider,
  OpenAIProvider,
  SystemTTSProvider,
} from '@slidesherlock/providers';
import Redis from 'ioredis';

async function createProviders() {
  const llmProvider = process.env.OPENAI_API_KEY
    ? new OpenAIProvider(process.env.OPENAI_API_KEY)
    : new NoOpLLMProvider();

  const ttsProvider = process.env.USE_SYSTEM_TTS === 'true'
    ? new SystemTTSProvider()
    : new NoOpTTSProvider();

  const ocrProvider = new NoOpOCRProvider();

  return { llmProvider, ttsProvider, ocrProvider };
}

async function main() {
  const db = new Database(
    process.env.DATABASE_URL || 'postgresql://slidesherlock:slidesherlock@localhost:5432/slidesherlock'
  );

  const storage = new MinIOStorageClient(
    process.env.MINIO_ENDPOINT || 'http://localhost:9000',
    process.env.MINIO_ACCESS_KEY || 'minioadmin',
    process.env.MINIO_SECRET_KEY || 'minioadmin',
    process.env.MINIO_BUCKET || 'slidesherlock'
  );

  const { llmProvider, ttsProvider, ocrProvider } = await createProviders();
  const pipeline = new Pipeline(db, storage, llmProvider, ttsProvider, ocrProvider);
  const redis = new Redis(process.env.REDIS_URL || 'redis://localhost:6379');

  await db.init();
  console.log('Worker started, waiting for jobs...');

  // Poll Redis for jobs
  while (true) {
    try {
      const jobId = await redis.brpop('jobs:queue', 5);
      if (jobId) {
        const [, id] = jobId;
        console.log(`Processing job: ${id}`);
        await pipeline.process(id);
        console.log(`Completed job: ${id}`);
      }
    } catch (error) {
      console.error('Error processing job:', error);
    }
  }
}

main().catch(console.error);
