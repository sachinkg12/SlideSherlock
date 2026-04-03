import { S3Client, CreateBucketCommand, PutBucketPolicyCommand } from '@aws-sdk/client-s3';

async function initMinIO() {
  const client = new S3Client({
    endpoint: process.env.MINIO_ENDPOINT || 'http://localhost:9000',
    credentials: {
      accessKeyId: process.env.MINIO_ACCESS_KEY || 'minioadmin',
      secretAccessKey: process.env.MINIO_SECRET_KEY || 'minioadmin',
    },
    region: 'us-east-1',
    forcePathStyle: true,
  });

  const bucket = process.env.MINIO_BUCKET || 'slidesherlock';

  try {
    // Create bucket if it doesn't exist
    await client.send(new CreateBucketCommand({ Bucket: bucket }));
    console.log(`Bucket ${bucket} created or already exists`);
  } catch (error: any) {
    if (error.name === 'BucketAlreadyOwnedByYou') {
      console.log(`Bucket ${bucket} already exists`);
    } else {
      console.error('Error creating bucket:', error);
      throw error;
    }
  }
}

initMinIO().catch(console.error);
