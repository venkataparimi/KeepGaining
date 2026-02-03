"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { TrendingUp, TrendingDown, Activity, Gauge } from "lucide-react";

interface GreeksDisplayProps {
    delta: number;
    gamma: number;
    theta: number;
    vega: number;
    iv?: number;
    compact?: boolean;
}

// Normalize value to percentage for progress bar (0-100)
const normalizeForProgress = (value: number, max: number): number => {
    const normalized = Math.min(Math.abs(value), max) / max * 100;
    return normalized;
};

// Get color based on value
const getGreekColor = (value: number, type: 'delta' | 'gamma' | 'theta' | 'vega'): string => {
    switch (type) {
        case 'delta':
            if (value > 0.5) return 'text-green-500';
            if (value < -0.5) return 'text-red-500';
            if (Math.abs(value) > 0.3) return 'text-yellow-500';
            return 'text-muted-foreground';
        case 'gamma':
            if (value > 0.05) return 'text-purple-500';
            return 'text-muted-foreground';
        case 'theta':
            return value < 0 ? 'text-red-500' : 'text-green-500';
        case 'vega':
            return value > 0 ? 'text-blue-500' : 'text-muted-foreground';
        default:
            return 'text-muted-foreground';
    }
};

const getProgressColor = (type: 'delta' | 'gamma' | 'theta' | 'vega'): string => {
    switch (type) {
        case 'delta': return 'bg-green-500';
        case 'gamma': return 'bg-purple-500';
        case 'theta': return 'bg-red-500';
        case 'vega': return 'bg-blue-500';
        default: return 'bg-primary';
    }
};

export function GreeksDisplay({ delta, gamma, theta, vega, iv, compact = false }: GreeksDisplayProps) {
    if (compact) {
        return (
            <div className="flex items-center gap-4 text-sm">
                <span className={`font-medium ${getGreekColor(delta, 'delta')}`}>
                    Δ {delta.toFixed(2)}
                </span>
                <span className={`font-medium ${getGreekColor(gamma, 'gamma')}`}>
                    Γ {gamma.toFixed(4)}
                </span>
                <span className={`font-medium ${getGreekColor(theta, 'theta')}`}>
                    Θ {theta.toFixed(2)}
                </span>
                <span className={`font-medium ${getGreekColor(vega, 'vega')}`}>
                    ν {vega.toFixed(2)}
                </span>
                {iv !== undefined && (
                    <span className="font-medium text-orange-500">
                        IV {iv.toFixed(1)}%
                    </span>
                )}
            </div>
        );
    }

    return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Delta */}
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-muted-foreground">Delta (Δ)</span>
                    <span className={`text-sm font-bold ${getGreekColor(delta, 'delta')}`}>
                        {delta >= 0 ? '+' : ''}{delta.toFixed(3)}
                    </span>
                </div>
                <div className="relative h-2 bg-muted rounded-full overflow-hidden">
                    <div 
                        className={`absolute h-full ${delta >= 0 ? 'bg-green-500' : 'bg-red-500'}`}
                        style={{ 
                            width: `${normalizeForProgress(delta, 1)}%`,
                            left: delta >= 0 ? '50%' : `${50 - normalizeForProgress(delta, 1)}%`,
                        }}
                    />
                    <div className="absolute left-1/2 top-0 bottom-0 w-px bg-border" />
                </div>
                <p className="text-xs text-muted-foreground">
                    {delta > 0 ? 'Long' : 'Short'} bias: {Math.abs(delta * 100).toFixed(0)}%
                </p>
            </div>

            {/* Gamma */}
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-muted-foreground">Gamma (Γ)</span>
                    <span className={`text-sm font-bold ${getGreekColor(gamma, 'gamma')}`}>
                        {gamma.toFixed(4)}
                    </span>
                </div>
                <Progress 
                    value={normalizeForProgress(gamma, 0.1)} 
                    className="h-2"
                />
                <p className="text-xs text-muted-foreground">
                    Delta sensitivity: {gamma > 0.01 ? 'High' : 'Low'}
                </p>
            </div>

            {/* Theta */}
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-muted-foreground">Theta (Θ)</span>
                    <span className={`text-sm font-bold ${getGreekColor(theta, 'theta')}`}>
                        {theta >= 0 ? '+' : ''}₹{theta.toFixed(2)}/day
                    </span>
                </div>
                <Progress 
                    value={normalizeForProgress(theta, 1000)} 
                    className="h-2"
                />
                <p className="text-xs text-muted-foreground">
                    Time decay: {theta < 0 ? 'Paying' : 'Earning'}
                </p>
            </div>

            {/* Vega */}
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-muted-foreground">Vega (ν)</span>
                    <span className={`text-sm font-bold ${getGreekColor(vega, 'vega')}`}>
                        ₹{vega.toFixed(2)}/1%
                    </span>
                </div>
                <Progress 
                    value={normalizeForProgress(vega, 500)} 
                    className="h-2"
                />
                <p className="text-xs text-muted-foreground">
                    Vol exposure: {vega > 0 ? 'Long' : 'Short'} volatility
                </p>
            </div>
        </div>
    );
}

