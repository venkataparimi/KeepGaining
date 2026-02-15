"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    TrendingUp,
    TrendingDown,
    Filter,
    Download,
    RefreshCw,
    Target,
    AlertTriangle,
    Clock,
    BarChart3,
    PieChart as PieChartIcon,
    Activity,
    Zap,
    DollarSign,
    Percent,
} from "lucide-react";
import {
    ResponsiveContainer,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    Tooltip,
    CartesianGrid,
    Cell,
    PieChart,
    Pie,
    Legend,
    LineChart,
    Line,
    Area,
    AreaChart,
} from "recharts";

// Types
interface Trade {
    trade_id: number;
    strategy_id: string;
    strategy_name: string;
    symbol: string;
    option_symbol: string | null;
    option_type: string | null;
    strike_price: number | null;
    expiry_date: string | null;
    sector: string | null;
    trade_date: string;
    entry_time: string;
    exit_time: string | null;
    hold_duration_minutes: number | null;
    entry_premium: number;
    exit_premium: number | null;
    momentum_pct: number | null;
    exit_reason: string | null;
    pnl_pct: number | null;
    pnl_amount: number | null;
    is_winner: boolean | null;
    signal_strength: string | null;
    quantity: number | null;
}

interface Summary {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number;
    total_pnl_pct: number;
    avg_pnl_pct: number;
    avg_win_pct: number | null;
    avg_loss_pct: number | null;
    avg_hold_minutes: number | null;
    best_trade_pct: number | null;
    worst_trade_pct: number | null;
    total_pnl_amount: number | null;
    avg_pnl_amount: number | null;
}

interface EquityCurvePoint {
    trade_number: number;
    trade_date: string;
    symbol: string;
    pnl_pct: number;
    pnl_amount: number;
    cumulative_pnl_pct: number;
    cumulative_pnl_amount: number;
    drawdown_pct: number;
}

interface SectorPerf {
    sector: string;
    total_trades: number;
    win_rate: number;
    total_pnl_pct: number;
    [key: string]: any;
}

interface SymbolPerf {
    symbol: string;
    sector: string | null;
    total_trades: number;
    win_rate: number;
    total_pnl_pct: number;
}

interface DailyPerf {
    trade_date: string;
    total_trades: number;
    win_rate: number;
    total_pnl_pct: number;
}

