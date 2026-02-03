"use client";

import { useState, useEffect, useCallback } from "react";
import { 
    X, TrendingUp, TrendingDown, Shield, Target, Clock, 
    AlertTriangle, Activity, BarChart3, Zap, Info,
    ChevronDown, ChevronUp, Settings
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient, TradeAnalyticsDetail, SetStopLossRequest } from "@/lib/api/client";

interface TradeDetailPanelProps {
    symbol: string;
    onClose: () => void;
}

export function TradeDetailPanel({ symbol, onClose }: TradeDetailPanelProps) {
    const [trade, setTrade] = useState<TradeAnalyticsDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showSLForm, setShowSLForm] = useState(false);
    const [showTargetForm, setShowTargetForm] = useState(false);
    const [slPrice, setSlPrice] = useState("");
    const [targetPrice, setTargetPrice] = useState("");

    // Handle escape key press
    const handleKeyDown = useCallback((e: KeyboardEvent) => {
        if (e.key === "Escape") {
            onClose();
        }
    }, [onClose]);

    useEffect(() => {
        // Add escape key listener
        document.addEventListener("keydown", handleKeyDown);
        // Prevent body scroll when modal is open
        document.body.style.overflow = "hidden";
        
        return () => {
            document.removeEventListener("keydown", handleKeyDown);
            document.body.style.overflow = "unset";
        };
    }, [handleKeyDown]);

    useEffect(() => {
        fetchTradeDetails();
        const interval = setInterval(fetchTradeDetails, 5000); // Refresh every 5s
        return () => clearInterval(interval);
    }, [symbol]);

    const fetchTradeDetails = async () => {
        try {
            const data = await apiClient.getTradeAnalyticsBySymbol(symbol);
            setTrade(data);
            setError(null);
        } catch (err: any) {
            setError(err.message || "Failed to fetch trade details");
        } finally {
            setLoading(false);
        }
    };

    const handleSetSL = async () => {
        if (!slPrice) return;
        try {
            await apiClient.setTradeStopLoss(symbol, {
                sl_type: "FIXED",
                sl_price: parseFloat(slPrice)
            });
            setShowSLForm(false);
            fetchTradeDetails();
        } catch (err) {
            console.error("Failed to set SL:", err);
        }
    };

    const handleSetTarget = async () => {
        if (!targetPrice) return;
        try {
            await apiClient.setTradeTarget(symbol, {
                target_price: parseFloat(targetPrice)
            });
            setShowTargetForm(false);
            fetchTradeDetails();
        } catch (err) {
            console.error("Failed to set target:", err);
        }
    };

    const handleApplyRecommendedSL = async () => {
        if (!trade?.sl_recommendation) return;
        try {
            await apiClient.setTradeStopLoss(symbol, {
                sl_type: trade.sl_recommendation.recommended_sl_type as any,
                sl_price: trade.sl_recommendation.recommended_sl
            });
            fetchTradeDetails();
        } catch (err) {
            console.error("Failed to apply recommended SL:", err);
        }
    };

    if (loading) {
        return (
            <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
                <div className="glass rounded-2xl p-8">
                    <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto" />
                    <p className="mt-4 text-muted-foreground">Loading trade details...</p>
                </div>
            </div>
        );
    }

    if (error || !trade) {
        return (
            <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
                <div className="glass rounded-2xl p-8 max-w-md">
                    <AlertTriangle className="h-12 w-12 text-red-400 mx-auto mb-4" />
                    <p className="text-center text-red-400">{error || "Trade not found"}</p>
                    <Button onClick={onClose} className="mt-4 w-full">Close</Button>
                </div>
            </div>
        );
    }

    const isProfit = trade.current_state.unrealized_pnl >= 0;
    const ctx = trade.entry_context;
    const sl = trade.stop_loss;
    const state = trade.current_state;
    const rec = trade.sl_recommendation;

    // Handle backdrop click to close
    const handleBackdropClick = (e: React.MouseEvent) => {
        if (e.target === e.currentTarget) {
            onClose();
        }
    };

    return (
        <div 
            className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
            onClick={handleBackdropClick}
        >
            <div className="glass rounded-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto scrollbar-thin scrollbar-track-transparent scrollbar-thumb-border/50 hover:scrollbar-thumb-border/80">
                {/* Header */}
                <div className="sticky top-0 bg-background/95 backdrop-blur border-b border-border/50 p-4 flex items-center justify-between z-10">
                    <div>
                        <h2 className="text-xl font-bold">{trade.tradingsymbol}</h2>
                        <div className="flex items-center gap-2 mt-1">
                            <span className={`text-xs px-2 py-0.5 rounded-full ${
                                trade.direction === 'LONG' 
                                    ? 'bg-green-500/20 text-green-400' 
                                    : 'bg-red-500/20 text-red-400'
                            }`}>
                                {trade.direction}
                            </span>
                            <span className="text-xs text-muted-foreground">
                                {trade.quantity} qty @ ₹{trade.entry_price.toFixed(2)}
                            </span>
                            <span className="text-xs text-muted-foreground">
                                • {trade.underlying}
                            </span>
                        </div>
                    </div>
                    <Button 
                        variant="ghost" 
                        size="icon" 
                        onClick={onClose}
                        className="hover:bg-red-500/20 hover:text-red-400 transition-colors"
                        title="Close (Esc)"
                    >
                        <X className="h-5 w-5" />
                    </Button>
                </div>

                <div className="p-4 space-y-4">
                    {/* P&L Card */}
                    <div className={`rounded-xl p-4 ${
                        isProfit ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'
                    }`}>
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">Unrealized P&L</p>
                                <div className={`text-3xl font-bold flex items-center ${
                                    isProfit ? 'text-green-400' : 'text-red-400'
                                }`}>
                                    {isProfit ? <TrendingUp className="h-6 w-6 mr-2" /> : <TrendingDown className="h-6 w-6 mr-2" />}
                                    {isProfit ? '+' : ''}₹{state.unrealized_pnl.toFixed(2)}
                                </div>
                                <p className={`text-sm ${isProfit ? 'text-green-400/80' : 'text-red-400/80'}`}>
                                    {isProfit ? '+' : ''}{state.unrealized_pnl_percent.toFixed(2)}%
                                </p>
                            </div>
                            <div className="text-right">
                                <p className="text-sm text-muted-foreground">Current LTP</p>
                                <p className="text-2xl font-bold">₹{state.current_ltp.toFixed(2)}</p>
                                <p className="text-xs text-muted-foreground">
                                    Entry: ₹{trade.entry_price.toFixed(2)}
                                </p>
                            </div>
                        </div>
                        
                        {/* MFE/MAE */}
                        <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-border/30">
                            <div>
                                <p className="text-xs text-muted-foreground">Max Profit Seen</p>
                                <p className="text-lg font-semibold text-green-400">
                                    +₹{state.max_profit_seen.toFixed(2)}
                                </p>
                            </div>
                            <div>
                                <p className="text-xs text-muted-foreground">Max Drawdown</p>
                                <p className="text-lg font-semibold text-red-400">
                                    -₹{Math.abs(state.max_drawdown_seen).toFixed(2)}
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Two Column Layout */}
                    <div className="grid md:grid-cols-2 gap-4">
                        {/* Entry Context */}
                        <div className="glass rounded-xl p-4">
                            <h3 className="font-semibold mb-3 flex items-center">
                                <Clock className="h-4 w-4 mr-2 text-blue-400" />
                                Entry Context
                            </h3>
                            <div className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                    <span className="text-muted-foreground">Spot at Entry</span>
                                    <span className="font-medium">₹{ctx.spot_price.toFixed(2)}</span>
                                </div>
                                {ctx.strike_price && (
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Strike</span>
                                        <span className="font-medium">{ctx.strike_price} {ctx.option_type}</span>
                                    </div>
                                )}
                                {ctx.moneyness && (
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Moneyness</span>
                                        <span className={`font-medium ${
                                            ctx.moneyness === 'ITM' ? 'text-green-400' :
                                            ctx.moneyness === 'ATM' ? 'text-yellow-400' : 'text-red-400'
                                        }`}>{ctx.moneyness}</span>
                                    </div>
                                )}
                                {ctx.iv_at_entry && (
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">IV at Entry</span>
                                        <span className="font-medium">{ctx.iv_at_entry.toFixed(2)}%</span>
                                    </div>
                                )}
                                {ctx.delta_at_entry && (
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Delta at Entry</span>
                                        <span className="font-medium">{ctx.delta_at_entry.toFixed(3)}</span>
                                    </div>
                                )}
                                {ctx.vix_at_entry && (
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">VIX at Entry</span>
                                        <span className="font-medium">{ctx.vix_at_entry.toFixed(2)}</span>
                                    </div>
                                )}
                                {ctx.days_to_expiry && (
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Days to Expiry</span>
                                        <span className="font-medium">{ctx.days_to_expiry}</span>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Current Greeks */}
                        <div className="glass rounded-xl p-4">
                            <h3 className="font-semibold mb-3 flex items-center">
                                <Activity className="h-4 w-4 mr-2 text-purple-400" />
                                Current State
                            </h3>
                            <div className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                    <span className="text-muted-foreground">Current Spot</span>
                                    <span className="font-medium">₹{state.current_spot_price.toFixed(2)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-muted-foreground">Spot Change</span>
                                    <span className={`font-medium ${state.spot_change_since_entry >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                        {state.spot_change_since_entry >= 0 ? '+' : ''}{state.spot_change_since_entry.toFixed(2)}%
                                    </span>
                                </div>
                                {state.current_iv && (
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Current IV</span>
                                        <span className="font-medium">{state.current_iv.toFixed(2)}%</span>
                                    </div>
                                )}
                                {state.iv_change !== null && (
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">IV Change</span>
                                        <span className={`font-medium ${state.iv_change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            {state.iv_change >= 0 ? '+' : ''}{state.iv_change.toFixed(2)}%
                                        </span>
                                    </div>
                                )}
                                {state.current_delta && (
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Current Delta</span>
                                        <span className="font-medium">{state.current_delta.toFixed(3)}</span>
                                    </div>
                                )}
                                {state.current_theta && (
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Theta Decay/Day</span>
                                        <span className="font-medium text-red-400">₹{Math.abs(state.current_theta).toFixed(2)}</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Stop Loss Section */}
                    <div className="glass rounded-xl p-4">
                        <div className="flex items-center justify-between mb-3">
                            <h3 className="font-semibold flex items-center">
                                <Shield className="h-4 w-4 mr-2 text-orange-400" />
                                Stop Loss
                            </h3>
                            <Button 
                                variant="outline" 
                                size="sm"
                                onClick={() => setShowSLForm(!showSLForm)}
                            >
                                <Settings className="h-4 w-4 mr-1" />
                                {sl.current_sl_price ? 'Modify' : 'Set'} SL
                            </Button>
                        </div>

                        {/* Current SL Status */}
                        <div className="grid md:grid-cols-3 gap-4 mb-4">
                            <div className="p-3 rounded-lg bg-background/50">
                                <p className="text-xs text-muted-foreground">SL Type</p>
                                <p className="font-semibold">{sl.sl_type}</p>
                            </div>
                            <div className="p-3 rounded-lg bg-background/50">
                                <p className="text-xs text-muted-foreground">Current SL</p>
                                <p className="font-semibold text-orange-400">
                                    {sl.current_sl_price ? `₹${sl.current_sl_price.toFixed(2)}` : 'Not Set'}
                                </p>
                            </div>
                            <div className="p-3 rounded-lg bg-background/50">
                                <p className="text-xs text-muted-foreground">Distance from SL</p>
                                <p className="font-semibold">
                                    {state.sl_distance_percent ? `${state.sl_distance_percent.toFixed(2)}%` : '-'}
                                </p>
                            </div>
                        </div>

                        {/* SL Form */}
                        {showSLForm && (
                            <div className="p-3 rounded-lg bg-background/50 mb-4">
                                <div className="flex gap-2">
                                    <Input
                                        type="number"
                                        placeholder="Stop Loss Price"
                                        value={slPrice}
                                        onChange={(e) => setSlPrice(e.target.value)}
                                        className="flex-1"
                                    />
                                    <Button onClick={handleSetSL}>Set SL</Button>
                                </div>
                            </div>
                        )}

                        {/* SL Recommendation */}
                        {rec && (
                            <div className="p-3 rounded-lg border border-blue-500/30 bg-blue-500/5">
                                <div className="flex items-start justify-between">
                                    <div>
                                        <p className="text-sm font-medium flex items-center">
                                            <Zap className="h-4 w-4 mr-1 text-blue-400" />
                                            Recommended SL
                                        </p>
                                        <p className="text-2xl font-bold text-blue-400">
                                            ₹{rec.recommended_sl.toFixed(2)}
                                        </p>
                                        <p className="text-xs text-muted-foreground mt-1">
                                            {rec.reasoning}
                                        </p>
                                    </div>
                                    <div className="text-right">
                                        <p className="text-xs text-muted-foreground">Risk if SL hit</p>
                                        <p className="text-lg font-semibold text-red-400">
                                            -₹{rec.sl_risk_amount.toFixed(2)}
                                        </p>
                                        <p className="text-xs text-muted-foreground">
                                            ({rec.sl_risk_percent.toFixed(1)}% of position)
                                        </p>
                                    </div>
                                </div>
                                <div className="flex gap-2 mt-3">
                                    <Button 
                                        size="sm" 
                                        className="flex-1"
                                        onClick={handleApplyRecommendedSL}
                                    >
                                        Apply Recommended SL
                                    </Button>
                                </div>
                                <div className="grid grid-cols-3 gap-2 mt-3 text-xs">
                                    <div className="text-center p-2 rounded bg-background/50">
                                        <p className="text-muted-foreground">ATR Based</p>
                                        <p className="font-medium">₹{rec.atr_based_sl.toFixed(2)}</p>
                                    </div>
                                    <div className="text-center p-2 rounded bg-background/50">
                                        <p className="text-muted-foreground">% Based</p>
                                        <p className="font-medium">₹{rec.percentage_sl.toFixed(2)}</p>
                                    </div>
                                    <div className="text-center p-2 rounded bg-background/50">
                                        <p className="text-muted-foreground">Support Based</p>
                                        <p className="font-medium">₹{rec.support_based_sl.toFixed(2)}</p>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Target Section */}
                    <div className="glass rounded-xl p-4">
                        <div className="flex items-center justify-between mb-3">
                            <h3 className="font-semibold flex items-center">
                                <Target className="h-4 w-4 mr-2 text-green-400" />
                                Target
                            </h3>
                            <Button 
                                variant="outline" 
                                size="sm"
                                onClick={() => setShowTargetForm(!showTargetForm)}
                            >
                                <Settings className="h-4 w-4 mr-1" />
                                {trade.targets.target_price ? 'Modify' : 'Set'} Target
                            </Button>
                        </div>

                        <div className="grid md:grid-cols-3 gap-4">
                            <div className="p-3 rounded-lg bg-background/50">
                                <p className="text-xs text-muted-foreground">Target Price</p>
                                <p className="font-semibold text-green-400">
                                    {trade.targets.target_price ? `₹${trade.targets.target_price.toFixed(2)}` : 'Not Set'}
                                </p>
                            </div>
                            <div className="p-3 rounded-lg bg-background/50">
                                <p className="text-xs text-muted-foreground">Distance to Target</p>
                                <p className="font-semibold">
                                    {state.target_distance_percent ? `${state.target_distance_percent.toFixed(2)}%` : '-'}
                                </p>
                            </div>
                            <div className="p-3 rounded-lg bg-background/50">
                                <p className="text-xs text-muted-foreground">Risk:Reward</p>
                                <p className="font-semibold">
                                    {trade.targets.risk_reward_ratio ? `1:${trade.targets.risk_reward_ratio.toFixed(1)}` : '-'}
                                </p>
                            </div>
                        </div>

                        {showTargetForm && (
                            <div className="p-3 rounded-lg bg-background/50 mt-4">
                                <div className="flex gap-2">
                                    <Input
                                        type="number"
                                        placeholder="Target Price"
                                        value={targetPrice}
                                        onChange={(e) => setTargetPrice(e.target.value)}
                                        className="flex-1"
                                    />
                                    <Button onClick={handleSetTarget}>Set Target</Button>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Trade Info Footer */}
                    <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t border-border/30">
                        <span>Trade ID: {trade.trade_id}</span>
                        <span>Duration: {trade.trade_duration_minutes} mins</span>
                        {trade.strategy_name && <span>Strategy: {trade.strategy_name}</span>}
                    </div>
                </div>
            </div>
        </div>
    );
}
