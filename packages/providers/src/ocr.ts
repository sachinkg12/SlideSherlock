export interface OCRProvider {
  recognize(imageBuffer: Buffer, options?: OCROptions): Promise<OCRResult>;
}

export interface OCROptions {
  language?: string;
}

export interface OCRResult {
  text: string;
  words: Array<{
    text: string;
    bbox: {
      x: number;
      y: number;
      width: number;
      height: number;
    };
    confidence: number;
  }>;
}

export class NoOpOCRProvider implements OCRProvider {
  async recognize(imageBuffer: Buffer, options?: OCROptions): Promise<OCRResult> {
    return {
      text: '',
      words: [],
    };
  }
}

export class TesseractOCRProvider implements OCRProvider {
  private language: string;

  constructor(language: string = 'eng') {
    this.language = language;
  }

  async recognize(imageBuffer: Buffer, options?: OCROptions): Promise<OCRResult> {
    // This would use tesseract.js in a real implementation
    // For now, return empty result
    return {
      text: '',
      words: [],
    };
  }
}
