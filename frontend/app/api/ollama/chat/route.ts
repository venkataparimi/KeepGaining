import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
    try {
        const { message } = await request.json();

        if (!message) {
            return NextResponse.json(
                { error: 'Message is required' },
                { status: 400 }
            );
        }

        // Call Ollama API with optimized settings
        const response = await fetch('http://localhost:11434/api/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                model: 'phi3',  // Fast, small model (3.8B parameters)
                prompt: `You are a concise trading expert. Answer briefly and actionably:\n\n${message}`,
                stream: false,
                options: {
                    temperature: 0.3,      // More focused responses
                    top_p: 0.9,           // Reduce randomness
                    num_predict: 300,     // Limit response length for speed
                    stop: ['\n\n\n']      // Stop at triple newlines
                }
            }),
        });

        if (!response.ok) {
            throw new Error(`Ollama API error: ${response.status}`);
        }

        const data = await response.json();

        return NextResponse.json({
            response: data.response || 'No response from AI',
        });
    } catch (error) {
        console.error('Ollama API error:', error);
        return NextResponse.json(
            {
                error: 'Failed to get AI response. Make sure Ollama is running (ollama serve)',
                details: error instanceof Error ? error.message : 'Unknown error'
            },
            { status: 500 }
        );
    }
}
