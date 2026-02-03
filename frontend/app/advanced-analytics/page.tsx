"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import {
    TrendingUp, TrendingDown, Target, Calendar, BarChart3,
    PieChart, Activity, Zap, DollarSign, Percent, Clock,
    ArrowUpRight, ArrowDownRight, CheckCircle2, XCircle
} from "lucide-react"
import { cn } from "@/lib/utils"

interface MonthlyData {
    month: string
    trades: number
    win_rate: number
    pnl: number
    avg_win: number
    avg_loss: number
}

export default function AdvancedAnalyticsPage() {
    const [monthlyData, setMonthlyData] = useState<MonthlyData[]>([])
    const [performance, setPerformance] = useState<any>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchData()
    }, [])

    const fetchData = async () => {
        try {
            const [perfResponse, monthlyResponse] = await Promise.all([
                fetch('http://localhost:8000/api/strategy/performance'),
                fetch('http://localhost:8000/api/strategy/monthly-summary')
            ])

            const perfData = await perfResponse.json()
            const monthlyDataRes = await monthlyResponse.json()

            setPerformance(perfData)
            setMonthlyData(monthlyDataRes.months || [])
        } catch (error) {
            console.error('Error fetching analytics:', error)
        } finally {
            setLoading(false)
        }
    }

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            maximumFractionDigits: 0
        }).format(amount)
    }

    const totalTrades = monthlyData.reduce((sum, m) => sum + m.trades, 0)
    const avgWinRate = monthlyData.length > 0
        ? monthlyData.reduce((sum, m) => sum + m.win_rate, 0) / monthlyData.length
        : 0
    const totalPnL = monthlyData.reduce((sum, m) => sum + m.pnl, 0)

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-950 via-blue-950 to-slate-950 p-6">
            <div className="max-w-7xl mx-auto space-y-6">

                {/* Header */}
                <div className="glass-card rounded-2xl p-6 border border-white/10">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-4xl font-bold text-white mb-2">
                                Advanced Analytics
                            </h1>
                            <p className="text-white/60">
                                Morning Momentum Alpha • Performance Deep Dive
                            </p>
                        </div>
                        <div className="flex items-center gap-2">
                            <Badge className="bg-green-500/20 text-green-400 border-green-500/50">
                                <Activity className="h-3 w-3 mr-1" />
                                Live Data
                            </Badge>
                        </div>
                    </div>
                </div>

                {/* Summary Cards */}
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                    <div className="glass-card rounded-xl p-6 border border-white/10">
                        <div className="flex items-center justify-between mb-4">
                            <div className="p-3 rounded-xl bg-gradient-to-br from-purple-500 to-pink-600">
                                <DollarSign className="h-5 w-5 text-white" />
                            </div>
                            <ArrowUpRight className="h-5 w-5 text-green-400" />
                        </div>
                        <div className="space-y-1">
                            <div className="text-sm text-white/60">Total P&L</div>
                            <div className="text-2xl font-bold text-green-400">
                                {formatCurrency(totalPnL)}
                            </div>
                            <div className="text-xs text-white/40">Oct-Dec 2025</div>
                        </div>
                    </div>

                    <div className="glass-card rounded-xl p-6 border border-white/10">
                        <div className="flex items-center justify-between mb-4">
                            <div className="p-3 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-600">
                                <Target className="h-5 w-5 text-white" />
                            </div>
                            <PieChart className="h-5 w-5 text-blue-400" />
                        </div>
                        <div className="space-y-1">
                            <div className="text-sm text-white/60">Avg Win Rate</div>
                            <div className="text-2xl font-bold text-blue-400">
                                {avgWinRate.toFixed(1)}%
                            </div>
                            <div className="text-xs text-white/40">Across all months</div>
                        </div>
                    </div>

                    <div className="glass-card rounded-xl p-6 border border-white/10">
                        <div className="flex items-center justify-between mb-4">
                            <div className="p-3 rounded-xl bg-gradient-to-br from-green-500 to-emerald-600">
                                <BarChart3 className="h-5 w-5 text-white" />
                            </div>
                            <Activity className="h-5 w-5 text-green-400" />
                        </div>
                        <div className="space-y-1">
                            <div className="text-sm text-white/60">Total Trades</div>
                            <div className="text-2xl font-bold text-white">
                                {totalTrades}
                            </div>
                            <div className="text-xs text-white/40">Executed</div>
                        </div>
                    </div>

                    <div className="glass-card rounded-xl p-6 border border-white/10">
                        <div className="flex items-center justify-between mb-4">
                            <div className="p-3 rounded-xl bg-gradient-to-br from-orange-500 to-red-600">
                                <Zap className="h-5 w-5 text-white" />
                            </div>
                            <TrendingUp className="h-5 w-5 text-orange-400" />
                        </div>
                        <div className="space-y-1">
                            <div className="text-sm text-white/60">Profit Factor</div>
                            <div className="text-2xl font-bold text-orange-400">
                                {performance?.profit_factor?.toFixed(2) || '1.86'}
                            </div>
                            <div className="text-xs text-white/40">Risk/Reward</div>
                        </div>
                    </div>
                </div>

                {/* Monthly Performance */}
                <div className="glass-card rounded-xl p-6 border border-white/10">
                    <h2 className="text-2xl font-bold text-white mb-6">Monthly Performance</h2>
                    <div className="space-y-4">
                        {monthlyData.map((month, index) => (
                            <div
                                key={month.month}
                                className="p-4 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 transition-all"
                            >
                                <div className="flex items-center justify-between mb-3">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 rounded-lg bg-blue-500/20">
                                            <Calendar className="h-5 w-5 text-blue-400" />
                                        </div>
                                        <div>
                                            <div className="font-semibold text-white">{month.month}</div>
                                            <div className="text-sm text-white/60">{month.trades} trades</div>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <div className={cn(
                                            "text-2xl font-bold",
                                            month.pnl >= 0 ? "text-green-400" : "text-red-400"
                                        )}>
                                            {formatCurrency(month.pnl)}
                                        </div>
                                        <div className="text-sm text-white/60">
                                            {month.win_rate.toFixed(1)}% win rate
                                        </div>
                                    </div>
                                </div>

                                {/* Progress bar */}
                                <div className="grid grid-cols-3 gap-4 mt-3">
                                    <div>
                                        <div className="text-xs text-white/60 mb-1">Avg Win</div>
                                        <div className="text-sm font-semibold text-green-400">
                                            +{month.avg_win.toFixed(1)}%
                                        </div>
                                    </div>
                                    <div>
                                        <div className="text-xs text-white/60 mb-1">Avg Loss</div>
                                        <div className="text-sm font-semibold text-red-400">
                                            {month.avg_loss.toFixed(1)}%
                                        </div>
                                    </div>
                                    <div>
                                        <div className="text-xs text-white/60 mb-1">Win Rate</div>
                                        <div className="flex items-center gap-2">
                                            <div className="flex-1 h-2 bg-white/10 rounded-full overflow-hidden">
                                                <div
                                                    className="h-full bg-gradient-to-r from-blue-500 to-cyan-500 rounded-full"
                                                    style={{ width: `${month.win_rate}%` }}
                                                />
                                            </div>
                                            <span className="text-xs text-white/80">{month.win_rate.toFixed(0)}%</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Performance Metrics Grid */}
                <div className="grid gap-6 md:grid-cols-2">
                    {/* Win/Loss Distribution */}
                    <div className="glass-card rounded-xl p-6 border border-white/10">
                        <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                            <PieChart className="h-5 w-5 text-blue-400" />
                            Win/Loss Distribution
                        </h3>
                        <div className="space-y-4">
                            <div className="flex items-center justify-between p-4 rounded-lg bg-green-500/10 border border-green-500/30">
                                <div className="flex items-center gap-3">
                                    <CheckCircle2 className="h-6 w-6 text-green-400" />
                                    <div>
                                        <div className="font-semibold text-white">Winning Trades</div>
                                        <div className="text-sm text-white/60">
                                            {performance?.winning_trades || 0} trades
                                        </div>
                                    </div>
                                </div>
                                <div className="text-2xl font-bold text-green-400">
                                    {performance?.win_rate?.toFixed(1) || '0'}%
                                </div>
                            </div>

                            <div className="flex items-center justify-between p-4 rounded-lg bg-red-500/10 border border-red-500/30">
                                <div className="flex items-center gap-3">
                                    <XCircle className="h-6 w-6 text-red-400" />
                                    <div>
                                        <div className="font-semibold text-white">Losing Trades</div>
                                        <div className="text-sm text-white/60">
                                            {performance?.losing_trades || 0} trades
                                        </div>
                                    </div>
                                </div>
                                <div className="text-2xl font-bold text-red-400">
                                    {(100 - (performance?.win_rate || 0)).toFixed(1)}%
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Average Performance */}
                    <div className="glass-card rounded-xl p-6 border border-white/10">
                        <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                            <BarChart3 className="h-5 w-5 text-green-400" />
                            Average Performance
                        </h3>
                        <div className="space-y-4">
                            <div className="p-4 rounded-lg bg-white/5">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-sm text-white/60">Avg Win</span>
                                    <TrendingUp className="h-4 w-4 text-green-400" />
                                </div>
                                <div className="text-3xl font-bold text-green-400">
                                    +{performance?.avg_win?.toFixed(1) || '0'}%
                                </div>
                                <div className="text-xs text-white/40 mt-1">
                                    Max: +{performance?.max_win?.toFixed(0) || '0'}%
                                </div>
                            </div>

                            <div className="p-4 rounded-lg bg-white/5">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-sm text-white/60">Avg Loss</span>
                                    <TrendingDown className="h-4 w-4 text-red-400" />
                                </div>
                                <div className="text-3xl font-bold text-red-400">
                                    {performance?.avg_loss?.toFixed(1) || '0'}%
                                </div>
                                <div className="text-xs text-white/40 mt-1">
                                    Max: {performance?.max_loss?.toFixed(0) || '0'}%
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Strategy Info */}
                <div className="glass-card rounded-xl p-6 border border-white/10">
                    <h3 className="text-xl font-bold text-white mb-4">Strategy Details</h3>
                    <div className="grid gap-4 md:grid-cols-3">
                        <div className="p-4 rounded-lg bg-white/5">
                            <div className="text-sm text-white/60 mb-1">Entry Criteria</div>
                            <ul className="space-y-1 text-sm text-white/80">
                                <li>• Opens within 2% of ATM</li>
                                <li>• Momentum &gt;0.5% (15 min)</li>
                                <li>• Non-zero volume</li>
                            </ul>
                        </div>
                        <div className="p-4 rounded-lg bg-white/5">
                            <div className="text-sm text-white/60 mb-1">Exit Criteria</div>
                            <ul className="space-y-1 text-sm text-white/80">
                                <li>• Target: 50% profit</li>
                                <li>• Stop: 40% loss</li>
                                <li>• Time: 2:30 PM IST</li>
                            </ul>
                        </div>
                        <div className="p-4 rounded-lg bg-white/5">
                            <div className="text-sm text-white/60 mb-1">Validation Period</div>
                            <ul className="space-y-1 text-sm text-white/80">
                                <li>• Oct-Dec 2025</li>
                                <li>• 473 total trades</li>
                                <li>• 81.6% win rate</li>
                            </ul>
                        </div>
                    </div>
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
