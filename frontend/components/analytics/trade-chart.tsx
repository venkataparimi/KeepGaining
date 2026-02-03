"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, ReferenceLine, ComposedChart, Bar,
    Area, Scatter, Cell
} from "recharts";
import { 
    TrendingUp, TrendingDown, RefreshCw, Loader2, Search,
    ArrowUpCircle, ArrowDownCircle, Settings2
} from "lucide-react";
import { apiClient } from "@/lib/api/client";

interface Candle {
    timestamp: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
}

interface TradeMarker {
    timestamp: string;
    type: "entry" | "exit";
    side: "BUY" | "SELL";
    price: number;
    quantity: number;
    pnl?: number;
    strategy?: string;
}

interface IndicatorValue {
    timestamp: string;
    value: number;
    color?: string;
}

interface Indicator {
    name: string;
    type: "line" | "histogram" | "band";
    values: IndicatorValue[];
    color?: string;
    overlay: boolean;
}

interface ChartData {
    symbol: string;
    timeframe: string;
    candles: Candle[];
    trades: TradeMarker[];
    indicators: Indicator[];
}

const TIMEFRAMES = [
    { value: "1m", label: "1 Min" },
    { value: "5m", label: "5 Min" },
    { value: "15m", label: "15 Min" },
    { value: "1H", label: "1 Hour" },
    { value: "1D", label: "Daily" },
];

const INDICATOR_OPTIONS = [
    { value: "ema_21", label: "EMA 21", color: "#22c55e" },
    { value: "ema_50", label: "EMA 50", color: "#3b82f6" },
    { value: "ema_100", label: "EMA 100", color: "#f59e0b" },
    { value: "ema_200", label: "EMA 200", color: "#ef4444" },
    { value: "sma_20", label: "SMA 20", color: "#8b5cf6" },
    { value: "rsi_14", label: "RSI 14", color: "#a855f7" },
    { value: "vwap", label: "VWAP", color: "#06b6d4" },
    { value: "bb", label: "Bollinger Bands", color: "#94a3b8" },
    { value: "volume", label: "Volume", color: "#64748b" },
];

