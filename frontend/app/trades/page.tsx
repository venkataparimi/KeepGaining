"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import {
    Calendar, Download, Filter, Search, TrendingUp, TrendingDown,
    CheckCircle2, XCircle, Clock, Target, FileText, Zap, Activity
} from "lucide-react"
import { cn } from "@/lib/utils"

interface Trade {
    date: string
    stock: string
    strike: number
    option_type: string
    entry_time: string
    entry_premium: number
    exit_time: string
    exit_premium: number
    option_pnl_pct: number
    option_pnl_amount: number
    exit_reason: string
    trade_type: string
}

export default function TradeLogPage() {
    const [trades, setTrades] = useState<Trade[]>([])
    const [filteredTrades, setFilteredTrades] = useState<Trade[]>([])
    const [loading, setLoading] = useState(true)
    const [selectedType, setSelectedType] = useState<string>("all")
    const [searchTerm, setSearchTerm] = useState("")
    const [selectedMonth, setSelectedMonth] = useState<string>("all")

    useEffect(() => {
        fetchTrades()
    }, [])

    useEffect(() => {
        filterTrades()
    }, [selectedType, searchTerm, selectedMonth, trades])

    const fetchTrades = async () => {
        try {
            // In production, this would load from your CSV files or database
            // For now, we'll create sample data structure
            const response = await fetch('http://localhost:8000/api/strategy/trades?limit=1000')
            const data = await response.json()

            // If API returns data, use it; otherwise use empty array
            setTrades(data.trades || [])
        } catch (error) {
            console.error('Error fetching trades:', error)
            // Load sample data for demonstration
            loadSampleTrades()
        } finally {
            setLoading(false)
        }
    }

    const loadSampleTrades = () => {
        // Sample trades for demonstration
        const sampleTrades: Trade[] = [
            {
                date: "2025-12-02",
                stock: "RELIANCE",
                strike: 1300,
                option_type: "CE",
                entry_time: "2025-12-02T09:30:00",
                entry_premium: 45.50,
                exit_time: "2025-12-02T11:45:00",
                exit_premium: 68.25,
                option_pnl_pct: 50.0,
                option_pnl_amount: 11375,
                exit_reason: "Target (50%)",
                trade_type: "backtest"
            },
            {
                date: "2025-12-03",
                stock: "TATASTEEL",
                strike: 160,
                option_type: "PE",
                entry_time: "2025-12-03T09:30:00",
                entry_premium: 3.25,
                exit_time: "2025-12-03T14:30:00",
                exit_premium: 2.15,
                option_pnl_pct: -33.8,
                option_pnl_amount: -4400,
                exit_reason: "Time (2:30PM)",
                trade_type: "backtest"
            }
        ]
        setTrades(sampleTrades)
    }

    const filterTrades = () => {
        let filtered = [...trades]

        // Filter by trade type
        if (selectedType !== "all") {
            filtered = filtered.filter(t => t.trade_type === selectedType)
        }

        // Filter by search term
        if (searchTerm) {
            filtered = filtered.filter(t =>
                t.stock.toLowerCase().includes(searchTerm.toLowerCase()) ||
                t.option_type.toLowerCase().includes(searchTerm.toLowerCase())
            )
        }

        // Filter by month
        if (selectedMonth !== "all") {
            filtered = filtered.filter(t => t.date.startsWith(selectedMonth))
        }

        setFilteredTrades(filtered)
    }

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            maximumFractionDigits: 0
        }).format(amount)
    }

    const formatTime = (timestamp: string) => {
        return new Date(timestamp).toLocaleTimeString('en-IN', {
            hour: '2-digit',
            minute: '2-digit'
        })
    }

    const getTradeTypeBadge = (type: string) => {
        const badges: Record<string, JSX.Element> = {
            backtest: <Badge variant="secondary" className="bg-blue-500/20 text-blue-400">📊 Backtest</Badge>,
            paper: <Badge variant="outline" className="bg-yellow-500/20 text-yellow-400">📝 Paper</Badge>,
            live: <Badge className="bg-green-500/20 text-green-400">🔴 Live</Badge>
        }
        return badges[type] || badges.backtest
    }

    const stats = {
        total: filteredTrades.length,
        wins: filteredTrades.filter(t => t.option_pnl_pct > 0).length,
        losses: filteredTrades.filter(t => t.option_pnl_pct < 0).length,
        totalPnL: filteredTrades.reduce((sum, t) => sum + t.option_pnl_amount, 0),
        winRate: filteredTrades.length > 0
            ? (filteredTrades.filter(t => t.option_pnl_pct > 0).length / filteredTrades.length * 100)
            : 0
    }

    const downloadCSV = () => {
        const headers = ['Date', 'Stock', 'Strike', 'Type', 'Entry Time', 'Entry Premium',
            'Exit Time', 'Exit Premium', 'P&L %', 'P&L Amount', 'Exit Reason', 'Trade Type']

        const csvContent = [
            headers.join(','),
            ...filteredTrades.map(t => [
                t.date,
                t.stock,
                t.strike,
                t.option_type,
                formatTime(t.entry_time),
                t.entry_premium,
                formatTime(t.exit_time),
                t.exit_premium,
                t.option_pnl_pct.toFixed(2),
                t.option_pnl_amount,
                t.exit_reason,
                t.trade_type
            ].join(','))
        ].join('\n')

        const blob = new Blob([csvContent], { type: 'text/csv' })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `morning-momentum-alpha-trades-${new Date().toISOString().split('T')[0]}.csv`
        a.click()
    }

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-950 via-blue-950 to-slate-950 p-6">
            <div className="max-w-7xl mx-auto space-y-6">

                {/* Header */}
                <div className="glass-card rounded-2xl p-6 border border-white/10">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-4xl font-bold text-white mb-2">
                                Trade Log & Journal
                            </h1>
                            <p className="text-white/60">
                                Morning Momentum Alpha • Complete Trade History
                            </p>
                        </div>
                        <Button
                            onClick={downloadCSV}
                            className="bg-gradient-to-r from-blue-500 to-cyan-600"
                        >
                            <Download className="h-4 w-4 mr-2" />
                            Export CSV
                        </Button>
                    </div>
                </div>

                {/* Stats Cards */}
                <div className="grid gap-4 md:grid-cols-5">
                    <div className="glass-card rounded-xl p-4 border border-white/10">
                        <div className="text-sm text-white/60 mb-1">Total Trades</div>
                        <div className="text-2xl font-bold text-white">{stats.total}</div>
                    </div>
                    <div className="glass-card rounded-xl p-4 border border-white/10">
                        <div className="text-sm text-white/60 mb-1">Wins</div>
                        <div className="text-2xl font-bold text-green-400">{stats.wins}</div>
                    </div>
                    <div className="glass-card rounded-xl p-4 border border-white/10">
                        <div className="text-sm text-white/60 mb-1">Losses</div>
                        <div className="text-2xl font-bold text-red-400">{stats.losses}</div>
                    </div>
                    <div className="glass-card rounded-xl p-4 border border-white/10">
                        <div className="text-sm text-white/60 mb-1">Win Rate</div>
                        <div className="text-2xl font-bold text-blue-400">{stats.winRate.toFixed(1)}%</div>
                    </div>
                    <div className="glass-card rounded-xl p-4 border border-white/10">
                        <div className="text-sm text-white/60 mb-1">Total P&L</div>
                        <div className={cn(
                            "text-2xl font-bold",
                            stats.totalPnL >= 0 ? "text-green-400" : "text-red-400"
                        )}>
                            {formatCurrency(stats.totalPnL)}
                        </div>
                    </div>
                </div>

                {/* Filters */}
                <div className="glass-card rounded-xl p-6 border border-white/10">
                    <div className="flex flex-wrap gap-4">
                        {/* Trade Type Filter */}
                        <div className="flex gap-2">
                            <Button
                                variant={selectedType === "all" ? "default" : "outline"}
                                size="sm"
                                onClick={() => setSelectedType("all")}
                                className={selectedType === "all" ? "bg-blue-500" : ""}
                            >
                                All
                            </Button>
                            <Button
                                variant={selectedType === "backtest" ? "default" : "outline"}
                                size="sm"
                                onClick={() => setSelectedType("backtest")}
                                className={selectedType === "backtest" ? "bg-blue-500" : ""}
                            >
                                📊 Backtest
                            </Button>
                            <Button
                                variant={selectedType === "paper" ? "default" : "outline"}
                                size="sm"
                                onClick={() => setSelectedType("paper")}
                                className={selectedType === "paper" ? "bg-yellow-500" : ""}
                            >
                                📝 Paper
                            </Button>
                            <Button
                                variant={selectedType === "live" ? "default" : "outline"}
                                size="sm"
                                onClick={() => setSelectedType("live")}
                                className={selectedType === "live" ? "bg-green-500" : ""}
                            >
                                🔴 Live
                            </Button>
                        </div>

                        {/* Month Filter */}
                        <select
                            value={selectedMonth}
                            onChange={(e) => setSelectedMonth(e.target.value)}
                            className="px-4 py-2 rounded-lg bg-white/10 border border-white/20 text-white text-sm"
                        >
                            <option value="all">All Months</option>
                            <option value="2025-10">October 2025</option>
                            <option value="2025-11">November 2025</option>
                            <option value="2025-12">December 2025</option>
                        </select>

                        {/* Search */}
                        <div className="flex-1 min-w-[200px]">
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/40" />
                                <input
                                    type="text"
                                    placeholder="Search stock..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="w-full pl-10 pr-4 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder:text-white/40 text-sm"
                                />
                            </div>
                        </div>
                    </div>
                </div>

                {/* Trades Table */}
                <div className="glass-card rounded-xl border border-white/10 overflow-hidden">
                    <div className="overflow-x-auto">
                        <Table>
                            <TableHeader>
                                <TableRow className="border-white/10 hover:bg-white/5">
                                    <TableHead className="text-white/80">Date</TableHead>
                                    <TableHead className="text-white/80">Stock</TableHead>
                                    <TableHead className="text-white/80">Strike</TableHead>
                                    <TableHead className="text-white/80">Type</TableHead>
                                    <TableHead className="text-white/80">Entry</TableHead>
                                    <TableHead className="text-white/80">Exit</TableHead>
                                    <TableHead className="text-white/80">P&L %</TableHead>
                                    <TableHead className="text-white/80">P&L ₹</TableHead>
                                    <TableHead className="text-white/80">Exit Reason</TableHead>
                                    <TableHead className="text-white/80">Trade Type</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {filteredTrades.map((trade, index) => (
                                    <TableRow key={index} className="border-white/10 hover:bg-white/5">
                                        <TableCell className="text-white/90">{trade.date}</TableCell>
                                        <TableCell className="font-semibold text-white">{trade.stock}</TableCell>
                                        <TableCell className="text-white/90">{trade.strike} {trade.option_type}</TableCell>
                                        <TableCell>
                                            <Badge variant={trade.option_type === "CE" ? "default" : "secondary"}>
                                                {trade.option_type}
                                            </Badge>
                                        </TableCell>
                                        <TableCell className="text-white/90">
                                            <div className="text-xs text-white/60">{formatTime(trade.entry_time)}</div>
                                            <div>₹{trade.entry_premium.toFixed(2)}</div>
                                        </TableCell>
                                        <TableCell className="text-white/90">
                                            <div className="text-xs text-white/60">{formatTime(trade.exit_time)}</div>
                                            <div>₹{trade.exit_premium.toFixed(2)}</div>
                                        </TableCell>
                                        <TableCell>
                                            <div className={cn(
                                                "font-bold flex items-center gap-1",
                                                trade.option_pnl_pct >= 0 ? "text-green-400" : "text-red-400"
                                            )}>
                                                {trade.option_pnl_pct >= 0 ? (
                                                    <TrendingUp className="h-3 w-3" />
                                                ) : (
                                                    <TrendingDown className="h-3 w-3" />
                                                )}
                                                {trade.option_pnl_pct >= 0 ? '+' : ''}{trade.option_pnl_pct.toFixed(1)}%
                                            </div>
                                        </TableCell>
                                        <TableCell>
                                            <div className={cn(
                                                "font-bold",
                                                trade.option_pnl_amount >= 0 ? "text-green-400" : "text-red-400"
                                            )}>
                                                {formatCurrency(trade.option_pnl_amount)}
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-white/90 text-sm">{trade.exit_reason}</TableCell>
                                        <TableCell>{getTradeTypeBadge(trade.trade_type)}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>

                    {filteredTrades.length === 0 && (
                        <div className="p-12 text-center text-white/60">
                            <Activity className="h-12 w-12 mx-auto mb-4 opacity-50" />
                            <p>No trades found matching your filters</p>
                        </div>
                    )}
                </div>

            </div>

            <style jsx global>{`
        .glass-card {
          background: rgba(255, 255, 255, 0.05);
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
        }
      `}</style>
        </div>
    )
}
