"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, TrendingDown, BarChart3, ArrowUpRight, ArrowDownRight, Calendar } from "lucide-react";
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
}

export function AnalyticsDashboard() {
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
    });
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchAnalytics = async () => {
            try {
                setLoading(true);
                const data = await apiClient.getAnalytics();
                setAnalytics({
                    totalTrades: data.total_trades,
                    winningTrades: data.winning_trades,
                    losingTrades: data.losing_trades,
                    totalPnL: data.total_pnl,
                    avgWin: data.avg_win,
                    avgLoss: data.avg_loss,
                    largestWin: data.largest_win,
                    largestLoss: data.largest_loss,
                    winRate: data.win_rate,
                    profitFactor: data.profit_factor,
                });
            } catch (error) {
                console.error("Failed to fetch analytics:", error);
            } finally {
                setLoading(false);
            }
        };

        fetchAnalytics();
    }, []);

    return (
        <div className="flex-1 space-y-6 p-8 pt-6 max-w-[1600px] mx-auto">
            {/* Header */}
            <div className="relative overflow-hidden rounded-2xl glass p-8">
                <div className="absolute inset-0 gradient-bg opacity-30"></div>
                <div className="relative z-10">
                    <h1 className="text-4xl font-bold gradient-text mb-2">Performance Analytics</h1>
                    <p className="text-muted-foreground">Track your trading performance and analyze results</p>
                </div>
            </div>

            {/* Key Metrics */}
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
                <div className="glass rounded-2xl overflow-hidden hover-lift">
                    <CardHeader className="bg-gradient-to-br from-green-500/10 to-emerald-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Total P&L</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className={`text-3xl font-bold flex items-center ${analytics.totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {analytics.totalPnL >= 0 ? <TrendingUp className="mr-2 h-8 w-8" /> : <TrendingDown className="mr-2 h-8 w-8" />}
                            {analytics.totalPnL >= 0 ? '+' : ''}₹{analytics.totalPnL.toLocaleString()}
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">All-time performance</p>
                    </CardContent>
                </div>

                <div className="glass rounded-2xl overflow-hidden hover-lift">
                    <CardHeader className="bg-gradient-to-br from-blue-500/10 to-cyan-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Win Rate</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="text-3xl font-bold gradient-text">
                            {analytics.winRate.toFixed(1)}%
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">
                            {analytics.winningTrades} wins, {analytics.losingTrades} losses
                        </p>
                    </CardContent>
                </div>

                <div className="glass rounded-2xl overflow-hidden hover-lift">
                    <CardHeader className="bg-gradient-to-br from-purple-500/10 to-pink-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Profit Factor</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="text-3xl font-bold text-purple-400">
                            {analytics.profitFactor.toFixed(2)}x
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">
                            {analytics.profitFactor > 1 ? 'Profitable' : 'Loss-making'} system
                        </p>
                    </CardContent>
                </div>

                <div className="glass rounded-2xl overflow-hidden hover-lift">
                    <CardHeader className="bg-gradient-to-br from-orange-500/10 to-amber-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Total Trades</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="text-3xl font-bold">
                            {analytics.totalTrades}
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">Executed positions</p>
                    </CardContent>
                </div>
            </div>

            {/* Detailed Stats */}
            <div className="grid gap-6 lg:grid-cols-2">
                <div className="glass rounded-2xl overflow-hidden">
                    <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10">
                        <CardTitle className="text-xl font-bold">Trade Statistics</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-6">
                        <div className="space-y-4">
                            <div className="flex justify-between items-center p-3 rounded-lg bg-green-500/10">
                                <span className="text-sm text-muted-foreground">Average Win</span>
                                <span className="text-lg font-bold text-green-400">₹{analytics.avgWin.toLocaleString()}</span>
                            </div>
                            <div className="flex justify-between items-center p-3 rounded-lg bg-red-500/10">
                                <span className="text-sm text-muted-foreground">Average Loss</span>
                                <span className="text-lg font-bold text-red-400">₹{analytics.avgLoss.toLocaleString()}</span>
                            </div>
                            <div className="flex justify-between items-center p-3 rounded-lg bg-green-500/10">
                                <span className="text-sm text-muted-foreground">Largest Win</span>
                                <span className="text-lg font-bold text-green-400 flex items-center">
                                    <ArrowUpRight className="h-4 w-4 mr-1" />
                                    ₹{analytics.largestWin.toLocaleString()}
                                </span>
                            </div>
                            <div className="flex justify-between items-center p-3 rounded-lg bg-red-500/10">
                                <span className="text-sm text-muted-foreground">Largest Loss</span>
                                <span className="text-lg font-bold text-red-400 flex items-center">
                                    <ArrowDownRight className="h-4 w-4 mr-1" />
                                    ₹{analytics.largestLoss.toLocaleString()}
                                </span>
                            </div>
                        </div>
                    </CardContent>
                </div>

                <div className="glass rounded-2xl overflow-hidden">
                    <CardHeader className="bg-gradient-to-r from-accent/10 to-primary/10">
                        <CardTitle className="text-xl font-bold">Performance Breakdown</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-6">
                        <div className="space-y-4">
                            <div>
                                <div className="flex justify-between mb-2">
                                    <span className="text-sm text-muted-foreground">Winning Trades</span>
                                    <span className="text-sm font-semibold text-green-400">{analytics.winningTrades} ({analytics.winRate.toFixed(1)}%)</span>
                                </div>
                                <div className="h-2 bg-muted rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-gradient-to-r from-green-400 to-emerald-400"
                                        style={{ width: `${analytics.winRate}%` }}
                                    ></div>
                                </div>
                            </div>
                            <div>
                                <div className="flex justify-between mb-2">
                                    <span className="text-sm text-muted-foreground">Losing Trades</span>
                                    <span className="text-sm font-semibold text-red-400">{analytics.losingTrades} ({(100 - analytics.winRate).toFixed(1)}%)</span>
                                </div>
                                <div className="h-2 bg-muted rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-gradient-to-r from-red-400 to-rose-400"
                                        style={{ width: `${100 - analytics.winRate}%` }}
                                    ></div>
                                </div>
                            </div>

                            <div className="pt-4 mt-4 border-t border-border/50">
                                <div className="flex items-center justify-between p-4 rounded-lg bg-primary/10">
                                    <div>
                                        <p className="text-sm text-muted-foreground">Risk/Reward Ratio</p>
                                        <p className="text-2xl font-bold gradient-text">
                                            {analytics.avgLoss !== 0
                                                ? `1:${(Math.abs(analytics.avgWin / analytics.avgLoss)).toFixed(2)}`
                                                : 'N/A'
                                            }
                                        </p>
                                    </div>
                                    <BarChart3 className="h-12 w-12 text-primary opacity-50" />
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </div>
            </div>

            {/* Coming Soon - Charts */}
            <div className="glass rounded-2xl overflow-hidden p-8">
                <div className="text-center text-muted-foreground">
                    <Calendar className="h-16 w-16 mx-auto mb-4 opacity-50" />
                    <h3 className="text-xl font-bold mb-2">P&L Charts Coming Soon</h3>
                    <p>Interactive charts showing equity curve, daily P&L, and strategy performance will be added here.</p>
                </div>
            </div>
        </div>
    );
}
