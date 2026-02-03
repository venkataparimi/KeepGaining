"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { ArrowUpRight, ArrowDownRight, Activity, DollarSign, BarChart3, TrendingUp, Zap, RefreshCw } from "lucide-react";
import { apiClient } from "@/lib/api/client";

interface Position {
    symbol: string;
    qty: number;
    avg: number;
    ltp: number;
    pnl: number;
    // Also accept API field names
    quantity?: number;
    average_price?: number;
    last_price?: number;
    product_type?: string;
}

interface BrokerStatus {
    connected: boolean;
    broker_name: string;
    message: string;
}

export function DashboardOverview() {
    const [positions, setPositions] = useState<Position[]>([]);
    const [brokerStatus, setBrokerStatus] = useState<BrokerStatus | null>(null);
    const [funds, setFunds] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

    // Smart refresh: positions change frequently, funds/status less so
    const fetchPositions = async () => {
        try {
            const posData = await apiClient.getPositions().catch(() => []);
            // Map API response to expected format
            const mappedPositions = (posData || []).map((p: any) => ({
                symbol: p.symbol || '',
                qty: p.qty || p.quantity || 0,
                avg: p.avg || p.average_price || 0,
                ltp: p.ltp || p.last_price || 0,
                pnl: p.pnl || 0,
            }));
            setPositions(mappedPositions);
            setLastUpdated(new Date());
        } catch (error) {
            console.error("Failed to fetch positions:", error);
        }
    };

    const fetchStaticData = async () => {
        try {
            const [statusData, fundsData] = await Promise.all([
                apiClient.getBrokerStatus().catch(() => null),
                apiClient.getFunds().catch(() => null),
            ]);
            setBrokerStatus(statusData);
            setFunds(fundsData);
        } catch (error) {
            console.error("Failed to fetch static data:", error);
        }
    };

    useEffect(() => {
        // Initial load - fetch everything
        const initialFetch = async () => {
            setLoading(true);
            await Promise.all([fetchPositions(), fetchStaticData()]);
            setLoading(false);
        };

        initialFetch();

        // Refresh positions every 10 seconds (fast-changing data)
        const positionsInterval = setInterval(fetchPositions, 10000);

        // Refresh static data every 60 seconds (slow-changing data)  
        const staticInterval = setInterval(fetchStaticData, 60000);

        return () => {
            clearInterval(positionsInterval);
            clearInterval(staticInterval);
        };
    }, []);

    const totalPnL = positions.reduce((sum, pos) => sum + (pos.pnl || 0), 0);
    const profitableCount = positions.filter(p => (p.pnl || 0) > 0).length;
    const lossCount = positions.filter(p => (p.pnl || 0) < 0).length;

    return (
        <div className="flex-1 space-y-6 p-8 pt-6 max-w-[1600px] mx-auto">
            {/* Hero Header */}
            <div className="relative overflow-hidden rounded-2xl glass p-8 animated-border">
                <div className="absolute inset-0 gradient-bg opacity-50"></div>
                <div className="relative z-10 flex items-center justify-between">
                    <div>
                        <h1 className="text-5xl font-bold gradient-text mb-2">KeepGaining</h1>
                        <p className="text-muted-foreground text-lg">
                            {brokerStatus?.connected ? (
                                <span className="text-green-400">● {brokerStatus.broker_name} Connected</span>
                            ) : (
                                <span className="text-red-400">● Disconnected</span>
                            )}
                        </p>
                    </div>
                    <div className="flex items-center space-x-3">
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

            {/* Metrics Cards */}
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
                <div className="glass rounded-2xl overflow-hidden hover-lift group">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 bg-gradient-to-br from-green-500/10 to-emerald-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Total PnL</CardTitle>
                        <div className="p-2 rounded-lg bg-green-500/20">
                            <DollarSign className="h-5 w-5 text-green-400" />
                        </div>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className={`text-3xl font-bold animate-number flex items-center ${totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            <TrendingUp className="mr-2 h-6 w-6" />
                            {totalPnL >= 0 ? '+' : ''}₹{totalPnL.toFixed(2)}
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">
                            From {positions.length} position{positions.length !== 1 ? 's' : ''}
                        </p>
                    </CardContent>
                </div>

                <div className="glass rounded-2xl overflow-hidden hover-lift group">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 bg-gradient-to-br from-blue-500/10 to-cyan-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Active Positions</CardTitle>
                        <div className="p-2 rounded-lg bg-blue-500/20">
                            <Activity className="h-5 w-5 text-blue-400" />
                        </div>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="text-3xl font-bold animate-number">{positions.length}</div>
                        <p className="text-xs text-muted-foreground mt-2">
                            <span className="text-green-400">{profitableCount} Profitable</span>, <span className="text-red-400">{lossCount} Loss</span>
                        </p>
                    </CardContent>
                </div>

                <div className="glass rounded-2xl overflow-hidden hover-lift group">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 bg-gradient-to-br from-purple-500/10 to-pink-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Win Rate</CardTitle>
                        <div className="p-2 rounded-lg bg-purple-500/20">
                            <BarChart3 className="h-5 w-5 text-purple-400" />
                        </div>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="text-3xl font-bold gradient-text animate-number">
                            {positions.length > 0 ? ((profitableCount / positions.length) * 100).toFixed(1) : '0'}%
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">Current session</p>
                    </CardContent>
                </div>

                <div className="glass rounded-2xl overflow-hidden hover-lift group">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 bg-gradient-to-br from-orange-500/10 to-amber-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Available Funds</CardTitle>
                        <div className="p-2 rounded-lg bg-orange-500/20">
                            <DollarSign className="h-5 w-5 text-orange-400" />
                        </div>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="text-3xl font-bold animate-number">
                            ₹{funds?.equityAmount ? funds.equityAmount.toLocaleString() : '--'}
                        </div>
                        <p className="text-xs text-muted-foreground mt-2" suppressHydrationWarning>
                            Last updated: {lastUpdated.toLocaleTimeString()}
                        </p>
                    </CardContent>
                </div>
            </div>

            {/* Positions Table and Activity */}
            <div className="grid gap-6 lg:grid-cols-7">
                <div className="lg:col-span-4">
                    <div className="glass rounded-2xl overflow-hidden">
                        <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10">
                            <CardTitle className="text-xl font-bold">Active Positions</CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                            {loading && positions.length === 0 ? (
                                <div className="p-8 text-center text-muted-foreground">
                                    <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-2" />
                                    Loading positions...
                                </div>
                            ) : positions.length === 0 ? (
                                <div className="p-8 text-center text-muted-foreground">
                                    No active positions
                                </div>
                            ) : (
                                <div className="overflow-x-auto">
                                    <Table>
                                        <TableHeader>
                                            <TableRow className="border-border/50 hover:bg-transparent">
                                                <TableHead className="font-semibold">Symbol</TableHead>
                                                <TableHead className="font-semibold">Qty</TableHead>
                                                <TableHead className="font-semibold">Avg Price</TableHead>
                                                <TableHead className="font-semibold">LTP</TableHead>
                                                <TableHead className="text-right font-semibold">PnL</TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {positions.map((pos, idx) => (
                                                <TableRow key={pos.symbol + idx} className="border-border/50 smooth-transition hover:bg-primary/5">
                                                    <TableCell className="font-bold text-foreground">{pos.symbol}</TableCell>
                                                    <TableCell className="text-muted-foreground">{pos.qty}</TableCell>
                                                    <TableCell className="text-muted-foreground">₹{pos.avg?.toFixed(2) || '0.00'}</TableCell>
                                                    <TableCell className="text-muted-foreground">₹{pos.ltp?.toFixed(2) || '0.00'}</TableCell>
                                                    <TableCell className="text-right">
                                                        <span className={`font-bold flex items-center justify-end ${(pos.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                            {(pos.pnl || 0) >= 0 ? <ArrowUpRight className="h-4 w-4 mr-1" /> : <ArrowDownRight className="h-4 w-4 mr-1" />}
                                                            {(pos.pnl || 0) >= 0 ? '+' : ''}₹{(pos.pnl || 0).toFixed(2)}
                                                        </span>
                                                    </TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                </div>
                            )}
                        </CardContent>
                    </div>
                </div>

                {/* Status Panel */}
                <div className="lg:col-span-3">
                    <div className="glass rounded-2xl overflow-hidden h-full">
                        <CardHeader className="bg-gradient-to-r from-accent/10 to-primary/10">
                            <CardTitle className="text-xl font-bold">System Status</CardTitle>
                        </CardHeader>
                        <CardContent className="pt-6">
                            <div className="space-y-6">
                                <div className="flex items-start space-x-4 p-4 rounded-lg bg-green-500/10 border border-green-500/20">
                                    <div className="p-2 rounded-lg bg-green-500/30">
                                        <Activity className="h-4 w-4 text-green-400" />
                                    </div>
                                    <div className="flex-1 space-y-1">
                                        <p className="text-sm font-semibold">Broker Connection</p>
                                        <p className="text-xs text-muted-foreground">
                                            {brokerStatus?.connected ? brokerStatus.broker_name + ' - Active' : 'Disconnected'}
                                        </p>
                                    </div>
                                </div>
                                <div className="flex items-start space-x-4 p-4 rounded-lg bg-blue-500/10 border border-blue-500/20">
                                    <div className="p-2 rounded-lg bg-blue-500/30">
                                        <Zap className="h-4 w-4 text-blue-400" />
                                    </div>
                                    <div className="flex-1 space-y-1">
                                        <p className="text-sm font-semibold">Smart Refresh</p>
                                        <p className="text-xs text-muted-foreground">Positions: 10s, Funds: 60s</p>
                                    </div>
                                </div>
                            </div>
                        </CardContent>
                    </div>
                </div>
            </div>
        </div>
    );
}
