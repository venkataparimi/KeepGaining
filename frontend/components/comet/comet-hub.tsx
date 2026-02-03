"use client";

import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { 
    Sparkles, Send, TrendingUp, TrendingDown, AlertTriangle,
    BarChart3, Target, Clock, Brain, Zap, RefreshCw, Search,
    Building2, Loader2, MessageSquare, ArrowUpRight, ArrowDownRight,
    Shield, Eye, Activity, ChevronRight, Lightbulb, Radio
} from "lucide-react";
import { apiClient } from "@/lib/api/client";

interface TradingSignal {
    symbol: string;
    action: 'BUY' | 'SELL' | 'WATCH' | 'SKIP';
    reasoning: string;
    timeframe: 'immediate' | 'short_term' | 'medium_term';
}

interface CometResponse {
    sentiment: number;
    confidence: number;
    key_insights: string[];
    trading_signals: TradingSignal[];
    risks: string[];
    data_freshness?: string;
    raw_response?: string;
}

interface ChatMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
    analysis?: CometResponse;
}

const SECTORS = [
    'IT', 'Banking', 'Pharma', 'Auto', 'FMCG', 'Energy', 
    'Metals', 'Realty', 'Infra', 'Media', 'Telecom'
];

const QUICK_PROMPTS = [
    { label: "Today's Market Outlook", type: "macro_analysis", event: "Today's Indian market outlook" },
    { label: "FII/DII Activity Impact", type: "macro_analysis", event: "Recent FII DII activity and market impact" },
    { label: "Global Cues Analysis", type: "macro_analysis", event: "Global market cues impact on Nifty" },
    { label: "Rate Cut Impact", type: "macro_analysis", event: "RBI rate cut expectations and beneficiary stocks" },
];

// Helper function to normalize API responses to the required types
function normalizeResponse(response: any): CometResponse {
    return {
        sentiment: response.sentiment,
        confidence: response.confidence,
        key_insights: response.key_insights,
        trading_signals: (response.trading_signals || []).map((signal: any) => ({
            symbol: signal.symbol,
            action: (signal.action?.toUpperCase?.() || 'WATCH') as 'BUY' | 'SELL' | 'WATCH' | 'SKIP',
            reasoning: signal.reasoning,
            timeframe: (signal.timeframe || 'short_term') as 'immediate' | 'short_term' | 'medium_term'
        })),
        risks: response.risks,
        data_freshness: response.data_freshness,
        raw_response: response.raw_response
    };
}

