"use client";

import { useState, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { 
    TrendingUp, TrendingDown, ArrowUp, ArrowDown, 
    Minus, RefreshCw, ChevronDown, Activity 
} from "lucide-react";

interface OptionData {
    strike: number;
    call: {
        ltp: number;
        change: number;
        changePercent: number;
        volume: number;
        oi: number;
        oiChange: number;
        iv: number;
        delta: number;
        gamma: number;
        theta: number;
        vega: number;
        bid: number;
        ask: number;
    };
    put: {
        ltp: number;
        change: number;
        changePercent: number;
        volume: number;
        oi: number;
        oiChange: number;
        iv: number;
        delta: number;
        gamma: number;
        theta: number;
        vega: number;
        bid: number;
        ask: number;
    };
}

interface OptionChainProps {
    symbol?: string;
    spotPrice?: number;
}

export function OptionChainViewer({ symbol = 'NIFTY', spotPrice = 24500 }: OptionChainProps) {
    const [selectedExpiry, setSelectedExpiry] = useState('28NOV24');
    const [showGreeks, setShowGreeks] = useState(false);
    const [highlightATM, setHighlightATM] = useState(true);
    const [strikeFilter, setStrikeFilter] = useState<'all' | 'itm' | 'otm' | 'atm'>('all');

    // Mock expiries
    const expiries = ['28NOV24', '05DEC24', '12DEC24', '26DEC24', '30JAN25'];

    // Mock option chain data
    const optionChain: OptionData[] = useMemo(() => {
        const atmStrike = Math.round(spotPrice / 100) * 100;
        const strikes: OptionData[] = [];

        for (let i = -10; i <= 10; i++) {
            const strike = atmStrike + i * 100;
            const distanceFromATM = Math.abs(strike - spotPrice);
            const isITMCall = strike < spotPrice;
            const isITMPut = strike > spotPrice;

            // Simulate option prices based on distance from ATM
            const callPremium = isITMCall 
                ? (spotPrice - strike) + 50 + Math.random() * 30
                : Math.max(5, 100 - distanceFromATM / 10 + Math.random() * 20);
            
            const putPremium = isITMPut
                ? (strike - spotPrice) + 50 + Math.random() * 30
                : Math.max(5, 100 - distanceFromATM / 10 + Math.random() * 20);

            const callOI = Math.floor(50000 + Math.random() * 200000 - distanceFromATM * 100);
            const putOI = Math.floor(50000 + Math.random() * 200000 - distanceFromATM * 100);

            strikes.push({
                strike,
                call: {
                    ltp: Math.round(callPremium * 100) / 100,
                    change: Math.round((Math.random() - 0.5) * 20 * 100) / 100,
                    changePercent: Math.round((Math.random() - 0.5) * 10 * 100) / 100,
                    volume: Math.floor(Math.random() * 500000),
                    oi: Math.max(1000, callOI),
                    oiChange: Math.floor((Math.random() - 0.5) * 10000),
                    iv: Math.round((15 + Math.random() * 10 + distanceFromATM / 500) * 100) / 100,
                    delta: isITMCall ? 0.5 + (spotPrice - strike) / 1000 : 0.5 - distanceFromATM / 1000,
                    gamma: 0.001 + Math.random() * 0.002,
                    theta: -(5 + Math.random() * 15),
                    vega: 10 + Math.random() * 10,
                    bid: Math.round((callPremium - Math.random() * 2) * 100) / 100,
                    ask: Math.round((callPremium + Math.random() * 2) * 100) / 100,
                },
                put: {
                    ltp: Math.round(putPremium * 100) / 100,
                    change: Math.round((Math.random() - 0.5) * 20 * 100) / 100,
                    changePercent: Math.round((Math.random() - 0.5) * 10 * 100) / 100,
                    volume: Math.floor(Math.random() * 500000),
                    oi: Math.max(1000, putOI),
                    oiChange: Math.floor((Math.random() - 0.5) * 10000),
                    iv: Math.round((15 + Math.random() * 10 + distanceFromATM / 500) * 100) / 100,
                    delta: isITMPut ? -(0.5 + (strike - spotPrice) / 1000) : -(0.5 - distanceFromATM / 1000),
                    gamma: 0.001 + Math.random() * 0.002,
                    theta: -(5 + Math.random() * 15),
                    vega: 10 + Math.random() * 10,
                    bid: Math.round((putPremium - Math.random() * 2) * 100) / 100,
                    ask: Math.round((putPremium + Math.random() * 2) * 100) / 100,
                }
            });
        }

        return strikes;
    }, [spotPrice]);

    const atmStrike = Math.round(spotPrice / 100) * 100;

    const filteredChain = optionChain.filter(opt => {
        switch (strikeFilter) {
            case 'itm':
                return opt.strike < spotPrice;
            case 'otm':
                return opt.strike > spotPrice;
            case 'atm':
                return Math.abs(opt.strike - spotPrice) <= 200;
            default:
                return true;
        }
    });

    // Calculate max OI for bar visualization
    const maxCallOI = Math.max(...optionChain.map(o => o.call.oi));
    const maxPutOI = Math.max(...optionChain.map(o => o.put.oi));
    const maxOI = Math.max(maxCallOI, maxPutOI);

    // PCR calculation
    const totalCallOI = optionChain.reduce((sum, o) => sum + o.call.oi, 0);
    const totalPutOI = optionChain.reduce((sum, o) => sum + o.put.oi, 0);
    const pcr = totalPutOI / totalCallOI;

    return (
        <Card className="glass rounded-2xl overflow-hidden">
            <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10 py-4">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    <div className="flex items-center gap-4">
                        <CardTitle className="text-xl font-bold">{symbol} Option Chain</CardTitle>
                        <div className="flex items-center gap-2 text-sm">
                            <span className="text-muted-foreground">Spot:</span>
                            <span className="font-bold text-green-400">₹{spotPrice.toLocaleString()}</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                            <span className="text-muted-foreground">PCR:</span>
                            <span className={`font-bold ${pcr > 1 ? 'text-green-400' : 'text-red-400'}`}>
                                {pcr.toFixed(2)}
                            </span>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <select
                            title="Select option expiry"
                            value={selectedExpiry}
                            onChange={(e) => setSelectedExpiry(e.target.value)}
                            className="h-9 px-3 rounded-md bg-muted/30 border border-border/30 text-sm"
                        >
                            {expiries.map(exp => (
                                <option key={exp} value={exp}>{exp}</option>
                            ))}
                        </select>
                        <select
                            title="Filter strikes"
                            value={strikeFilter}
                            onChange={(e) => setStrikeFilter(e.target.value as any)}
                            className="h-9 px-3 rounded-md bg-muted/30 border border-border/30 text-sm"
                        >
                            <option value="all">All Strikes</option>
                            <option value="itm">ITM Only</option>
                            <option value="otm">OTM Only</option>
                            <option value="atm">Near ATM</option>
                        </select>
                        <Button 
                            variant={showGreeks ? "secondary" : "outline"} 
                            size="sm"
                            onClick={() => setShowGreeks(!showGreeks)}
                        >
                            Greeks
                        </Button>
                        <Button variant="outline" size="sm">
                            <RefreshCw className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="p-0">
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-border/30 bg-muted/10">
                                <th colSpan={showGreeks ? 8 : 5} className="text-center p-2 text-green-400 border-r border-border/30">
                                    CALLS
                                </th>
                                <th className="text-center p-2 bg-muted/20">STRIKE</th>
                                <th colSpan={showGreeks ? 8 : 5} className="text-center p-2 text-red-400 border-l border-border/30">
                                    PUTS
                                </th>
                            </tr>
                            <tr className="border-b border-border/30 bg-muted/5 text-xs text-muted-foreground">
                                {/* Call Headers */}
                                <th className="p-2 text-right">OI</th>
                                <th className="p-2 text-right">Chg OI</th>
                                <th className="p-2 text-right">Volume</th>
                                <th className="p-2 text-right">IV</th>
                                <th className="p-2 text-right border-r border-border/30">LTP</th>
                                {showGreeks && (
                                    <>
                                        <th className="p-2 text-right">Δ</th>
                                        <th className="p-2 text-right">Γ</th>
                                        <th className="p-2 text-right border-r border-border/30">Θ</th>
                                    </>
                                )}
                                
                                {/* Strike */}
                                <th className="p-2 text-center bg-muted/20"></th>
                                
                                {/* Put Headers */}
                                {showGreeks && (
                                    <>
                                        <th className="p-2 text-left border-l border-border/30">Θ</th>
                                        <th className="p-2 text-left">Γ</th>
                                        <th className="p-2 text-left">Δ</th>
                                    </>
                                )}
                                <th className="p-2 text-left border-l border-border/30">LTP</th>
                                <th className="p-2 text-left">IV</th>
                                <th className="p-2 text-left">Volume</th>
                                <th className="p-2 text-left">Chg OI</th>
                                <th className="p-2 text-left">OI</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredChain.map((option) => {
                                const isATM = option.strike === atmStrike;
                                const isITMCall = option.strike < spotPrice;
                                const isITMPut = option.strike > spotPrice;

                                return (
                                    <tr 
                                        key={option.strike}
                                        className={`border-b border-border/10 hover:bg-muted/10 transition-colors ${
                                            isATM ? 'bg-primary/10 font-medium' : ''
                                        }`}
                                    >
                                        {/* Call Side */}
                                        <td className={`p-2 text-right ${isITMCall ? 'bg-green-500/5' : ''}`}>
                                            <div className="relative">
                                                <div 
                                                    className="absolute right-0 top-0 h-full bg-green-500/20 rounded-l"
                                                    style={{ width: `${(option.call.oi / maxOI) * 100}%` }}
                                                ></div>
                                                <span className="relative z-10">{(option.call.oi / 1000).toFixed(0)}K</span>
                                            </div>
                                        </td>
                                        <td className={`p-2 text-right ${isITMCall ? 'bg-green-500/5' : ''}`}>
                                            <span className={option.call.oiChange >= 0 ? 'text-green-400' : 'text-red-400'}>
                                                {option.call.oiChange >= 0 ? '+' : ''}{(option.call.oiChange / 1000).toFixed(1)}K
                                            </span>
                                        </td>
                                        <td className={`p-2 text-right ${isITMCall ? 'bg-green-500/5' : ''}`}>
                                            {(option.call.volume / 1000).toFixed(0)}K
                                        </td>
                                        <td className={`p-2 text-right ${isITMCall ? 'bg-green-500/5' : ''}`}>
                                            {option.call.iv.toFixed(1)}%
                                        </td>
                                        <td className={`p-2 text-right font-medium border-r border-border/30 ${isITMCall ? 'bg-green-500/5' : ''}`}>
                                            <div className={option.call.change >= 0 ? 'text-green-400' : 'text-red-400'}>
                                                ₹{option.call.ltp.toFixed(2)}
                                            </div>
                                        </td>
                                        {showGreeks && (
                                            <>
                                                <td className={`p-2 text-right text-xs ${isITMCall ? 'bg-green-500/5' : ''}`}>
                                                    {option.call.delta.toFixed(2)}
                                                </td>
                                                <td className={`p-2 text-right text-xs ${isITMCall ? 'bg-green-500/5' : ''}`}>
                                                    {option.call.gamma.toFixed(4)}
                                                </td>
                                                <td className={`p-2 text-right text-xs border-r border-border/30 ${isITMCall ? 'bg-green-500/5' : ''}`}>
                                                    {option.call.theta.toFixed(1)}
                                                </td>
                                            </>
                                        )}

                                        {/* Strike */}
                                        <td className={`p-2 text-center font-bold bg-muted/20 ${isATM ? 'text-primary' : ''}`}>
                                            {option.strike.toLocaleString()}
                                            {isATM && <span className="ml-1 text-xs">ATM</span>}
                                        </td>

                                        {/* Put Side */}
                                        {showGreeks && (
                                            <>
                                                <td className={`p-2 text-left text-xs border-l border-border/30 ${isITMPut ? 'bg-red-500/5' : ''}`}>
                                                    {option.put.theta.toFixed(1)}
                                                </td>
                                                <td className={`p-2 text-left text-xs ${isITMPut ? 'bg-red-500/5' : ''}`}>
                                                    {option.put.gamma.toFixed(4)}
                                                </td>
                                                <td className={`p-2 text-left text-xs ${isITMPut ? 'bg-red-500/5' : ''}`}>
                                                    {option.put.delta.toFixed(2)}
                                                </td>
                                            </>
                                        )}
                                        <td className={`p-2 text-left font-medium border-l border-border/30 ${isITMPut ? 'bg-red-500/5' : ''}`}>
                                            <div className={option.put.change >= 0 ? 'text-green-400' : 'text-red-400'}>
                                                ₹{option.put.ltp.toFixed(2)}
                                            </div>
                                        </td>
                                        <td className={`p-2 text-left ${isITMPut ? 'bg-red-500/5' : ''}`}>
                                            {option.put.iv.toFixed(1)}%
                                        </td>
                                        <td className={`p-2 text-left ${isITMPut ? 'bg-red-500/5' : ''}`}>
                                            {(option.put.volume / 1000).toFixed(0)}K
                                        </td>
                                        <td className={`p-2 text-left ${isITMPut ? 'bg-red-500/5' : ''}`}>
                                            <span className={option.put.oiChange >= 0 ? 'text-green-400' : 'text-red-400'}>
                                                {option.put.oiChange >= 0 ? '+' : ''}{(option.put.oiChange / 1000).toFixed(1)}K
                                            </span>
                                        </td>
                                        <td className={`p-2 text-left ${isITMPut ? 'bg-red-500/5' : ''}`}>
                                            <div className="relative">
                                                <div 
                                                    className="absolute left-0 top-0 h-full bg-red-500/20 rounded-r"
                                                    style={{ width: `${(option.put.oi / maxOI) * 100}%` }}
                                                ></div>
                                                <span className="relative z-10">{(option.put.oi / 1000).toFixed(0)}K</span>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>

                {/* Summary Footer */}
                <div className="p-4 border-t border-border/30 bg-muted/10 grid grid-cols-4 gap-4 text-sm">
                    <div className="text-center">
                        <p className="text-muted-foreground">Total Call OI</p>
                        <p className="font-bold text-green-400">{(totalCallOI / 100000).toFixed(2)} L</p>
                    </div>
                    <div className="text-center">
                        <p className="text-muted-foreground">Total Put OI</p>
                        <p className="font-bold text-red-400">{(totalPutOI / 100000).toFixed(2)} L</p>
                    </div>
                    <div className="text-center">
                        <p className="text-muted-foreground">Max Pain</p>
                        <p className="font-bold text-primary">{atmStrike.toLocaleString()}</p>
                    </div>
                    <div className="text-center">
                        <p className="text-muted-foreground">PCR</p>
                        <p className={`font-bold ${pcr > 1 ? 'text-green-400' : 'text-red-400'}`}>
                            {pcr.toFixed(2)} ({pcr > 1.2 ? 'Bullish' : pcr < 0.8 ? 'Bearish' : 'Neutral'})
                        </p>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
