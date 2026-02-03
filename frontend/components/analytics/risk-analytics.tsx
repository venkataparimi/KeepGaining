"use client";

import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { 
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, 
    ResponsiveContainer, Cell, PieChart, Pie 
} from "recharts";
import { 
    Shield, AlertTriangle, Activity, Target, 
    TrendingUp, TrendingDown, Zap 
} from "lucide-react";

interface RiskMetrics {
    var95: number;
    var99: number;
    cvar: number;
    maxDrawdown: number;
    sharpeRatio: number;
    sortinoRatio: number;
    calmarRatio: number;
    beta: number;
    alpha: number;
    treynorRatio: number;
    informationRatio: number;
    dailyVol: number;
    monthlyVol: number;
    annualVol: number;
}

interface GreeksExposure {
    delta: number;
    gamma: number;
    theta: number;
    vega: number;
}

interface RiskAnalyticsProps {
    metrics?: RiskMetrics;
    greeks?: GreeksExposure;
}

export function RiskAnalytics({ metrics, greeks }: RiskAnalyticsProps) {
    // Mock data
    const mockMetrics: RiskMetrics = {
        var95: -12500,
        var99: -18750,
        cvar: -22500,
        maxDrawdown: -15.5,
        sharpeRatio: 1.85,
        sortinoRatio: 2.32,
        calmarRatio: 1.42,
        beta: 0.78,
        alpha: 4.2,
        treynorRatio: 0.12,
        informationRatio: 0.95,
        dailyVol: 1.8,
        monthlyVol: 8.2,
        annualVol: 28.5
    };

    const mockGreeks: GreeksExposure = {
        delta: 0.45,
        gamma: 0.02,
        theta: -450,
        vega: 850
    };

    const riskData = metrics || mockMetrics;
    const greeksData = greeks || mockGreeks;

    // Risk distribution data for bar chart
    const riskDistribution = useMemo(() => [
        { name: 'VaR 95%', value: Math.abs(riskData.var95), color: '#eab308' },
        { name: 'VaR 99%', value: Math.abs(riskData.var99), color: '#f97316' },
        { name: 'CVaR', value: Math.abs(riskData.cvar), color: '#ef4444' },
    ], [riskData]);

    // Greeks visualization data
    const greeksChartData = useMemo(() => [
        { name: 'Delta', value: Math.abs(greeksData.delta * 100), fullValue: greeksData.delta, color: greeksData.delta >= 0 ? '#22c55e' : '#ef4444' },
        { name: 'Gamma', value: Math.abs(greeksData.gamma * 1000), fullValue: greeksData.gamma, color: '#3b82f6' },
        { name: 'Theta', value: Math.abs(greeksData.theta / 100), fullValue: greeksData.theta, color: greeksData.theta >= 0 ? '#22c55e' : '#ef4444' },
        { name: 'Vega', value: Math.abs(greeksData.vega / 100), fullValue: greeksData.vega, color: '#8b5cf6' },
    ], [greeksData]);

    // Risk rating
    const getRiskRating = () => {
        if (riskData.sharpeRatio > 2 && riskData.maxDrawdown > -10) return { label: 'Excellent', color: 'text-green-400', bg: 'bg-green-500/20' };
        if (riskData.sharpeRatio > 1.5 && riskData.maxDrawdown > -15) return { label: 'Good', color: 'text-blue-400', bg: 'bg-blue-500/20' };
        if (riskData.sharpeRatio > 1) return { label: 'Moderate', color: 'text-yellow-400', bg: 'bg-yellow-500/20' };
        return { label: 'High Risk', color: 'text-red-400', bg: 'bg-red-500/20' };
    };

    const riskRating = getRiskRating();

    const CustomTooltip = ({ active, payload, label }: any) => {
        if (active && payload && payload.length) {
            return (
                <div className="glass rounded-lg p-3 border border-border/50 shadow-xl">
                    <p className="text-sm font-medium">{label}</p>
                    <p className="text-lg font-bold">₹{payload[0].value.toLocaleString()}</p>
                </div>
            );
        }
        return null;
    };

    return (
        <Card className="glass rounded-2xl overflow-hidden">
            <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Shield className="h-5 w-5 text-primary" />
                        <CardTitle className="text-xl font-bold">Risk Analytics</CardTitle>
                    </div>
                    <div className={`flex items-center gap-2 px-3 py-1 rounded-full ${riskRating.bg}`}>
                        <Activity className={`h-4 w-4 ${riskRating.color}`} />
                        <span className={`text-sm font-medium ${riskRating.color}`}>{riskRating.label}</span>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="pt-4 space-y-6">
                {/* Key Risk Metrics */}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    <div className="p-4 rounded-xl bg-gradient-to-br from-blue-500/10 to-cyan-500/10 border border-blue-500/20">
                        <div className="flex items-center gap-2 mb-2">
                            <Target className="h-4 w-4 text-blue-400" />
                            <span className="text-xs text-muted-foreground">Sharpe Ratio</span>
                        </div>
                        <p className="text-2xl font-bold text-blue-400">{riskData.sharpeRatio.toFixed(2)}</p>
                    </div>
                    <div className="p-4 rounded-xl bg-gradient-to-br from-purple-500/10 to-pink-500/10 border border-purple-500/20">
                        <div className="flex items-center gap-2 mb-2">
                            <Zap className="h-4 w-4 text-purple-400" />
                            <span className="text-xs text-muted-foreground">Sortino Ratio</span>
                        </div>
                        <p className="text-2xl font-bold text-purple-400">{riskData.sortinoRatio.toFixed(2)}</p>
                    </div>
                    <div className="p-4 rounded-xl bg-gradient-to-br from-red-500/10 to-orange-500/10 border border-red-500/20">
                        <div className="flex items-center gap-2 mb-2">
                            <TrendingDown className="h-4 w-4 text-red-400" />
                            <span className="text-xs text-muted-foreground">Max Drawdown</span>
                        </div>
                        <p className="text-2xl font-bold text-red-400">{riskData.maxDrawdown.toFixed(1)}%</p>
                    </div>
                    <div className="p-4 rounded-xl bg-gradient-to-br from-green-500/10 to-emerald-500/10 border border-green-500/20">
                        <div className="flex items-center gap-2 mb-2">
                            <TrendingUp className="h-4 w-4 text-green-400" />
                            <span className="text-xs text-muted-foreground">Alpha</span>
                        </div>
                        <p className="text-2xl font-bold text-green-400">{riskData.alpha.toFixed(1)}%</p>
                    </div>
                </div>

                {/* VaR Chart and Greeks */}
                <div className="grid lg:grid-cols-2 gap-6">
                    {/* Value at Risk */}
                    <div className="space-y-4">
                        <h4 className="font-semibold flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4 text-yellow-400" />
                            Value at Risk (Daily)
                        </h4>
                        <div className="h-48 min-h-[192px]">
                            <ResponsiveContainer width="100%" height="100%" minHeight={180}>
                                <BarChart data={riskDistribution} layout="vertical">
                                    <CartesianGrid strokeDasharray="3 3" stroke="#333" horizontal={false} />
                                    <XAxis 
                                        type="number" 
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fill: '#888', fontSize: 11 }}
                                        tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}K`}
                                    />
                                    <YAxis 
                                        type="category" 
                                        dataKey="name"
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fill: '#888', fontSize: 11 }}
                                        width={70}
                                    />
                                    <Tooltip content={<CustomTooltip />} />
                                    <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                                        {riskDistribution.map((entry, index) => (
                                            <Cell key={`cell-${index}`} fill={entry.color} />
                                        ))}
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                        <p className="text-xs text-muted-foreground">
                            There's a 5% chance of losing more than ₹{Math.abs(riskData.var95).toLocaleString()} in a single day
                        </p>
                    </div>

                    {/* Greeks Exposure */}
                    <div className="space-y-4">
                        <h4 className="font-semibold flex items-center gap-2">
                            <Activity className="h-4 w-4 text-blue-400" />
                            Greeks Exposure
                        </h4>
                        <div className="grid grid-cols-2 gap-3">
                            <div className="p-3 rounded-lg bg-muted/20">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-sm text-muted-foreground">Delta (Δ)</span>
                                    <span className={`text-sm font-medium ${greeksData.delta >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                        {greeksData.delta >= 0 ? '+' : ''}{greeksData.delta.toFixed(2)}
                                    </span>
                                </div>
                                <div className="w-full h-2 bg-muted/30 rounded-full overflow-hidden">
                                    <div 
                                        className={`h-full rounded-full ${greeksData.delta >= 0 ? 'bg-green-400' : 'bg-red-400'}`}
                                        style={{ width: `${Math.min(Math.abs(greeksData.delta) * 100, 100)}%` }}
                                    ></div>
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">
                                    {greeksData.delta >= 0 ? 'Long' : 'Short'} market exposure
                                </p>
                            </div>
                            <div className="p-3 rounded-lg bg-muted/20">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-sm text-muted-foreground">Gamma (Γ)</span>
                                    <span className="text-sm font-medium text-blue-400">
                                        {greeksData.gamma.toFixed(4)}
                                    </span>
                                </div>
                                <div className="w-full h-2 bg-muted/30 rounded-full overflow-hidden">
                                    <div 
                                        className="h-full rounded-full bg-blue-400"
                                        style={{ width: `${Math.min(Math.abs(greeksData.gamma) * 5000, 100)}%` }}
                                    ></div>
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">Delta sensitivity</p>
                            </div>
                            <div className="p-3 rounded-lg bg-muted/20">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-sm text-muted-foreground">Theta (Θ)</span>
                                    <span className={`text-sm font-medium ${greeksData.theta >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                        ₹{greeksData.theta.toLocaleString()}/day
                                    </span>
                                </div>
                                <div className="w-full h-2 bg-muted/30 rounded-full overflow-hidden">
                                    <div 
                                        className={`h-full rounded-full ${greeksData.theta >= 0 ? 'bg-green-400' : 'bg-red-400'}`}
                                        style={{ width: `${Math.min(Math.abs(greeksData.theta) / 10, 100)}%` }}
                                    ></div>
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">
                                    {greeksData.theta >= 0 ? 'Earning' : 'Losing'} from time decay
                                </p>
                            </div>
                            <div className="p-3 rounded-lg bg-muted/20">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-sm text-muted-foreground">Vega (ν)</span>
                                    <span className="text-sm font-medium text-purple-400">
                                        ₹{greeksData.vega.toLocaleString()}
                                    </span>
                                </div>
                                <div className="w-full h-2 bg-muted/30 rounded-full overflow-hidden">
                                    <div 
                                        className="h-full rounded-full bg-purple-400"
                                        style={{ width: `${Math.min(Math.abs(greeksData.vega) / 15, 100)}%` }}
                                    ></div>
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">
                                    P&L per 1% IV change
                                </p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Volatility Metrics */}
                <div className="p-4 rounded-xl bg-muted/10 border border-border/30">
                    <h4 className="font-semibold mb-4">Volatility Analysis</h4>
                    <div className="grid grid-cols-3 gap-6">
                        <div className="text-center">
                            <p className="text-2xl font-bold">{riskData.dailyVol.toFixed(2)}%</p>
                            <p className="text-sm text-muted-foreground">Daily Vol</p>
                        </div>
                        <div className="text-center">
                            <p className="text-2xl font-bold">{riskData.monthlyVol.toFixed(2)}%</p>
                            <p className="text-sm text-muted-foreground">Monthly Vol</p>
                        </div>
                        <div className="text-center">
                            <p className="text-2xl font-bold">{riskData.annualVol.toFixed(2)}%</p>
                            <p className="text-sm text-muted-foreground">Annual Vol</p>
                        </div>
                    </div>
                </div>

                {/* Additional Ratios */}
                <div className="grid grid-cols-4 gap-4 text-sm">
                    <div className="p-3 rounded-lg bg-muted/20 text-center">
                        <p className="text-muted-foreground">Beta</p>
                        <p className="font-bold">{riskData.beta.toFixed(2)}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-muted/20 text-center">
                        <p className="text-muted-foreground">Calmar</p>
                        <p className="font-bold">{riskData.calmarRatio.toFixed(2)}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-muted/20 text-center">
                        <p className="text-muted-foreground">Treynor</p>
                        <p className="font-bold">{riskData.treynorRatio.toFixed(2)}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-muted/20 text-center">
                        <p className="text-muted-foreground">Info Ratio</p>
                        <p className="font-bold">{riskData.informationRatio.toFixed(2)}</p>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
