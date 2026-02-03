"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { 
    Search, Filter, Download, ArrowUpDown, 
    TrendingUp, TrendingDown, Clock, Target, Loader2, RefreshCw
} from "lucide-react";
import { apiClient } from "@/lib/api/client";

interface Trade {
    id: string;
    date: string;
    time: string;
    strategy: string;
    symbol: string;
    direction: 'BUY' | 'SELL' | 'LONG' | 'SHORT';
    quantity: number;
    entryPrice: number;
    exitPrice: number;
    pnl: number;
    pnlPercent: number;
    duration: number; // minutes
    tags?: string[];
}

interface TradeTableProps {
    trades?: Trade[];
    strategyId?: string;
}

// Mock data generator for fallback
const generateMockTrades = (): Trade[] => {
    const strategies = ['EMA Crossover', 'RSI Reversal', 'Momentum Breakout', 'Iron Condor'];
    const symbols = ['NIFTY', 'BANKNIFTY', 'RELIANCE', 'TCS', 'INFY'];
    const trades: Trade[] = [];

    for (let i = 0; i < 50; i++) {
        const date = new Date();
        date.setDate(date.getDate() - Math.floor(Math.random() * 60));
        const entryPrice = 100 + Math.random() * 500;
        const pnlPercent = (Math.random() - 0.4) * 20;
        const exitPrice = entryPrice * (1 + pnlPercent / 100);
        const quantity = Math.floor(Math.random() * 100 + 25);
        
        trades.push({
            id: `T${1000 + i}`,
            date: date.toISOString().split('T')[0],
            time: `${9 + Math.floor(Math.random() * 6)}:${String(Math.floor(Math.random() * 60)).padStart(2, '0')}`,
            strategy: strategies[Math.floor(Math.random() * strategies.length)],
            symbol: symbols[Math.floor(Math.random() * symbols.length)],
            direction: Math.random() > 0.5 ? 'LONG' : 'SHORT',
            quantity: quantity,
            entryPrice: Math.round(entryPrice * 100) / 100,
            exitPrice: Math.round(exitPrice * 100) / 100,
            pnl: Math.round(quantity * (exitPrice - entryPrice)),
            pnlPercent: Math.round(pnlPercent * 100) / 100,
            duration: Math.floor(Math.random() * 300 + 5),
            tags: Math.random() > 0.7 ? ['Scalp'] : Math.random() > 0.5 ? ['Swing'] : []
        });
    }
    return trades;
};

