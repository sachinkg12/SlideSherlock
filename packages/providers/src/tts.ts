export interface TTSProvider {
  synthesize(text: string, options?: TTSOptions): Promise<Buffer>;
}

export interface TTSOptions {
  voice?: string;
  speed?: number;
  pitch?: number;
}

export class NoOpTTSProvider implements TTSProvider {
  async synthesize(text: string, options?: TTSOptions): Promise<Buffer> {
    // Return empty audio buffer
    return Buffer.from([]);
  }
}

export class SystemTTSProvider implements TTSProvider {
  async synthesize(text: string, options?: TTSOptions): Promise<Buffer> {
    // Use system TTS (e.g., macOS say command)
    const { execSync } = await import('child_process');
    const fs = await import('fs');
    const os = await import('os');
    const path = await import('path');

    const tempFile = path.join(os.tmpdir(), `tts-${Date.now()}.aiff`);
    
    try {
      const speed = options?.speed ?? 1.0;
      execSync(`say -o "${tempFile}" -r ${Math.round(175 * speed)} "${text}"`, { stdio: 'ignore' });
      const audio = fs.readFileSync(tempFile);
      fs.unlinkSync(tempFile);
      return audio;
    } catch (error) {
      if (fs.existsSync(tempFile)) {
        try {
          fs.unlinkSync(tempFile);
        } catch {
          // Ignore cleanup errors
        }
      }
      throw error;
    }
  }
}
