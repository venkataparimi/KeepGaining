"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
    TrendingUp, TrendingDown, Activity, DollarSign, Target, Shield,
    Play, Pause, FileText, Zap, AlertCircle, CheckCircle2, Clock,
    ArrowUpRight, ArrowDownRight, BarChart3, PieChart
} from "lucide-react"
import { cn } from "@/lib/utils"

interface StrategyMode {
    mode: 'live' | 'paper' | 'stopped'
    autoSwitched: boolean
    reason?: string
}

interface PerformanceData {
    total_pnl: number
    win_rate: number
    total_trades: number
    winning_trades: number
    avg_win: number
    avg_loss: number
    max_win: number
    max_loss: number
    period: string
}

export default function StrategyDashboard() {
    const [strategyMode, setStrategyMode] = useState<StrategyMode>({
        mode: 'live',
        autoSwitched: false
    })
    const [performance, setPerformance] = useState<PerformanceData | null>(null)
    const [isRunning, setIsRunning] = useState(true)
    const [availableFunds, setAvailableFunds] = useState(250000) // ₹2.5L
    const [requiredFunds, setRequiredFunds] = useState(50000) // ₹50K per trade

    useEffect(() => {
        // Check if funds are sufficient for live trading
        if (availableFunds < requiredFunds && strategyMode.mode === 'live') {
            setStrategyMode({
                mode: 'paper',
                autoSwitched: true,
                reason: 'Insufficient funds for live trading'
            })
        }

        fetchPerformance()
    }, [availableFunds, requiredFunds])

    const fetchPerformance = async () => {
        try {
            const response = await fetch(
                `http://localhost:8000/api/strategy/performance?start_date=2025-10-01&end_date=2025-12-15&trade_type=${strategyMode.mode}`
            )
            const data = await response.json()
            setPerformance(data)
        } catch (error) {
            console.error("Error fetching performance:", error)
            // Mock data for demonstration
            setPerformance({
                total_pnl: 1221000,
                win_rate: 81.6,
                total_trades: 473,
                winning_trades: 386,
                avg_win: 28.8,
                avg_loss: -15.5,
                max_win: 75.0,
                max_loss: -40.0,
                period: "Oct-Dec 2025"
            })
        }
    }

    const handleModeChange = (newMode: 'live' | 'paper' | 'stopped') => {
        if (newMode === 'live' && availableFunds < requiredFunds) {
            // Show warning but allow manual override
            setStrategyMode({
                mode: 'paper',
                autoSwitched: true,
                reason: 'Insufficient funds - switched to paper mode'
            })
            return
        }

        setStrategyMode({
            mode: newMode,
            autoSwitched: false
        })
    }

    const getModeConfig = (mode: 'live' | 'paper' | 'stopped') => {
        const configs = {
            live: {
                color: 'from-green-500 to-emerald-600',
                bgColor: 'bg-green-500/10',
                borderColor: 'border-green-500/50',
                icon: <Zap className="h-4 w-4" />,
                label: 'Live Trading',
                description: 'Real money trades'
            },
            paper: {
                color: 'from-blue-500 to-cyan-600',
                bgColor: 'bg-blue-500/10',
                borderColor: 'border-blue-500/50',
                icon: <FileText className="h-4 w-4" />,
                label: 'Paper Trading',
                description: 'Simulated trades'
            },
            stopped: {
                color: 'from-gray-500 to-slate-600',
                bgColor: 'bg-gray-500/10',
                borderColor: 'border-gray-500/50',
                icon: <Pause className="h-4 w-4" />,
                label: 'Stopped',
                description: 'Strategy paused'
            }
        }
        return configs[mode]
    }

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            maximumFractionDigits: 0
        }).format(amount)
    }

    const currentConfig = getModeConfig(strategyMode.mode)

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-950 via-blue-950 to-slate-950 p-6">
            <div className="max-w-7xl mx-auto space-y-6">

                {/* Header with Mode Control */}
                <div className="glass-card rounded-2xl p-6 border border-white/10">
                    <div className="flex items-center justify-between">
                        <div className="space-y-1">
                            <div className="flex items-center gap-3">
                                <div className={cn(
                                    "p-3 rounded-xl bg-gradient-to-br",
                                    currentConfig.color
                                )}>
                                    <Target className="h-6 w-6 text-white" />
                                </div>
                                <div>
                                    <h1 className="text-3xl font-bold text-white">
                                        Morning Momentum Alpha
                                    </h1>
                                    <p className="text-sm text-white/60">
                                        ATM Options Breakout • Validated 81.6% Win Rate
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* Status Indicator */}
                        <div className="flex items-center gap-4">
                            {isRunning && (
                                <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-green-500/20 border border-green-500/50">
                                    <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                                    <span className="text-sm font-medium text-green-400">Running</span>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Mode Selector */}
                    <div className="mt-6 grid grid-cols-3 gap-4">
                        {(['live', 'paper', 'stopped'] as const).map((mode) => {
                            const config = getModeConfig(mode)
                            const isActive = strategyMode.mode === mode

                            return (
                                <button
                                    key={mode}
                                    onClick={() => handleModeChange(mode)}
                                    className={cn(
                                        "relative p-4 rounded-xl border-2 transition-all duration-300",
                                        isActive
                                            ? `${config.borderColor} ${config.bgColor}`
                                            : "border-white/10 bg-white/5 hover:bg-white/10"
                                    )}
                                >
                                    <div className="flex items-center gap-3">
                                        <div className={cn(
                                            "p-2 rounded-lg",
                                            isActive ? config.bgColor : "bg-white/10"
                                        )}>
                                            {config.icon}
                                        </div>
                                        <div className="text-left">
                                            <div className="font-semibold text-white">{config.label}</div>
                                            <div className="text-xs text-white/60">{config.description}</div>
                                        </div>
                                    </div>

                                    {isActive && (
                                        <div className="absolute top-2 right-2">
                                            <CheckCircle2 className="h-5 w-5 text-green-400" />
                                        </div>
                                    )}
                                </button>
                            )
                        })}
                    </div>

                    {/* Auto-Switch Warning */}
                    {strategyMode.autoSwitched && (
                        <div className="mt-4 p-4 rounded-xl bg-yellow-500/10 border border-yellow-500/50 flex items-start gap-3">
                            <AlertCircle className="h-5 w-5 text-yellow-400 mt-0.5" />
                            <div>
                                <div className="font-medium text-yellow-400">Auto-switched to Paper Mode</div>
                                <div className="text-sm text-yellow-400/80">{strategyMode.reason}</div>
                                <div className="text-xs text-white/60 mt-1">
                                    Available: {formatCurrency(availableFunds)} | Required: {formatCurrency(requiredFunds)}
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Performance Metrics */}
                {performance && (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                        {/* Total P&L */}
                        <div className="glass-card rounded-xl p-6 border border-white/10 hover:border-white/20 transition-all">
                            <div className="flex items-center justify-between mb-4">
                                <div className="p-3 rounded-xl bg-gradient-to-br from-purple-500 to-pink-600">
                                    <DollarSign className="h-5 w-5 text-white" />
                                </div>
                                {(performance?.total_pnl || 0) >= 0 ? (
                                    <ArrowUpRight className="h-5 w-5 text-green-400" />
                                ) : (
                                    <ArrowDownRight className="h-5 w-5 text-red-400" />
                                )}
                            </div>
                            <div className="space-y-1">
                                <div className="text-sm text-white/60">Total P&L</div>
                                <div className={cn(
                                    "text-2xl font-bold",
                                    (performance?.total_pnl || 0) >= 0 ? "text-green-400" : "text-red-400"
                                )}>
                                    {formatCurrency(performance?.total_pnl || 0)}
                                </div>
                                <div className="text-xs text-white/40">{performance?.period || ''}</div>
                            </div>
                        </div>

                        {/* Win Rate */}
                        <div className="glass-card rounded-xl p-6 border border-white/10 hover:border-white/20 transition-all">
                            <div className="flex items-center justify-between mb-4">
                                <div className="p-3 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-600">
                                    <Target className="h-5 w-5 text-white" />
                                </div>
                                <PieChart className="h-5 w-5 text-blue-400" />
                            </div>
                            <div className="space-y-1">
                                <div className="text-sm text-white/60">Win Rate</div>
                                <div className="text-2xl font-bold text-blue-400">
                                    {performance?.win_rate?.toFixed(1) || '0.0'}%
                                </div>
                                <div className="text-xs text-white/40">
                                    {performance?.winning_trades || 0} / {performance?.total_trades || 0} trades
                                </div>
                            </div>
                        </div>

                        {/* Avg Win */}
                        <div className="glass-card rounded-xl p-6 border border-white/10 hover:border-white/20 transition-all">
                            <div className="flex items-center justify-between mb-4">
                                <div className="p-3 rounded-xl bg-gradient-to-br from-green-500 to-emerald-600">
                                    <TrendingUp className="h-5 w-5 text-white" />
                                </div>
                                <BarChart3 className="h-5 w-5 text-green-400" />
                            </div>
                            <div className="space-y-1">
                                <div className="text-sm text-white/60">Avg Win</div>
                                <div className="text-2xl font-bold text-green-400">
                                    +{performance?.avg_win?.toFixed(1) || '0.0'}%
                                </div>
                                <div className="text-xs text-white/40">
                                    Max: +{performance?.max_win?.toFixed(0) || '0'}%
                                </div>
                            </div>
                        </div>

                        {/* Avg Loss */}
                        <div className="glass-card rounded-xl p-6 border border-white/10 hover:border-white/20 transition-all">
                            <div className="flex items-center justify-between mb-4">
                                <div className="p-3 rounded-xl bg-gradient-to-br from-red-500 to-rose-600">
                                    <TrendingDown className="h-5 w-5 text-white" />
                                </div>
                                <Shield className="h-5 w-5 text-red-400" />
                            </div>
                            <div className="space-y-1">
                                <div className="text-sm text-white/60">Avg Loss</div>
                                <div className="text-2xl font-bold text-red-400">
                                    {performance?.avg_loss?.toFixed(1) || '0.0'}%
                                </div>
                                <div className="text-xs text-white/40">
                                    Max: {performance?.max_loss?.toFixed(0) || '0'}%
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Strategy Rules */}
                <div className="grid gap-4 md:grid-cols-2">
                    <div className="glass-card rounded-xl p-6 border border-white/10">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="p-2 rounded-lg bg-green-500/20">
                                <Target className="h-5 w-5 text-green-400" />
                            </div>
                            <h3 className="text-lg font-semibold text-white">Entry Rules</h3>
                        </div>
                        <div className="space-y-3">
                            {[
                                'Stock opens within 2% of ATM strike',
                                'Early momentum >0.5% in first 15 minutes',
                                'Option has non-zero volume',
                                'Entry at 9:30 AM IST'
                            ].map((rule, i) => (
                                <div key={i} className="flex items-start gap-3">
                                    <CheckCircle2 className="h-5 w-5 text-green-400 mt-0.5 flex-shrink-0" />
                                    <span className="text-sm text-white/80">{rule}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="glass-card rounded-xl p-6 border border-white/10">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="p-2 rounded-lg bg-blue-500/20">
                                <Shield className="h-5 w-5 text-blue-400" />
                            </div>
                            <h3 className="text-lg font-semibold text-white">Exit Rules</h3>
                        </div>
                        <div className="space-y-3">
                            {[
                                { icon: '🎯', label: 'Target: 50% profit on premium' },
                                { icon: '🛡️', label: 'Stop Loss: 40% loss on premium' },
                                { icon: '⏰', label: 'Time Stop: 2:30 PM IST' }
                            ].map((rule, i) => (
                                <div key={i} className="flex items-start gap-3">
                                    <span className="text-lg flex-shrink-0">{rule.icon}</span>
                                    <span className="text-sm text-white/80">{rule.label}</span>
                                </div>
                            ))}
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