export function TradeTable({ trades: propTrades, strategyId }: TradeTableProps) {
    const [trades, setTrades] = useState<Trade[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [sortField, setSortField] = useState<keyof Trade>('date');
    const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
    const [filterStrategy, setFilterStrategy] = useState<string>('all');
    const [filterOutcome, setFilterOutcome] = useState<'all' | 'win' | 'loss'>('all');

    const fetchTrades = useCallback(async () => {
        if (propTrades) {
            setTrades(propTrades);
            setLoading(false);
            return;
        }

        setLoading(true);
        try {
            const data = await apiClient.getTradeHistory(100, 0, strategyId);
            if (data && data.length > 0) {
                // Map API response to Trade interface
                const mappedTrades: Trade[] = data.map((t: any) => {
                    const entryTime = new Date(t.entry_time);
                    const exitTime = t.exit_time ? new Date(t.exit_time) : entryTime;
                    const durationMs = exitTime.getTime() - entryTime.getTime();
                    const durationMinutes = Math.round(durationMs / (1000 * 60));
                    
                    const entryPrice = t.entry_price || 0;
                    const exitPrice = t.exit_price || entryPrice;
                    const pnlPercent = entryPrice > 0 ? ((exitPrice - entryPrice) / entryPrice) * 100 : 0;
                    
                    return {
                        id: t.id,
                        date: entryTime.toISOString().split('T')[0],
                        time: entryTime.toTimeString().slice(0, 5),
                        strategy: t.strategy || 'Unknown',
                        symbol: t.symbol,
                        direction: t.side as 'LONG' | 'SHORT',
                        quantity: t.quantity,
                        entryPrice: entryPrice,
                        exitPrice: exitPrice,
                        pnl: t.pnl || 0,
                        pnlPercent: Math.round(pnlPercent * 100) / 100,
                        duration: durationMinutes > 0 ? durationMinutes : 1,
                        tags: []
                    };
                });
                setTrades(mappedTrades);
            } else {
                // Fallback to mock data
                setTrades(generateMockTrades());
            }
        } catch (error) {
            console.error("Failed to fetch trades:", error);
            setTrades(generateMockTrades());
        } finally {
            setLoading(false);
        }
    }, [propTrades, strategyId]);

    useEffect(() => {
        fetchTrades();
    }, [fetchTrades]);

    const filteredAndSortedTrades = useMemo(() => {
        let result = [...trades];

        // Search filter
        if (searchTerm) {
            result = result.filter(t => 
                t.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
                t.strategy.toLowerCase().includes(searchTerm.toLowerCase()) ||
                t.id.toLowerCase().includes(searchTerm.toLowerCase())
            );
        }

        // Strategy filter
        if (filterStrategy !== 'all') {
            result = result.filter(t => t.strategy === filterStrategy);
        }

        // Outcome filter
        if (filterOutcome === 'win') {
            result = result.filter(t => t.pnl > 0);
        } else if (filterOutcome === 'loss') {
            result = result.filter(t => t.pnl < 0);
        }

        // Sort
        result.sort((a, b) => {
            const aVal = a[sortField] ?? '';
            const bVal = b[sortField] ?? '';
            
            const aCompare = typeof aVal === 'string' ? aVal.toLowerCase() : aVal;
            const bCompare = typeof bVal === 'string' ? bVal.toLowerCase() : bVal;
            
            if (sortDirection === 'asc') {
                return aCompare > bCompare ? 1 : -1;
            }
            return aCompare < bCompare ? 1 : -1;
        });

        return result;
    }, [trades, searchTerm, sortField, sortDirection, filterStrategy, filterOutcome]);

    const strategies = useMemo(() => 
        Array.from(new Set(trades.map(t => t.strategy))),
        [trades]
    );

    const stats = useMemo(() => ({
        total: filteredAndSortedTrades.length,
        wins: filteredAndSortedTrades.filter(t => t.pnl > 0).length,
        losses: filteredAndSortedTrades.filter(t => t.pnl < 0).length,
        totalPnl: filteredAndSortedTrades.reduce((sum, t) => sum + t.pnl, 0)
    }), [filteredAndSortedTrades]);

    const handleSort = (field: keyof Trade) => {
        if (sortField === field) {
            setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            setSortDirection('desc');
        }
    };

    const formatDuration = (minutes: number) => {
        if (minutes < 60) return `${minutes}m`;
        const hours = Math.floor(minutes / 60);
        const mins = minutes % 60;
        return `${hours}h ${mins}m`;
    };

    return (
        <Card className="glass rounded-2xl overflow-hidden">
            <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    <div className="flex items-center gap-4">
                        <CardTitle className="text-xl font-bold">Trade History</CardTitle>
                        <div className="flex gap-2 text-sm">
                            <span className="px-2 py-1 rounded-full bg-muted/30">{stats.total} trades</span>
                            <span className="px-2 py-1 rounded-full bg-green-500/20 text-green-400">{stats.wins} wins</span>
                            <span className="px-2 py-1 rounded-full bg-red-500/20 text-red-400">{stats.losses} losses</span>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <Input
                                placeholder="Search trades..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="pl-9 w-48 bg-muted/30 border-border/30"
                            />
                        </div>
                        <select
                            title="Filter by strategy"
                            value={filterStrategy}
                            onChange={(e) => setFilterStrategy(e.target.value)}
                            className="h-9 px-3 rounded-md bg-muted/30 border border-border/30 text-sm"
                        >
                            <option value="all">All Strategies</option>
                            {strategies.map(s => (
                                <option key={s} value={s}>{s}</option>
                            ))}
                        </select>
                        <select
                            title="Filter by outcome"
                            value={filterOutcome}
                            onChange={(e) => setFilterOutcome(e.target.value as any)}
                            className="h-9 px-3 rounded-md bg-muted/30 border border-border/30 text-sm"
                        >
                            <option value="all">All Outcomes</option>
                            <option value="win">Winners</option>
                            <option value="loss">Losers</option>
                        </select>
                        <Button variant="outline" size="sm">
                            <Download className="h-4 w-4 mr-1" /> Export
                        </Button>
                        <Button 
                            variant="outline" 
                            size="sm"
                            onClick={() => fetchTrades()}
                            disabled={loading}
                        >
                            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                        </Button>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="p-0">
                {loading ? (
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                    </div>
                ) : (
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-border/30 bg-muted/10">
                                <th className="text-left p-3 text-xs font-medium text-muted-foreground">
                                    <button 
                                        className="flex items-center gap-1 hover:text-foreground"
                                        onClick={() => handleSort('date')}
                                    >
                                        Date/Time
                                        <ArrowUpDown className="h-3 w-3" />
                                    </button>
                                </th>
                                <th className="text-left p-3 text-xs font-medium text-muted-foreground">
                                    <button 
                                        className="flex items-center gap-1 hover:text-foreground"
                                        onClick={() => handleSort('strategy')}
                                    >
                                        Strategy
                                        <ArrowUpDown className="h-3 w-3" />
                                    </button>
                                </th>
                                <th className="text-left p-3 text-xs font-medium text-muted-foreground">
                                    <button 
                                        className="flex items-center gap-1 hover:text-foreground"
                                        onClick={() => handleSort('symbol')}
                                    >
                                        Symbol
                                        <ArrowUpDown className="h-3 w-3" />
                                    </button>
                                </th>
                                <th className="text-center p-3 text-xs font-medium text-muted-foreground">Direction</th>
                                <th className="text-right p-3 text-xs font-medium text-muted-foreground">Qty</th>
                                <th className="text-right p-3 text-xs font-medium text-muted-foreground">Entry</th>
                                <th className="text-right p-3 text-xs font-medium text-muted-foreground">Exit</th>
                                <th className="text-right p-3 text-xs font-medium text-muted-foreground">
                                    <button 
                                        className="flex items-center gap-1 hover:text-foreground ml-auto"
                                        onClick={() => handleSort('pnl')}
                                    >
                                        P&L
                                        <ArrowUpDown className="h-3 w-3" />
                                    </button>
                                </th>
                                <th className="text-right p-3 text-xs font-medium text-muted-foreground">Duration</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredAndSortedTrades.slice(0, 20).map((trade, idx) => (
                                <tr 
                                    key={trade.id} 
                                    className={`border-b border-border/10 hover:bg-muted/10 transition-colors cursor-pointer ${
                                        idx % 2 === 0 ? '' : 'bg-muted/5'
                                    }`}
                                >
                                    <td className="p-3">
                                        <div className="text-sm font-medium">{trade.date}</div>
                                        <div className="text-xs text-muted-foreground">{trade.time}</div>
                                    </td>
                                    <td className="p-3">
                                        <span className="text-sm">{trade.strategy}</span>
                                    </td>
                                    <td className="p-3">
                                        <div className="flex items-center gap-2">
                                            <span className="font-medium">{trade.symbol}</span>
                                            {trade.tags?.map(tag => (
                                                <span key={tag} className="text-xs px-1.5 py-0.5 rounded bg-primary/20 text-primary">
                                                    {tag}
                                                </span>
                                            ))}
                                        </div>
                                    </td>
                                    <td className="p-3 text-center">
                                        <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${
                                            trade.direction === 'BUY' || trade.direction === 'LONG'
                                                ? 'bg-green-500/20 text-green-400' 
                                                : 'bg-red-500/20 text-red-400'
                                        }`}>
                                            {trade.direction === 'BUY' || trade.direction === 'LONG' ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                                            {trade.direction}
                                        </span>
                                    </td>
                                    <td className="p-3 text-right text-sm">{trade.quantity}</td>
                                    <td className="p-3 text-right text-sm">₹{trade.entryPrice.toFixed(2)}</td>
                                    <td className="p-3 text-right text-sm">₹{trade.exitPrice.toFixed(2)}</td>
                                    <td className="p-3 text-right">
                                        <div className={`text-sm font-bold ${trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            {trade.pnl >= 0 ? '+' : ''}₹{trade.pnl.toLocaleString()}
                                        </div>
                                        <div className={`text-xs ${trade.pnl >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
                                            {trade.pnlPercent >= 0 ? '+' : ''}{trade.pnlPercent}%
                                        </div>
                                    </td>
                                    <td className="p-3 text-right">
                                        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                                            <Clock className="h-3 w-3" />
                                            {formatDuration(trade.duration)}
                                        </span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                )}

                {/* Summary Footer */}
                <div className="p-4 border-t border-border/30 bg-muted/10">
                    <div className="flex justify-between items-center">
                        <span className="text-sm text-muted-foreground">
                            Showing {Math.min(20, filteredAndSortedTrades.length)} of {filteredAndSortedTrades.length} trades
                        </span>
                        <div className={`text-lg font-bold ${stats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            Total: {stats.totalPnl >= 0 ? '+' : ''}₹{stats.totalPnl.toLocaleString()}
                        </div>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
