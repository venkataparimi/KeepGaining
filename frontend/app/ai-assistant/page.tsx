'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Sparkles, TrendingUp, BarChart3, Lightbulb } from 'lucide-react';

interface Message {
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
}

const QUICK_PROMPTS = [
    { icon: TrendingUp, text: "Analyze my recent trades", prompt: "Analyze my recent trading performance and identify patterns" },
    { icon: BarChart3, text: "Explain RSI indicator", prompt: "Explain the RSI indicator and how to use it for trading" },
    { icon: Lightbulb, text: "Generate strategy", prompt: "Help me create a systematic trading strategy based on breakouts" },
    { icon: Sparkles, text: "Market insights", prompt: "What are the key things to watch in today's market?" },
];

export default function AIAssistantPage() {
    const [messages, setMessages] = useState<Message[]>([
        {
            role: 'assistant',
            content: "👋 Hi! I'm your AI trading assistant powered by Ollama. I can help you analyze trades, explain indicators, generate strategies, and answer any trading questions. What would you like to know?",
            timestamp: new Date()
        }
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const sendMessage = async (messageText?: string) => {
        const text = messageText || input;
        if (!text.trim() || isLoading) return;

        const userMessage: Message = {
            role: 'user',
            content: text,
            timestamp: new Date()
        };

        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsLoading(true);

        try {
            const response = await fetch('/api/ollama/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });

            if (!response.ok) throw new Error('Failed to get response');

            const data = await response.json();

            const assistantMessage: Message = {
                role: 'assistant',
                content: data.response,
                timestamp: new Date()
            };

            setMessages(prev => [...prev, assistantMessage]);
        } catch (error) {
            console.error('Error:', error);
            const errorMessage: Message = {
                role: 'assistant',
                content: '❌ Sorry, I encountered an error. Make sure Ollama is running (ollama serve) and try again.',
                timestamp: new Date()
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 p-6">
            <div className="max-w-6xl mx-auto">
                {/* Header */}
                <div className="mb-6 text-center">
                    <div className="flex items-center justify-center gap-3 mb-2">
                        <Bot className="w-10 h-10 text-purple-400" />
                        <h1 className="text-4xl font-bold text-white">AI Trading Assistant</h1>
                    </div>
                    <p className="text-purple-200">Powered by Ollama - 100% Local & Private</p>
                </div>

                {/* Quick Prompts */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-6">
                    {QUICK_PROMPTS.map((prompt, idx) => (
                        <button
                            key={idx}
                            onClick={() => sendMessage(prompt.prompt)}
                            disabled={isLoading}
                            className="flex items-center gap-2 p-3 bg-white/10 hover:bg-white/20 backdrop-blur-sm rounded-lg border border-purple-500/30 transition-all hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <prompt.icon className="w-5 h-5 text-purple-400" />
                            <span className="text-sm text-white font-medium">{prompt.text}</span>
                        </button>
                    ))}
                </div>

                {/* Chat Container */}
                <div className="bg-white/10 backdrop-blur-md rounded-2xl border border-purple-500/30 shadow-2xl overflow-hidden">
                    {/* Messages */}
                    <div className="h-[600px] overflow-y-auto p-6 space-y-4">
                        {messages.map((message, idx) => (
                            <div
                                key={idx}
                                className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                            >
                                {message.role === 'assistant' && (
                                    <div className="flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
                                        <Bot className="w-6 h-6 text-white" />
                                    </div>
                                )}

                                <div
                                    className={`max-w-[70%] rounded-2xl p-4 ${message.role === 'user'
                                            ? 'bg-gradient-to-br from-blue-500 to-purple-600 text-white'
                                            : 'bg-white/20 text-white backdrop-blur-sm'
                                        }`}
                                >
                                    <div className="whitespace-pre-wrap break-words">{message.content}</div>
                                    <div className="text-xs opacity-60 mt-2">
                                        {message.timestamp.toLocaleTimeString()}
                                    </div>
                                </div>

                                {message.role === 'user' && (
                                    <div className="flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center">
                                        <User className="w-6 h-6 text-white" />
                                    </div>
                                )}
                            </div>
                        ))}

                        {isLoading && (
                            <div className="flex gap-3 justify-start">
                                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
                                    <Bot className="w-6 h-6 text-white animate-pulse" />
                                </div>
                                <div className="bg-white/20 backdrop-blur-sm rounded-2xl p-4">
                                    <div className="flex gap-2">
                                        <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                                        <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                                        <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                                    </div>
                                </div>
                            </div>
                        )}

                        <div ref={messagesEndRef} />
                    </div>

                    {/* Input */}
                    <div className="border-t border-purple-500/30 p-4 bg-white/5">
                        <div className="flex gap-3">
                            <textarea
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyPress={handleKeyPress}
                                placeholder="Ask me anything about trading, strategies, or indicators..."
                                disabled={isLoading}
                                className="flex-1 bg-white/10 text-white placeholder-purple-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none disabled:opacity-50"
                                rows={2}
                            />
                            <button
                                onClick={() => sendMessage()}
                                disabled={isLoading || !input.trim()}
                                className="px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-xl font-medium transition-all hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 flex items-center gap-2"
                            >
                                <Send className="w-5 h-5" />
                                Send
                            </button>
                        </div>
                        <div className="mt-2 text-xs text-purple-300 text-center">
                            Press Enter to send • Shift+Enter for new line
                        </div>
                    </div>
                </div>

                {/* Info Footer */}
                <div className="mt-6 text-center text-sm text-purple-300">
                    <p>💡 This AI runs 100% locally on your computer using Ollama</p>
                    <p className="mt-1">No data is sent to external servers • Completely private</p>
                </div>
            </div>
        </div>
    );
}
