export interface LLMProvider {
  generate(prompt: string, options?: LLMOptions): Promise<string>;
  generateStructured<T>(prompt: string, schema: unknown, options?: LLMOptions): Promise<T>;
}

export interface LLMOptions {
  temperature?: number;
  maxTokens?: number;
  model?: string;
}

export class NoOpLLMProvider implements LLMProvider {
  async generate(prompt: string, options?: LLMOptions): Promise<string> {
    return `[NO-OP LLM] Response to: ${prompt.substring(0, 50)}...`;
  }

  async generateStructured<T>(prompt: string, schema: unknown, options?: LLMOptions): Promise<T> {
    return {} as T;
  }
}

export class OpenAIProvider implements LLMProvider {
  private apiKey: string;
  private model: string;

  constructor(apiKey: string, model: string = 'gpt-4') {
    this.apiKey = apiKey;
    this.model = model;
  }

  async generate(prompt: string, options?: LLMOptions): Promise<string> {
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: options?.model || this.model,
        messages: [{ role: 'user', content: prompt }],
        temperature: options?.temperature ?? 0.7,
        max_tokens: options?.maxTokens ?? 2000,
      }),
    });

    if (!response.ok) {
      throw new Error(`OpenAI API error: ${response.statusText}`);
    }

    const data = await response.json();
    return data.choices[0].message.content;
  }

  async generateStructured<T>(prompt: string, schema: unknown, options?: LLMOptions): Promise<T> {
    const response = await this.generate(prompt, options);
    try {
      return JSON.parse(response) as T;
    } catch {
      throw new Error('Failed to parse structured response');
    }
  }
}
