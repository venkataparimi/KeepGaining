"use client";

import { useState, useEffect } from "react";
import { TrendingUp, TrendingDown, Activity } from "lucide-react";
import { apiClient } from "@/lib/api/client";

interface IndexData {
    symbol: string;
    name: string;
    ltp: number;
    change: number;
    changePercent: number;
    high: number;
    low: number;
}

export function MarketPulse() {
    const [indices, setIndices] = useState<IndexData[]>([
        { symbol: "NIFTY", name: "NIFTY 50", ltp: 0, change: 0, changePercent: 0, high: 0, low: 0 },
        { symbol: "BANKNIFTY", name: "BANK NIFTY", ltp: 0, change: 0, changePercent: 0, high: 0, low: 0 },
        { symbol: "INDIAVIX", name: "INDIA VIX", ltp: 0, change: 0, changePercent: 0, high: 0, low: 0 },
        { symbol: "FINNIFTY", name: "FIN NIFTY", ltp: 0, change: 0, changePercent: 0, high: 0, low: 0 },
    ]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchIndices = async () => {
            try {
                const data = await apiClient.getMarketOverview().catch(() => null);
                if (data) {
                    // Map the API response to our index format
                    setIndices(prev => prev.map(idx => {
                        // Try indices array first (old format), then direct keys (new format)
                        let found = null;
                        if (data.indices) {
                            found = data.indices.find((d: any) => d.symbol?.includes(idx.symbol));
                        } else {
                            // Map our symbol names to API keys
                            const keyMap: Record<string, string> = {
                                "NIFTY": "nifty",
                                "BANKNIFTY": "banknifty",
                                "INDIAVIX": "vix",
                                "FINNIFTY": "finnifty",
                            };
                            const key = keyMap[idx.symbol];
                            if (key && data[key]) {
                                found = data[key];
                            }
                        }
                        if (found) {
                            return {
                                ...idx,
                                ltp: found.ltp || found.last_price || 0,
                                change: found.change || 0,
                                changePercent: found.change_percent || found.pChange || 0,
                                high: found.high || 0,
                                low: found.low || 0,
                            };
                        }
                        return idx;
                    }));
                }
            } catch (error) {
                console.error("Failed to fetch market overview:", error);
            } finally {
                setLoading(false);
            }
        };

        fetchIndices();
        const interval = setInterval(fetchIndices, 5000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="glass rounded-xl p-4 overflow-hidden">
            <div className="flex items-center gap-2 mb-3">
                <Activity className="h-4 w-4 text-primary animate-pulse" />
                <span className="text-sm font-medium text-muted-foreground">Market Pulse</span>
                <div className="ml-auto flex items-center gap-1">
                    <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
                    <span className="text-xs text-muted-foreground">Live</span>
                </div>
            </div>
            
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                {indices.map((index) => {
                    const isPositive = index.changePercent >= 0;
                    const isVix = index.symbol === "INDIAVIX";
                    
                    return (
                        <div
                            key={index.symbol}
                            className={`p-3 rounded-lg border transition-all duration-300 hover:scale-[1.02] ${
                                isVix 
                                    ? 'bg-gradient-to-br from-purple-500/10 to-pink-500/10 border-purple-500/20'
                                    : isPositive 
                                        ? 'bg-gradient-to-br from-green-500/10 to-emerald-500/10 border-green-500/20' 
                                        : 'bg-gradient-to-br from-red-500/10 to-rose-500/10 border-red-500/20'
                            }`}
                        >
                            <div className="flex items-center justify-between mb-1">
                                <span className="text-xs font-medium text-muted-foreground">{index.name}</span>
                                {isPositive ? (
                                    <TrendingUp className={`h-3 w-3 ${isVix ? 'text-purple-400' : 'text-green-400'}`} />
                                ) : (
                                    <TrendingDown className={`h-3 w-3 ${isVix ? 'text-purple-400' : 'text-red-400'}`} />
                                )}
                            </div>
                            <div className="flex items-baseline gap-2">
                                <span className="text-lg font-bold">
                                    {loading ? '--' : index.ltp.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                                </span>
                            </div>
                            <div className={`text-xs font-medium ${
                                isVix ? 'text-purple-400' : isPositive ? 'text-green-400' : 'text-red-400'
                            }`}>
                                {isPositive ? '+' : ''}{index.changePercent.toFixed(2)}%
                                <span className="text-muted-foreground ml-1">
                                    ({isPositive ? '+' : ''}{index.change.toFixed(2)})
                                </span>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