export function TradeChart() {
    const [symbol, setSymbol] = useState("RELIANCE");
    const [searchSymbol, setSearchSymbol] = useState("RELIANCE");
    const [timeframe, setTimeframe] = useState("1D");
    const [days, setDays] = useState(90);
    const [selectedIndicators, setSelectedIndicators] = useState<string[]>(["ema_21", "ema_50", "rsi_14"]);
    const [loading, setLoading] = useState(false);
    const [chartData, setChartData] = useState<ChartData | null>(null);
    const [error, setError] = useState<string | null>(null);

    const fetchChartData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch(
                `/api/trade-chart/chart/${symbol}?timeframe=${timeframe}&days=${days}&indicators=${selectedIndicators.join(",")}&include_trades=true`
            );
            
            if (!response.ok) {
                throw new Error("Failed to fetch chart data");
            }
            
            const data = await response.json();
            setChartData(data);
        } catch (err) {
            console.error("Chart fetch error:", err);
            setError("Failed to load chart data");
            // Generate mock data for demo
            setChartData(generateMockChartData(symbol, timeframe, days, selectedIndicators));
        } finally {
            setLoading(false);
        }
    }, [symbol, timeframe, days, selectedIndicators]);

    useEffect(() => {
        fetchChartData();
    }, [fetchChartData]);

    const handleSearch = () => {
        if (searchSymbol.trim()) {
            setSymbol(searchSymbol.trim().toUpperCase());
        }
    };

    const toggleIndicator = (indicator: string) => {
        setSelectedIndicators(prev => 
            prev.includes(indicator)
                ? prev.filter(i => i !== indicator)
                : [...prev, indicator]
        );
    };

    // Prepare chart data
    const preparedData = chartData?.candles.map((candle, index) => {
        const dataPoint: any = {
            timestamp: new Date(candle.timestamp).toLocaleDateString(),
            fullTimestamp: candle.timestamp,
            open: candle.open,
            high: candle.high,
            low: candle.low,
            close: candle.close,
            volume: candle.volume,
            // For candlestick visualization
            candleBody: [candle.open, candle.close],
            candleWick: [candle.low, candle.high],
            isGreen: candle.close >= candle.open,
        };

        // Add indicator values
        chartData?.indicators.forEach(indicator => {
            const value = indicator.values.find(v => v.timestamp === candle.timestamp);
            if (value) {
                dataPoint[indicator.name] = value.value;
            }
        });

        return dataPoint;
    }) || [];

    // Get trade markers mapped to chart data
    const entryMarkers = chartData?.trades.filter(t => t.type === "entry") || [];
    const exitMarkers = chartData?.trades.filter(t => t.type === "exit") || [];

    // Get overlay indicators (on price chart)
    const overlayIndicators = chartData?.indicators.filter(i => i.overlay && i.type === "line") || [];
    
    // Get RSI (separate panel)
    const rsiIndicator = chartData?.indicators.find(i => i.name.includes("RSI"));
    
    // Get Volume
    const volumeIndicator = chartData?.indicators.find(i => i.name === "Volume");

    // Calculate price range for Y axis
    const prices = chartData?.candles.flatMap(c => [c.high, c.low]) || [0];
    const minPrice = Math.min(...prices) * 0.99;
    const maxPrice = Math.max(...prices) * 1.01;

    // Calculate stats
    const latestCandle = chartData?.candles[chartData.candles.length - 1];
    const firstCandle = chartData?.candles[0];
    const priceChange = latestCandle && firstCandle 
        ? ((latestCandle.close - firstCandle.close) / firstCandle.close * 100) 
        : 0;

    return (
        <div className="space-y-4">
            {/* Header Controls */}
            <Card className="glass rounded-2xl">
                <CardContent className="pt-4">
                    <div className="flex flex-wrap items-center gap-4">
                        {/* Symbol Search */}
                        <div className="flex items-center gap-2">
                            <Input
                                value={searchSymbol}
                                onChange={(e) => setSearchSymbol(e.target.value.toUpperCase())}
                                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                                placeholder="Symbol..."
                                className="w-32 bg-muted/20"
                            />
                            <Button variant="outline" size="icon" onClick={handleSearch}>
                                <Search className="h-4 w-4" />
                            </Button>
                        </div>

                        {/* Timeframe Select */}
                        <Select value={timeframe} onValueChange={setTimeframe}>
                            <SelectTrigger className="w-24 bg-muted/20">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {TIMEFRAMES.map(tf => (
                                    <SelectItem key={tf.value} value={tf.value}>
                                        {tf.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        {/* Days Select */}
                        <Select value={days.toString()} onValueChange={(v) => setDays(parseInt(v))}>
                            <SelectTrigger className="w-24 bg-muted/20">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="30">30 Days</SelectItem>
                                <SelectItem value="60">60 Days</SelectItem>
                                <SelectItem value="90">90 Days</SelectItem>
                                <SelectItem value="180">180 Days</SelectItem>
                                <SelectItem value="365">1 Year</SelectItem>
                            </SelectContent>
                        </Select>

                        {/* Indicator Toggles */}
                        <div className="flex flex-wrap gap-1 ml-auto">
                            {INDICATOR_OPTIONS.slice(0, 6).map(ind => (
                                <Badge
                                    key={ind.value}
                                    variant={selectedIndicators.includes(ind.value) ? "default" : "outline"}
                                    className="cursor-pointer text-xs"
                                    style={{
                                        backgroundColor: selectedIndicators.includes(ind.value) ? ind.color : undefined,
                                        borderColor: ind.color,
                                    }}
                                    onClick={() => toggleIndicator(ind.value)}
                                >
                                    {ind.label}
                                </Badge>
                            ))}
                        </div>

                        {/* Refresh Button */}
                        <Button variant="outline" size="sm" onClick={fetchChartData} disabled={loading}>
                            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Main Chart */}
            <Card className="glass rounded-2xl">
                <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <CardTitle className="text-xl font-bold">{symbol}</CardTitle>
                            {latestCandle && (
                                <>
                                    <span className="text-2xl font-bold">
                                        ₹{latestCandle.close.toLocaleString()}
                                    </span>
                                    <Badge variant={priceChange >= 0 ? "default" : "destructive"}>
                                        {priceChange >= 0 ? <TrendingUp className="h-3 w-3 mr-1" /> : <TrendingDown className="h-3 w-3 mr-1" />}
                                        {priceChange >= 0 ? "+" : ""}{priceChange.toFixed(2)}%
                                    </Badge>
                                </>
                            )}
                        </div>
                        <div className="flex items-center gap-4 text-sm text-muted-foreground">
                            <div className="flex items-center gap-1">
                                <ArrowUpCircle className="h-4 w-4 text-green-500" />
                                <span>{entryMarkers.length} entries</span>
                            </div>
                            <div className="flex items-center gap-1">
                                <ArrowDownCircle className="h-4 w-4 text-red-500" />
                                <span>{exitMarkers.length} exits</span>
                            </div>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="pt-4">
                    {loading ? (
                        <div className="flex items-center justify-center h-96">
                            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {/* Price Chart */}
                            <div className="h-96">
                                <ResponsiveContainer width="100%" height="100%">
                                    <ComposedChart data={preparedData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                                        <XAxis 
                                            dataKey="timestamp" 
                                            stroke="#64748b" 
                                            tick={{ fill: "#94a3b8", fontSize: 10 }}
                                            interval="preserveStartEnd"
                                        />
                                        <YAxis 
                                            domain={[minPrice, maxPrice]}
                                            stroke="#64748b"
                                            tick={{ fill: "#94a3b8", fontSize: 10 }}
                                            tickFormatter={(v) => `₹${v.toLocaleString()}`}
                                        />
                                        <Tooltip
                                            contentStyle={{
                                                backgroundColor: "rgba(15, 23, 42, 0.9)",
                                                border: "1px solid rgba(148, 163, 184, 0.2)",
                                                borderRadius: "8px",
                                            }}
                                            formatter={(value: any, name: string) => [
                                                typeof value === "number" ? `₹${value.toLocaleString()}` : value,
                                                name
                                            ]}
                                        />
                                        
                                        {/* Candlestick approximation using high/low line and open/close bar */}
                                        <Line
                                            type="monotone"
                                            dataKey="close"
                                            stroke="#8b5cf6"
                                            strokeWidth={2}
                                            dot={false}
                                            name="Close"
                                        />
                                        
                                        {/* Overlay Indicators */}
                                        {overlayIndicators.map((indicator, idx) => (
                                            <Line
                                                key={indicator.name}
                                                type="monotone"
                                                dataKey={indicator.name}
                                                stroke={indicator.color || `hsl(${idx * 60}, 70%, 50%)`}
                                                strokeWidth={1.5}
                                                dot={false}
                                                name={indicator.name}
                                            />
                                        ))}

                                        {/* Entry Markers */}
                                        {entryMarkers.map((marker, idx) => (
                                            <ReferenceLine
                                                key={`entry-${idx}`}
                                                x={new Date(marker.timestamp).toLocaleDateString()}
                                                stroke="#22c55e"
                                                strokeDasharray="3 3"
                                                label={{
                                                    value: "▲",
                                                    position: "bottom",
                                                    fill: "#22c55e",
                                                    fontSize: 16,
                                                }}
                                            />
                                        ))}

                                        {/* Exit Markers */}
                                        {exitMarkers.map((marker, idx) => (
                                            <ReferenceLine
                                                key={`exit-${idx}`}
                                                x={new Date(marker.timestamp).toLocaleDateString()}
                                                stroke="#ef4444"
                                                strokeDasharray="3 3"
                                                label={{
                                                    value: "▼",
                                                    position: "top",
                                                    fill: "#ef4444",
                                                    fontSize: 16,
                                                }}
                                            />
                                        ))}
                                    </ComposedChart>
                                </ResponsiveContainer>
                            </div>

                            {/* RSI Panel */}
                            {rsiIndicator && (
                                <div className="h-32 border-t border-border/30 pt-2">
                                    <p className="text-xs text-muted-foreground mb-1">{rsiIndicator.name}</p>
                                    <ResponsiveContainer width="100%" height="100%">
                                        <LineChart data={preparedData}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                                            <XAxis dataKey="timestamp" hide />
                                            <YAxis 
                                                domain={[0, 100]} 
                                                stroke="#64748b"
                                                tick={{ fill: "#94a3b8", fontSize: 10 }}
                                                ticks={[30, 50, 70]}
                                            />
                                            <Tooltip
                                                contentStyle={{
                                                    backgroundColor: "rgba(15, 23, 42, 0.9)",
                                                    border: "1px solid rgba(148, 163, 184, 0.2)",
                                                    borderRadius: "8px",
                                                }}
                                            />
                                            {/* Overbought/Oversold zones */}
                                            <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="3 3" />
                                            <ReferenceLine y={30} stroke="#22c55e" strokeDasharray="3 3" />
                                            <Line
                                                type="monotone"
                                                dataKey={rsiIndicator.name}
                                                stroke={rsiIndicator.color || "#a855f7"}
                                                strokeWidth={1.5}
                                                dot={false}
                                            />
                                        </LineChart>
                                    </ResponsiveContainer>
                                </div>
                            )}

                            {/* Volume Panel */}
                            {selectedIndicators.includes("volume") && (
                                <div className="h-24 border-t border-border/30 pt-2">
                                    <p className="text-xs text-muted-foreground mb-1">Volume</p>
                                    <ResponsiveContainer width="100%" height="100%">
                                        <ComposedChart data={preparedData}>
                                            <XAxis dataKey="timestamp" hide />
                                            <YAxis hide />
                                            <Bar dataKey="volume" fill="#64748b" opacity={0.5}>
                                                {preparedData.map((entry, index) => (
                                                    <Cell 
                                                        key={`cell-${index}`} 
                                                        fill={entry.isGreen ? "#22c55e" : "#ef4444"}
                                                        opacity={0.6}
                                                    />
                                                ))}
                                            </Bar>
                                        </ComposedChart>
                                    </ResponsiveContainer>
                                </div>
                            )}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Trade Details */}
            {chartData && chartData.trades.length > 0 && (
                <Card className="glass rounded-2xl">
                    <CardHeader>
                        <CardTitle className="text-lg">Trade History on Chart</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b border-border/30">
                                        <th className="text-left py-2 px-3 text-muted-foreground">Type</th>
                                        <th className="text-left py-2 px-3 text-muted-foreground">Date</th>
                                        <th className="text-left py-2 px-3 text-muted-foreground">Side</th>
                                        <th className="text-right py-2 px-3 text-muted-foreground">Price</th>
                                        <th className="text-right py-2 px-3 text-muted-foreground">Qty</th>
                                        <th className="text-right py-2 px-3 text-muted-foreground">P&L</th>
                                        <th className="text-left py-2 px-3 text-muted-foreground">Strategy</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {chartData.trades.map((trade, idx) => (
                                        <tr key={idx} className="border-b border-border/10 hover:bg-muted/10">
                                            <td className="py-2 px-3">
                                                <Badge variant={trade.type === "entry" ? "default" : "secondary"}>
                                                    {trade.type === "entry" ? (
                                                        <ArrowUpCircle className="h-3 w-3 mr-1" />
                                                    ) : (
                                                        <ArrowDownCircle className="h-3 w-3 mr-1" />
                                                    )}
                                                    {trade.type}
                                                </Badge>
                                            </td>
                                            <td className="py-2 px-3">{new Date(trade.timestamp).toLocaleDateString()}</td>
                                            <td className="py-2 px-3">
                                                <span className={trade.side === "BUY" ? "text-green-500" : "text-red-500"}>
                                                    {trade.side}
                                                </span>
                                            </td>
                                            <td className="py-2 px-3 text-right">₹{trade.price.toLocaleString()}</td>
                                            <td className="py-2 px-3 text-right">{trade.quantity}</td>
                                            <td className="py-2 px-3 text-right">
                                                {trade.pnl !== undefined && trade.pnl !== null ? (
                                                    <span className={trade.pnl >= 0 ? "text-green-500" : "text-red-500"}>
                                                        {trade.pnl >= 0 ? "+" : ""}₹{trade.pnl.toLocaleString()}
                                                    </span>
                                                ) : "-"}
                                            </td>
                                            <td className="py-2 px-3 text-muted-foreground">{trade.strategy || "-"}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}

// Mock data generator for demo
function generateMockChartData(
    symbol: string,
    timeframe: string,
    days: number,
    indicators: string[]
): ChartData {
    const candles: Candle[] = [];
    let basePrice = 1500 + Math.random() * 1000;
    let currentTime = new Date();
    currentTime.setDate(currentTime.getDate() - days);

    for (let i = 0; i < Math.min(days * (timeframe === "1D" ? 1 : 7), 200); i++) {
        const change = (Math.random() - 0.5) * 0.03 * basePrice;
        const open = basePrice;
        const close = basePrice + change;
        const high = Math.max(open, close) + Math.abs(change) * Math.random();
        const low = Math.min(open, close) - Math.abs(change) * Math.random();
        
        candles.push({
            timestamp: currentTime.toISOString(),
            open: Math.round(open * 100) / 100,
            high: Math.round(high * 100) / 100,
            low: Math.round(low * 100) / 100,
            close: Math.round(close * 100) / 100,
            volume: Math.floor(Math.random() * 1000000 + 100000),
        });
        
        basePrice = close;
        currentTime.setDate(currentTime.getDate() + 1);
    }

    // Generate some mock trades
    const trades: TradeMarker[] = [];
    const tradeCount = Math.floor(Math.random() * 5) + 2;
    
    for (let i = 0; i < tradeCount; i++) {
        const entryIdx = Math.floor(Math.random() * (candles.length - 10));
        const exitIdx = entryIdx + Math.floor(Math.random() * 10) + 1;
        
        if (exitIdx < candles.length) {
            const entryPrice = candles[entryIdx].close;
            const exitPrice = candles[exitIdx].close;
            const quantity = Math.floor(Math.random() * 50) + 10;
            const pnl = (exitPrice - entryPrice) * quantity;
            
            trades.push({
                timestamp: candles[entryIdx].timestamp,
                type: "entry",
                side: "BUY",
                price: entryPrice,
                quantity,
                strategy: "Volume Rocket",
            });
            
            trades.push({
                timestamp: candles[exitIdx].timestamp,
                type: "exit",
                side: "SELL",
                price: exitPrice,
                quantity,
                pnl: Math.round(pnl * 100) / 100,
                strategy: "Volume Rocket",
            });
        }
    }

    // Calculate indicators
    const indicatorData: Indicator[] = [];
    const closes = candles.map(c => c.close);

    if (indicators.includes("ema_21")) {
        indicatorData.push({
            name: "EMA 21",
            type: "line",
            values: calculateEMA(candles, 21),
            color: "#22c55e",
            overlay: true,
        });
    }

    if (indicators.includes("ema_50")) {
        indicatorData.push({
            name: "EMA 50",
            type: "line",
            values: calculateEMA(candles, 50),
            color: "#3b82f6",
            overlay: true,
        });
    }

    if (indicators.includes("rsi_14")) {
        indicatorData.push({
            name: "RSI 14",
            type: "line",
            values: calculateRSI(candles, 14),
            color: "#a855f7",
            overlay: false,
        });
    }

    return {
        symbol,
        timeframe,
        candles,
        trades,
        indicators: indicatorData,
    };
}

function calculateEMA(candles: Candle[], period: number): IndicatorValue[] {
    const values: IndicatorValue[] = [];
    const multiplier = 2 / (period + 1);
    let ema = candles.slice(0, period).reduce((sum, c) => sum + c.close, 0) / period;

    for (let i = period - 1; i < candles.length; i++) {
        if (i === period - 1) {
            values.push({ timestamp: candles[i].timestamp, value: ema });
        } else {
            ema = (candles[i].close - ema) * multiplier + ema;
            values.push({ timestamp: candles[i].timestamp, value: Math.round(ema * 100) / 100 });
        }
    }

    return values;
}

function calculateRSI(candles: Candle[], period: number): IndicatorValue[] {
    const values: IndicatorValue[] = [];
    
    if (candles.length < period + 1) return values;

    const changes = candles.slice(1).map((c, i) => c.close - candles[i].close);
    const gains = changes.map(c => c > 0 ? c : 0);
    const losses = changes.map(c => c < 0 ? Math.abs(c) : 0);

    let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
    let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;

    for (let i = period; i < candles.length; i++) {
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        const rsi = 100 - (100 / (1 + rs));
        
        values.push({
            timestamp: candles[i].timestamp,
            value: Math.round(rsi * 100) / 100,
        });

        avgGain = (avgGain * (period - 1) + gains[i - 1]) / period;
        avgLoss = (avgLoss * (period - 1) + losses[i - 1]) / period;
    }

    return values;
}
