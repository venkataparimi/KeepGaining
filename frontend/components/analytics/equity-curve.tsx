"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { 
    AreaChart, Area, XAxis, YAxis, CartesianGrid, 
    Tooltip, ResponsiveContainer, ReferenceLine 
} from "recharts";
import { TrendingUp, TrendingDown, Calendar, Maximize2, Loader2, RefreshCw } from "lucide-react";
import { apiClient } from "@/lib/api/client";

interface EquityPoint {
    date: string;
    equity: number;
    drawdown: number;
    pnl: number;
}

interface EquityCurveProps {
    data?: EquityPoint[];
    startingCapital?: number;
}

// Generate mock data for fallback
const generateMockData = (): EquityPoint[] => {
    const points: EquityPoint[] = [];
    let equity = 100000;
    const today = new Date();
    
    for (let i = 180; i >= 0; i--) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        
        if (date.getDay() === 0 || date.getDay() === 6) continue;
        
        const dailyReturn = (Math.random() - 0.45) * 3000;
        equity = Math.max(80000, equity + dailyReturn);
        const drawdown = ((100000 - Math.min(equity, 100000)) / 100000) * -100;
        
        points.push({
            date: date.toISOString().split('T')[0],
            equity: Math.round(equity),
            drawdown: Math.round(drawdown * 100) / 100,
            pnl: Math.round(dailyReturn)
        });
    }
    return points;
};

