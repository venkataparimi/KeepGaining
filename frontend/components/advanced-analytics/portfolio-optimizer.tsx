"use client";

import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { 
    PieChart, 
    Scale, 
    TrendingUp, 
    Shield, 
    Target,
    RefreshCw,
    Plus,
    X,
    AlertTriangle,
    CheckCircle2,
    BarChart3
} from "lucide-react";
import { apiClient, PortfolioOptimizationResult, PortfolioRiskMetrics } from "@/lib/api/client";

export function PortfolioOptimizer() {
    const [selectedSymbols, setSelectedSymbols] = useState<string[]>(["RELIANCE", "TCS", "HDFCBANK"]);
    const [newSymbol, setNewSymbol] = useState<string>("");
    const [method, setMethod] = useState<string>("mean_variance");
    const [targetReturn, setTargetReturn] = useState<number>(12);
    const [riskFreeRate, setRiskFreeRate] = useState<number>(6);
    const [optimization, setOptimization] = useState<PortfolioOptimizationResult | null>(null);
    const [riskMetrics, setRiskMetrics] = useState<PortfolioRiskMetrics | null>(null);
    const [loading, setLoading] = useState(false);
    const [frontier, setFrontier] = useState<any[]>([]);

    const availableSymbols = [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", 
        "HINDUNILVR", "ITC", "KOTAKBANK", "LT", "AXISBANK", "BAJFINANCE",
        "MARUTI", "TITAN", "ASIANPAINT", "SUNPHARMA", "WIPRO", "TECHM"
    ];

    const addSymbol = () => {
        if (newSymbol && !selectedSymbols.includes(newSymbol)) {
            setSelectedSymbols([...selectedSymbols, newSymbol]);
            setNewSymbol("");
        }
    };

    const removeSymbol = (symbol: string) => {
        setSelectedSymbols(selectedSymbols.filter(s => s !== symbol));
    };

    const runOptimization = async () => {
        if (selectedSymbols.length < 2) return;
        setLoading(true);
        try {
            const result = await apiClient.optimizePortfolio(
                selectedSymbols,
                method,
                targetReturn / 100,
                riskFreeRate / 100
            );
            setOptimization(result);
            
            // Also get risk metrics with optimized weights
            if (result.weights) {
                const risk = await apiClient.getPortfolioRiskMetrics(selectedSymbols, result.weights);
                setRiskMetrics(risk);
            }
        } catch (error) {
            console.error("Failed to optimize portfolio:", error);
        } finally {
            setLoading(false);
        }
    };

    const loadEfficientFrontier = async () => {
        if (selectedSymbols.length < 2) return;
        setLoading(true);
        try {
            const result = await apiClient.getEfficientFrontier(selectedSymbols, 20);
            setFrontier(result.frontier);
        } catch (error) {
            console.error("Failed to load efficient frontier:", error);
        } finally {
            setLoading(false);
        }
    };

    const getWeightColor = (weight: number) => {
        if (weight >= 0.3) return "bg-blue-500";
        if (weight >= 0.2) return "bg-blue-400";
        if (weight >= 0.1) return "bg-blue-300";
        return "bg-blue-200";
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold flex items-center gap-2">
                        <PieChart className="h-6 w-6 text-indigo-500" />
                        Portfolio Optimizer
                    </h2>
                    <p className="text-muted-foreground">
                        Optimize portfolio allocation using modern portfolio theory
                    </p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Configuration Panel */}
                <Card className="lg:col-span-1">
                    <CardHeader>
                        <CardTitle className="text-lg">Configuration</CardTitle>
                        <CardDescription>Select assets and optimization parameters</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        {/* Symbol Selection */}
                        <div className="space-y-2">
                            <Label>Portfolio Assets</Label>
                            <div className="flex gap-2">
                                <Select value={newSymbol} onValueChange={setNewSymbol}>
                                    <SelectTrigger className="flex-1">
                                        <SelectValue placeholder="Add symbol" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {availableSymbols
                                            .filter(s => !selectedSymbols.includes(s))
                                            .map((s) => (
                                                <SelectItem key={s} value={s}>{s}</SelectItem>
                                            ))}
                                    </SelectContent>
                                </Select>
                                <Button onClick={addSymbol} size="icon" disabled={!newSymbol}>
                                    <Plus className="h-4 w-4" />
                                </Button>
                            </div>
                            <div className="flex flex-wrap gap-2 mt-2">
                                {selectedSymbols.map((symbol) => (
                                    <Badge key={symbol} variant="secondary" className="pr-1">
                                        {symbol}
                                        <button
                                            title={`Remove ${symbol}`}
                                            onClick={() => removeSymbol(symbol)}
                                            className="ml-1 hover:text-destructive"
                                        >
                                            <X className="h-3 w-3" />
                                        </button>
                                    </Badge>
                                ))}
                            </div>
                            {selectedSymbols.length < 2 && (
                                <p className="text-xs text-muted-foreground">
                                    Add at least 2 symbols to optimize
                                </p>
                            )}
                        </div>

                        {/* Optimization Method */}
                        <div className="space-y-2">
                            <Label>Optimization Method</Label>
                            <Select value={method} onValueChange={setMethod}>
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="mean_variance">Mean-Variance (Markowitz)</SelectItem>
                                    <SelectItem value="risk_parity">Risk Parity</SelectItem>
                                    <SelectItem value="max_sharpe">Maximum Sharpe Ratio</SelectItem>
                                    <SelectItem value="min_volatility">Minimum Volatility</SelectItem>
                                    <SelectItem value="black_litterman">Black-Litterman</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        {/* Target Return */}
                        <div className="space-y-2">
                            <div className="flex justify-between">
                                <Label>Target Annual Return</Label>
                                <span className="text-sm text-muted-foreground">{targetReturn}%</span>
                            </div>
                            <Slider
                                value={[targetReturn]}
                                onValueChange={(v) => setTargetReturn(v[0])}
                                min={5}
                                max={30}
                                step={1}
                            />
                        </div>

                        {/* Risk-Free Rate */}
                        <div className="space-y-2">
                            <div className="flex justify-between">
                                <Label>Risk-Free Rate</Label>
                                <span className="text-sm text-muted-foreground">{riskFreeRate}%</span>
                            </div>
                            <Slider
                                value={[riskFreeRate]}
                                onValueChange={(v) => setRiskFreeRate(v[0])}
                                min={2}
                                max={10}
                                step={0.5}
                            />
                        </div>

                        <Button 
                            onClick={runOptimization} 
                            className="w-full"
                            disabled={loading || selectedSymbols.length < 2}
                        >
                            {loading ? (
                                <>
                                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                                    Optimizing...
                                </>
                            ) : (
                                <>
                                    <Target className="h-4 w-4 mr-2" />
                                    Optimize Portfolio
                                </>
                            )}
                        </Button>
                    </CardContent>
                </Card>

                {/* Results Panel */}
                <Card className="lg:col-span-2">
                    <CardHeader>
                        <CardTitle className="text-lg">Optimization Results</CardTitle>
                        <CardDescription>
                            {optimization ? `${optimization.optimization_method} optimization` : "Run optimization to see results"}
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {!optimization ? (
                            <div className="text-center py-12 text-muted-foreground">
                                <PieChart className="h-16 w-16 mx-auto mb-4 opacity-20" />
                                <p>Configure parameters and click Optimize</p>
                            </div>
                        ) : (
                            <Tabs defaultValue="weights" className="space-y-4">
                                <TabsList>
                                    <TabsTrigger value="weights">Weights</TabsTrigger>
                                    <TabsTrigger value="metrics">Metrics</TabsTrigger>
                                    <TabsTrigger value="risk">Risk Analysis</TabsTrigger>
                                </TabsList>

                                <TabsContent value="weights" className="space-y-4">
                                    {/* Portfolio Allocation */}
                                    <div className="space-y-3">
                                        {Object.entries(optimization.weights)
                                            .sort((a, b) => b[1] - a[1])
                                            .map(([symbol, weight]) => (
                                                <div key={symbol} className="space-y-1">
                                                    <div className="flex justify-between text-sm">
                                                        <span className="font-medium">{symbol}</span>
                                                        <span>{(weight * 100).toFixed(1)}%</span>
                                                    </div>
                                                    <div className="h-3 bg-muted rounded-full overflow-hidden">
                                                        <div 
                                                            className={`h-full ${getWeightColor(weight)} transition-all`}
                                                            style={{ width: `${weight * 100}%` }}
                                                        />
                                                    </div>
                                                </div>
                                            ))}
                                    </div>

                                    {/* Recommendations */}
                                    {optimization.recommendations && optimization.recommendations.length > 0 && (
                                        <div className="pt-4 border-t">
                                            <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                                                <CheckCircle2 className="h-4 w-4 text-green-500" />
                                                Recommendations
                                            </h4>
                                            <ul className="space-y-1 text-sm text-muted-foreground">
                                                {optimization.recommendations.map((rec, idx) => (
                                                    <li key={idx}>• {rec}</li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                </TabsContent>

                                <TabsContent value="metrics" className="space-y-4">
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="p-4 bg-muted rounded-lg">
                                            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                                                <TrendingUp className="h-4 w-4" />
                                                Expected Return
                                            </div>
                                            <div className="text-2xl font-bold text-green-500">
                                                {(optimization.expected_return * 100).toFixed(2)}%
                                            </div>
                                            <div className="text-xs text-muted-foreground">Annual</div>
                                        </div>

                                        <div className="p-4 bg-muted rounded-lg">
                                            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                                                <AlertTriangle className="h-4 w-4" />
                                                Volatility
                                            </div>
                                            <div className="text-2xl font-bold text-orange-500">
                                                {(optimization.expected_volatility * 100).toFixed(2)}%
                                            </div>
                                            <div className="text-xs text-muted-foreground">Annual</div>
                                        </div>

                                        <div className="p-4 bg-muted rounded-lg">
                                            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                                                <Scale className="h-4 w-4" />
                                                Sharpe Ratio
                                            </div>
                                            <div className="text-2xl font-bold text-blue-500">
                                                {optimization.sharpe_ratio.toFixed(2)}
                                            </div>
                                            <div className="text-xs text-muted-foreground">Risk-Adjusted</div>
                                        </div>

                                        <div className="p-4 bg-muted rounded-lg">
                                            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                                                <Shield className="h-4 w-4" />
                                                Max Drawdown
                                            </div>
                                            <div className="text-2xl font-bold text-red-500">
                                                {(optimization.max_drawdown * 100).toFixed(2)}%
                                            </div>
                                            <div className="text-xs text-muted-foreground">Historical</div>
                                        </div>
                                    </div>

                                    <div className="p-4 bg-muted rounded-lg">
                                        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                                            <BarChart3 className="h-4 w-4" />
                                            Diversification Ratio
                                        </div>
                                        <div className="flex items-center gap-4">
                                            <div className="text-2xl font-bold">
                                                {optimization.diversification_ratio.toFixed(2)}
                                            </div>
                                            <Progress 
                                                value={Math.min(optimization.diversification_ratio * 50, 100)} 
                                                className="flex-1 h-3" 
                                            />
                                        </div>
                                        <div className="text-xs text-muted-foreground mt-1">
                                            Higher ratio indicates better diversification
                                        </div>
                                    </div>
                                </TabsContent>

                                <TabsContent value="risk" className="space-y-4">
                                    {riskMetrics ? (
                                        <>
                                            <div className="grid grid-cols-2 gap-4">
                                                <div className="p-4 border rounded-lg">
                                                    <div className="text-sm text-muted-foreground mb-1">VaR (95%)</div>
                                                    <div className="text-xl font-bold text-red-500">
                                                        {(riskMetrics.var_95 * 100).toFixed(2)}%
                                                    </div>
                                                    <div className="text-xs text-muted-foreground">
                                                        Daily Value at Risk
                                                    </div>
                                                </div>

                                                <div className="p-4 border rounded-lg">
                                                    <div className="text-sm text-muted-foreground mb-1">VaR (99%)</div>
                                                    <div className="text-xl font-bold text-red-600">
                                                        {(riskMetrics.var_99 * 100).toFixed(2)}%
                                                    </div>
                                                    <div className="text-xs text-muted-foreground">
                                                        Daily Value at Risk
                                                    </div>
                                                </div>

                                                <div className="p-4 border rounded-lg">
                                                    <div className="text-sm text-muted-foreground mb-1">CVaR (95%)</div>
                                                    <div className="text-xl font-bold text-orange-500">
                                                        {(riskMetrics.cvar_95 * 100).toFixed(2)}%
                                                    </div>
                                                    <div className="text-xs text-muted-foreground">
                                                        Expected Shortfall
                                                    </div>
                                                </div>

                                                <div className="p-4 border rounded-lg">
                                                    <div className="text-sm text-muted-foreground mb-1">Portfolio Beta</div>
                                                    <div className="text-xl font-bold">
                                                        {riskMetrics.beta.toFixed(2)}
                                                    </div>
                                                    <div className="text-xs text-muted-foreground">
                                                        vs Market
                                                    </div>
                                                </div>
                                            </div>

                                            {/* Sector Exposure */}
                                            {riskMetrics.sector_exposure && Object.keys(riskMetrics.sector_exposure).length > 0 && (
                                                <div className="pt-4 border-t">
                                                    <h4 className="text-sm font-medium mb-3">Sector Exposure</h4>
                                                    <div className="space-y-2">
                                                        {Object.entries(riskMetrics.sector_exposure).map(([sector, exposure]) => (
                                                            <div key={sector} className="flex items-center gap-2">
                                                                <span className="text-sm w-24 truncate">{sector}</span>
                                                                <Progress value={exposure * 100} className="flex-1 h-2" />
                                                                <span className="text-sm text-muted-foreground w-12 text-right">
                                                                    {(exposure * 100).toFixed(0)}%
                                                                </span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            <div className="p-4 bg-yellow-100 dark:bg-yellow-900/30 rounded-lg">
                                                <div className="flex items-start gap-2">
                                                    <AlertTriangle className="h-5 w-5 text-yellow-600 mt-0.5" />
                                                    <div>
                                                        <div className="font-medium text-yellow-800 dark:text-yellow-200">
                                                            Concentration Risk: {(riskMetrics.concentration_risk * 100).toFixed(1)}%
                                                        </div>
                                                        <div className="text-sm text-yellow-700 dark:text-yellow-300">
                                                            {riskMetrics.concentration_risk > 0.5 
                                                                ? "High concentration - consider adding more assets"
                                                                : "Concentration within acceptable limits"}
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </>
                                    ) : (
                                        <div className="text-center py-8 text-muted-foreground">
                                            <Shield className="h-12 w-12 mx-auto mb-4 opacity-20" />
                                            <p>Risk metrics will appear after optimization</p>
                                        </div>
                                    )}
                                </TabsContent>
                            </Tabs>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
