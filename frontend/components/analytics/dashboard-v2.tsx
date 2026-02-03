"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { 
    TrendingUp, TrendingDown, BarChart3, Calendar, 
    Shield, Download, RefreshCw, Filter, ChevronDown, Target 
} from "lucide-react";
import { EquityCurve } from "./equity-curve";
import { TradeTable } from "./trade-table";
import { CalendarHeatmap } from "./calendar-heatmap";
import { RiskAnalytics } from "./risk-analytics";
import { StrategyPerformance } from "./strategy-performance";
import { apiClient } from "@/lib/api/client";

interface AnalyticsData {
    totalTrades: number;
    winningTrades: number;
    losingTrades: number;
    totalPnL: number;
    avgWin: number;
    avgLoss: number;
    largestWin: number;
    largestLoss: number;
    winRate: number;
    profitFactor: number;
    avgHoldingTime: number;
    avgTradesPerDay: number;
}

export function AnalyticsDashboardV2() {
    const [analytics, setAnalytics] = useState<AnalyticsData>({
        totalTrades: 0,
        winningTrades: 0,
        losingTrades: 0,
        totalPnL: 0,
        avgWin: 0,
        avgLoss: 0,
        largestWin: 0,
        largestLoss: 0,
        winRate: 0,
        profitFactor: 0,
        avgHoldingTime: 0,
        avgTradesPerDay: 0,
    });
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('overview');
    const [dateRange, setDateRange] = useState('30d');

    // Convert dateRange to days for API
    const getDays = (range: string): number => {
        switch (range) {
            case '7d': return 7;
            case '30d': return 30;
            case '90d': return 90;
            case 'YTD': return Math.ceil((Date.now() - new Date(new Date().getFullYear(), 0, 1).getTime()) / (1000 * 60 * 60 * 24));
            case 'ALL': return 365 * 5; // 5 years
            default: return 30;
        }
    };

    const fetchAnalytics = async () => {
        setLoading(true);
        try {
            const days = getDays(dateRange);
            const data = await apiClient.getAnalytics(days);
            if (data) {
                setAnalytics({
                    totalTrades: data.total_trades || 0,
                    winningTrades: data.winning_trades || 0,
                    losingTrades: data.losing_trades || 0,
                    totalPnL: data.total_pnl || 0,
                    avgWin: data.avg_win || 0,
                    avgLoss: data.avg_loss || 0,
                    largestWin: data.largest_win || 0,
                    largestLoss: data.largest_loss || 0,
                    winRate: data.win_rate || 0,
                    profitFactor: data.profit_factor || 0,
                    avgHoldingTime: data.avg_holding_time || 0,
                    avgTradesPerDay: data.avg_trades_per_day || 0,
                });
            }
        } catch (error) {
            console.error("Failed to fetch analytics:", error);
            // Use mock data as fallback
            setAnalytics({
                totalTrades: 156,
                winningTrades: 98,
                losingTrades: 58,
                totalPnL: 142500,
                avgWin: 2850,
                avgLoss: 1450,
                largestWin: 18500,
                largestLoss: 8200,
                winRate: 62.8,
                profitFactor: 1.96,
                avgHoldingTime: 45,
                avgTradesPerDay: 5.2,
            });
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAnalytics();
    }, [dateRange]);

    const expectancy = analytics.avgWin * (analytics.winRate / 100) - 
                       analytics.avgLoss * (1 - analytics.winRate / 100);

    return (
        <div className="flex-1 space-y-6 p-6 pt-4 max-w-[1800px] mx-auto">
            {/* Header */}
            <div className="relative overflow-hidden rounded-2xl glass p-6">
                <div className="absolute inset-0 gradient-bg opacity-30"></div>
                <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-4xl font-bold gradient-text mb-2">Performance Analytics</h1>
                        <p className="text-muted-foreground">Deep dive into your trading performance and risk metrics</p>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="flex bg-muted/30 rounded-lg p-1">
                            {['7d', '30d', '90d', 'YTD', 'ALL'].map((range) => (
                                <Button
                                    key={range}
                                    variant={dateRange === range ? "secondary" : "ghost"}
                                    size="sm"
                                    className="h-8 px-4"
                                    onClick={() => setDateRange(range)}
                                >
                                    {range}
                                </Button>
                            ))}
                        </div>
                        <Button variant="outline" size="sm">
                            <Download className="h-4 w-4 mr-2" /> Export
                        </Button>
                        <Button variant="outline" size="sm">
                            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} /> Refresh
                        </Button>
                    </div>
                </div>
            </div>

            {/* Key Performance Indicators */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
                <div className="glass rounded-xl p-4 hover-lift">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-muted-foreground">Total P&L</span>
                        {analytics.totalPnL >= 0 ? 
                            <TrendingUp className="h-4 w-4 text-green-400" /> : 
                            <TrendingDown className="h-4 w-4 text-red-400" />
                        }
                    </div>
                    <p className={`text-2xl font-bold ${analytics.totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {analytics.totalPnL >= 0 ? '+' : ''}₹{analytics.totalPnL.toLocaleString()}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">From {analytics.totalTrades} trades</p>
                </div>

                <div className="glass rounded-xl p-4 hover-lift">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-muted-foreground">Win Rate</span>
                        <BarChart3 className="h-4 w-4 text-blue-400" />
                    </div>
                    <p className="text-2xl font-bold text-blue-400">{analytics.winRate.toFixed(1)}%</p>
                    <div className="w-full h-1.5 bg-muted/30 rounded-full mt-2 overflow-hidden">
                        <div 
                            className="h-full bg-gradient-to-r from-blue-400 to-cyan-400 rounded-full"
                            style={{ width: `${analytics.winRate}%` }}
                        ></div>
                    </div>
                </div>

                <div className="glass rounded-xl p-4 hover-lift">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-muted-foreground">Profit Factor</span>
                        <TrendingUp className="h-4 w-4 text-purple-400" />
                    </div>
                    <p className="text-2xl font-bold text-purple-400">{analytics.profitFactor.toFixed(2)}x</p>
                    <p className="text-xs text-muted-foreground mt-1">
                        {analytics.profitFactor > 1.5 ? 'Excellent' : analytics.profitFactor > 1 ? 'Good' : 'Needs work'}
                    </p>
                </div>

                <div className="glass rounded-xl p-4 hover-lift">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-muted-foreground">Expectancy</span>
                        <Shield className="h-4 w-4 text-green-400" />
                    </div>
                    <p className={`text-2xl font-bold ${expectancy >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ₹{Math.round(expectancy).toLocaleString()}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">Expected per trade</p>
                </div>

                <div className="glass rounded-xl p-4 hover-lift">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-muted-foreground">Avg Hold Time</span>
                        <Calendar className="h-4 w-4 text-orange-400" />
                    </div>
                    <p className="text-2xl font-bold text-orange-400">{analytics.avgHoldingTime}m</p>
                    <p className="text-xs text-muted-foreground mt-1">{analytics.avgTradesPerDay.toFixed(1)} trades/day</p>
                </div>
            </div>

            {/* Win/Loss Stats Row */}
            <div className="grid gap-4 lg:grid-cols-4">
                <div className="glass rounded-xl p-4 bg-gradient-to-br from-green-500/5 to-emerald-500/5 border border-green-500/20">
                    <p className="text-sm text-muted-foreground">Average Win</p>
                    <p className="text-xl font-bold text-green-400">+₹{analytics.avgWin.toLocaleString()}</p>
                </div>
                <div className="glass rounded-xl p-4 bg-gradient-to-br from-red-500/5 to-rose-500/5 border border-red-500/20">
                    <p className="text-sm text-muted-foreground">Average Loss</p>
                    <p className="text-xl font-bold text-red-400">-₹{analytics.avgLoss.toLocaleString()}</p>
                </div>
                <div className="glass rounded-xl p-4 bg-gradient-to-br from-green-500/5 to-emerald-500/5 border border-green-500/20">
                    <p className="text-sm text-muted-foreground">Largest Win</p>
                    <p className="text-xl font-bold text-green-400">+₹{analytics.largestWin.toLocaleString()}</p>
                </div>
                <div className="glass rounded-xl p-4 bg-gradient-to-br from-red-500/5 to-rose-500/5 border border-red-500/20">
                    <p className="text-sm text-muted-foreground">Largest Loss</p>
                    <p className="text-xl font-bold text-red-400">-₹{analytics.largestLoss.toLocaleString()}</p>
                </div>
            </div>

            {/* Tabbed Content */}
            <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
                <TabsList className="glass p-1 gap-1">
                    <TabsTrigger value="overview" className="data-[state=active]:bg-primary/20">
                        <TrendingUp className="h-4 w-4 mr-2" /> Overview
                    </TabsTrigger>
                    <TabsTrigger value="strategies" className="data-[state=active]:bg-primary/20">
                        <Target className="h-4 w-4 mr-2" /> Strategies
                    </TabsTrigger>
                    <TabsTrigger value="trades" className="data-[state=active]:bg-primary/20">
                        <BarChart3 className="h-4 w-4 mr-2" /> Trades
                    </TabsTrigger>
                    <TabsTrigger value="calendar" className="data-[state=active]:bg-primary/20">
                        <Calendar className="h-4 w-4 mr-2" /> Calendar
                    </TabsTrigger>
                    <TabsTrigger value="risk" className="data-[state=active]:bg-primary/20">
                        <Shield className="h-4 w-4 mr-2" /> Risk
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="space-y-6">
                    {/* Equity Curve */}
                    <EquityCurve />
                    
                    {/* Quick Stats Grid */}
                    <div className="grid gap-6 lg:grid-cols-2">
                        {/* Trade Distribution */}
                        <Card className="glass rounded-2xl overflow-hidden">
                            <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10 py-4">
                                <CardTitle className="text-lg font-bold">Trade Distribution</CardTitle>
                            </CardHeader>
                            <CardContent className="pt-4">
                                <div className="space-y-4">
                                    <div>
                                        <div className="flex justify-between text-sm mb-1">
                                            <span className="text-muted-foreground">Winning Trades</span>
                                            <span className="text-green-400 font-medium">{analytics.winningTrades}</span>
                                        </div>
                                        <div className="w-full h-3 bg-muted/30 rounded-full overflow-hidden">
                                            <div 
                                                className="h-full bg-gradient-to-r from-green-500 to-emerald-400 rounded-full"
                                                style={{ width: `${analytics.winRate}%` }}
                                            ></div>
                                        </div>
                                    </div>
                                    <div>
                                        <div className="flex justify-between text-sm mb-1">
                                            <span className="text-muted-foreground">Losing Trades</span>
                                            <span className="text-red-400 font-medium">{analytics.losingTrades}</span>
                                        </div>
                                        <div className="w-full h-3 bg-muted/30 rounded-full overflow-hidden">
                                            <div 
                                                className="h-full bg-gradient-to-r from-red-500 to-rose-400 rounded-full"
                                                style={{ width: `${100 - analytics.winRate}%` }}
                                            ></div>
                                        </div>
                                    </div>
                                </div>

                                {/* Win/Loss Ratio */}
                                <div className="mt-6 p-4 rounded-lg bg-muted/10">
                                    <div className="flex items-center justify-between">
                                        <span className="text-sm text-muted-foreground">Risk/Reward Ratio</span>
                                        <span className="text-lg font-bold">
                                            1 : {(analytics.avgWin / analytics.avgLoss).toFixed(2)}
                                        </span>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Performance by Strategy */}
                        <Card className="glass rounded-2xl overflow-hidden">
                            <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10 py-4">
                                <CardTitle className="text-lg font-bold">Performance by Strategy</CardTitle>
                            </CardHeader>
                            <CardContent className="pt-4">
                                <div className="space-y-3">
                                    {[
                                        { name: 'EMA Crossover', pnl: 45200, trades: 42, winRate: 68 },
                                        { name: 'RSI Reversal', pnl: 28500, trades: 35, winRate: 62 },
                                        { name: 'Momentum Breakout', pnl: 52800, trades: 48, winRate: 58 },
                                        { name: 'Iron Condor', pnl: 16000, trades: 31, winRate: 74 },
                                    ].map((strategy) => (
                                        <div key={strategy.name} className="p-3 rounded-lg bg-muted/10 hover:bg-muted/20 transition-colors">
                                            <div className="flex items-center justify-between mb-2">
                                                <span className="font-medium">{strategy.name}</span>
                                                <span className={`font-bold ${strategy.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                    {strategy.pnl >= 0 ? '+' : ''}₹{strategy.pnl.toLocaleString()}
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-4 text-xs text-muted-foreground">
                                                <span>{strategy.trades} trades</span>
                                                <span>{strategy.winRate}% win rate</span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </TabsContent>

                <TabsContent value="strategies">
                    <StrategyPerformance />
                </TabsContent>

                <TabsContent value="trades">
                    <TradeTable />
                </TabsContent>

                <TabsContent value="calendar">
                    <CalendarHeatmap />
                </TabsContent>

                <TabsContent value="risk">
                    <RiskAnalytics />
                </TabsContent>
            </Tabs>
        </div>
    );
}