export function EquityCurve({ data: propData, startingCapital = 100000 }: EquityCurveProps) {
    const [chartData, setChartData] = useState<EquityPoint[]>([]);
    const [loading, setLoading] = useState(true);
    const [timeRange, setTimeRange] = useState<'1W' | '1M' | '3M' | '6M' | 'YTD' | 'ALL'>('1M');
    const [showDrawdown, setShowDrawdown] = useState(false);

    const getDaysForRange = (range: string): number => {
        switch (range) {
            case '1W': return 7;
            case '1M': return 30;
            case '3M': return 90;
            case '6M': return 180;
            case 'YTD': return Math.ceil((Date.now() - new Date(new Date().getFullYear(), 0, 1).getTime()) / (1000 * 60 * 60 * 24));
            case 'ALL': return 365 * 2;
            default: return 30;
        }
    };

    const fetchData = useCallback(async () => {
        if (propData) {
            setChartData(propData);
            setLoading(false);
            return;
        }

        setLoading(true);
        try {
            const days = getDaysForRange(timeRange);
            const data = await apiClient.getEquityCurve(days, startingCapital);
            if (data && data.length > 0) {
                setChartData(data);
            } else {
                setChartData(generateMockData());
            }
        } catch (error) {
            console.error("Failed to fetch equity curve:", error);
            setChartData(generateMockData());
        } finally {
            setLoading(false);
        }
    }, [propData, timeRange, startingCapital]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    // Calculate stats from current data
    const stats = useMemo(() => {
        if (chartData.length < 2) return { change: 0, changePercent: 0, maxDrawdown: 0, sharpe: 0 };
        
        const startEquity = chartData[0].equity;
        const endEquity = chartData[chartData.length - 1].equity;
        const change = endEquity - startEquity;
        const changePercent = (change / startEquity) * 100;
        const maxDrawdown = Math.min(...chartData.map(d => d.drawdown));
        
        // Simple Sharpe approximation
        const returns = chartData.map((d, i) => 
            i === 0 ? 0 : (d.equity - chartData[i - 1].equity) / chartData[i - 1].equity
        ).slice(1);
        const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
        const stdDev = Math.sqrt(returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / returns.length);
        const sharpe = stdDev > 0 ? (avgReturn / stdDev) * Math.sqrt(252) : 0;
        
        return { change, changePercent, maxDrawdown, sharpe };
    }, [chartData]);

    const CustomTooltip = ({ active, payload, label }: any) => {
        if (active && payload && payload.length) {
            return (
                <div className="glass rounded-lg p-3 border border-border/50 shadow-xl">
                    <p className="text-sm font-medium text-muted-foreground">{label}</p>
                    <p className="text-lg font-bold">₹{payload[0].value.toLocaleString()}</p>
                    {showDrawdown && payload[1] && (
                        <p className="text-sm text-red-400">Drawdown: {payload[1].value}%</p>
                    )}
                </div>
            );
        }
        return null;
    };

    return (
        <Card className="glass rounded-2xl overflow-hidden">
            <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10 pb-2">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    <div className="flex items-center gap-4">
                        <CardTitle className="text-xl font-bold">Equity Curve</CardTitle>
                        <div className={`flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium ${
                            stats.change >= 0 
                                ? 'bg-green-500/20 text-green-400' 
                                : 'bg-red-500/20 text-red-400'
                        }`}>
                            {stats.change >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                            {stats.change >= 0 ? '+' : ''}{stats.changePercent.toFixed(2)}%
                        </div>
                    </div>
                    
                    <div className="flex items-center gap-2">
                        <div className="flex bg-muted/30 rounded-lg p-1">
                            {(['1W', '1M', '3M', '6M', 'YTD', 'ALL'] as const).map((range) => (
                                <Button
                                    key={range}
                                    variant={timeRange === range ? "secondary" : "ghost"}
                                    size="sm"
                                    className="h-7 px-3 text-xs"
                                    onClick={() => setTimeRange(range)}
                                >
                                    {range}
                                </Button>
                            ))}
                        </div>
                        <Button 
                            variant={showDrawdown ? "secondary" : "outline"} 
                            size="sm"
                            onClick={() => setShowDrawdown(!showDrawdown)}
                        >
                            Drawdown
                        </Button>
                        <Button 
                            variant="outline" 
                            size="sm"
                            onClick={() => fetchData()}
                            disabled={loading}
                        >
                            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                        </Button>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="pt-4">
                {loading ? (
                    <div className="flex items-center justify-center h-80">
                        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                    </div>
                ) : (
                <>
                {/* Mini Stats Row */}
                <div className="grid grid-cols-4 gap-4 mb-6">
                    <div className="p-3 rounded-lg bg-muted/20 text-center">
                        <p className="text-xs text-muted-foreground">Period P&L</p>
                        <p className={`text-lg font-bold ${stats.change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {stats.change >= 0 ? '+' : ''}₹{stats.change.toLocaleString()}
                        </p>
                    </div>
                    <div className="p-3 rounded-lg bg-muted/20 text-center">
                        <p className="text-xs text-muted-foreground">Max Drawdown</p>
                        <p className="text-lg font-bold text-red-400">{stats.maxDrawdown.toFixed(1)}%</p>
                    </div>
                    <div className="p-3 rounded-lg bg-muted/20 text-center">
                        <p className="text-xs text-muted-foreground">Sharpe Ratio</p>
                        <p className="text-lg font-bold text-blue-400">{stats.sharpe.toFixed(2)}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-muted/20 text-center">
                        <p className="text-xs text-muted-foreground">Trading Days</p>
                        <p className="text-lg font-bold">{chartData.length}</p>
                    </div>
                </div>

                {/* Chart */}
                <div className="h-80 min-h-[320px]">
                    <ResponsiveContainer width="100%" height="100%" minHeight={300}>
                        <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                            <defs>
                                <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                            <XAxis 
                                dataKey="date" 
                                axisLine={false}
                                tickLine={false}
                                tick={{ fill: '#888', fontSize: 11 }}
                                tickFormatter={(value) => new Date(value).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}
                            />
                            <YAxis 
                                yAxisId="equity"
                                axisLine={false}
                                tickLine={false}
                                tick={{ fill: '#888', fontSize: 11 }}
                                tickFormatter={(value) => `₹${(value / 1000).toFixed(0)}K`}
                                domain={['dataMin - 5000', 'dataMax + 5000']}
                            />
                            {showDrawdown && (
                                <YAxis 
                                    yAxisId="drawdown"
                                    orientation="right"
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fill: '#ef4444', fontSize: 11 }}
                                    tickFormatter={(value) => `${value}%`}
                                    domain={['dataMin - 5', 0]}
                                />
                            )}
                            <Tooltip content={<CustomTooltip />} />
                            <ReferenceLine yAxisId="equity" y={100000} stroke="#666" strokeDasharray="5 5" />
                            <Area
                                yAxisId="equity"
                                type="monotone"
                                dataKey="equity"
                                stroke="#22c55e"
                                strokeWidth={2}
                                fill="url(#equityGradient)"
                            />
                            {showDrawdown && (
                                <Area
                                    yAxisId="drawdown"
                                    type="monotone"
                                    dataKey="drawdown"
                                    stroke="#ef4444"
                                    strokeWidth={1}
                                    fill="url(#drawdownGradient)"
                                />
                            )}
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
                </>
                )}
            </CardContent>
        </Card>
    );
}
