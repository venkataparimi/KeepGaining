"use client";

import { useState } from "react";
import { TrendingUp, TrendingDown, MoreHorizontal, Target, Shield, X, BarChart3, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TradeDetailPanel } from "./trade-detail-panel";
import { apiClient } from "@/lib/api/client";

interface Position {
    symbol: string;
    tradingsymbol?: string;
    qty: number;
    avg: number;
    ltp: number;
    pnl: number;
    pnlPercent?: number;
    delta?: number;
    theta?: number;
    productType?: string;
}

interface PositionCardsProps {
    positions: Position[];
    onSquareOff?: (symbol: string) => void;
    onSetSL?: (symbol: string, price: number) => void;
}

export function PositionCards({ positions, onSquareOff, onSetSL }: PositionCardsProps) {
    const [expandedCard, setExpandedCard] = useState<string | null>(null);
    const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
    const [slInputSymbol, setSLInputSymbol] = useState<string | null>(null);
    const [slPrice, setSLPrice] = useState<string>("");
    const [settingSL, setSettingSL] = useState(false);

    const handleSetSL = async (symbol: string) => {
        if (!slPrice || isNaN(parseFloat(slPrice))) return;
        
        setSettingSL(true);
        try {
            await apiClient.setTradeStopLoss(symbol, {
                sl_type: "FIXED",
                sl_price: parseFloat(slPrice)
            });
            // Close the SL input form on success
            setSLInputSymbol(null);
            setSLPrice("");
            // Also call parent handler if provided
            onSetSL?.(symbol, parseFloat(slPrice));
        } catch (err) {
            console.error("Failed to set SL:", err);
            alert("Failed to set stop loss. Please try again.");
        } finally {
            setSettingSL(false);
        }
    };

    if (positions.length === 0) {
        return (
            <div className="glass rounded-xl p-8 text-center">
                <div className="text-muted-foreground">
                    <Target className="h-12 w-12 mx-auto mb-3 opacity-50" />
                    <p className="text-lg font-medium">No Active Positions</p>
                    <p className="text-sm mt-1">Your positions will appear here when you have open trades</p>
                </div>
            </div>
        );
    }

    return (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {positions.map((position, idx) => {
                const isProfit = (position.pnl || 0) >= 0;
                const pnlPercent = position.avg > 0 
                    ? ((position.ltp - position.avg) / position.avg * 100 * (position.qty > 0 ? 1 : -1))
                    : 0;
                const isExpanded = expandedCard === position.symbol + idx;
                
                // Risk indicator based on P&L percentage
                const getRiskColor = () => {
                    const absPercent = Math.abs(pnlPercent);
                    if (absPercent < 1) return 'border-blue-500/30';
                    if (isProfit) return absPercent > 3 ? 'border-green-500/50' : 'border-green-500/30';
                    return absPercent > 3 ? 'border-red-500/50' : 'border-red-500/30';
                };

                return (
                    <div
                        key={position.symbol + idx}
                        className={`glass rounded-xl overflow-hidden transition-all duration-300 hover:shadow-lg border-l-4 ${getRiskColor()}`}
                    >
                        {/* Header */}
                        <div className="p-4 pb-2">
                            <div className="flex items-start justify-between">
                                <div>
                                    <h3 className="font-bold text-lg">{position.tradingsymbol || position.symbol}</h3>
                                    <div className="flex items-center gap-2 mt-1">
                                        <span className={`text-xs px-2 py-0.5 rounded-full ${
                                            position.qty > 0 
                                                ? 'bg-green-500/20 text-green-400' 
                                                : 'bg-red-500/20 text-red-400'
                                        }`}>
                                            {position.qty > 0 ? 'LONG' : 'SHORT'}
                                        </span>
                                        <span className="text-xs text-muted-foreground">
                                            {Math.abs(position.qty)} qty
                                        </span>
                                        {position.productType && (
                                            <span className="text-xs text-muted-foreground">
                                                • {position.productType}
                                            </span>
                                        )}
                                    </div>
                                </div>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => setExpandedCard(isExpanded ? null : position.symbol + idx)}
                                    className="h-8 w-8 p-0"
                                >
                                    <MoreHorizontal className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>

                        {/* P&L Section */}
                        <div className="px-4 py-3 bg-gradient-to-r from-background/50 to-transparent">
                            <div className="flex items-end justify-between">
                                <div>
                                    <p className="text-xs text-muted-foreground mb-1">Unrealized P&L</p>
                                    <div className={`text-2xl font-bold flex items-center ${
                                        isProfit ? 'text-green-400' : 'text-red-400'
                                    }`}>
                                        {isProfit ? (
                                            <TrendingUp className="h-5 w-5 mr-1" />
                                        ) : (
                                            <TrendingDown className="h-5 w-5 mr-1" />
                                        )}
                                        {isProfit ? '+' : ''}₹{(position.pnl || 0).toFixed(2)}
                                    </div>
                                    <p className={`text-sm ${isProfit ? 'text-green-400/80' : 'text-red-400/80'}`}>
                                        {isProfit ? '+' : ''}{pnlPercent.toFixed(2)}%
                                    </p>
                                </div>
                                <div className="text-right">
                                    <p className="text-xs text-muted-foreground">LTP</p>
                                    <p className="text-lg font-semibold">₹{(position.ltp || 0).toFixed(2)}</p>
                                    <p className="text-xs text-muted-foreground">Avg: ₹{(position.avg || 0).toFixed(2)}</p>
                                </div>
                            </div>
                        </div>

                        {/* Greeks Bar (if available) */}
                        {(position.delta !== undefined || position.theta !== undefined) && (
                            <div className="px-4 py-2 border-t border-border/30">
                                <div className="flex gap-4">
                                    {position.delta !== undefined && (
                                        <div className="flex-1">
                                            <div className="flex justify-between text-xs mb-1">
                                                <span className="text-muted-foreground">Delta</span>
                                                <span>{position.delta.toFixed(3)}</span>
                                            </div>
                                            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                                                <div 
                                                    className="h-full bg-blue-400 rounded-full transition-all"
                                                    style={{ width: `${Math.abs(position.delta) * 100}%` }}
                                                />
                                            </div>
                                        </div>
                                    )}
                                    {position.theta !== undefined && (
                                        <div className="flex-1">
                                            <div className="flex justify-between text-xs mb-1">
                                                <span className="text-muted-foreground">Theta</span>
                                                <span className="text-red-400">{position.theta.toFixed(2)}</span>
                                            </div>
                                            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                                                <div 
                                                    className="h-full bg-red-400 rounded-full transition-all"
                                                    style={{ width: `${Math.min(Math.abs(position.theta) / 50 * 100, 100)}%` }}
                                                />
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* Expanded Actions */}
                        {isExpanded && (
                            <div className="px-4 py-3 border-t border-border/30 bg-background/50 animate-in slide-in-from-top-2">
                                {/* SL Input Form */}
                                {slInputSymbol === position.symbol ? (
                                    <div className="flex gap-2 mb-2">
                                        <Input
                                            type="number"
                                            placeholder={`SL Price (LTP: ${position.ltp.toFixed(2)})`}
                                            value={slPrice}
                                            onChange={(e) => setSLPrice(e.target.value)}
                                            className="flex-1 h-8 text-sm"
                                            autoFocus
                                        />
                                        <Button
                                            size="sm"
                                            className="h-8 bg-yellow-500 hover:bg-yellow-600 text-black"
                                            onClick={() => handleSetSL(position.symbol)}
                                            disabled={settingSL || !slPrice}
                                        >
                                            <Check className="h-3 w-3 mr-1" />
                                            {settingSL ? "..." : "Set"}
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            className="h-8"
                                            onClick={() => { setSLInputSymbol(null); setSLPrice(""); }}
                                        >
                                            <X className="h-3 w-3" />
                                        </Button>
                                    </div>
                                ) : null}
                                
                                <div className="flex gap-2">
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="flex-1 border-blue-500/30 text-blue-400 hover:bg-blue-500/10"
                                        onClick={() => setSelectedSymbol(position.symbol)}
                                    >
                                        <BarChart3 className="h-3 w-3 mr-1" />
                                        Details
                                    </Button>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="flex-1 border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/10"
                                        onClick={() => {
                                            setSLInputSymbol(position.symbol);
                                            // Pre-fill with 2% below current price for long, 2% above for short
                                            const suggestedSL = position.qty > 0 
                                                ? position.ltp * 0.98 
                                                : position.ltp * 1.02;
                                            setSLPrice(suggestedSL.toFixed(2));
                                        }}
                                    >
                                        <Shield className="h-3 w-3 mr-1" />
                                        Set SL
                                    </Button>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="flex-1 border-red-500/30 text-red-400 hover:bg-red-500/10"
                                        onClick={() => onSquareOff?.(position.symbol)}
                                    >
                                        <X className="h-3 w-3 mr-1" />
                                        Exit
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                );
            })}

            {/* Trade Detail Panel */}
            {selectedSymbol && (
                <TradeDetailPanel 
                    symbol={selectedSymbol} 
                    onClose={() => setSelectedSymbol(null)} 
                />
            )}
        </div>
    );
}
