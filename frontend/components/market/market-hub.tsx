"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { 
    TrendingUp, TrendingDown, BarChart3, Grid3X3, 
    Table2, Activity, RefreshCw, Clock 
} from "lucide-react";
import { SectorTreemap } from "./sector-treemap";
import { OptionChainViewer } from "./option-chain";
import { IndexMultiTimeframe } from "./index-multi-timeframe";

export function MarketHub() {
    const [activeTab, setActiveTab] = useState('overview');
    const [lastUpdated, setLastUpdated] = useState(new Date());

    // Market breadth data
    const marketBreadth = {
        advances: 1245,
        declines: 856,
        unchanged: 125,
        newHighs: 45,
        newLows: 12,
        aboveVWAP: 1120,
        belowVWAP: 1106,
    };

    const advDecRatio = marketBreadth.advances / marketBreadth.declines;

    return (
        <div className="flex-1 space-y-6 p-6 pt-4 max-w-[1800px] mx-auto">
            {/* Header */}
            <div className="relative overflow-hidden rounded-2xl glass p-6">
                <div className="absolute inset-0 gradient-bg opacity-30"></div>
                <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-4xl font-bold gradient-text mb-2">Market Intelligence</h1>
                        <p className="text-muted-foreground">Real-time market data, sector analysis, and option chain</p>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <Clock className="h-4 w-4" />
                            Last updated: {lastUpdated.toLocaleTimeString()}
                        </div>
                        <Button variant="outline" size="sm" onClick={() => setLastUpdated(new Date())}>
                            <RefreshCw className="h-4 w-4 mr-2" /> Refresh
                        </Button>
                    </div>
                </div>
            </div>

            {/* Market Breadth Summary */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-6">
                <div className="glass rounded-xl p-4 hover-lift">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-muted-foreground">Advances</span>
                        <TrendingUp className="h-4 w-4 text-green-400" />
                    </div>
                    <p className="text-2xl font-bold text-green-400">{marketBreadth.advances}</p>
                </div>
                <div className="glass rounded-xl p-4 hover-lift">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-muted-foreground">Declines</span>
                        <TrendingDown className="h-4 w-4 text-red-400" />
                    </div>
                    <p className="text-2xl font-bold text-red-400">{marketBreadth.declines}</p>
                </div>
                <div className="glass rounded-xl p-4 hover-lift">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-muted-foreground">A/D Ratio</span>
                        <Activity className="h-4 w-4 text-blue-400" />
                    </div>
                    <p className={`text-2xl font-bold ${advDecRatio > 1 ? 'text-green-400' : 'text-red-400'}`}>
                        {advDecRatio.toFixed(2)}
                    </p>
                </div>
                <div className="glass rounded-xl p-4 hover-lift">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-muted-foreground">New Highs</span>
                        <TrendingUp className="h-4 w-4 text-green-400" />
                    </div>
                    <p className="text-2xl font-bold text-green-400">{marketBreadth.newHighs}</p>
                </div>
                <div className="glass rounded-xl p-4 hover-lift">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-muted-foreground">New Lows</span>
                        <TrendingDown className="h-4 w-4 text-red-400" />
                    </div>
                    <p className="text-2xl font-bold text-red-400">{marketBreadth.newLows}</p>
                </div>
                <div className="glass rounded-xl p-4 hover-lift">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-muted-foreground">Above VWAP</span>
                        <BarChart3 className="h-4 w-4 text-purple-400" />
                    </div>
                    <p className="text-2xl font-bold text-purple-400">{marketBreadth.aboveVWAP}</p>
                </div>
            </div>

            {/* Breadth Indicator Bar */}
            <div className="glass rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium">Market Breadth</span>
                    <span className={`text-sm font-bold ${advDecRatio > 1.2 ? 'text-green-400' : advDecRatio < 0.8 ? 'text-red-400' : 'text-yellow-400'}`}>
                        {advDecRatio > 1.2 ? 'Bullish' : advDecRatio < 0.8 ? 'Bearish' : 'Neutral'}
                    </span>
                </div>
                <div className="h-4 bg-muted/30 rounded-full overflow-hidden flex">
                    <div 
                        className="h-full bg-gradient-to-r from-green-600 to-green-400"
                        style={{ width: `${(marketBreadth.advances / (marketBreadth.advances + marketBreadth.declines + marketBreadth.unchanged)) * 100}%` }}
                    ></div>
                    <div 
                        className="h-full bg-gray-500"
                        style={{ width: `${(marketBreadth.unchanged / (marketBreadth.advances + marketBreadth.declines + marketBreadth.unchanged)) * 100}%` }}
                    ></div>
                    <div 
                        className="h-full bg-gradient-to-r from-red-400 to-red-600"
                        style={{ width: `${(marketBreadth.declines / (marketBreadth.advances + marketBreadth.declines + marketBreadth.unchanged)) * 100}%` }}
                    ></div>
                </div>
                <div className="flex justify-between text-xs text-muted-foreground mt-1">
                    <span>{((marketBreadth.advances / (marketBreadth.advances + marketBreadth.declines + marketBreadth.unchanged)) * 100).toFixed(1)}% Advancing</span>
                    <span>{((marketBreadth.declines / (marketBreadth.advances + marketBreadth.declines + marketBreadth.unchanged)) * 100).toFixed(1)}% Declining</span>
                </div>
            </div>

            {/* Tabbed Content */}
            <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
                <TabsList className="glass p-1 gap-1">
                    <TabsTrigger value="overview" className="data-[state=active]:bg-primary/20">
                        <Grid3X3 className="h-4 w-4 mr-2" /> Sector Heatmap
                    </TabsTrigger>
                    <TabsTrigger value="indices" className="data-[state=active]:bg-primary/20">
                        <Activity className="h-4 w-4 mr-2" /> Index Analysis
                    </TabsTrigger>
                    <TabsTrigger value="options" className="data-[state=active]:bg-primary/20">
                        <Table2 className="h-4 w-4 mr-2" /> Option Chain
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="overview">
                    <SectorTreemap />
                </TabsContent>

                <TabsContent value="indices">
                    <IndexMultiTimeframe />
                </TabsContent>

                <TabsContent value="options" className="space-y-6">
                    {/* Option Chain Index Selector */}
                    <div className="flex gap-2">
                        <Button variant="secondary" size="sm">NIFTY</Button>
                        <Button variant="outline" size="sm">BANKNIFTY</Button>
                        <Button variant="outline" size="sm">FINNIFTY</Button>
                    </div>
                    <OptionChainViewer symbol="NIFTY" spotPrice={24523.50} />
                </TabsContent>
            </Tabs>
        </div>
    );
}