export function CometHub() {
    const [loading, setLoading] = useState(false);
    const [activeTab, setActiveTab] = useState('chat');
    
    // Chat state
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [inputValue, setInputValue] = useState('');
    const [conversationId] = useState(() => `conv_${Date.now()}`);
    const chatEndRef = useRef<HTMLDivElement>(null);
    
    // Analysis state
    const [selectedSector, setSelectedSector] = useState<string>('');
    const [stockSymbol, setStockSymbol] = useState('');
    const [breakoutSymbol, setBreakoutSymbol] = useState('');
    const [breakoutPrice, setBreakoutPrice] = useState('');
    const [currentAnalysis, setCurrentAnalysis] = useState<CometResponse | null>(null);
    
    // API Status
    const [apiStatus, setApiStatus] = useState<'connected' | 'disconnected' | 'checking'>('checking');

    useEffect(() => {
        checkApiStatus();
    }, []);

    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const checkApiStatus = async () => {
        setApiStatus('checking');
        try {
            const response = await apiClient.cometAnalyze({
                type: 'general',
                additional_data: { test: true }
            });
            setApiStatus(response.confidence > 0 ? 'connected' : 'disconnected');
        } catch {
            setApiStatus('disconnected');
        }
    };

    const handleSendMessage = async () => {
        if (!inputValue.trim() || loading) return;
        
        const userMessage: ChatMessage = {
            id: `msg_${Date.now()}`,
            role: 'user',
            content: inputValue,
            timestamp: new Date()
        };
        
        setMessages(prev => [...prev, userMessage]);
        setInputValue('');
        setLoading(true);
        
        try {
            const response = await apiClient.cometAnalyze({
                type: 'general',
                additional_data: { query: inputValue }
            });
            
            const assistantMessage: ChatMessage = {
                id: `msg_${Date.now()}`,
                role: 'assistant',
                content: response.key_insights.join('\n\n') || 'Analysis complete.',
                timestamp: new Date(),
                analysis: response
            };
            
            setMessages(prev => [...prev, assistantMessage]);
            setCurrentAnalysis(normalizeResponse(response));
        } catch (error) {
            const errorMessage: ChatMessage = {
                id: `msg_${Date.now()}`,
                role: 'assistant',
                content: 'Sorry, I encountered an error processing your request. Please ensure the backend is running with a valid ANTHROPIC_API_KEY.',
                timestamp: new Date()
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setLoading(false);
        }
    };

    const handleQuickPrompt = async (prompt: typeof QUICK_PROMPTS[0]) => {
        setLoading(true);
        
        const userMessage: ChatMessage = {
            id: `msg_${Date.now()}`,
            role: 'user',
            content: prompt.label,
            timestamp: new Date()
        };
        setMessages(prev => [...prev, userMessage]);
        
        try {
            const response = await apiClient.cometAnalyze({
                type: prompt.type as 'breakout_confirm' | 'macro_analysis' | 'sector_scan' | 'stock_buzz' | 'general',
                event: prompt.event
            });
            
            const assistantMessage: ChatMessage = {
                id: `msg_${Date.now()}`,
                role: 'assistant',
                content: response.key_insights.join('\n\n') || 'Analysis complete.',
                timestamp: new Date(),
                analysis: response
            };
            
            setMessages(prev => [...prev, assistantMessage]);
            setCurrentAnalysis(normalizeResponse(response));
        } catch (error) {
            const errorMessage: ChatMessage = {
                id: `msg_${Date.now()}`,
                role: 'assistant',
                content: 'Analysis failed. Check backend connection.',
                timestamp: new Date()
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setLoading(false);
        }
    };

    const handleSectorAnalysis = async (sector: string) => {
        setSelectedSector(sector);
        setLoading(true);
        
        try {
            const response = await apiClient.cometSectorSentiment(sector);
            // Normalize the action and timeframe fields to the required types
            const normalizedResponse: CometResponse = {
                ...response,
                trading_signals: response.trading_signals.map(signal => ({
                    symbol: signal.symbol,
                    action: (signal.action.toUpperCase() as 'BUY' | 'SELL' | 'WATCH' | 'SKIP') || 'WATCH',
                    reasoning: signal.reasoning,
                    timeframe: (signal.timeframe as 'immediate' | 'short_term' | 'medium_term') || 'short_term'
                }))
            };
            setCurrentAnalysis(normalizedResponse);
            
            const message: ChatMessage = {
                id: `msg_${Date.now()}`,
                role: 'assistant',
                content: `**${sector} Sector Analysis**\n\n${normalizedResponse.key_insights.join('\n\n')}`,
                timestamp: new Date(),
                analysis: normalizedResponse
            };
            setMessages(prev => [...prev, message]);
        } catch (error) {
            console.error('Sector analysis failed:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleStockBuzz = async () => {
        if (!stockSymbol.trim()) return;
        setLoading(true);
        
        try {
            const response = await apiClient.cometStockBuzz(stockSymbol.toUpperCase());
            const normalizedResp = normalizeResponse(response);
            setCurrentAnalysis(normalizedResp);
            
            const message: ChatMessage = {
                id: `msg_${Date.now()}`,
                role: 'assistant',
                content: `**${stockSymbol.toUpperCase()} Analysis**\n\n${normalizedResp.key_insights.join('\n\n')}`,
                timestamp: new Date(),
                analysis: normalizedResp
            };
            setMessages(prev => [...prev, message]);
        } catch (error) {
            console.error('Stock buzz failed:', error);
        } finally {
            setLoading(false);
            setStockSymbol('');
        }
    };

    const handleBreakoutConfirm = async () => {
        if (!breakoutSymbol.trim() || !breakoutPrice.trim()) return;
        setLoading(true);
        
        try {
            const response = await apiClient.cometAnalyze({
                type: 'breakout_confirm',
                symbol: breakoutSymbol.toUpperCase(),
                price: parseFloat(breakoutPrice)
            });
            setCurrentAnalysis(response);
            
            const message: ChatMessage = {
                id: `msg_${Date.now()}`,
                role: 'assistant',
                content: `**Breakout Confirmation: ${breakoutSymbol.toUpperCase()} @ ₹${breakoutPrice}**\n\n${response.key_insights.join('\n\n')}`,
                timestamp: new Date(),
                analysis: response
            };
            setMessages(prev => [...prev, message]);
        } catch (error) {
            console.error('Breakout confirmation failed:', error);
        } finally {
            setLoading(false);
            setBreakoutSymbol('');
            setBreakoutPrice('');
        }
    };

    const getSentimentColor = (sentiment: number) => {
        if (sentiment >= 0.7) return 'text-green-400';
        if (sentiment >= 0.5) return 'text-yellow-400';
        return 'text-red-400';
    };

    const getSentimentLabel = (sentiment: number) => {
        if (sentiment >= 0.7) return 'Bullish';
        if (sentiment >= 0.5) return 'Neutral';
        return 'Bearish';
    };

    const getActionColor = (action: string) => {
        switch (action) {
            case 'BUY': return 'bg-green-500/20 text-green-400 border-green-500/30';
            case 'SELL': return 'bg-red-500/20 text-red-400 border-red-500/30';
            case 'WATCH': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
            default: return 'bg-muted text-muted-foreground';
        }
    };

    return (
        <div className="flex-1 space-y-6 p-8 pt-6 max-w-[1800px] mx-auto">
            {/* Header */}
            <div className="relative overflow-hidden rounded-2xl glass p-8">
                <div className="absolute inset-0 gradient-bg opacity-30"></div>
                <div className="relative z-10 flex items-center justify-between">
                    <div>
                        <div className="flex items-center space-x-3 mb-2">
                            <Brain className="h-10 w-10 text-primary" />
                            <h1 className="text-4xl font-bold gradient-text">Comet</h1>
                            <Badge className={apiStatus === 'connected' 
                                ? "bg-green-500/20 text-green-400 border-green-500/30" 
                                : apiStatus === 'checking'
                                ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
                                : "bg-red-500/20 text-red-400 border-red-500/30"
                            }>
                                {apiStatus === 'connected' ? 'AI Connected' : 
                                 apiStatus === 'checking' ? 'Checking...' : 'AI Offline'}
                            </Badge>
                        </div>
                        <p className="text-muted-foreground">AI-powered market intelligence • Breakout confirmation • Sector analysis</p>
                    </div>
                    <Button
                        onClick={checkApiStatus}
                        variant="outline"
                        className="border-primary/30"
                        disabled={apiStatus === 'checking'}
                    >
                        <RefreshCw className={`mr-2 h-4 w-4 ${apiStatus === 'checking' ? 'animate-spin' : ''}`} />
                        Refresh
                    </Button>
                </div>
            </div>

            {/* Main Content Grid */}
            <div className="grid gap-6 lg:grid-cols-3">
                {/* Left Panel - Chat & Analysis */}
                <div className="lg:col-span-2 space-y-6">
                    <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
                        <TabsList className="glass grid w-full grid-cols-3">
                            <TabsTrigger value="chat">
                                <MessageSquare className="h-4 w-4 mr-2" />
                                Ask Comet
                            </TabsTrigger>
                            <TabsTrigger value="breakout">
                                <Zap className="h-4 w-4 mr-2" />
                                Breakout Check
                            </TabsTrigger>
                            <TabsTrigger value="sectors">
                                <Building2 className="h-4 w-4 mr-2" />
                                Sector Scan
                            </TabsTrigger>
                        </TabsList>

                        {/* Chat Tab */}
                        <TabsContent value="chat" className="space-y-4">
                            {/* Quick Prompts */}
                            <div className="flex flex-wrap gap-2">
                                {QUICK_PROMPTS.map((prompt, idx) => (
                                    <Button
                                        key={idx}
                                        variant="outline"
                                        size="sm"
                                        onClick={() => handleQuickPrompt(prompt)}
                                        disabled={loading}
                                        className="border-primary/30 hover:bg-primary/10"
                                    >
                                        <Lightbulb className="h-3 w-3 mr-1" />
                                        {prompt.label}
                                    </Button>
                                ))}
                            </div>

                            {/* Chat Messages */}
                            <Card className="glass rounded-2xl overflow-hidden">
                                <CardContent className="p-0">
                                    <div className="h-[400px] overflow-y-auto p-4 space-y-4">
                                        {messages.length === 0 && (
                                            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                                                <Brain className="h-12 w-12 mb-4 opacity-50" />
                                                <p className="text-lg font-medium">Ask Comet anything</p>
                                                <p className="text-sm">Market analysis, stock insights, macro events...</p>
                                            </div>
                                        )}
                                        
                                        {messages.map((msg) => (
                                            <div
                                                key={msg.id}
                                                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                                            >
                                                <div className={`max-w-[80%] rounded-2xl p-4 ${
                                                    msg.role === 'user' 
                                                        ? 'bg-primary/20 text-foreground' 
                                                        : 'bg-muted/50'
                                                }`}>
                                                    <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                                                    
                                                    {/* Trading Signals */}
                                                    {msg.analysis?.trading_signals && msg.analysis.trading_signals.length > 0 && (
                                                        <div className="mt-3 pt-3 border-t border-border/50 space-y-2">
                                                            <p className="text-xs font-semibold text-muted-foreground">Trading Signals:</p>
                                                            {msg.analysis.trading_signals.map((signal, idx) => (
                                                                <div key={idx} className="flex items-center gap-2 text-sm">
                                                                    <Badge className={getActionColor(signal.action)}>
                                                                        {signal.action}
                                                                    </Badge>
                                                                    <span className="font-medium">{signal.symbol}</span>
                                                                    <span className="text-xs text-muted-foreground">({signal.timeframe})</span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}
                                                    
                                                    {/* Risks */}
                                                    {msg.analysis?.risks && msg.analysis.risks.length > 0 && (
                                                        <div className="mt-2 pt-2 border-t border-border/50">
                                                            <p className="text-xs text-yellow-400 flex items-center gap-1">
                                                                <AlertTriangle className="h-3 w-3" />
                                                                {msg.analysis.risks[0]}
                                                            </p>
                                                        </div>
                                                    )}
                                                    
                                                    <p className="text-xs text-muted-foreground mt-2">
                                                        {msg.timestamp.toLocaleTimeString()}
                                                    </p>
                                                </div>
                                            </div>
                                        ))}
                                        
                                        {loading && (
                                            <div className="flex justify-start">
                                                <div className="bg-muted/50 rounded-2xl p-4">
                                                    <div className="flex items-center gap-2">
                                                        <Loader2 className="h-4 w-4 animate-spin" />
                                                        <span className="text-sm text-muted-foreground">Analyzing...</span>
                                                    </div>
                                                </div>
                                            </div>
                                        )}
                                        <div ref={chatEndRef} />
                                    </div>
                                    
                                    {/* Input */}
                                    <div className="border-t border-border/50 p-4">
                                        <div className="flex gap-2">
                                            <Input
                                                placeholder="Ask about markets, stocks, sectors..."
                                                value={inputValue}
                                                onChange={(e) => setInputValue(e.target.value)}
                                                onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                                                disabled={loading || apiStatus !== 'connected'}
                                                className="flex-1"
                                            />
                                            <Button 
                                                onClick={handleSendMessage}
                                                disabled={loading || !inputValue.trim() || apiStatus !== 'connected'}
                                            >
                                                <Send className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* Breakout Tab */}
                        <TabsContent value="breakout" className="space-y-4">
                            <Card className="glass rounded-2xl overflow-hidden">
                                <CardHeader className="bg-gradient-to-r from-yellow-500/10 to-orange-500/10">
                                    <CardTitle className="flex items-center gap-2">
                                        <Zap className="h-5 w-5 text-yellow-400" />
                                        Breakout Confirmation
                                    </CardTitle>
                                    <CardDescription>
                                        Validate technical breakouts with AI-powered fundamental/news analysis
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="pt-6 space-y-4">
                                    <div className="grid gap-4 md:grid-cols-2">
                                        <div className="space-y-2">
                                            <Label htmlFor="breakoutSymbol">Stock Symbol</Label>
                                            <Input
                                                id="breakoutSymbol"
                                                placeholder="e.g., RELIANCE, TCS"
                                                value={breakoutSymbol}
                                                onChange={(e) => setBreakoutSymbol(e.target.value.toUpperCase())}
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="breakoutPrice">Breakout Price (₹)</Label>
                                            <Input
                                                id="breakoutPrice"
                                                type="number"
                                                placeholder="e.g., 2850"
                                                value={breakoutPrice}
                                                onChange={(e) => setBreakoutPrice(e.target.value)}
                                            />
                                        </div>
                                    </div>
                                    <Button 
                                        onClick={handleBreakoutConfirm}
                                        disabled={loading || !breakoutSymbol || !breakoutPrice || apiStatus !== 'connected'}
                                        className="w-full"
                                    >
                                        {loading ? (
                                            <>
                                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                                Analyzing Breakout...
                                            </>
                                        ) : (
                                            <>
                                                <Target className="h-4 w-4 mr-2" />
                                                Confirm Breakout
                                            </>
                                        )}
                                    </Button>
                                    
                                    <div className="p-4 rounded-xl bg-muted/30 text-sm text-muted-foreground">
                                        <p className="font-medium mb-2">What Comet checks:</p>
                                        <ul className="list-disc list-inside space-y-1">
                                            <li>Recent news & corporate announcements</li>
                                            <li>Social media sentiment & buzz</li>
                                            <li>Sector momentum alignment</li>
                                            <li>Risk factors & contradictory signals</li>
                                        </ul>
                                    </div>
                                </CardContent>
                            </Card>

                            {/* Stock Buzz Check */}
                            <Card className="glass rounded-2xl overflow-hidden">
                                <CardHeader className="bg-gradient-to-r from-purple-500/10 to-pink-500/10">
                                    <CardTitle className="flex items-center gap-2">
                                        <Activity className="h-5 w-5 text-purple-400" />
                                        Stock Buzz Check
                                    </CardTitle>
                                    <CardDescription>
                                        Investigate why a stock is getting attention
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="pt-6 space-y-4">
                                    <div className="flex gap-2">
                                        <Input
                                            placeholder="Enter stock symbol..."
                                            value={stockSymbol}
                                            onChange={(e) => setStockSymbol(e.target.value.toUpperCase())}
                                            onKeyDown={(e) => e.key === 'Enter' && handleStockBuzz()}
                                        />
                                        <Button 
                                            onClick={handleStockBuzz}
                                            disabled={loading || !stockSymbol || apiStatus !== 'connected'}
                                        >
                                            <Search className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* Sectors Tab */}
                        <TabsContent value="sectors" className="space-y-4">
                            <Card className="glass rounded-2xl overflow-hidden">
                                <CardHeader className="bg-gradient-to-r from-blue-500/10 to-cyan-500/10">
                                    <CardTitle className="flex items-center gap-2">
                                        <Building2 className="h-5 w-5 text-blue-400" />
                                        Sector Intelligence
                                    </CardTitle>
                                    <CardDescription>
                                        Get AI-powered sector analysis with actionable insights
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="pt-6">
                                    <div className="grid grid-cols-3 md:grid-cols-4 gap-3">
                                        {SECTORS.map((sector) => (
                                            <Button
                                                key={sector}
                                                variant={selectedSector === sector ? 'default' : 'outline'}
                                                onClick={() => handleSectorAnalysis(sector)}
                                                disabled={loading || apiStatus !== 'connected'}
                                                className="h-auto py-3"
                                            >
                                                {loading && selectedSector === sector ? (
                                                    <Loader2 className="h-4 w-4 animate-spin" />
                                                ) : (
                                                    sector
                                                )}
                                            </Button>
                                        ))}
                                    </div>
                                </CardContent>
                            </Card>
                        </TabsContent>
                    </Tabs>
                </div>

                {/* Right Panel - Current Analysis */}
                <div className="space-y-6">
                    {/* Sentiment Card */}
                    <Card className="glass rounded-2xl overflow-hidden">
                        <CardHeader className="bg-gradient-to-br from-primary/10 to-secondary/10">
                            <CardTitle className="text-lg">Current Analysis</CardTitle>
                        </CardHeader>
                        <CardContent className="pt-6">
                            {currentAnalysis ? (
                                <div className="space-y-4">
                                    {/* Sentiment Meter */}
                                    <div className="text-center">
                                        <div className={`text-4xl font-bold ${getSentimentColor(currentAnalysis.sentiment)}`}>
                                            {(currentAnalysis.sentiment * 100).toFixed(0)}%
                                        </div>
                                        <p className="text-sm text-muted-foreground">
                                            {getSentimentLabel(currentAnalysis.sentiment)} Sentiment
                                        </p>
                                        <div className="mt-2 h-2 bg-muted rounded-full overflow-hidden">
                                            <div 
                                                className={`h-full rounded-full ${
                                                    currentAnalysis.sentiment >= 0.5 
                                                        ? 'bg-gradient-to-r from-green-500 to-emerald-400'
                                                        : 'bg-gradient-to-r from-red-500 to-rose-400'
                                                }`}
                                                style={{ width: `${currentAnalysis.sentiment * 100}%` }}
                                            />
                                        </div>
                                    </div>
                                    
                                    {/* Confidence */}
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="text-muted-foreground">Confidence</span>
                                        <span className="font-medium">{(currentAnalysis.confidence * 100).toFixed(0)}%</span>
                                    </div>
                                    
                                    {/* Data Freshness */}
                                    {currentAnalysis.data_freshness && (
                                        <div className="flex items-center justify-between text-sm">
                                            <span className="text-muted-foreground">Data</span>
                                            <Badge className="bg-blue-500/20 text-blue-400">
                                                {currentAnalysis.data_freshness}
                                            </Badge>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <div className="text-center text-muted-foreground py-8">
                                    <BarChart3 className="h-12 w-12 mx-auto mb-3 opacity-50" />
                                    <p>No analysis yet</p>
                                    <p className="text-xs">Ask Comet a question to see insights</p>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Trading Signals */}
                    {currentAnalysis?.trading_signals && currentAnalysis.trading_signals.length > 0 && (
                        <Card className="glass rounded-2xl overflow-hidden">
                            <CardHeader className="bg-gradient-to-br from-green-500/10 to-emerald-500/10">
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <Target className="h-5 w-5 text-green-400" />
                                    Trading Signals
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-4 space-y-3">
                                {currentAnalysis.trading_signals.map((signal, idx) => (
                                    <div key={idx} className="p-3 rounded-xl bg-muted/30">
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="font-bold">{signal.symbol}</span>
                                            <Badge className={getActionColor(signal.action)}>
                                                {signal.action}
                                            </Badge>
                                        </div>
                                        <p className="text-sm text-muted-foreground mb-1">{signal.reasoning}</p>
                                        <div className="flex items-center gap-1 text-xs text-muted-foreground">
                                            <Clock className="h-3 w-3" />
                                            {signal.timeframe.replace('_', ' ')}
                                        </div>
                                    </div>
                                ))}
                            </CardContent>
                        </Card>
                    )}

                    {/* Risks */}
                    {currentAnalysis?.risks && currentAnalysis.risks.length > 0 && (
                        <Card className="glass rounded-2xl overflow-hidden">
                            <CardHeader className="bg-gradient-to-br from-yellow-500/10 to-orange-500/10">
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <Shield className="h-5 w-5 text-yellow-400" />
                                    Risk Factors
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-4">
                                <ul className="space-y-2">
                                    {currentAnalysis.risks.map((risk, idx) => (
                                        <li key={idx} className="flex items-start gap-2 text-sm">
                                            <AlertTriangle className="h-4 w-4 text-yellow-400 shrink-0 mt-0.5" />
                                            <span className="text-muted-foreground">{risk}</span>
                                        </li>
                                    ))}
                                </ul>
                            </CardContent>
                        </Card>
                    )}

                    {/* API Status Info */}
                    {apiStatus === 'disconnected' && (
                        <Card className="glass rounded-2xl overflow-hidden border-red-500/30">
                            <CardContent className="pt-6">
                                <div className="text-center">
                                    <AlertTriangle className="h-8 w-8 text-red-400 mx-auto mb-2" />
                                    <p className="font-medium text-red-400">AI Service Offline</p>
                                    <p className="text-sm text-muted-foreground mt-2">
                                        Ensure backend is running with<br />
                                        <code className="text-xs bg-muted px-1 rounded">ANTHROPIC_API_KEY</code> configured
                                    </p>
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </div>
            </div>
        </div>
    );
}