interface PortfolioGreeksProps {
    netDelta: number;
    netGamma: number;
    netTheta: number;
    netVega: number;
}

export function PortfolioGreeksSummary({ netDelta, netGamma, netTheta, netVega }: PortfolioGreeksProps) {
    return (
        <Card className="glass rounded-2xl overflow-hidden">
            <CardHeader className="bg-gradient-to-r from-indigo-500/10 to-cyan-500/10">
                <CardTitle className="text-lg font-bold flex items-center gap-2">
                    <Gauge className="h-5 w-5" />
                    Portfolio Greeks
                </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
                <div className="grid grid-cols-4 gap-4">
                    {/* Net Delta */}
                    <div className="text-center p-3 rounded-lg bg-muted/30">
                        <div className="flex items-center justify-center gap-1 mb-1">
                            {netDelta >= 0 ? (
                                <TrendingUp className="h-4 w-4 text-green-500" />
                            ) : (
                                <TrendingDown className="h-4 w-4 text-red-500" />
                            )}
                            <span className="text-xs text-muted-foreground">Net Δ</span>
                        </div>
                        <div className={`text-2xl font-bold ${netDelta >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                            {netDelta >= 0 ? '+' : ''}{netDelta.toFixed(2)}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                            {Math.abs(netDelta) < 0.1 ? 'Delta Neutral' : 
                             netDelta > 0 ? 'Bullish' : 'Bearish'}
                        </p>
                    </div>

                    {/* Net Gamma */}
                    <div className="text-center p-3 rounded-lg bg-muted/30">
                        <div className="flex items-center justify-center gap-1 mb-1">
                            <Activity className="h-4 w-4 text-purple-500" />
                            <span className="text-xs text-muted-foreground">Net Γ</span>
                        </div>
                        <div className="text-2xl font-bold text-purple-500">
                            {netGamma.toFixed(3)}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                            {netGamma > 0 ? 'Long Gamma' : 'Short Gamma'}
                        </p>
                    </div>

                    {/* Net Theta */}
                    <div className="text-center p-3 rounded-lg bg-muted/30">
                        <div className="flex items-center justify-center gap-1 mb-1">
                            <span className="text-xs text-muted-foreground">Net Θ</span>
                        </div>
                        <div className={`text-2xl font-bold ${netTheta >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                            ₹{netTheta >= 0 ? '+' : ''}{netTheta.toFixed(0)}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                            {netTheta >= 0 ? 'Collecting' : 'Paying'}/day
                        </p>
                    </div>

                    {/* Net Vega */}
                    <div className="text-center p-3 rounded-lg bg-muted/30">
                        <div className="flex items-center justify-center gap-1 mb-1">
                            <span className="text-xs text-muted-foreground">Net ν</span>
                        </div>
                        <div className={`text-2xl font-bold ${netVega >= 0 ? 'text-blue-500' : 'text-orange-500'}`}>
                            ₹{netVega >= 0 ? '+' : ''}{netVega.toFixed(0)}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                            {netVega >= 0 ? 'Long Vol' : 'Short Vol'}
                        </p>
                    </div>
                </div>

                {/* Risk Summary */}
                <div className="mt-4 p-3 rounded-lg bg-muted/20 border border-border/50">
                    <h4 className="text-sm font-medium mb-2">Risk Profile</h4>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                            <span className="text-muted-foreground">Direction:</span>{' '}
                            <span className={netDelta > 0.5 ? 'text-green-500' : netDelta < -0.5 ? 'text-red-500' : 'text-yellow-500'}>
                                {Math.abs(netDelta) < 0.1 ? 'Neutral' : 
                                 netDelta > 0 ? `Bullish (${(netDelta * 100).toFixed(0)}%)` : 
                                 `Bearish (${(Math.abs(netDelta) * 100).toFixed(0)}%)`}
                            </span>
                        </div>
                        <div>
                            <span className="text-muted-foreground">Gamma Risk:</span>{' '}
                            <span className={netGamma > 0 ? 'text-green-500' : 'text-red-500'}>
                                {netGamma > 0 ? 'Protected' : 'Exposed'}
                            </span>
                        </div>
                        <div>
                            <span className="text-muted-foreground">Time Decay:</span>{' '}
                            <span className={netTheta > 0 ? 'text-green-500' : 'text-red-500'}>
                                {netTheta > 0 ? 'Favorable' : `₹${Math.abs(netTheta).toFixed(0)}/day`}
                            </span>
                        </div>
                        <div>
                            <span className="text-muted-foreground">Vol Exposure:</span>{' '}
                            <span className={netVega > 0 ? 'text-blue-500' : 'text-orange-500'}>
                                {netVega > 0 ? 'Long Vol' : 'Short Vol'}
                            </span>
                        </div>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
