"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
    TrendingUp, TrendingDown, BarChart3, Target, Activity,
    ChevronRight, ArrowUpRight, ArrowDownRight, Loader2
} from "lucide-react";
import {
    ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
    Cell, PieChart, Pie, Legend
} from "recharts";
import { apiClient } from "@/lib/api/client";

interface StrategyPerformance {
    id: number;
    name: string;
    totalTrades: number;
    winningTrades: number;
    losingTrades: number;
    winRate: number;
    totalPnL: number;
    avgPnL: number;
    profitFactor: number;
    maxDrawdown: number;
    sharpeRatio: number;
    status: 'active' | 'paused' | 'backtesting';
}

// Mock data for fallback
const MOCK_STRATEGIES: StrategyPerformance[] = [
    {
        id: 1, name: 'EMA Crossover', totalTrades: 48, winningTrades: 32, losingTrades: 16,
        winRate: 66.7, totalPnL: 45200, avgPnL: 942, profitFactor: 2.1, maxDrawdown: 8.2, sharpeRatio: 1.85, status: 'active'
    },
    {
        id: 2, name: 'RSI Reversal', totalTrades: 36, winningTrades: 21, losingTrades: 15,
        winRate: 58.3, totalPnL: 18500, avgPnL: 514, profitFactor: 1.6, maxDrawdown: 12.1, sharpeRatio: 1.2, status: 'active'
    },
    {
        id: 3, name: 'Momentum Breakout', totalTrades: 52, winningTrades: 35, losingTrades: 17,
        winRate: 67.3, totalPnL: 62800, avgPnL: 1208, profitFactor: 2.4, maxDrawdown: 6.8, sharpeRatio: 2.1, status: 'active'
    },
    {
        id: 4, name: 'Iron Condor', totalTrades: 20, winningTrades: 10, losingTrades: 10,
        winRate: 50.0, totalPnL: 16000, avgPnL: 800, profitFactor: 1.3, maxDrawdown: 15.2, sharpeRatio: 0.9, status: 'paused'
    },
];

const COLORS = ['#10b981', '#f59e0b', '#3b82f6', '#ef4444', '#8b5cf6', '#ec4899'];

