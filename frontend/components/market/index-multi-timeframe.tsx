"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { 
    LineChart, Line, XAxis, YAxis, ResponsiveContainer, 
    CartesianGrid, Tooltip 
} from "recharts";
import { 
    TrendingUp, TrendingDown, Activity, Clock, 
    ChevronUp, ChevronDown, Minus, RefreshCw, Loader2
} from "lucide-react";
import { apiClient } from "@/lib/api/client";

interface IndexData {
    name: string;
    symbol: string;
    price: number;
    change: number;
    changePercent: number;
    dayHigh: number;
    dayLow: number;
    open: number;
    prevClose: number;
    timeframes: {
        [key: string]: TimeframeData;
    };
}

interface TimeframeData {
    trend: 'bullish' | 'bearish' | 'neutral';
    change: number;
    support: number;
    resistance: number;
    signal: string;
    candles: { time: string; open: number; high: number; low: number; close: number }[];
}

interface IndexMultiTimeframeProps {
    indices?: IndexData[];
}

export function IndexMultiTimeframe({ indices: propIndices }: IndexMultiTimeframeProps) {
    const [indices, setIndices] = useState<IndexData[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedIndex, setSelectedIndex] = useState('NIFTY 50');
    const [selectedTimeframe, setSelectedTimeframe] = useState('1H');

    const timeframes = ['5M', '15M', '1H', '4H', '1D'];

    const fetchIndices = useCallback(async () => {
        if (propIndices) {
            setIndices(propIndices);
            setLoading(false);
            return;
        }

        try {
            const data = await apiClient.getIndices();
            if (data && data.length > 0) {
                setIndices(data);
            } else {
                // Fallback to generated data if API returns empty
                setIndices(generateMockIndices());
            }
        } catch (error) {
            console.error("Failed to fetch indices:", error);
            setIndices(generateMockIndices());
        } finally {
            setLoading(false);
        }
    }, [propIndices]);

    useEffect(() => {
        fetchIndices();
        // Auto-refresh every 30 seconds
        const interval = setInterval(fetchIndices, 30000);
        return () => clearInterval(interval);
    }, [fetchIndices]);

    // Fallback mock data generator
    const mockIndices: IndexData[] = useMemo(() => {
        const generateCandles = (basePrice: number, count: number, volatility: number) => {
            const candles = [];
            let price = basePrice * (0.98 + Math.random() * 0.04);
            
            for (let i = count; i >= 0; i--) {
                const change = (Math.random() - 0.48) * volatility;
                const open = price;
                const close = price + change;
                const high = Math.max(open, close) + Math.random() * volatility * 0.3;
                const low = Math.min(open, close) - Math.random() * volatility * 0.3;
                
                candles.push({
                    time: `${i}`,
                    open: Math.round(open * 100) / 100,
                    high: Math.round(high * 100) / 100,
                    low: Math.round(low * 100) / 100,
                    close: Math.round(close * 100) / 100,
                });
                price = close;
            }
            return candles;
        };

        const createTimeframes = (basePrice: number) => ({
            '5M': {
                trend: Math.random() > 0.5 ? 'bullish' : 'bearish',
                change: (Math.random() - 0.5) * 0.5,
                support: basePrice * 0.995,
                resistance: basePrice * 1.005,
                signal: Math.random() > 0.6 ? 'Buy' : Math.random() > 0.3 ? 'Sell' : 'Hold',
                candles: generateCandles(basePrice, 50, basePrice * 0.001),
            },
            '15M': {
                trend: Math.random() > 0.5 ? 'bullish' : 'bearish',
                change: (Math.random() - 0.5) * 1,
                support: basePrice * 0.99,
                resistance: basePrice * 1.01,
                signal: Math.random() > 0.6 ? 'Buy' : Math.random() > 0.3 ? 'Sell' : 'Hold',
                candles: generateCandles(basePrice, 50, basePrice * 0.002),
            },
            '1H': {
                trend: Math.random() > 0.5 ? 'bullish' : 'bearish',
                change: (Math.random() - 0.5) * 2,
                support: basePrice * 0.985,
                resistance: basePrice * 1.015,
                signal: Math.random() > 0.6 ? 'Buy' : Math.random() > 0.3 ? 'Sell' : 'Hold',
                candles: generateCandles(basePrice, 50, basePrice * 0.003),
            },
            '4H': {
                trend: Math.random() > 0.5 ? 'bullish' : 'bearish',
                change: (Math.random() - 0.5) * 3,
                support: basePrice * 0.98,
                resistance: basePrice * 1.02,
                signal: Math.random() > 0.6 ? 'Buy' : Math.random() > 0.3 ? 'Sell' : 'Hold',
                candles: generateCandles(basePrice, 50, basePrice * 0.005),
            },
            '1D': {
                trend: Math.random() > 0.5 ? 'bullish' : 'bearish',
                change: (Math.random() - 0.5) * 5,
                support: basePrice * 0.97,
                resistance: basePrice * 1.03,
                signal: Math.random() > 0.6 ? 'Buy' : Math.random() > 0.3 ? 'Sell' : 'Hold',
                candles: generateCandles(basePrice, 50, basePrice * 0.008),
            },
        }) as IndexData['timeframes'];

        return [
            {
                name: 'NIFTY 50',
                symbol: '^NSEI',
                price: 24523.50,
                change: 125.30,
                changePercent: 0.51,
                dayHigh: 24580.00,
                dayLow: 24420.15,
                open: 24450.00,
                prevClose: 24398.20,
                timeframes: createTimeframes(24523.50),
            },
            {
                name: 'BANK NIFTY',
                symbol: '^NSEBANK',
                price: 52180.75,
                change: -245.50,
                changePercent: -0.47,
                dayHigh: 52450.00,
                dayLow: 52050.25,
                open: 52420.00,
                prevClose: 52426.25,
                timeframes: createTimeframes(52180.75),
            },
            {
                name: 'NIFTY IT',
                symbol: '^CNXIT',
                price: 38542.25,
                change: 312.80,
                changePercent: 0.82,
                dayHigh: 38620.00,
                dayLow: 38280.50,
                open: 38350.00,
                prevClose: 38229.45,
                timeframes: createTimeframes(38542.25),
            },
            {
                name: 'NIFTY FIN',
                symbol: '^CNXFIN',
                price: 22845.60,
                change: 85.20,
                changePercent: 0.37,
                dayHigh: 22920.00,
                dayLow: 22750.35,
                open: 22780.00,
                prevClose: 22760.40,
                timeframes: createTimeframes(22845.60),
            },
        ];
    }, []);

    // Use API data or fallback to mock
    const indexData = indices.length > 0 ? indices : mockIndices;
    const currentIndex = indexData.find(i => i.name === selectedIndex) || indexData[0];
    const currentTimeframeData = currentIndex?.timeframes?.[selectedTimeframe];

    // Helper function for mock data generation
    function generateMockIndices(): IndexData[] {
        return mockIndices;
    }

    if (loading) {
        return (
            <Card className="glass rounded-2xl">
                <CardContent className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </CardContent>
            </Card>
        );
    }

    const getTrendIcon = (trend: string) => {
        switch (trend) {
            case 'bullish': return <ChevronUp className="h-4 w-4 text-green-400" />;
            case 'bearish': return <ChevronDown className="h-4 w-4 text-red-400" />;
            default: return <Minus className="h-4 w-4 text-gray-400" />;
        }
    };

    const getTrendBg = (trend: string) => {
        switch (trend) {
            case 'bullish': return 'bg-green-500/10 border-green-500/30 text-green-400';
            case 'bearish': return 'bg-red-500/10 border-red-500/30 text-red-400';
            default: return 'bg-gray-500/10 border-gray-500/30 text-gray-400';
        }
    };

    const getSignalColor = (signal: string) => {
        switch (signal) {
            case 'Buy': return 'text-green-400 bg-green-500/20';
            case 'Sell': return 'text-red-400 bg-red-500/20';
            default: return 'text-gray-400 bg-gray-500/20';
        }
    };

    return (
        <Card className="glass rounded-2xl overflow-hidden">
            <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10 py-4">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    <CardTitle className="text-xl font-bold">Index Multi-Timeframe Analysis</CardTitle>
                    <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm">
                            <RefreshCw className="h-4 w-4 mr-1" /> Live
                        </Button>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="p-4">
                {/* Index Selector */}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
                    {indexData.map((index) => (
                        <div
                            key={index.name}
                            onClick={() => setSelectedIndex(index.name)}
                            className={`p-4 rounded-xl cursor-pointer transition-all hover:scale-[1.02] ${
                                selectedIndex === index.name 
                                    ? 'ring-2 ring-primary bg-primary/10' 
                                    : 'glass hover:bg-muted/20'
                            }`}
                        >
                            <div className="flex items-center justify-between mb-2">
                                <span className="font-bold">{index.name}</span>
                                {index.change >= 0 ? 
                                    <TrendingUp className="h-4 w-4 text-green-400" /> : 
                                    <TrendingDown className="h-4 w-4 text-red-400" />
                                }
                            </div>
                            <p className="text-xl font-bold">₹{index.price.toLocaleString()}</p>
                            <p className={`text-sm ${index.change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                {index.change >= 0 ? '+' : ''}{index.change.toFixed(2)} ({index.changePercent.toFixed(2)}%)
                            </p>
                        </div>
                    ))}
                </div>

                {/* Timeframe Selector */}
                <div className="flex gap-2 mb-6">
                    {timeframes.map((tf) => (
                        <Button
                            key={tf}
                            variant={selectedTimeframe === tf ? "secondary" : "outline"}
                            size="sm"
                            onClick={() => setSelectedTimeframe(tf)}
                            className="flex-1"
                        >
                            {tf}
                        </Button>
                    ))}
                </div>

                {/* Multi-Timeframe Grid */}
                <div className="grid lg:grid-cols-5 gap-4 mb-6">
                    {timeframes.map((tf) => {
                        const tfData = currentIndex.timeframes[tf];
                        return (
                            <div 
                                key={tf}
                                className={`p-4 rounded-xl border ${getTrendBg(tfData.trend)} ${
                                    selectedTimeframe === tf ? 'ring-2 ring-primary' : ''
                                }`}
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <span className="font-bold">{tf}</span>
                                    {getTrendIcon(tfData.trend)}
                                </div>
                                <p className="text-lg font-bold capitalize">{tfData.trend}</p>
                                <p className={`text-sm ${tfData.change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {tfData.change >= 0 ? '+' : ''}{tfData.change.toFixed(2)}%
                                </p>
                                <div className={`mt-2 px-2 py-1 rounded text-xs font-medium inline-block ${getSignalColor(tfData.signal)}`}>
                                    {tfData.signal}
                                </div>
                            </div>
                        );
                    })}
                </div>

                {/* Price Chart */}
                <div className="grid lg:grid-cols-3 gap-6">
                    <div className="lg:col-span-2 glass rounded-xl p-4">
                        <h4 className="font-semibold mb-4">{currentIndex.name} - {selectedTimeframe} Chart</h4>
                        <div className="h-64 min-h-[256px]">
                            <ResponsiveContainer width="100%" height="100%" minHeight={240}>
                                <LineChart data={currentTimeframeData.candles}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                                    <XAxis 
                                        dataKey="time" 
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fill: '#888', fontSize: 10 }}
                                    />
                                    <YAxis 
                                        domain={['dataMin - 50', 'dataMax + 50']}
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fill: '#888', fontSize: 10 }}
                                        tickFormatter={(v) => `₹${v.toLocaleString()}`}
                                    />
                                    <Tooltip 
                                        content={({ active, payload }) => {
                                            if (active && payload && payload.length) {
                                                const data = payload[0].payload;
                                                return (
                                                    <div className="glass rounded-lg p-3 border border-border/50">
                                                        <p className="text-xs text-muted-foreground">O: ₹{data.open}</p>
                                                        <p className="text-xs text-muted-foreground">H: ₹{data.high}</p>
                                                        <p className="text-xs text-muted-foreground">L: ₹{data.low}</p>
                                                        <p className="text-xs font-bold">C: ₹{data.close}</p>
                                                    </div>
                                                );
                                            }
                                            return null;
                                        }}
                                    />
                                    <Line 
                                        type="monotone" 
                                        dataKey="close" 
                                        stroke={currentTimeframeData.trend === 'bullish' ? '#22c55e' : '#ef4444'}
                                        strokeWidth={2}
                                        dot={false}
                                    />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    {/* Key Levels */}
                    <div className="glass rounded-xl p-4">
                        <h4 className="font-semibold mb-4">Key Levels ({selectedTimeframe})</h4>
                        <div className="space-y-4">
                            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30">
                                <p className="text-xs text-muted-foreground">Resistance</p>
                                <p className="text-lg font-bold text-red-400">
                                    ₹{currentTimeframeData.resistance.toLocaleString()}
                                </p>
                            </div>
                            <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/30">
                                <p className="text-xs text-muted-foreground">Current Price</p>
                                <p className="text-lg font-bold text-blue-400">
                                    ₹{currentIndex.price.toLocaleString()}
                                </p>
                            </div>
                            <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/30">
                                <p className="text-xs text-muted-foreground">Support</p>
                                <p className="text-lg font-bold text-green-400">
                                    ₹{currentTimeframeData.support.toLocaleString()}
                                </p>
                            </div>

                            <div className="border-t border-border/30 pt-4 mt-4">
                                <h5 className="text-sm font-medium mb-3">Day Range</h5>
                                <div className="flex justify-between text-xs mb-1">
                                    <span className="text-muted-foreground">Low</span>
                                    <span className="text-muted-foreground">High</span>
                                </div>
                                <div className="relative h-2 bg-muted/30 rounded-full">
                                    <div 
                                        className="absolute h-full bg-gradient-to-r from-green-500 to-red-500 rounded-full"
                                        style={{ 
                                            left: '0%',
                                            width: '100%'
                                        }}
                                    ></div>
                                    <div 
                                        className="absolute w-3 h-3 bg-primary rounded-full -top-0.5 border-2 border-background"
                                        style={{
                                            left: `${((currentIndex.price - currentIndex.dayLow) / (currentIndex.dayHigh - currentIndex.dayLow)) * 100}%`,
                                            transform: 'translateX(-50%)'
                                        }}
                                    ></div>
                                </div>
                                <div className="flex justify-between text-sm mt-1">
                                    <span>₹{currentIndex.dayLow.toLocaleString()}</span>
                                    <span>₹{currentIndex.dayHigh.toLocaleString()}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
