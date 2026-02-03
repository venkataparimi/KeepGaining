"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Play, Square, Settings, Code, RefreshCw, PlusCircle } from "lucide-react";
import { apiClient } from "@/lib/api/client";

interface Strategy {
    name: string;
    description?: string;
}

export function StrategyEditor() {
    const [strategies, setStrategies] = useState<Strategy[]>([]);
    const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);
    const [loading, setLoading] = useState(true);
    const [config, setConfig] = useState({
        underlying: "NSE:NIFTY50-INDEX",
        expiry_date: "28NOV",
        quantity: "50",
        fast_ema: "9",
        slow_ema: "21",
        sl_percentage: "0.10",
        target_percentage: "0.20"
    });

    useEffect(() => {
        fetchStrategies();
    }, []);

    const fetchStrategies = async () => {
        try {
            setLoading(true);
            const data = await apiClient.listStrategies();
            setStrategies(data || []);
        } catch (error) {
            console.error("Failed to fetch strategies:", error);
        } finally {
            setLoading(false);
        }
    };

    const handleDeploy = async () => {
        if (!selectedStrategy) return;

        try {
            const deployConfig = {
                underlying: config.underlying,
                expiry_date: config.expiry_date,
                quantity: parseInt(config.quantity),
                fast_ema: parseInt(config.fast_ema),
                slow_ema: parseInt(config.slow_ema),
                sl_percentage: parseFloat(config.sl_percentage),
                target_percentage: parseFloat(config.target_percentage)
            };

            const result = await apiClient.deployStrategy(selectedStrategy.name, deployConfig);
            alert(`Strategy deployed: ${result.message}`);
        } catch (error: any) {
            alert(`Failed to deploy: ${error.message}`);
        }
    };

    return (
        <div className="flex-1 space-y-6 p-8 pt-6 max-w-[1600px] mx-auto">
            {/* Header */}
            <div className="relative overflow-hidden rounded-2xl glass p-8 ">
                <div className="absolute inset-0 gradient-bg opacity-30"></div>
                <div className="relative z-10 flex items-center justify-between">
                    <div>
                        <h1 className="text-4xl font-bold gradient-text mb-2">Strategy Management</h1>
                        <p className="text-muted-foreground">Deploy and manage your trading strategies</p>
                    </div>
                    <Button onClick={fetchStrategies} variant="outline" className="border-primary/30">
                        <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </Button>
                </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-7">
                {/* Strategy List */}
                <div className="lg:col-span-3">
                    <div className="glass rounded-2xl overflow-hidden">
                        <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10">
                            <CardTitle className="text-xl font-bold">Available Strategies</CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                            {loading ? (
                                <div className="p-8 text-center text-muted-foreground">
                                    <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-2" />
                                    Loading...
                                </div>
                            ) : (
                                <Table>
                                    <TableHeader>
                                        <TableRow className="border-border/50 hover:bg-transparent">
                                            <TableHead className="font-semibold">Strategy Name</TableHead>
                                            <TableHead className="text-right font-semibold">Action</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {strategies.map((strat, idx) => (
                                            <TableRow
                                                key={strat.name + idx}
                                                className={`cursor-pointer border-border/50 smooth-transition hover:bg-primary/5 ${selectedStrategy?.name === strat.name ? 'bg-primary/10' : ''}`}
                                                onClick={() => setSelectedStrategy(strat)}
                                            >
                                                <TableCell className="font-medium">
                                                    <div>
                                                        <div className="font-bold text-foreground">{strat.name}</div>
                                                        <div className="text-xs text-muted-foreground">{strat.description || 'Trading strategy'}</div>
                                                    </div>
                                                </TableCell>
                                                <TableCell className="text-right">
                                                    <Button variant="ghost" size="sm">
                                                        <Settings className="h-4 w-4" />
                                                    </Button>
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            )}
                        </CardContent>
                    </div>
                </div>

                {/* Configuration Panel */}
                <div className="lg:col-span-4">
                    <div className="glass rounded-2xl overflow-hidden">
                        <CardHeader className="bg-gradient-to-r from-accent/10 to-primary/10">
                            <CardTitle className="text-xl font-bold">
                                {selectedStrategy ? `Deploy: ${selectedStrategy.name}` : "Select  a Strategy"}
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-6">
                            {selectedStrategy ? (
                                <div className="space-y-6">
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-2">
                                            <Label htmlFor="underlying">Underlying</Label>
                                            <Input
                                                id="underlying"
                                                value={config.underlying}
                                                onChange={(e) => setConfig({ ...config, underlying: e.target.value })}
                                                placeholder="NSE:NIFTY50-INDEX"
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="expiry">Expiry Date</Label>
                                            <Input
                                                id="expiry"
                                                value={config.expiry_date}
                                                onChange={(e) => setConfig({ ...config, expiry_date: e.target.value })}
                                                placeholder="28NOV"
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="quantity">Quantity</Label>
                                            <Input
                                                id="quantity"
                                                type="number"
                                                value={config.quantity}
                                                onChange={(e) => setConfig({ ...config, quantity: e.target.value })}
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="fast_ema">Fast EMA</Label>
                                            <Input
                                                id="fast_ema"
                                                type="number"
                                                value={config.fast_ema}
                                                onChange={(e) => setConfig({ ...config, fast_ema: e.target.value })}
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="slow_ema">Slow EMA</Label>
                                            <Input
                                                id="slow_ema"
                                                type="number"
                                                value={config.slow_ema}
                                                onChange={(e) => setConfig({ ...config, slow_ema: e.target.value })}
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="sl">Stop Loss %</Label>
                                            <Input
                                                id="sl"
                                                type="number"
                                                step="0.01"
                                                value={config.sl_percentage}
                                                onChange={(e) => setConfig({ ...config, sl_percentage: e.target.value })}
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="target">Target %</Label>
                                            <Input
                                                id="target"
                                                type="number"
                                                step="0.01"
                                                value={config.target_percentage}
                                                onChange={(e) => setConfig({ ...config, target_percentage: e.target.value })}
                                            />
                                        </div>
                                    </div>

                                    <div className="space-y-2">
                                        <Label>Configuration Preview</Label>
                                        <div className="rounded-md bg-muted p-4">
                                            <pre className="text-sm text-foreground overflow-x-auto">
                                                {JSON.stringify({
                                                    strategy: selectedStrategy.name,
                                                    underlying: config.underlying,
                                                    expiry_date: config.expiry_date,
                                                    quantity: parseInt(config.quantity),
                                                    fast_ema: parseInt(config.fast_ema),
                                                    slow_ema: parseInt(config.slow_ema),
                                                    sl_percentage: parseFloat(config.sl_percentage),
                                                    target_percentage: parseFloat(config.target_percentage)
                                                }, null, 2)}
                                            </pre>
                                        </div>
                                    </div>

                                    <div className="flex space-x-3">
                                        <Button onClick={handleDeploy} className="flex-1 bg-gradient-to-r from-primary to-secondary hover:opacity-90">
                                            <Play className="mr-2 h-4 w-4" />
                                            Deploy Strategy
                                        </Button>
                                        <Button variant="outline" className="flex-1 border-primary/30">
                                            <Code className="mr-2 h-4 w-4" />
                                            View Code
                                        </Button>
                                    </div>
                                </div>
                            ) : (
                                <div className="flex h-[400px] items-center justify-center text-muted-foreground">
                                    <div className="text-center">
                                        <PlusCircle className="h-16 w-16 mx-auto mb-4 opacity-50" />
                                        <p>Select a strategy from the list to configure and deploy</p>
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    </div>
                </div>
            </div>
        </div>
    );
}