export function StrategyPerformance() {
    const [strategies, setStrategies] = useState<StrategyPerformance[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedStrategy, setSelectedStrategy] = useState<StrategyPerformance | null>(null);

    useEffect(() => {
        const fetchStrategies = async () => {
            setLoading(true);
            try {
                const data = await apiClient.listStrategiesManagement();
                if (data && data.length > 0) {
                    const mapped = data.map((s: any) => ({
                        id: s.id,
                        name: s.name,
                        totalTrades: s.metrics?.total_trades || 0,
                        winningTrades: s.metrics?.winning_trades || 0,
                        losingTrades: s.metrics?.losing_trades || 0,
                        winRate: s.metrics?.win_rate || 0,
                        totalPnL: s.metrics?.total_pnl || 0,
                        avgPnL: s.metrics?.avg_pnl || 0,
                        profitFactor: s.metrics?.profit_factor || 0,
                        maxDrawdown: s.metrics?.max_drawdown || 0,
                        sharpeRatio: s.metrics?.sharpe_ratio || 0,
                        status: s.status || 'active'
                    }));
                    setStrategies(mapped);
                } else {
                    setStrategies(MOCK_STRATEGIES);
                }
            } catch (error) {
                console.error("Failed to fetch strategy performance:", error);
                setStrategies(MOCK_STRATEGIES);
            } finally {
                setLoading(false);
            }
        };
        
        fetchStrategies();
    }, []);

    const totalPnL = strategies.reduce((sum, s) => sum + s.totalPnL, 0);
    const totalTrades = strategies.reduce((sum, s) => sum + s.totalTrades, 0);
    
    // Data for PnL distribution chart
    const pnlData = strategies.map((s, idx) => ({
        name: s.name,
        value: s.totalPnL,
        color: COLORS[idx % COLORS.length]
    }));
    
    // Data for win rate comparison
    const winRateData = strategies.map(s => ({
        name: s.name.split(' ')[0], // Short name
        winRate: s.winRate,
        profitFactor: s.profitFactor
    }));

    if (loading) {
        return (
            <Card className="glass rounded-2xl">
                <CardContent className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            {/* Summary Cards */}
            <div className="grid gap-4 md:grid-cols-3">
                <Card className="glass rounded-xl border-primary/20">
                    <CardContent className="p-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">Total Strategy P&L</p>
                                <p className={`text-2xl font-bold ${totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {totalPnL >= 0 ? '+' : ''}₹{totalPnL.toLocaleString()}
                                </p>
                            </div>
                            <div className={`h-12 w-12 rounded-xl flex items-center justify-center ${
                                totalPnL >= 0 ? 'bg-green-500/20' : 'bg-red-500/20'
                            }`}>
                                {totalPnL >= 0 ? (
                                    <TrendingUp className="h-6 w-6 text-green-400" />
                                ) : (
                                    <TrendingDown className="h-6 w-6 text-red-400" />
                                )}
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card className="glass rounded-xl border-primary/20">
                    <CardContent className="p-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">Active Strategies</p>
                                <p className="text-2xl font-bold text-blue-400">
                                    {strategies.filter(s => s.status === 'active').length}
                                </p>
                            </div>
                            <div className="h-12 w-12 rounded-xl bg-blue-500/20 flex items-center justify-center">
                                <Activity className="h-6 w-6 text-blue-400" />
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card className="glass rounded-xl border-primary/20">
                    <CardContent className="p-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">Total Trades</p>
                                <p className="text-2xl font-bold text-purple-400">{totalTrades}</p>
                            </div>
                            <div className="h-12 w-12 rounded-xl bg-purple-500/20 flex items-center justify-center">
                                <BarChart3 className="h-6 w-6 text-purple-400" />
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Charts Row */}
            <div className="grid gap-6 lg:grid-cols-2">
                {/* P&L Distribution Pie Chart */}
                <Card className="glass rounded-xl">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-lg">P&L Distribution</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <ResponsiveContainer width="100%" height={250} minHeight={250}>
                            <PieChart>
                                <Pie
                                    data={pnlData.filter(d => d.value > 0)}
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={60}
                                    outerRadius={90}
                                    dataKey="value"
                                    nameKey="name"
                                    label={({ name, percent }) => `${name}: ${((percent || 0) * 100).toFixed(0)}%`}
                                    labelLine={false}
                                >
                                    {pnlData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.color} />
                                    ))}
                                </Pie>
                                <Tooltip 
                                    formatter={(value: number) => `₹${value.toLocaleString()}`}
                                    contentStyle={{ 
                                        backgroundColor: 'rgba(0,0,0,0.8)', 
                                        border: '1px solid rgba(255,255,255,0.1)',
                                        borderRadius: '8px'
                                    }}
                                />
                            </PieChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>

                {/* Win Rate Comparison Bar Chart */}
                <Card className="glass rounded-xl">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-lg">Win Rate Comparison</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <ResponsiveContainer width="100%" height={250} minHeight={250}>
                            <BarChart data={winRateData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                                <XAxis dataKey="name" stroke="#888" fontSize={12} />
                                <YAxis stroke="#888" fontSize={12} />
                                <Tooltip 
                                    formatter={(value: number, name: string) => [
                                        name === 'winRate' ? `${value.toFixed(1)}%` : value.toFixed(2),
                                        name === 'winRate' ? 'Win Rate' : 'Profit Factor'
                                    ]}
                                    contentStyle={{ 
                                        backgroundColor: 'rgba(0,0,0,0.8)', 
                                        border: '1px solid rgba(255,255,255,0.1)',
                                        borderRadius: '8px'
                                    }}
                                />
                                <Bar dataKey="winRate" fill="#10b981" radius={[4, 4, 0, 0]} name="winRate" />
                            </BarChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>
            </div>

            {/* Strategy List */}
            <Card className="glass rounded-xl overflow-hidden">
                <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10 py-4">
                    <CardTitle className="text-lg flex items-center gap-2">
                        <Target className="h-5 w-5" />
                        Strategy Breakdown
                    </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                    <div className="divide-y divide-border/50">
                        {strategies.map((strategy, idx) => (
                            <div 
                                key={strategy.id}
                                className={`p-4 hover:bg-muted/30 cursor-pointer transition-colors ${
                                    selectedStrategy?.id === strategy.id ? 'bg-muted/30' : ''
                                }`}
                                onClick={() => setSelectedStrategy(
                                    selectedStrategy?.id === strategy.id ? null : strategy
                                )}
                            >
                                <div className="flex items-center justify-between mb-3">
                                    <div className="flex items-center gap-3">
                                        <div 
                                            className="h-3 w-3 rounded-full" 
                                            style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                                        />
                                        <h4 className="font-medium">{strategy.name}</h4>
                                        <Badge className={`text-xs ${
                                            strategy.status === 'active' 
                                                ? 'bg-green-500/20 text-green-400'
                                                : strategy.status === 'paused'
                                                ? 'bg-yellow-500/20 text-yellow-400'
                                                : 'bg-blue-500/20 text-blue-400'
                                        }`}>
                                            {strategy.status}
                                        </Badge>
                                    </div>
                                    <div className="flex items-center gap-4">
                                        <span className={`font-bold ${
                                            strategy.totalPnL >= 0 ? 'text-green-400' : 'text-red-400'
                                        }`}>
                                            {strategy.totalPnL >= 0 ? '+' : ''}₹{strategy.totalPnL.toLocaleString()}
                                        </span>
                                        <ChevronRight className={`h-4 w-4 text-muted-foreground transition-transform ${
                                            selectedStrategy?.id === strategy.id ? 'rotate-90' : ''
                                        }`} />
                                    </div>
                                </div>

                                <div className="grid grid-cols-4 gap-4 text-sm">
                                    <div>
                                        <p className="text-muted-foreground text-xs">Trades</p>
                                        <p className="font-medium">{strategy.totalTrades}</p>
                                    </div>
                                    <div>
                                        <p className="text-muted-foreground text-xs">Win Rate</p>
                                        <p className={`font-medium ${
                                            strategy.winRate >= 50 ? 'text-green-400' : 'text-red-400'
                                        }`}>{strategy.winRate.toFixed(1)}%</p>
                                    </div>
                                    <div>
                                        <p className="text-muted-foreground text-xs">Profit Factor</p>
                                        <p className={`font-medium ${
                                            strategy.profitFactor >= 1.5 ? 'text-green-400' : 'text-yellow-400'
                                        }`}>{strategy.profitFactor.toFixed(2)}</p>
                                    </div>
                                    <div>
                                        <p className="text-muted-foreground text-xs">Max DD</p>
                                        <p className="font-medium text-red-400">{strategy.maxDrawdown.toFixed(1)}%</p>
                                    </div>
                                </div>

                                {/* Expanded Details */}
                                {selectedStrategy?.id === strategy.id && (
                                    <div className="mt-4 pt-4 border-t border-border/30 grid grid-cols-2 md:grid-cols-4 gap-4">
                                        <div className="p-3 rounded-lg bg-muted/30">
                                            <p className="text-xs text-muted-foreground">Winning Trades</p>
                                            <p className="text-lg font-bold text-green-400">{strategy.winningTrades}</p>
                                        </div>
                                        <div className="p-3 rounded-lg bg-muted/30">
                                            <p className="text-xs text-muted-foreground">Losing Trades</p>
                                            <p className="text-lg font-bold text-red-400">{strategy.losingTrades}</p>
                                        </div>
                                        <div className="p-3 rounded-lg bg-muted/30">
                                            <p className="text-xs text-muted-foreground">Avg P&L/Trade</p>
                                            <p className={`text-lg font-bold ${
                                                strategy.avgPnL >= 0 ? 'text-green-400' : 'text-red-400'
                                            }`}>₹{strategy.avgPnL.toLocaleString()}</p>
                                        </div>
                                        <div className="p-3 rounded-lg bg-muted/30">
                                            <p className="text-xs text-muted-foreground">Sharpe Ratio</p>
                                            <p className={`text-lg font-bold ${
                                                strategy.sharpeRatio >= 1.5 ? 'text-green-400' : 'text-yellow-400'
                                            }`}>{strategy.sharpeRatio.toFixed(2)}</p>
                                        </div>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