interface Filters {
    strategies: { id: string; name: string }[];
    symbols: string[];
    sectors: string[];
    exit_reasons: string[];
    date_range: { min: string | null; max: string | null };
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

const CHART_COLORS = {
    primary: "#3b82f6",
    secondary: "#8b5cf6",
    accent: "#10b981",
    warning: "#f59e0b",
    danger: "#ef4444",
    success: "#22c55e",
    muted: "#64748b",
};

const SECTOR_COLORS = [
    "#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444",
    "#ec4899", "#14b8a6", "#f97316", "#06b6d4", "#84cc16"
];

export default function StrategyTradesExplorer() {
    // State
    const [trades, setTrades] = useState<Trade[]>([]);
    const [summary, setSummary] = useState<Summary | null>(null);
    const [sectorData, setSectorData] = useState<SectorPerf[]>([]);
    const [symbolData, setSymbolData] = useState<SymbolPerf[]>([]);
    const [dailyData, setDailyData] = useState<DailyPerf[]>([]);
    const [equityCurve, setEquityCurve] = useState<EquityCurvePoint[]>([]);
    const [filters, setFilters] = useState<Filters | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Filter state
    const [selectedStrategy, setSelectedStrategy] = useState<string>("all");
    const [selectedSymbol, setSelectedSymbol] = useState<string>("all");
    const [selectedSector, setSelectedSector] = useState<string>("all");
    const [selectedOptionType, setSelectedOptionType] = useState<string>("all");
    const [selectedExitReason, setSelectedExitReason] = useState<string>("all");
    const [startDate, setStartDate] = useState<string>("");
    const [endDate, setEndDate] = useState<string>("");
    const [isWinner, setIsWinner] = useState<string>("all");

    // View state
    const [activeTab, setActiveTab] = useState<"trades" | "analytics">("trades");

    // Build query params
    const buildQueryParams = useCallback(() => {
        const params = new URLSearchParams();
        if (selectedStrategy !== "all") params.append("strategy_id", selectedStrategy);
        if (selectedSymbol !== "all") params.append("symbol", selectedSymbol);
        if (selectedSector !== "all") params.append("sector", selectedSector);
        if (selectedOptionType !== "all") params.append("option_type", selectedOptionType);
        if (selectedExitReason !== "all") params.append("exit_reason", selectedExitReason);
        if (startDate) params.append("start_date", startDate);
        if (endDate) params.append("end_date", endDate);
        if (isWinner !== "all") params.append("is_winner", isWinner);
        return params.toString();
    }, [selectedStrategy, selectedSymbol, selectedSector, selectedOptionType, selectedExitReason, startDate, endDate, isWinner]);

    // Fetch trades data (main view)
    const fetchTradesData = useCallback(async () => {
        setLoading(true);
        setError(null);
        const queryString = buildQueryParams();

        try {
            // Only fetch essential data for trades view
            const [tradesRes, summaryRes] = await Promise.all([
                fetch(`${API_BASE}/strategy-trades/trades?${queryString}&limit=100`),
                fetch(`${API_BASE}/strategy-trades/summary?${queryString}`),
            ]);

            if (tradesRes.ok) {
                setTrades(await tradesRes.json());
            }
            if (summaryRes.ok) {
                setSummary(await summaryRes.json());
            }
        } catch (err) {
            setError("Failed to fetch data. Please check if the API is running.");
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [buildQueryParams]);

    // Fetch analytics data (lazy loaded when Analytics tab is clicked)
    const [analyticsLoaded, setAnalyticsLoaded] = useState(false);
    const fetchAnalyticsData = useCallback(async () => {
        if (analyticsLoaded) return; // Already loaded

        const queryString = buildQueryParams();
        try {
            const [sectorRes, symbolRes, dailyRes, equityRes] = await Promise.all([
                fetch(`${API_BASE}/strategy-trades/by-sector?${queryString}`),
                fetch(`${API_BASE}/strategy-trades/by-symbol?${queryString}&limit=10`),
                fetch(`${API_BASE}/strategy-trades/daily?${queryString}&limit=30`),
                fetch(`${API_BASE}/strategy-trades/equity-curve?${queryString}`),
            ]);

            if (sectorRes.ok) setSectorData(await sectorRes.json());
            if (symbolRes.ok) setSymbolData(await symbolRes.json());
            if (dailyRes.ok) setDailyData((await dailyRes.json()).reverse());
            if (equityRes.ok) setEquityCurve(await equityRes.json());
            setAnalyticsLoaded(true);
        } catch (err) {
            console.error("Failed to fetch analytics:", err);
        }
    }, [buildQueryParams, analyticsLoaded]);

    // Fetch filters
    const fetchFilters = async () => {
        try {
            const res = await fetch(`${API_BASE}/strategy-trades/filters`);
            if (res.ok) {
                const data = await res.json();
                setFilters(data);
                if (data.date_range.min) setStartDate(data.date_range.min);
                if (data.date_range.max) setEndDate(data.date_range.max);
            }
        } catch (err) {
            console.error("Failed to fetch filters:", err);
        }
    };

    useEffect(() => {
        fetchFilters();
    }, []);

    useEffect(() => {
        fetchTradesData();
        setAnalyticsLoaded(false); // Reset analytics when filters change
    }, [fetchTradesData]);

    // Load analytics data when Analytics tab is clicked
    useEffect(() => {
        if (activeTab === "analytics") {
            fetchAnalyticsData();
        }
    }, [activeTab, fetchAnalyticsData]);

    // Reset filters
    const resetFilters = () => {
        setSelectedStrategy("all");
        setSelectedSymbol("all");
        setSelectedSector("all");
        setSelectedOptionType("all");
        setSelectedExitReason("all");
        setIsWinner("all");
        if (filters?.date_range.min) setStartDate(filters.date_range.min);
        if (filters?.date_range.max) setEndDate(filters.date_range.max);
        setAnalyticsLoaded(false);
    };

    // Export to CSV
    const exportToCSV = () => {
        const headers = [
            "Date", "Symbol", "Option", "Strike", "Type", "Entry Time", "Exit Time",
            "Entry Premium", "Exit Premium", "P&L %", "Exit Reason", "Sector", "Strength"
        ];
        const rows = trades.map(t => [
            t.trade_date, t.symbol, t.option_symbol || "", t.strike_price || "",
            t.option_type || "", t.entry_time, t.exit_time || "",
            t.entry_premium, t.exit_premium || "", t.pnl_pct?.toFixed(2) || "",
            t.exit_reason || "", t.sector || "", t.signal_strength || ""
        ]);

        const csv = [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
        const blob = new Blob([csv], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `strategy_trades_${new Date().toISOString().split("T")[0]}.csv`;
        a.click();
    };

    // Format functions
    const formatPnL = (pnl: number | null) => {
        if (pnl === null) return <span className="text-slate-500">-</span>;
        const isPositive = pnl >= 0;
        return (
            <span className={`inline-flex items-center gap-1 font-semibold ${isPositive ? "text-emerald-400" : "text-red-400"}`}>
                {isPositive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                {isPositive ? "+" : ""}{pnl.toFixed(2)}%
            </span>
        );
    };

    const formatTime = (time: string) => {
        return new Date(time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
    };

    const formatDate = (dateStr: string) => {
        return new Date(dateStr).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
    };

    // Custom tooltip for charts
    const CustomTooltip = ({ active, payload, label }: any) => {
        if (active && payload && payload.length) {
            return (
                <div className="bg-slate-800 border border-slate-600 rounded-lg p-3 shadow-xl">
                    <p className="text-slate-300 text-sm mb-1">{label}</p>
                    {payload.map((entry: any, index: number) => (
                        <p key={index} className="text-sm font-medium" style={{ color: entry.color }}>
                            {entry.name}: {typeof entry.value === 'number' ? entry.value.toFixed(2) : entry.value}
                            {entry.name.includes('%') || entry.name.includes('Rate') || entry.name.includes('P&L') ? '%' : ''}
                        </p>
                    ))}
                </div>
            );
        }
        return null;
    };

    return (
        <div className="p-6 space-y-6 min-h-screen">
            {/* Header */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h1 className="text-3xl font-bold gradient-text">Strategy Trades Explorer</h1>
                    <p className="text-slate-400 mt-1">
                        Analyze historical and live strategy performance
                    </p>
                </div>
                <div className="flex gap-3">
                    <Button
                        variant="outline"
                        onClick={resetFilters}
                        className="border-slate-600 hover:bg-slate-700 hover:border-slate-500"
                    >
                        <RefreshCw className="w-4 h-4 mr-2" />
                        Reset
                    </Button>
                    <Button
                        onClick={exportToCSV}
                        className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500"
                    >
                        <Download className="w-4 h-4 mr-2" />
                        Export CSV
                    </Button>
                </div>
            </div>

            {/* Filters */}
            <Card className="glass border-slate-700/50">
                <CardHeader className="pb-3">
                    <CardTitle className="text-lg flex items-center gap-2 text-slate-200">
                        <Filter className="w-5 h-5 text-blue-400" />
                        Filters
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
                        <Select value={selectedStrategy} onValueChange={setSelectedStrategy}>
                            <SelectTrigger className="bg-slate-800/50 border-slate-600 text-slate-200">
                                <SelectValue placeholder="Strategy" />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-800 border-slate-600">
                                <SelectItem value="all">All Strategies</SelectItem>
                                {filters?.strategies.map(s => (
                                    <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        <Select value={selectedSector} onValueChange={setSelectedSector}>
                            <SelectTrigger className="bg-slate-800/50 border-slate-600 text-slate-200">
                                <SelectValue placeholder="Sector" />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-800 border-slate-600">
                                <SelectItem value="all">All Sectors</SelectItem>
                                {filters?.sectors.map(s => (
                                    <SelectItem key={s} value={s}>{s}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        <Select value={selectedSymbol} onValueChange={setSelectedSymbol}>
                            <SelectTrigger className="bg-slate-800/50 border-slate-600 text-slate-200">
                                <SelectValue placeholder="Symbol" />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-800 border-slate-600">
                                <SelectItem value="all">All Symbols</SelectItem>
                                {filters?.symbols.slice(0, 50).map(s => (
                                    <SelectItem key={s} value={s}>{s}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        <Select value={selectedOptionType} onValueChange={setSelectedOptionType}>
                            <SelectTrigger className="bg-slate-800/50 border-slate-600 text-slate-200">
                                <SelectValue placeholder="Type" />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-800 border-slate-600">
                                <SelectItem value="all">CE & PE</SelectItem>
                                <SelectItem value="CE">CE Only</SelectItem>
                                <SelectItem value="PE">PE Only</SelectItem>
                            </SelectContent>
                        </Select>

                        <Select value={selectedExitReason} onValueChange={setSelectedExitReason}>
                            <SelectTrigger className="bg-slate-800/50 border-slate-600 text-slate-200">
                                <SelectValue placeholder="Exit Reason" />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-800 border-slate-600">
                                <SelectItem value="all">All Exits</SelectItem>
                                {filters?.exit_reasons.map(r => (
                                    <SelectItem key={r} value={r}>{r}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        <Select value={isWinner} onValueChange={setIsWinner}>
                            <SelectTrigger className="bg-slate-800/50 border-slate-600 text-slate-200">
                                <SelectValue placeholder="Result" />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-800 border-slate-600">
                                <SelectItem value="all">All</SelectItem>
                                <SelectItem value="true">Winners</SelectItem>
                                <SelectItem value="false">Losers</SelectItem>
                            </SelectContent>
                        </Select>

                        <Input
                            type="date"
                            value={startDate}
                            onChange={e => setStartDate(e.target.value)}
                            className="bg-slate-800/50 border-slate-600 text-slate-200"
                        />

                        <Input
                            type="date"
                            value={endDate}
                            onChange={e => setEndDate(e.target.value)}
                            className="bg-slate-800/50 border-slate-600 text-slate-200"
                        />
                    </div>
                </CardContent>
            </Card>

            {/* Summary Cards */}
            {summary && (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                    <Card className="glass border-slate-700/50 hover-lift">
                        <CardContent className="pt-5">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Total Trades</p>
                                    <p className="text-3xl font-bold text-slate-100">{summary.total_trades}</p>
                                </div>
                                <div className="p-3 rounded-xl bg-blue-500/10">
                                    <Activity className="w-6 h-6 text-blue-400" />
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="glass border-slate-700/50 hover-lift">
                        <CardContent className="pt-5">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Win Rate</p>
                                    <p className={`text-3xl font-bold ${summary.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                                        {summary.win_rate.toFixed(1)}%
                                    </p>
                                </div>
                                <div className={`p-3 rounded-xl ${summary.win_rate >= 50 ? 'bg-emerald-500/10' : 'bg-amber-500/10'}`}>
                                    <Target className={`w-6 h-6 ${summary.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`} />
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="glass border-slate-700/50 hover-lift">
                        <CardContent className="pt-5">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Total P&L</p>
                                    <p className={`text-3xl font-bold ${summary.total_pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                        {summary.total_pnl_pct >= 0 ? "+" : ""}{summary.total_pnl_pct.toFixed(1)}%
                                    </p>
                                </div>
                                <div className={`p-3 rounded-xl ${summary.total_pnl_pct >= 0 ? 'bg-emerald-500/10' : 'bg-red-500/10'}`}>
                                    <DollarSign className={`w-6 h-6 ${summary.total_pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`} />
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="glass border-slate-700/50 hover-lift">
                        <CardContent className="pt-5">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Avg Win</p>
                                    <p className="text-3xl font-bold text-emerald-400">
                                        +{summary.avg_win_pct?.toFixed(1) || 0}%
                                    </p>
                                </div>
                                <div className="p-3 rounded-xl bg-emerald-500/10">
                                    <TrendingUp className="w-6 h-6 text-emerald-400" />
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="glass border-slate-700/50 hover-lift">
                        <CardContent className="pt-5">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Avg Loss</p>
                                    <p className="text-3xl font-bold text-red-400">
                                        {summary.avg_loss_pct?.toFixed(1) || 0}%
                                    </p>
                                </div>
                                <div className="p-3 rounded-xl bg-red-500/10">
                                    <TrendingDown className="w-6 h-6 text-red-400" />
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="glass border-slate-700/50 hover-lift">
                        <CardContent className="pt-5">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Avg Hold</p>
                                    <p className="text-3xl font-bold text-purple-400">
                                        {Math.round(summary.avg_hold_minutes || 0)}m
                                    </p>
                                </div>
                                <div className="p-3 rounded-xl bg-purple-500/10">
                                    <Clock className="w-6 h-6 text-purple-400" />
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}

            {/* Tab Switch */}
            <div className="flex gap-2">
                <Button
                    variant={activeTab === "trades" ? "default" : "outline"}
                    onClick={() => setActiveTab("trades")}
                    className={activeTab === "trades"
                        ? "bg-gradient-to-r from-blue-600 to-purple-600"
                        : "border-slate-600 hover:bg-slate-700"}
                >
                    <BarChart3 className="w-4 h-4 mr-2" />
                    Trade History
                </Button>
                <Button
                    variant={activeTab === "analytics" ? "default" : "outline"}
                    onClick={() => setActiveTab("analytics")}
                    className={activeTab === "analytics"
                        ? "bg-gradient-to-r from-blue-600 to-purple-600"
                        : "border-slate-600 hover:bg-slate-700"}
                >
                    <PieChartIcon className="w-4 h-4 mr-2" />
                    Analytics
                </Button>
            </div>

            {/* Content based on tab */}
            {activeTab === "trades" ? (
                /* Trade History Table */
                <Card className="glass border-slate-700/50">
                    <CardHeader className="border-b border-slate-700/50">
                        <CardTitle className="text-slate-200 flex items-center gap-2">
                            <Zap className="w-5 h-5 text-amber-400" />
                            Trade History
                            <Badge variant="secondary" className="ml-2 bg-slate-700 text-slate-300">
                                {trades.length} trades
                            </Badge>
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                        {loading ? (
                            <div className="flex items-center justify-center py-16">
                                <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-blue-500"></div>
                            </div>
                        ) : error ? (
                            <div className="text-center py-16 text-red-400">{error}</div>
                        ) : trades.length === 0 ? (
                            <div className="text-center py-16 text-slate-500">
                                No trades found. Run the backtest script to generate data.
                            </div>
                        ) : (
                            <div className="overflow-x-auto scrollbar-thin">
                                <Table>
                                    <TableHeader>
                                        <TableRow className="border-slate-700/50 hover:bg-transparent">
                                            <TableHead className="text-slate-400 font-medium">Date</TableHead>
                                            <TableHead className="text-slate-400 font-medium">Symbol</TableHead>
                                            <TableHead className="text-slate-400 font-medium">Option</TableHead>
                                            <TableHead className="text-slate-400 font-medium">Expiry</TableHead>
                                            <TableHead className="text-slate-400 font-medium">Entry</TableHead>
                                            <TableHead className="text-slate-400 font-medium">Exit</TableHead>
                                            <TableHead className="text-slate-400 font-medium">P&L %</TableHead>
                                            <TableHead className="text-slate-400 font-medium">P&L ₹</TableHead>
                                            <TableHead className="text-slate-400 font-medium">Exit Reason</TableHead>
                                            <TableHead className="text-slate-400 font-medium">Hold</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {trades.map((trade) => (
                                            <TableRow
                                                key={trade.trade_id}
                                                className="border-slate-700/30 hover:bg-slate-800/50 transition-colors"
                                            >
                                                <TableCell className="font-medium text-slate-300">
                                                    {formatDate(trade.trade_date)}
                                                </TableCell>
                                                <TableCell className="text-slate-200 font-semibold">
                                                    {trade.symbol}
                                                </TableCell>
                                                <TableCell>
                                                    <Badge
                                                        className={`${trade.option_type === "CE"
                                                            ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                                                            : "bg-red-500/20 text-red-400 border-red-500/30"}`}
                                                    >
                                                        {trade.strike_price} {trade.option_type}
                                                    </Badge>
                                                </TableCell>
                                                <TableCell className="text-slate-400 text-sm">
                                                    {trade.expiry_date ? formatDate(trade.expiry_date) : "-"}
                                                </TableCell>
                                                <TableCell className="text-slate-300">
                                                    <div className="font-medium">₹{trade.entry_premium.toFixed(2)}</div>
                                                    <div className="text-xs text-slate-500">
                                                        {formatTime(trade.entry_time)}
                                                    </div>
                                                </TableCell>
                                                <TableCell className="text-slate-300">
                                                    <div className="font-medium">₹{trade.exit_premium?.toFixed(2) || "-"}</div>
                                                    <div className="text-xs text-slate-500">
                                                        {trade.exit_time ? formatTime(trade.exit_time) : "-"}
                                                    </div>
                                                </TableCell>
                                                <TableCell>{formatPnL(trade.pnl_pct)}</TableCell>
                                                <TableCell>
                                                    {trade.pnl_amount !== null ? (
                                                        <span className={`font-semibold ${trade.pnl_amount >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                                            {trade.pnl_amount >= 0 ? '+' : ''}₹{trade.pnl_amount.toFixed(0)}
                                                        </span>
                                                    ) : (
                                                        <span className="text-slate-500">-</span>
                                                    )}
                                                </TableCell>
                                                <TableCell>
                                                    <Badge
                                                        className={`${trade.exit_reason?.includes("Target")
                                                            ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                                                            : trade.exit_reason?.includes("Stop")
                                                                ? "bg-red-500/20 text-red-400 border-red-500/30"
                                                                : "bg-amber-500/20 text-amber-400 border-amber-500/30"
                                                            }`}
                                                    >
                                                        {trade.exit_reason?.replace(/\s*\([^)]*\)/g, '') || "-"}
                                                    </Badge>
                                                </TableCell>
                                                <TableCell className="text-slate-400">{trade.hold_duration_minutes}m</TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                        )}
                    </CardContent>
                </Card>
            ) : (
                /* Analytics View */
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Sector Win Rate Pie Chart */}
                    <Card className="glass border-slate-700/50">
                        <CardHeader className="border-b border-slate-700/50">
                            <CardTitle className="text-slate-200 flex items-center gap-2">
                                <PieChartIcon className="w-5 h-5 text-purple-400" />
                                Win Rate by Sector
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-6">
                            <ResponsiveContainer width="100%" height={300}>
                                <PieChart>
                                    <Pie
                                        data={sectorData}
                                        dataKey="total_trades"
                                        nameKey="sector"
                                        cx="50%"
                                        cy="50%"
                                        innerRadius={60}
                                        outerRadius={100}
                                        paddingAngle={2}
                                        label={({ sector, win_rate }: any) => `${sector}: ${win_rate}%`}
                                        labelLine={{ stroke: '#64748b' }}
                                    >
                                        {sectorData.map((_, index) => (
                                            <Cell key={index} fill={SECTOR_COLORS[index % SECTOR_COLORS.length]} />
                                        ))}
                                    </Pie>
                                    <Tooltip content={<CustomTooltip />} />
                                </PieChart>
                            </ResponsiveContainer>
                        </CardContent>
                    </Card>

                    {/* Top 10 Symbols */}
                    <Card className="glass border-slate-700/50">
                        <CardHeader className="border-b border-slate-700/50">
                            <CardTitle className="text-slate-200 flex items-center gap-2">
                                <BarChart3 className="w-5 h-5 text-blue-400" />
                                Top 10 Performing Symbols
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-6">
                            <ResponsiveContainer width="100%" height={300}>
                                <BarChart data={symbolData} layout="vertical" margin={{ left: 10 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                                    <XAxis type="number" stroke="#64748b" />
                                    <YAxis dataKey="symbol" type="category" width={80} stroke="#64748b" tick={{ fill: '#94a3b8' }} />
                                    <Tooltip content={<CustomTooltip />} />
                                    <Bar dataKey="total_pnl_pct" name="Total P&L %" radius={[0, 4, 4, 0]}>
                                        {symbolData.map((entry, index) => (
                                            <Cell
                                                key={index}
                                                fill={entry.total_pnl_pct >= 0 ? CHART_COLORS.success : CHART_COLORS.danger}
                                            />
                                        ))}
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        </CardContent>
                    </Card>

                    {/* Daily P&L Trend */}
                    <Card className="glass border-slate-700/50 lg:col-span-2">
                        <CardHeader className="border-b border-slate-700/50">
                            <CardTitle className="text-slate-200 flex items-center gap-2">
                                <Activity className="w-5 h-5 text-emerald-400" />
                                Daily Performance Trend
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-6">
                            <ResponsiveContainer width="100%" height={300}>
                                <AreaChart data={dailyData}>
                                    <defs>
                                        <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                                            <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                                        </linearGradient>
                                        <linearGradient id="winRateGradient" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                                    <XAxis
                                        dataKey="trade_date"
                                        tickFormatter={(date) => formatDate(date)}
                                        stroke="#64748b"
                                        tick={{ fill: '#94a3b8' }}
                                    />
                                    <YAxis stroke="#64748b" tick={{ fill: '#94a3b8' }} />
                                    <Tooltip content={<CustomTooltip />} />
                                    <Legend wrapperStyle={{ color: '#94a3b8' }} />
                                    <Area
                                        type="monotone"
                                        dataKey="total_pnl_pct"
                                        stroke="#10b981"
                                        strokeWidth={2}
                                        fill="url(#pnlGradient)"
                                        name="Daily P&L %"
                                    />
                                    <Line
                                        type="monotone"
                                        dataKey="win_rate"
                                        stroke="#3b82f6"
                                        strokeWidth={2}
                                        dot={{ r: 3, fill: '#3b82f6' }}
                                        name="Win Rate %"
                                    />
                                </AreaChart>
                            </ResponsiveContainer>
                        </CardContent>
                    </Card>

                    {/* Equity Curve & Drawdown */}
                    <Card className="glass border-slate-700/50 lg:col-span-2">
                        <CardHeader className="border-b border-slate-700/50">
                            <CardTitle className="text-slate-200 flex items-center gap-2">
                                <DollarSign className="w-5 h-5 text-amber-400" />
                                Equity Curve & Drawdown (₹ per trade @ 25 lot)
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-6">
                            {equityCurve.length > 0 ? (
                                <ResponsiveContainer width="100%" height={350}>
                                    <AreaChart data={equityCurve}>
                                        <defs>
                                            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                                                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                                            </linearGradient>
                                            <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4} />
                                                <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                                            </linearGradient>
                                        </defs>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                                        <XAxis
                                            dataKey="trade_number"
                                            stroke="#64748b"
                                            tick={{ fill: '#94a3b8' }}
                                            label={{ value: 'Trade #', position: 'insideBottom', offset: -5, fill: '#64748b' }}
                                        />
                                        <YAxis
                                            yAxisId="equity"
                                            stroke="#10b981"
                                            tick={{ fill: '#94a3b8' }}
                                            tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}K`}
                                        />
                                        <YAxis
                                            yAxisId="drawdown"
                                            orientation="right"
                                            stroke="#ef4444"
                                            tick={{ fill: '#94a3b8' }}
                                            tickFormatter={(v) => `${v}%`}
                                            domain={[0, 'auto']}
                                        />
                                        <Tooltip
                                            content={({ active, payload }) => {
                                                if (active && payload && payload.length) {
                                                    const data = payload[0].payload as EquityCurvePoint;
                                                    return (
                                                        <div className="bg-slate-800 border border-slate-600 rounded-lg p-3 shadow-xl">
                                                            <p className="text-slate-300 text-sm mb-1">Trade #{data.trade_number}</p>
                                                            <p className="text-slate-400 text-xs mb-2">{data.symbol} • {formatDate(data.trade_date)}</p>
                                                            <p className={`text-sm font-medium ${data.pnl_amount >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                                                Trade P&L: {data.pnl_amount >= 0 ? '+' : ''}₹{data.pnl_amount.toFixed(0)}
                                                            </p>
                                                            <p className={`text-sm font-medium ${data.cumulative_pnl_amount >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                                                Cumulative: {data.cumulative_pnl_amount >= 0 ? '+' : ''}₹{data.cumulative_pnl_amount.toFixed(0)}
                                                            </p>
                                                            <p className="text-sm text-red-400">
                                                                Drawdown: {data.drawdown_pct.toFixed(1)}%
                                                            </p>
                                                        </div>
                                                    );
                                                }
                                                return null;
                                            }}
                                        />
                                        <Legend wrapperStyle={{ color: '#94a3b8' }} />
                                        <Area
                                            yAxisId="equity"
                                            type="monotone"
                                            dataKey="cumulative_pnl_amount"
                                            stroke="#10b981"
                                            strokeWidth={2}
                                            fill="url(#equityGradient)"
                                            name="Cumulative P&L (₹)"
                                        />
                                        <Area
                                            yAxisId="drawdown"
                                            type="monotone"
                                            dataKey="drawdown_pct"
                                            stroke="#ef4444"
                                            strokeWidth={2}
                                            fill="url(#drawdownGradient)"
                                            name="Drawdown %"
                                        />
                                    </AreaChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="text-center py-8 text-slate-500">No equity data available</div>
                            )}
                            {equityCurve.length > 0 && (
                                <div className="grid grid-cols-4 gap-4 mt-4 pt-4 border-t border-slate-700/50">
                                    <div className="text-center">
                                        <p className="text-slate-400 text-xs uppercase">Total P&L</p>
                                        <p className={`text-xl font-bold ${equityCurve[equityCurve.length - 1]?.cumulative_pnl_amount >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                            {equityCurve[equityCurve.length - 1]?.cumulative_pnl_amount >= 0 ? '+' : ''}₹{equityCurve[equityCurve.length - 1]?.cumulative_pnl_amount.toLocaleString() || 0}
                                        </p>
                                    </div>
                                    <div className="text-center">
                                        <p className="text-slate-400 text-xs uppercase">Max Drawdown</p>
                                        <p className="text-xl font-bold text-red-400">
                                            {Math.max(...equityCurve.map(e => e.drawdown_pct)).toFixed(1)}%
                                        </p>
                                    </div>
                                    <div className="text-center">
                                        <p className="text-slate-400 text-xs uppercase">Avg Trade</p>
                                        <p className={`text-xl font-bold ${(equityCurve.reduce((sum, e) => sum + e.pnl_amount, 0) / equityCurve.length) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                            ₹{(equityCurve.reduce((sum, e) => sum + e.pnl_amount, 0) / equityCurve.length).toFixed(0)}
                                        </p>
                                    </div>
                                    <div className="text-center">
                                        <p className="text-slate-400 text-xs uppercase">Trades</p>
                                        <p className="text-xl font-bold text-blue-400">
                                            {equityCurve.length}
                                        </p>
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Sector Performance Table */}
                    <Card className="glass border-slate-700/50 lg:col-span-2">
                        <CardHeader className="border-b border-slate-700/50">
                            <CardTitle className="text-slate-200 flex items-center gap-2">
                                <Target className="w-5 h-5 text-amber-400" />
                                Sector Performance
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-4">
                            <Table>
                                <TableHeader>
                                    <TableRow className="border-slate-700/50 hover:bg-transparent">
                                        <TableHead className="text-slate-400 font-medium">Sector</TableHead>
                                        <TableHead className="text-slate-400 font-medium text-right">Trades</TableHead>
                                        <TableHead className="text-slate-400 font-medium text-right">Win Rate</TableHead>
                                        <TableHead className="text-slate-400 font-medium text-right">Total P&L</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {sectorData.map((sector, idx) => (
                                        <TableRow key={sector.sector} className="border-slate-700/30 hover:bg-slate-800/50">
                                            <TableCell className="font-medium text-slate-200 flex items-center gap-2">
                                                <div
                                                    className="w-3 h-3 rounded-full"
                                                    style={{ backgroundColor: SECTOR_COLORS[idx % SECTOR_COLORS.length] }}
                                                />
                                                {sector.sector}
                                            </TableCell>
                                            <TableCell className="text-right text-slate-300">{sector.total_trades}</TableCell>
                                            <TableCell className="text-right">
                                                <Badge
                                                    className={`${sector.win_rate >= 50
                                                        ? "bg-emerald-500/20 text-emerald-400"
                                                        : "bg-amber-500/20 text-amber-400"}`}
                                                >
                                                    {sector.win_rate.toFixed(1)}%
                                                </Badge>
                                            </TableCell>
                                            <TableCell className="text-right">{formatPnL(sector.total_pnl_pct)}</TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                </div>
            )}
        </div>
    );
}
