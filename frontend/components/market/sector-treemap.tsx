"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { TrendingUp, TrendingDown, Minus, Loader2 } from "lucide-react";
import { apiClient } from "@/lib/api/client";

interface SectorData {
    name: string;
    change: number;
    marketCap: number;
    volume: number;
    advances: number;
    declines: number;
    unchanged: number;
    stocks: StockData[];
}

interface StockData {
    symbol: string;
    name: string;
    change: number;
    price: number;
    marketCap: number;
    volume: number;
}

interface SectorTreemapProps {
    data?: SectorData[];
    onSectorClick?: (sector: string) => void;
    onStockClick?: (symbol: string) => void;
}

export function SectorTreemap({ data: propData, onSectorClick, onStockClick }: SectorTreemapProps) {
    const [sectorData, setSectorData] = useState<SectorData[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedSector, setSelectedSector] = useState<string | null>(null);
    const [viewMode, setViewMode] = useState<'sectors' | 'stocks'>('sectors');

    // Fetch sector data from API
    const fetchSectorData = useCallback(async () => {
        if (propData) {
            setSectorData(propData);
            setLoading(false);
            return;
        }

        try {
            const data = await apiClient.getSectorPerformance();
            if (data && data.length > 0) {
                // Transform API response to match component interface
                const transformed = data.map((s: any) => ({
                    name: s.sector || s.name,
                    change: s.change_percent || s.change || 0,
                    marketCap: s.marketCap || s.market_cap || 1000000,
                    volume: s.volume || s.volume_million * 1000000 || 0,
                    advances: s.advances || 0,
                    declines: s.declines || 0,
                    unchanged: s.unchanged || 0,
                    stocks: s.stocks || [],
                }));
                setSectorData(transformed);
            } else {
                setSectorData(mockData);
            }
        } catch (error) {
            console.error("Failed to fetch sector data:", error);
            setSectorData(mockData);
        } finally {
            setLoading(false);
        }
    }, [propData]);

    useEffect(() => {
        fetchSectorData();
        // Auto-refresh every 60 seconds
        const interval = setInterval(fetchSectorData, 60000);
        return () => clearInterval(interval);
    }, [fetchSectorData]);

    // Mock data for fallback
    const mockData: SectorData[] = useMemo(() => [
        {
            name: 'Banking',
            change: 1.45,
            marketCap: 2500000,
            volume: 450000000,
            advances: 8,
            declines: 4,
            unchanged: 0,
            stocks: [
                { symbol: 'HDFCBANK', name: 'HDFC Bank', change: 1.8, price: 1650, marketCap: 1200000, volume: 12000000 },
                { symbol: 'ICICIBANK', name: 'ICICI Bank', change: 2.1, price: 1020, marketCap: 720000, volume: 8500000 },
                { symbol: 'SBIN', name: 'State Bank', change: 0.9, price: 620, marketCap: 550000, volume: 15000000 },
                { symbol: 'KOTAKBANK', name: 'Kotak Bank', change: -0.5, price: 1780, marketCap: 350000, volume: 3200000 },
            ]
        },
        {
            name: 'IT',
            change: -0.85,
            marketCap: 1800000,
            volume: 280000000,
            advances: 3,
            declines: 7,
            unchanged: 2,
            stocks: [
                { symbol: 'TCS', name: 'TCS', change: -1.2, price: 3850, marketCap: 1400000, volume: 2500000 },
                { symbol: 'INFY', name: 'Infosys', change: -0.6, price: 1480, marketCap: 620000, volume: 5500000 },
                { symbol: 'WIPRO', name: 'Wipro', change: 0.3, price: 450, marketCap: 235000, volume: 6200000 },
            ]
        },
        {
            name: 'Auto',
            change: 2.15,
            marketCap: 1200000,
            volume: 320000000,
            advances: 9,
            declines: 2,
            unchanged: 1,
            stocks: [
                { symbol: 'TATAMOTORS', name: 'Tata Motors', change: 3.2, price: 920, marketCap: 340000, volume: 18000000 },
                { symbol: 'M&M', name: 'M&M', change: 1.8, price: 1650, marketCap: 205000, volume: 4500000 },
                { symbol: 'MARUTI', name: 'Maruti', change: 0.9, price: 10200, marketCap: 310000, volume: 1200000 },
            ]
        },
        {
            name: 'Pharma',
            change: 0.65,
            marketCap: 850000,
            volume: 180000000,
            advances: 6,
            declines: 5,
            unchanged: 1,
            stocks: [
                { symbol: 'SUNPHARMA', name: 'Sun Pharma', change: 1.1, price: 1180, marketCap: 285000, volume: 3800000 },
                { symbol: 'DRREDDY', name: "Dr Reddy's", change: -0.4, price: 5450, marketCap: 91000, volume: 650000 },
                { symbol: 'CIPLA', name: 'Cipla', change: 0.8, price: 1210, marketCap: 98000, volume: 2100000 },
            ]
        },
        {
            name: 'Energy',
            change: 1.92,
            marketCap: 2200000,
            volume: 380000000,
            advances: 7,
            declines: 3,
            unchanged: 0,
            stocks: [
                { symbol: 'RELIANCE', name: 'Reliance', change: 2.1, price: 2850, marketCap: 1930000, volume: 8500000 },
                { symbol: 'ONGC', name: 'ONGC', change: 1.5, price: 275, marketCap: 345000, volume: 12000000 },
            ]
        },
        {
            name: 'FMCG',
            change: -0.32,
            marketCap: 1100000,
            volume: 150000000,
            advances: 4,
            declines: 6,
            unchanged: 2,
            stocks: [
                { symbol: 'HINDUNILVR', name: 'HUL', change: -0.8, price: 2650, marketCap: 625000, volume: 1800000 },
                { symbol: 'ITC', name: 'ITC', change: 0.5, price: 445, marketCap: 555000, volume: 9500000 },
            ]
        },
        {
            name: 'Metals',
            change: 3.25,
            marketCap: 650000,
            volume: 420000000,
            advances: 10,
            declines: 2,
            unchanged: 0,
            stocks: [
                { symbol: 'TATASTEEL', name: 'Tata Steel', change: 4.2, price: 142, marketCap: 175000, volume: 35000000 },
                { symbol: 'HINDALCO', name: 'Hindalco', change: 3.1, price: 545, marketCap: 122000, volume: 8500000 },
                { symbol: 'JSWSTEEL', name: 'JSW Steel', change: 2.8, price: 880, marketCap: 215000, volume: 5200000 },
            ]
        },
        {
            name: 'Realty',
            change: -1.45,
            marketCap: 280000,
            volume: 95000000,
            advances: 2,
            declines: 8,
            unchanged: 1,
            stocks: [
                { symbol: 'DLF', name: 'DLF', change: -2.1, price: 820, marketCap: 203000, volume: 4500000 },
                { symbol: 'GODREJPROP', name: 'Godrej Prop', change: -0.9, price: 2450, marketCap: 68000, volume: 1200000 },
            ]
        },
    ], []);

    const sectors = sectorData.length > 0 ? sectorData : mockData;

    const totalMarketCap = sectors.reduce((sum, s) => sum + s.marketCap, 0);

    const getColor = (change: number) => {
        if (change > 3) return 'from-green-600 to-green-500';
        if (change > 1.5) return 'from-green-500 to-green-400';
        if (change > 0) return 'from-green-400/80 to-green-300/80';
        if (change === 0) return 'from-gray-500 to-gray-400';
        if (change > -1.5) return 'from-red-400/80 to-red-300/80';
        if (change > -3) return 'from-red-500 to-red-400';
        return 'from-red-600 to-red-500';
    };

    const getBgColor = (change: number) => {
        if (change > 3) return 'bg-green-600';
        if (change > 1.5) return 'bg-green-500';
        if (change > 0) return 'bg-green-400/80';
        if (change === 0) return 'bg-gray-500';
        if (change > -1.5) return 'bg-red-400/80';
        if (change > -3) return 'bg-red-500';
        return 'bg-red-600';
    };

    const handleSectorClick = (sectorName: string) => {
        setSelectedSector(sectorName);
        setViewMode('stocks');
        onSectorClick?.(sectorName);
    };

    const selectedSectorData = sectors.find(s => s.name === selectedSector);

    if (loading) {
        return (
            <Card className="glass rounded-2xl overflow-hidden">
                <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10 py-4">
                    <CardTitle className="text-xl font-bold">Sector Heatmap</CardTitle>
                </CardHeader>
                <CardContent className="p-4">
                    <div className="flex items-center justify-center h-[400px]">
                        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="glass rounded-2xl overflow-hidden">
            <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10 py-4">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <CardTitle className="text-xl font-bold">Sector Heatmap</CardTitle>
                        {selectedSector && viewMode === 'stocks' && (
                            <button 
                                onClick={() => { setViewMode('sectors'); setSelectedSector(null); }}
                                className="text-sm text-muted-foreground hover:text-foreground"
                            >
                                ← Back to Sectors
                            </button>
                        )}
                    </div>
                    <div className="flex items-center gap-4 text-xs">
                        <div className="flex items-center gap-1">
                            <span className="w-3 h-3 rounded bg-green-500"></span>
                            <span className="text-muted-foreground">Gainers</span>
                        </div>
                        <div className="flex items-center gap-1">
                            <span className="w-3 h-3 rounded bg-red-500"></span>
                            <span className="text-muted-foreground">Losers</span>
                        </div>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="p-4">
                <TooltipProvider>
                    {viewMode === 'sectors' ? (
                        <div className="grid grid-cols-4 gap-2 auto-rows-fr min-h-[400px]">
                            {sectors
                                .sort((a, b) => b.marketCap - a.marketCap)
                                .map((sector) => {
                                    const widthPercent = (sector.marketCap / totalMarketCap) * 100;
                                    const gridCols = widthPercent > 20 ? 2 : 1;
                                    
                                    return (
                                        <Tooltip key={sector.name}>
                                            <TooltipTrigger asChild>
                                                <div
                                                    className={`relative rounded-lg p-3 cursor-pointer transition-all hover:scale-[1.02] hover:z-10 bg-gradient-to-br ${getColor(sector.change)} text-white overflow-hidden`}
                                                    style={{ 
                                                        gridColumn: `span ${gridCols}`,
                                                        gridRow: widthPercent > 20 ? 'span 2' : 'span 1'
                                                    }}
                                                    onClick={() => handleSectorClick(sector.name)}
                                                >
                                                    <div className="relative z-10">
                                                        <p className="font-bold text-lg truncate">{sector.name}</p>
                                                        <p className="text-2xl font-bold mt-1">
                                                            {sector.change > 0 ? '+' : ''}{sector.change.toFixed(2)}%
                                                        </p>
                                                        <div className="flex items-center gap-2 mt-2 text-xs opacity-90">
                                                            <span className="flex items-center gap-1">
                                                                <TrendingUp className="h-3 w-3" /> {sector.advances}
                                                            </span>
                                                            <span className="flex items-center gap-1">
                                                                <TrendingDown className="h-3 w-3" /> {sector.declines}
                                                            </span>
                                                        </div>
                                                    </div>
                                                </div>
                                            </TooltipTrigger>
                                            <TooltipContent className="glass border-border/50">
                                                <div className="p-2">
                                                    <p className="font-bold">{sector.name}</p>
                                                    <p className="text-sm">Market Cap: ₹{(sector.marketCap / 1000).toFixed(0)}K Cr</p>
                                                    <p className="text-sm">Volume: {(sector.volume / 10000000).toFixed(1)} Cr</p>
                                                    <p className="text-sm">{sector.advances}A / {sector.declines}D / {sector.unchanged}U</p>
                                                </div>
                                            </TooltipContent>
                                        </Tooltip>
                                    );
                                })}
                        </div>
                    ) : selectedSectorData ? (
                        <div className="space-y-4">
                            {/* Sector Header */}
                            <div className={`p-4 rounded-lg ${getBgColor(selectedSectorData.change)} text-white`}>
                                <div className="flex items-center justify-between">
                                    <div>
                                        <h3 className="text-2xl font-bold">{selectedSectorData.name}</h3>
                                        <p className="text-sm opacity-90">
                                            {selectedSectorData.advances} Advancing | {selectedSectorData.declines} Declining
                                        </p>
                                    </div>
                                    <div className="text-right">
                                        <p className="text-3xl font-bold">
                                            {selectedSectorData.change > 0 ? '+' : ''}{selectedSectorData.change.toFixed(2)}%
                                        </p>
                                    </div>
                                </div>
                            </div>

                            {/* Stocks Grid */}
                            <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
                                {selectedSectorData.stocks
                                    .sort((a, b) => b.marketCap - a.marketCap)
                                    .map((stock) => (
                                        <Tooltip key={stock.symbol}>
                                            <TooltipTrigger asChild>
                                                <div
                                                    className={`p-3 rounded-lg cursor-pointer transition-all hover:scale-[1.02] ${getBgColor(stock.change)} text-white`}
                                                    onClick={() => onStockClick?.(stock.symbol)}
                                                >
                                                    <p className="font-bold truncate">{stock.symbol}</p>
                                                    <p className="text-lg font-bold mt-1">
                                                        {stock.change > 0 ? '+' : ''}{stock.change.toFixed(2)}%
                                                    </p>
                                                    <p className="text-xs opacity-80">₹{stock.price.toLocaleString()}</p>
                                                </div>
                                            </TooltipTrigger>
                                            <TooltipContent className="glass border-border/50">
                                                <div className="p-2">
                                                    <p className="font-bold">{stock.name}</p>
                                                    <p className="text-sm">Price: ₹{stock.price.toLocaleString()}</p>
                                                    <p className="text-sm">M.Cap: ₹{(stock.marketCap / 1000).toFixed(0)}K Cr</p>
                                                </div>
                                            </TooltipContent>
                                        </Tooltip>
                                    ))}
                            </div>
                        </div>
                    ) : null}
                </TooltipProvider>
            </CardContent>
        </Card>
    );
}
