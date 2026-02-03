"use client";

import { useState, useEffect, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { RefreshCw, TrendingUp, TrendingDown, Activity } from "lucide-react";
import { apiClient, OptionChain, OptionStrike } from "@/lib/api/client";
import { useRealtime, OptionChainData } from "@/lib/hooks/useRealtime";

interface OptionChainViewerProps {
    underlying?: string;
}

// Format number with fixed decimals
const formatNumber = (value: number | undefined, decimals: number = 2): string => {
    if (value === undefined || value === null) return '-';
    return value.toFixed(decimals);
};

// Format large numbers with K/L/Cr suffixes
const formatOI = (value: number | undefined): string => {
    if (value === undefined || value === null) return '-';
    if (value >= 10000000) return (value / 10000000).toFixed(2) + 'Cr';
    if (value >= 100000) return (value / 100000).toFixed(2) + 'L';
    if (value >= 1000) return (value / 1000).toFixed(1) + 'K';
    return value.toString();
};

// Get color based on delta
const getDeltaColor = (delta: number | undefined): string => {
    if (!delta) return 'text-muted-foreground';
    const absDelta = Math.abs(delta);
    if (absDelta >= 0.7) return 'text-green-500';
    if (absDelta >= 0.5) return 'text-blue-500';
    if (absDelta >= 0.3) return 'text-yellow-500';
    return 'text-muted-foreground';
};

// Get IV color
const getIVColor = (iv: number | undefined): string => {
    if (!iv) return 'text-muted-foreground';
    if (iv >= 30) return 'text-red-500';
    if (iv >= 20) return 'text-yellow-500';
    return 'text-green-500';
};

export function OptionChainViewer({ underlying = 'NIFTY' }: OptionChainViewerProps) {
    const [selectedUnderlying, setSelectedUnderlying] = useState(underlying);
    const [selectedExpiry, setSelectedExpiry] = useState<string>('');
    const [expiries, setExpiries] = useState<string[]>([]);
    const [optionChain, setOptionChain] = useState<OptionChain | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Real-time updates
    const { connected, subscribeOptionChain } = useRealtime({
        onOptionChain: (data: OptionChainData) => {
            if (data.data.underlying === selectedUnderlying) {
                setOptionChain({
                    underlying: data.data.underlying,
                    spot_price: data.data.spot_price,
                    expiry: data.data.expiry,
                    timestamp: data.data.timestamp,
                    pcr: data.data.pcr,
                    max_pain: data.data.max_pain,
                    strikes: data.data.strikes,
                });
            }
        },
    });

    // Fetch expiries when underlying changes
    useEffect(() => {
        const fetchExpiries = async () => {
            try {
                const data = await apiClient.getOptionExpiries(selectedUnderlying);
                setExpiries(data.expiries);
                if (data.expiries.length > 0) {
                    setSelectedExpiry(data.expiries[0]);
                }
            } catch (err) {
                console.error('Failed to fetch expiries:', err);
                setExpiries([]);
            }
        };

        fetchExpiries();
    }, [selectedUnderlying]);

    // Fetch option chain when expiry changes
    useEffect(() => {
        if (!selectedExpiry) return;

        const fetchChain = async () => {
            setLoading(true);
            setError(null);
            try {
                const data = await apiClient.getOptionChain(selectedUnderlying, selectedExpiry);
                setOptionChain(data);
                
                // Subscribe to real-time updates if connected
                if (connected) {
                    subscribeOptionChain(selectedUnderlying, selectedExpiry);
                }
            } catch (err: any) {
                console.error('Failed to fetch option chain:', err);
                setError(err.message || 'Failed to fetch option chain');
                setOptionChain(null);
            } finally {
                setLoading(false);
            }
        };

        fetchChain();
    }, [selectedExpiry, selectedUnderlying, connected, subscribeOptionChain]);

    // Calculate ATM strike
    const atmStrike = useMemo(() => {
        if (!optionChain) return 0;
        const spot = optionChain.spot_price;
        const strikes = optionChain.strikes.map(s => s.strike_price);
        if (strikes.length === 0) return 0;
        return strikes.reduce((prev, curr) => 
            Math.abs(curr - spot) < Math.abs(prev - spot) ? curr : prev
        );
    }, [optionChain]);

    // Filter strikes around ATM
    const displayStrikes = useMemo(() => {
        if (!optionChain) return [];
        const strikes = [...optionChain.strikes].sort((a, b) => a.strike_price - b.strike_price);
        const atmIndex = strikes.findIndex(s => s.strike_price === atmStrike);
        if (atmIndex === -1) return strikes.slice(0, 20);
        const start = Math.max(0, atmIndex - 10);
        const end = Math.min(strikes.length, atmIndex + 11);
        return strikes.slice(start, end);
    }, [optionChain, atmStrike]);

    const underlyings = ['NIFTY', 'BANKNIFTY', 'FINNIFTY'];

    return (
        <Card className="glass rounded-2xl overflow-hidden">
            <CardHeader className="bg-gradient-to-r from-purple-500/10 to-pink-500/10">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <CardTitle className="text-xl font-bold">Option Chain</CardTitle>
                        <div className="flex items-center gap-2">
                            <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
                            <span className="text-xs text-muted-foreground">
                                {connected ? 'Live' : 'Offline'}
                            </span>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <Select value={selectedUnderlying} onValueChange={setSelectedUnderlying}>
                            <SelectTrigger className="w-[140px]">
                                <SelectValue placeholder="Select Index" />
                            </SelectTrigger>
                            <SelectContent>
                                {underlyings.map(u => (
                                    <SelectItem key={u} value={u}>{u}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <Select value={selectedExpiry} onValueChange={setSelectedExpiry}>
                            <SelectTrigger className="w-[140px]">
                                <SelectValue placeholder="Select Expiry" />
                            </SelectTrigger>
                            <SelectContent>
                                {expiries.map(e => (
                                    <SelectItem key={e} value={e}>{e}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setSelectedExpiry(selectedExpiry)}
                            disabled={loading}
                        >
                            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                        </Button>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="p-4">
                {/* Chain Stats */}
                {optionChain && (
                    <div className="flex items-center gap-6 mb-4 p-3 rounded-lg bg-muted/30">
                        <div className="flex items-center gap-2">
                            <Activity className="h-4 w-4 text-blue-500" />
                            <span className="text-sm font-medium">Spot:</span>
                            <span className="text-sm font-bold">{formatNumber(optionChain.spot_price, 2)}</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">PCR:</span>
                            <Badge variant={optionChain.pcr > 1 ? 'default' : 'destructive'}>
                                {formatNumber(optionChain.pcr, 2)}
                            </Badge>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">Max Pain:</span>
                            <span className="text-sm font-bold text-purple-500">
                                {formatNumber(optionChain.max_pain, 0)}
                            </span>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">ATM:</span>
                            <span className="text-sm font-bold text-yellow-500">{atmStrike}</span>
                        </div>
                    </div>
                )}

                {/* Option Chain Table */}
                {loading ? (
                    <div className="flex items-center justify-center py-12">
                        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
                    </div>
                ) : error ? (
                    <div className="text-center py-12 text-red-500">{error}</div>
                ) : !optionChain ? (
                    <div className="text-center py-12 text-muted-foreground">
                        Select an underlying and expiry to view the option chain
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <Table>
                            <TableHeader>
                                <TableRow className="border-border/50">
                                    {/* Call Side */}
                                    <TableHead className="text-center text-green-500">OI</TableHead>
                                    <TableHead className="text-center text-green-500">Vol</TableHead>
                                    <TableHead className="text-center text-green-500">IV</TableHead>
                                    <TableHead className="text-center text-green-500">Δ</TableHead>
                                    <TableHead className="text-center text-green-500">LTP</TableHead>
                                    {/* Strike */}
                                    <TableHead className="text-center bg-muted/30 font-bold">Strike</TableHead>
                                    {/* Put Side */}
                                    <TableHead className="text-center text-red-500">LTP</TableHead>
                                    <TableHead className="text-center text-red-500">Δ</TableHead>
                                    <TableHead className="text-center text-red-500">IV</TableHead>
                                    <TableHead className="text-center text-red-500">Vol</TableHead>
                                    <TableHead className="text-center text-red-500">OI</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {displayStrikes.map((strike) => {
                                    const isATM = strike.strike_price === atmStrike;
                                    const isITMCall = strike.strike_price < optionChain.spot_price;
                                    const isITMPut = strike.strike_price > optionChain.spot_price;
                                    
                                    return (
                                        <TableRow
                                            key={strike.strike_price}
                                            className={`border-border/30 ${isATM ? 'bg-yellow-500/10' : ''}`}
                                        >
                                            {/* Call Side */}
                                            <TableCell className={`text-center ${isITMCall ? 'bg-green-500/5' : ''}`}>
                                                {formatOI(strike.call_oi)}
                                            </TableCell>
                                            <TableCell className={`text-center ${isITMCall ? 'bg-green-500/5' : ''}`}>
                                                {formatOI(strike.call_volume)}
                                            </TableCell>
                                            <TableCell className={`text-center ${isITMCall ? 'bg-green-500/5' : ''} ${getIVColor(strike.call_iv)}`}>
                                                {formatNumber(strike.call_iv, 1)}
                                            </TableCell>
                                            <TableCell className={`text-center ${isITMCall ? 'bg-green-500/5' : ''} ${getDeltaColor(strike.call_delta)}`}>
                                                {formatNumber(strike.call_delta, 2)}
                                            </TableCell>
                                            <TableCell className={`text-center font-medium ${isITMCall ? 'bg-green-500/5' : ''}`}>
                                                {formatNumber(strike.call_ltp, 2)}
                                            </TableCell>
                                            
                                            {/* Strike */}
                                            <TableCell className={`text-center font-bold bg-muted/30 ${isATM ? 'text-yellow-500' : ''}`}>
                                                {strike.strike_price}
                                            </TableCell>
                                            
                                            {/* Put Side */}
                                            <TableCell className={`text-center font-medium ${isITMPut ? 'bg-red-500/5' : ''}`}>
                                                {formatNumber(strike.put_ltp, 2)}
                                            </TableCell>
                                            <TableCell className={`text-center ${isITMPut ? 'bg-red-500/5' : ''} ${getDeltaColor(strike.put_delta)}`}>
                                                {formatNumber(strike.put_delta, 2)}
                                            </TableCell>
                                            <TableCell className={`text-center ${isITMPut ? 'bg-red-500/5' : ''} ${getIVColor(strike.put_iv)}`}>
                                                {formatNumber(strike.put_iv, 1)}
                                            </TableCell>
                                            <TableCell className={`text-center ${isITMPut ? 'bg-red-500/5' : ''}`}>
                                                {formatOI(strike.put_volume)}
                                            </TableCell>
                                            <TableCell className={`text-center ${isITMPut ? 'bg-red-500/5' : ''}`}>
                                                {formatOI(strike.put_oi)}
                                            </TableCell>
                                        </TableRow>
                                    );
                                })}
                            </TableBody>
                        </Table>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
