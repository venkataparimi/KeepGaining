"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { 
    ArrowUpRight, ArrowDownRight, Activity, DollarSign, 
    BarChart3, TrendingUp, RefreshCw, Wallet, Target,
    Clock
} from "lucide-react";
import { apiClient } from "@/lib/api/client";
import { MarketPulse } from "./market-pulse";
import { PositionCards } from "./position-cards";
import { QuickActions } from "./quick-actions";
import { VixGauge } from "./vix-gauge";
import { NotificationCenter } from "./notification-center";
import { TradingControls } from "./trading-controls";

interface Position {
    symbol: string;
    tradingsymbol?: string;
    qty: number;
    avg: number;
    ltp: number;
    pnl: number;
    delta?: number;
    theta?: number;
    productType?: string;
}

interface BrokerStatus {
    connected: boolean;
    broker_name: string;
    message: string;
}

interface Notification {
    id: string;
    type: 'success' | 'warning' | 'error' | 'info';
    title: string;
    message: string;
    timestamp: Date;
    read: boolean;
}

export function DashboardOverviewV2() {
    const [positions, setPositions] = useState<Position[]>([]);
    const [brokerStatus, setBrokerStatus] = useState<BrokerStatus | null>(null);
    const [funds, setFunds] = useState<any>(null);
    const [vixValue, setVixValue] = useState(0);
    const [loading, setLoading] = useState(true);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
    const [isPaused, setIsPaused] = useState(false);
    const [mounted, setMounted] = useState(false);
    const [notifications, setNotifications] = useState<Notification[]>([]);
    const [todayActivity, setTodayActivity] = useState({
        orders_placed: 0,
        orders_executed: 0,
        orders_rejected: 0,
        orders_pending: 0,
        orders_cancelled: 0,
        strategies_running: 0
    });
    
    // Fix hydration mismatch - only render time on client
    useEffect(() => {
        setMounted(true);
        setLastUpdated(new Date());
        // Initialize sample notifications after mount
        setNotifications([
            {
                id: '1',
                type: 'success',
                title: 'Order Executed',
                message: 'NIFTY 24500 CE bought at ₹125.50',
                timestamp: new Date(),
                read: false
            },
            {
                id: '2', 
                type: 'warning',
                title: 'Margin Warning',
                message: 'Available margin below 20%',
                timestamp: new Date(Date.now() - 300000),
                read: true
            }
        ]);
    }, []);

    const fetchPositions = useCallback(async () => {
        try {
            const posData = await apiClient.getPositions().catch(() => []);
            // Map API response fields to frontend expected format
            const mappedPositions = (posData || []).map((p: any) => ({
                symbol: p.symbol || '',
                tradingsymbol: p.tradingsymbol || p.symbol || '',
                qty: p.qty ?? p.quantity ?? 0,
                avg: p.avg ?? p.average_price ?? 0,
                ltp: p.ltp ?? p.last_price ?? 0,
                pnl: p.pnl ?? 0,
                pnlPercent: p.pnlPercent ?? p.pnl_percent ?? 0,
                delta: p.delta,
                theta: p.theta,
                productType: p.productType ?? p.product_type ?? 'INTRADAY'
            }));
            setPositions(mappedPositions);
            setLastUpdated(new Date());
        } catch (error) {
            console.error("Failed to fetch positions:", error);
        }
    }, []);

    const fetchStaticData = useCallback(async () => {
        try {
            const [statusData, fundsData, marketData, activityData] = await Promise.all([
                apiClient.getBrokerStatus().catch(() => null),
                apiClient.getFunds().catch(() => null),
                apiClient.getMarketOverview().catch(() => null),
                apiClient.getTodayActivity().catch(() => null),
            ]);
            setBrokerStatus(statusData);
            setFunds(fundsData);
            
            // Update today's activity
            if (activityData) {
                setTodayActivity({
                    orders_placed: activityData.orders_placed || 0,
                    orders_executed: activityData.orders_executed || 0,
                    orders_rejected: activityData.orders_rejected || 0,
                    orders_pending: activityData.orders_pending || 0,
                    orders_cancelled: activityData.orders_cancelled || 0,
                    strategies_running: activityData.strategies_running || 0
                });
            }
            
            // Extract VIX from market data
            if (marketData?.indices) {
                const vix = marketData.indices.find((i: any) => 
                    i.symbol?.includes('VIX') || i.tradingsymbol?.includes('VIX')
                );
                if (vix) {
                    setVixValue(vix.ltp || vix.last_price || 0);
                }
            }
        } catch (error) {
            console.error("Failed to fetch static data:", error);
        }
    }, []);

    useEffect(() => {
        const initialFetch = async () => {
            setLoading(true);
            await Promise.all([fetchPositions(), fetchStaticData()]);
            setLoading(false);
        };

        initialFetch();
        const positionsInterval = setInterval(fetchPositions, 10000);
        const staticInterval = setInterval(fetchStaticData, 30000);

        return () => {
            clearInterval(positionsInterval);
            clearInterval(staticInterval);
        };
    }, [fetchPositions, fetchStaticData]);

    const totalPnL = positions.reduce((sum, pos) => sum + (pos.pnl || 0), 0);
    const profitableCount = positions.filter(p => (p.pnl || 0) > 0).length;
    const lossCount = positions.filter(p => (p.pnl || 0) < 0).length;
    const winRate = positions.length > 0 ? (profitableCount / positions.length) * 100 : 0;

    const handleSquareOffAll = () => {
        if (confirm('Are you sure you want to square off all positions?')) {
            // Implement square off logic
            console.log('Square off all');
        }
    };

    const handlePauseTrading = () => {
        setIsPaused(!isPaused);
    };

    const handleEmergencyExit = () => {
        if (confirm('⚠️ EMERGENCY EXIT: This will close all positions and cancel all orders. Continue?')) {
            // Implement emergency exit
            console.log('Emergency exit');
        }
    };

    const dismissNotification = (id: string) => {
        setNotifications(prev => prev.filter(n => n.id !== id));
    };

    return (
        <div className="flex-1 space-y-6 p-6 pt-4 max-w-[1800px] mx-auto">
            {/* Hero Header with P&L Ticker */}
            <div className="relative overflow-hidden rounded-2xl glass p-6 animated-border">
                <div className="absolute inset-0 gradient-bg opacity-30"></div>
                <div className="relative z-10">
                    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                        <div className="flex items-center gap-6">
                            <div>
                                <h1 className="text-4xl font-bold gradient-text mb-1">KeepGaining</h1>
                                <div className="flex items-center gap-3">
                                    {brokerStatus?.connected ? (
                                        <span className="flex items-center text-green-400 text-sm">
                                            <span className="w-2 h-2 bg-green-400 rounded-full mr-2 animate-pulse"></span>
                                            {brokerStatus.broker_name} Connected
                                        </span>
                                    ) : (
                                        <span className="flex items-center text-red-400 text-sm">
                                            <span className="w-2 h-2 bg-red-400 rounded-full mr-2"></span>
                                            Disconnected
                                        </span>
                                    )}
                                    <span className="text-muted-foreground text-sm flex items-center">
                                        <Clock className="h-3 w-3 mr-1" />
                                        {mounted && lastUpdated ? lastUpdated.toLocaleTimeString() : '--:--:--'}
                                    </span>
                                </div>
                            </div>
                            
                            {/* Large P&L Display */}
                            <div className={`px-6 py-3 rounded-xl ${
                                totalPnL >= 0 
                                    ? 'bg-green-500/20 border border-green-500/30' 
                                    : 'bg-red-500/20 border border-red-500/30'
                            }`}>
                                <p className="text-xs text-muted-foreground mb-1">Today's P&L</p>
                                <div className={`text-3xl font-bold flex items-center ${
                                    totalPnL >= 0 ? 'text-green-400' : 'text-red-400'
                                }`}>
                                    {totalPnL >= 0 ? (
                                        <ArrowUpRight className="h-6 w-6 mr-1" />
                                    ) : (
                                        <ArrowDownRight className="h-6 w-6 mr-1" />
                                    )}
                                    {totalPnL >= 0 ? '+' : ''}₹{Math.abs(totalPnL).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                                </div>
                            </div>
                        </div>

                        <div className="flex items-center gap-3">
                            <QuickActions
                                onSquareOffAll={handleSquareOffAll}
                                onPauseTrading={handlePauseTrading}
                                onEmergencyExit={handleEmergencyExit}
                                hasPositions={positions.length > 0}
                                isPaused={isPaused}
                            />
                            <NotificationCenter
                                notifications={notifications}
                                onDismiss={dismissNotification}
                                onClearAll={() => setNotifications([])}
                            />
                            <Button
                                onClick={async () => {
                                    setLoading(true);
                                    await Promise.all([fetchPositions(), fetchStaticData()]);
                                    setLoading(false);
                                }}
                                variant="outline"
                                className="border-primary/30 hover:bg-primary/10"
                                disabled={loading}
                            >
                                <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                                Refresh
                            </Button>
                        </div>
                    </div>
                </div>
            </div>

            {/* Market Pulse Strip */}
            <MarketPulse />

            {/* Stats Grid */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <div className="glass rounded-xl overflow-hidden hover-lift group">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 bg-gradient-to-br from-blue-500/10 to-cyan-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Active Positions</CardTitle>
                        <div className="p-2 rounded-lg bg-blue-500/20">
                            <Activity className="h-5 w-5 text-blue-400" />
                        </div>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="text-3xl font-bold">{positions.length}</div>
                        <p className="text-xs text-muted-foreground mt-1">
                            <span className="text-green-400">{profitableCount} ↑</span>
                            {' · '}
                            <span className="text-red-400">{lossCount} ↓</span>
                        </p>
                    </CardContent>
                </div>

                <div className="glass rounded-xl overflow-hidden hover-lift group">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 bg-gradient-to-br from-purple-500/10 to-pink-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Win Rate</CardTitle>
                        <div className="p-2 rounded-lg bg-purple-500/20">
                            <BarChart3 className="h-5 w-5 text-purple-400" />
                        </div>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="text-3xl font-bold gradient-text">{winRate.toFixed(1)}%</div>
                        <div className="mt-2 h-2 bg-muted rounded-full overflow-hidden">
                            <div 
                                className="h-full bg-gradient-to-r from-purple-400 to-pink-400 rounded-full transition-all duration-500"
                                style={{ width: `${winRate}%` }}
                            />
                        </div>
                    </CardContent>
                </div>

                <div className="glass rounded-xl overflow-hidden hover-lift group">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 bg-gradient-to-br from-orange-500/10 to-amber-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Available Margin</CardTitle>
                        <div className="p-2 rounded-lg bg-orange-500/20">
                            <Wallet className="h-5 w-5 text-orange-400" />
                        </div>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="text-3xl font-bold">
                            ₹{funds?.equityAmount ? (funds.equityAmount / 1000).toFixed(1) + 'K' : '--'}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                            {funds?.usedAmount ? `Used: ₹${(funds.usedAmount / 1000).toFixed(1)}K` : 'Equity segment'}
                        </p>
                    </CardContent>
                </div>

                <div className="glass rounded-xl overflow-hidden hover-lift group">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 bg-gradient-to-br from-green-500/10 to-emerald-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Net Exposure</CardTitle>
                        <div className="p-2 rounded-lg bg-green-500/20">
                            <Target className="h-5 w-5 text-green-400" />
                        </div>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="text-3xl font-bold">
                            {positions.reduce((sum, p) => sum + Math.abs(p.qty * p.ltp), 0).toLocaleString('en-IN', {
                                style: 'currency',
                                currency: 'INR',
                                maximumFractionDigits: 0
                            })}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                            Across {positions.length} position{positions.length !== 1 ? 's' : ''}
                        </p>
                    </CardContent>
                </div>
            </div>

            {/* Main Content Grid */}
            <div className="grid gap-6 lg:grid-cols-12">
                {/* Positions Section */}
                <div className="lg:col-span-8">
                    <div className="glass rounded-xl overflow-hidden">
                        <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10 py-4">
                            <div className="flex items-center justify-between">
                                <CardTitle className="text-xl font-bold">Active Positions</CardTitle>
                                <span className="text-sm text-muted-foreground">
                                    {positions.length} position{positions.length !== 1 ? 's' : ''}
                                </span>
                            </div>
                        </CardHeader>
                        <CardContent className="p-4">
                            {loading && positions.length === 0 ? (
                                <div className="p-8 text-center text-muted-foreground">
                                    <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-2" />
                                    Loading positions...
                                </div>
                            ) : (
                                <PositionCards 
                                    positions={positions}
                                    onSquareOff={(symbol) => console.log('Square off', symbol)}
                                    onSetSL={(symbol, price) => console.log('Set SL', symbol, price)}
                                />
                            )}
                        </CardContent>
                    </div>
                </div>

                {/* Sidebar */}
                <div className="lg:col-span-4 space-y-4">
                    {/* Trading Controls */}
                    <TradingControls />

                    {/* VIX Gauge */}
                    <VixGauge value={vixValue || 14.5} />

                    {/* System Status */}
                    <div className="glass rounded-xl p-4">
                        <h3 className="font-semibold mb-3 flex items-center gap-2">
                            <Activity className="h-4 w-4 text-primary" />
                            System Status
                        </h3>
                        <div className="space-y-3">
                            <div className="flex items-center justify-between p-2 rounded-lg bg-green-500/10">
                                <span className="text-sm">Broker API</span>
                                <span className="text-xs px-2 py-1 rounded-full bg-green-500/20 text-green-400">
                                    {brokerStatus?.connected ? 'Connected' : 'Disconnected'}
                                </span>
                            </div>
                            <div className="flex items-center justify-between p-2 rounded-lg bg-blue-500/10">
                                <span className="text-sm">Trading Mode</span>
                                <span className={`text-xs px-2 py-1 rounded-full ${
                                    isPaused 
                                        ? 'bg-yellow-500/20 text-yellow-400' 
                                        : 'bg-green-500/20 text-green-400'
                                }`}>
                                    {isPaused ? 'Paused' : 'Active'}
                                </span>
                            </div>
                            <div className="flex items-center justify-between p-2 rounded-lg bg-purple-500/10">
                                <span className="text-sm">Data Feed</span>
                                <span className="text-xs px-2 py-1 rounded-full bg-green-500/20 text-green-400">
                                    Live
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* Quick Stats */}
                    <div className="glass rounded-xl p-4">
                        <h3 className="font-semibold mb-3">Today's Activity</h3>
                        <div className="space-y-2 text-sm">
                            <div className="flex justify-between">
                                <span className="text-muted-foreground">Orders Placed</span>
                                <span className="font-medium">{todayActivity.orders_placed}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-muted-foreground">Orders Executed</span>
                                <span className="font-medium text-green-400">{todayActivity.orders_executed}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-muted-foreground">Orders Rejected</span>
                                <span className="font-medium text-red-400">{todayActivity.orders_rejected}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-muted-foreground">Orders Pending</span>
                                <span className="font-medium text-yellow-400">{todayActivity.orders_pending}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-muted-foreground">Strategies Running</span>
                                <span className="font-medium text-blue-400">{todayActivity.strategies_running}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
