"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Play, Pause, Square, RefreshCw, Activity, Clock,
    TrendingUp, TrendingDown, AlertTriangle, CheckCircle,
    Settings, Trash2, Eye, MoreVertical, Zap, Target,
    ChevronRight, ArrowUpRight, ArrowDownRight, Rocket, Plus, Loader2
} from "lucide-react";
import { apiClient } from "@/lib/api/client";
import { DeploymentWorkflow } from "./deployment-workflow";

interface Deployment {
    id: string;
    strategy_name: string;
    status: 'running' | 'paused' | 'stopped' | 'error' | 'pending_approval';
    deployed_at: string;
    deployment_type?: 'sandbox' | 'canary' | 'production';
    canary_percent?: number;
    config: {
        underlying: string;
        quantity: number;
        expiry?: string;
    };
    metrics: {
        pnl: number;
        trades: number;
        winRate: number;
    };
    current_state: 'waiting' | 'in_position' | 'exited';
    last_signal?: string;
    last_action?: string;
    last_action_time?: string;
}

interface TimelineEvent {
    id: string;
    deployment_id: string;
    type: 'signal' | 'order' | 'fill' | 'error' | 'info';
    message: string;
    timestamp: string;
    details?: any;
}

// Mock data as fallback
const MOCK_DEPLOYMENTS: Deployment[] = [
    {
        id: '1',
        strategy_name: 'EMA Crossover',
        status: 'running',
        deployed_at: new Date(Date.now() - 3600000 * 2).toISOString(),
        deployment_type: 'production',
        config: { underlying: 'NIFTY', quantity: 50, expiry: '28NOV' },
        metrics: { pnl: 2450, trades: 5, winRate: 80 },
        current_state: 'in_position',
        last_signal: 'BUY',
        last_action: 'Bought NIFTY 24500 CE',
        last_action_time: new Date(Date.now() - 1800000).toISOString()
    },
    {
        id: '2',
        strategy_name: 'RSI Reversal',
        status: 'paused',
        deployed_at: new Date(Date.now() - 3600000 * 5).toISOString(),
        deployment_type: 'canary',
        canary_percent: 25,
        config: { underlying: 'BANKNIFTY', quantity: 25, expiry: '28NOV' },
        metrics: { pnl: -850, trades: 3, winRate: 33 },
        current_state: 'waiting',
        last_signal: 'SELL',
        last_action: 'Position closed',
        last_action_time: new Date(Date.now() - 3600000).toISOString()
    },
    {
        id: '3',
        strategy_name: 'Momentum Breakout',
        status: 'running',
        deployed_at: new Date(Date.now() - 3600000 * 8).toISOString(),
        deployment_type: 'sandbox',
        config: { underlying: 'NIFTY', quantity: 75, expiry: '05DEC' },
        metrics: { pnl: 5200, trades: 8, winRate: 62.5 },
        current_state: 'waiting',
        last_signal: 'NEUTRAL',
        last_action: 'Monitoring for breakout',
        last_action_time: new Date(Date.now() - 600000).toISOString()
    },
    {
        id: '4',
        strategy_name: 'Iron Condor',
        status: 'pending_approval',
        deployed_at: new Date(Date.now() - 3600000 * 24).toISOString(),
        deployment_type: 'production',
        config: { underlying: 'NIFTY', quantity: 50, expiry: '28NOV' },
        metrics: { pnl: 0, trades: 0, winRate: 0 },
        current_state: 'exited',
        last_action: 'Awaiting approval',
        last_action_time: new Date(Date.now() - 300000).toISOString()
    }
];

const MOCK_TIMELINE: TimelineEvent[] = [
    { id: '1', deployment_id: '1', type: 'fill', message: 'Order filled: BUY NIFTY 24500 CE @ ₹125.50', timestamp: new Date(Date.now() - 1800000).toISOString() },
    { id: '2', deployment_id: '1', type: 'order', message: 'Order placed: BUY NIFTY 24500 CE', timestamp: new Date(Date.now() - 1805000).toISOString() },
    { id: '3', deployment_id: '1', type: 'signal', message: 'BUY signal generated - EMA 9 crossed above EMA 21', timestamp: new Date(Date.now() - 1810000).toISOString() },
    { id: '4', deployment_id: '2', type: 'info', message: 'Strategy paused by user', timestamp: new Date(Date.now() - 3600000).toISOString() },
    { id: '5', deployment_id: '3', type: 'fill', message: 'Position closed with profit ₹1,250', timestamp: new Date(Date.now() - 600000).toISOString() },
    { id: '6', deployment_id: '4', type: 'info', message: 'Deployment awaiting approval', timestamp: new Date(Date.now() - 300000).toISOString() },
];

export function DeploymentsCommandCenter() {
    const [deployments, setDeployments] = useState<Deployment[]>([]);
    const [selectedDeployment, setSelectedDeployment] = useState<Deployment | null>(null);
    const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
    const [loading, setLoading] = useState(true);
    const [actionLoading, setActionLoading] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState('overview');
    const [showNewDeployment, setShowNewDeployment] = useState(false);

    const fetchDeployments = useCallback(async () => {
        setLoading(true);
        try {
            // Fetch real strategy status from our API
            const strategyResponse = await fetch('http://localhost:8000/api/strategy/status');
            const strategyData = await strategyResponse.json();

            const performanceResponse = await fetch('http://localhost:8000/api/strategy/performance');
            const performanceData = await performanceResponse.json();

            // Map to deployment format
            const realDeployment: Deployment = {
                id: '1',
                strategy_name: 'Morning Momentum Alpha',
                status: strategyData.is_running ?
                    (strategyData.mode === 'live' ? 'running' :
                        strategyData.mode === 'paper' ? 'running' : 'stopped') : 'stopped',
                deployed_at: new Date().toISOString(),
                deployment_type: strategyData.mode === 'live' ? 'production' :
                    strategyData.mode === 'paper' ? 'sandbox' : undefined,
                config: {
                    underlying: 'F&O Stocks',
                    quantity: 1,
                    expiry: 'Weekly'
                },
                metrics: {
                    pnl: performanceData.total_pnl || 0,
                    trades: performanceData.total_trades || 0,
                    winRate: performanceData.win_rate || 0
                },
                current_state: strategyData.active_positions > 0 ? 'in_position' : 'waiting',
                last_signal: strategyData.mode === 'live' ? 'LIVE' :
                    strategyData.mode === 'paper' ? 'PAPER' : 'STOPPED',
                last_action: strategyData.auto_switched ?
                    `Auto-switched to ${strategyData.mode.toUpperCase()} mode` :
                    `Running in ${strategyData.mode.toUpperCase()} mode`,
                last_action_time: new Date().toISOString()
            };

            setDeployments([realDeployment]);

            // Create timeline events
            const timelineEvents: TimelineEvent[] = [
                {
                    id: '1',
                    deployment_id: '1',
                    type: 'info',
                    message: `Strategy running in ${strategyData.mode.toUpperCase()} mode`,
                    timestamp: new Date().toISOString()
                },
                {
                    id: '2',
                    deployment_id: '1',
                    type: 'info',
                    message: `Available funds: ₹${strategyData.available_funds?.toLocaleString()}`,
                    timestamp: new Date(Date.now() - 60000).toISOString()
                }
            ];

            if (strategyData.auto_switched) {
                timelineEvents.unshift({
                    id: '0',
                    deployment_id: '1',
                    type: 'info',
                    message: strategyData.switch_reason || 'Auto-switched mode',
                    timestamp: new Date(Date.now() - 30000).toISOString()
                });
            }

            setTimeline(timelineEvents);

        } catch (error) {
            console.error('Failed to fetch strategy data:', error);
            // Fallback to mock data
            setDeployments(MOCK_DEPLOYMENTS);
            setTimeline(MOCK_TIMELINE);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchDeployments();

        // Auto-refresh every 30 seconds
        const interval = setInterval(fetchDeployments, 30000);
        return () => clearInterval(interval);
    }, [fetchDeployments]);

    // Deployment control actions
    const handlePause = async (id: string) => {
        setActionLoading(id);
        try {
            await apiClient.pauseDeployment(parseInt(id));
            setDeployments(prev => prev.map(d =>
                d.id === id ? { ...d, status: 'paused' as const } : d
            ));
        } catch (error) {
            console.error('Failed to pause deployment:', error);
        } finally {
            setActionLoading(null);
        }
    };

    const handleResume = async (id: string) => {
        setActionLoading(id);
        try {
            await apiClient.resumeDeployment(parseInt(id));
            setDeployments(prev => prev.map(d =>
                d.id === id ? { ...d, status: 'running' as const } : d
            ));
        } catch (error) {
            console.error('Failed to resume deployment:', error);
        } finally {
            setActionLoading(null);
        }
    };

    const handleStop = async (id: string) => {
        setActionLoading(id);
        try {
            await apiClient.stopDeployment(parseInt(id));
            setDeployments(prev => prev.map(d =>
                d.id === id ? { ...d, status: 'stopped' as const } : d
            ));
        } catch (error) {
            console.error('Failed to stop deployment:', error);
        } finally {
            setActionLoading(null);
        }
    };

    const handleApprove = async (id: string) => {
        setActionLoading(id);
        try {
            await apiClient.approveDeployment(parseInt(id), true);
            setDeployments(prev => prev.map(d =>
                d.id === id ? { ...d, status: 'running' as const } : d
            ));
        } catch (error) {
            console.error('Failed to approve deployment:', error);
        } finally {
            setActionLoading(null);
        }
    };

    const getStatusColor = (status: Deployment['status']) => {
        switch (status) {
            case 'running': return 'bg-green-500';
            case 'paused': return 'bg-yellow-500';
            case 'stopped': return 'bg-gray-500';
            case 'error': return 'bg-red-500';
            case 'pending_approval': return 'bg-blue-500';
        }
    };

    const getStatusBg = (status: Deployment['status']) => {
        switch (status) {
            case 'running': return 'bg-green-500/10 border-green-500/30';
            case 'paused': return 'bg-yellow-500/10 border-yellow-500/30';
            case 'stopped': return 'bg-gray-500/10 border-gray-500/30';
            case 'error': return 'bg-red-500/10 border-red-500/30';
            case 'pending_approval': return 'bg-blue-500/10 border-blue-500/30';
        }
    };

    const getDeploymentTypeBadge = (type?: string) => {
        switch (type) {
            case 'production': return 'bg-green-500/20 text-green-400';
            case 'canary': return 'bg-yellow-500/20 text-yellow-400';
            case 'sandbox': return 'bg-blue-500/20 text-blue-400';
            default: return 'bg-gray-500/20 text-gray-400';
        }
    };

    const getStateIcon = (state: Deployment['current_state']) => {
        switch (state) {
            case 'waiting': return <Clock className="h-4 w-4 text-blue-400" />;
            case 'in_position': return <Target className="h-4 w-4 text-green-400" />;
            case 'exited': return <CheckCircle className="h-4 w-4 text-gray-400" />;
        }
    };

    const getEventIcon = (type: TimelineEvent['type']) => {
        switch (type) {
            case 'signal': return <Zap className="h-4 w-4 text-yellow-400" />;
            case 'order': return <ArrowUpRight className="h-4 w-4 text-blue-400" />;
            case 'fill': return <CheckCircle className="h-4 w-4 text-green-400" />;
            case 'error': return <AlertTriangle className="h-4 w-4 text-red-400" />;
            case 'info': return <Activity className="h-4 w-4 text-gray-400" />;
        }
    };

    const runningCount = deployments.filter(d => d.status === 'running').length;
    const pendingCount = deployments.filter(d => d.status === 'pending_approval').length;
    const totalPnL = deployments.reduce((sum, d) => sum + d.metrics.pnl, 0);

    // Show deployment workflow
    if (showNewDeployment) {
        return (
            <div className="flex-1 p-6 pt-4 max-w-[1800px] mx-auto">
                <DeploymentWorkflow
                    onComplete={() => {
                        setShowNewDeployment(false);
                        fetchDeployments();
                    }}
                    onCancel={() => setShowNewDeployment(false)}
                />
            </div>
        );
    }

    return (
        <div className="flex-1 space-y-6 p-6 pt-4 max-w-[1800px] mx-auto">
            {/* Header */}
            <div className="relative overflow-hidden rounded-2xl glass p-6">
                <div className="absolute inset-0 gradient-bg opacity-30"></div>
                <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-4xl font-bold gradient-text mb-2">Deployment Command Center</h1>
                        <p className="text-muted-foreground">Monitor and control your live trading strategies</p>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-6">
                            <div className="text-center">
                                <p className="text-3xl font-bold text-green-400">{runningCount}</p>
                                <p className="text-xs text-muted-foreground">Running</p>
                            </div>
                            {pendingCount > 0 && (
                                <div className="text-center">
                                    <p className="text-3xl font-bold text-blue-400">{pendingCount}</p>
                                    <p className="text-xs text-muted-foreground">Pending</p>
                                </div>
                            )}
                            <div className="text-center">
                                <p className={`text-3xl font-bold ${totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {totalPnL >= 0 ? '+' : ''}₹{totalPnL.toLocaleString()}
                                </p>
                                <p className="text-xs text-muted-foreground">Total P&L</p>
                            </div>
                        </div>
                        <Button
                            variant="outline"
                            className="border-primary/30"
                            onClick={() => fetchDeployments()}
                            disabled={loading}
                        >
                            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                            Refresh
                        </Button>
                        <Button
                            onClick={() => setShowNewDeployment(true)}
                            className="bg-gradient-to-r from-primary to-secondary"
                        >
                            <Plus className="mr-2 h-4 w-4" />
                            New Deployment
                        </Button>
                    </div>
                </div>
            </div>

            {/* Deployment Grid */}
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                {deployments.map((deployment) => (
                    <div
                        key={deployment.id}
                        className={`glass rounded-xl overflow-hidden cursor-pointer transition-all hover:shadow-lg hover:scale-[1.02] border ${getStatusBg(deployment.status)} ${selectedDeployment?.id === deployment.id ? 'ring-2 ring-primary' : ''
                            }`}
                        onClick={() => setSelectedDeployment(deployment)}
                    >
                        <div className="p-4">
                            <div className="flex items-start justify-between mb-3">
                                <div className="flex items-center gap-2">
                                    <span className={`w-2.5 h-2.5 rounded-full ${getStatusColor(deployment.status)} ${deployment.status === 'running' ? 'animate-pulse' : ''
                                        }`}></span>
                                    <h3 className="font-bold">{deployment.strategy_name}</h3>
                                </div>
                                <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
                                    <MoreVertical className="h-4 w-4" />
                                </Button>
                            </div>

                            <div className="space-y-2 text-sm">
                                <div className="flex items-center justify-between">
                                    <span className="text-muted-foreground">{deployment.config.underlying}</span>
                                    <span className="flex items-center gap-1">
                                        {getStateIcon(deployment.current_state)}
                                        <span className="capitalize text-xs">{deployment.current_state.replace('_', ' ')}</span>
                                    </span>
                                </div>

                                {deployment.deployment_type && (
                                    <div className="flex items-center gap-2">
                                        <span className={`px-2 py-0.5 rounded text-xs ${getDeploymentTypeBadge(deployment.deployment_type)}`}>
                                            {deployment.deployment_type}
                                        </span>
                                        {deployment.deployment_type === 'canary' && deployment.canary_percent && (
                                            <span className="text-xs text-muted-foreground">
                                                {deployment.canary_percent}%
                                            </span>
                                        )}
                                    </div>
                                )}

                                <div className={`text-xl font-bold ${deployment.metrics.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {deployment.metrics.pnl >= 0 ? '+' : ''}₹{deployment.metrics.pnl.toLocaleString()}
                                </div>

                                <div className="flex items-center justify-between text-xs text-muted-foreground">
                                    <span>{deployment.metrics.trades} trades</span>
                                    <span>{deployment.metrics.winRate}% win rate</span>
                                </div>
                            </div>

                            {/* Control Buttons */}
                            <div className="flex gap-2 mt-3 pt-3 border-t border-border/30">
                                {deployment.status === 'pending_approval' ? (
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="flex-1 h-8 text-green-400 border-green-500/30 hover:bg-green-500/10"
                                        onClick={(e) => { e.stopPropagation(); handleApprove(deployment.id); }}
                                        disabled={actionLoading === deployment.id}
                                    >
                                        {actionLoading === deployment.id ? (
                                            <Loader2 className="h-3 w-3 animate-spin" />
                                        ) : (
                                            <><CheckCircle className="h-3 w-3 mr-1" /> Approve</>
                                        )}
                                    </Button>
                                ) : deployment.status === 'running' ? (
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="flex-1 h-8 text-yellow-400 border-yellow-500/30 hover:bg-yellow-500/10"
                                        onClick={(e) => { e.stopPropagation(); handlePause(deployment.id); }}
                                        disabled={actionLoading === deployment.id}
                                    >
                                        {actionLoading === deployment.id ? (
                                            <Loader2 className="h-3 w-3 animate-spin" />
                                        ) : (
                                            <><Pause className="h-3 w-3 mr-1" /> Pause</>
                                        )}
                                    </Button>
                                ) : deployment.status === 'paused' ? (
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="flex-1 h-8 text-green-400 border-green-500/30 hover:bg-green-500/10"
                                        onClick={(e) => { e.stopPropagation(); handleResume(deployment.id); }}
                                        disabled={actionLoading === deployment.id}
                                    >
                                        {actionLoading === deployment.id ? (
                                            <Loader2 className="h-3 w-3 animate-spin" />
                                        ) : (
                                            <><Play className="h-3 w-3 mr-1" /> Resume</>
                                        )}
                                    </Button>
                                ) : (
                                    <Button variant="outline" size="sm" className="flex-1 h-8 text-blue-400 border-blue-500/30 hover:bg-blue-500/10">
                                        <RefreshCw className="h-3 w-3 mr-1" /> Restart
                                    </Button>
                                )}
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-8 px-2 text-red-400 border-red-500/30 hover:bg-red-500/10"
                                    onClick={(e) => { e.stopPropagation(); handleStop(deployment.id); }}
                                    disabled={actionLoading === deployment.id || deployment.status === 'stopped'}
                                >
                                    <Square className="h-3 w-3" />
                                </Button>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Detail View */}
            {selectedDeployment && (
                <div className="grid gap-6 lg:grid-cols-12">
                    {/* Deployment Details */}
                    <div className="lg:col-span-8">
                        <div className="glass rounded-xl overflow-hidden">
                            <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10 py-4">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <span className={`w-3 h-3 rounded-full ${getStatusColor(selectedDeployment.status)} ${selectedDeployment.status === 'running' ? 'animate-pulse' : ''
                                            }`}></span>
                                        <CardTitle className="text-xl font-bold">{selectedDeployment.strategy_name}</CardTitle>
                                    </div>
                                    <div className="flex gap-2">
                                        <Button variant="outline" size="sm">
                                            <Settings className="h-4 w-4 mr-1" /> Configure
                                        </Button>
                                        <Button variant="outline" size="sm" className="text-red-400 border-red-500/30">
                                            <Trash2 className="h-4 w-4 mr-1" /> Remove
                                        </Button>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent className="p-6">
                                <Tabs value={activeTab} onValueChange={setActiveTab}>
                                    <TabsList className="grid w-full grid-cols-3 mb-6">
                                        <TabsTrigger value="overview">Overview</TabsTrigger>
                                        <TabsTrigger value="timeline">Timeline</TabsTrigger>
                                        <TabsTrigger value="config">Configuration</TabsTrigger>
                                    </TabsList>

                                    <TabsContent value="overview" className="space-y-6">
                                        {/* Current State */}
                                        <div className="p-4 rounded-lg bg-gradient-to-r from-primary/10 to-secondary/10 border border-primary/20">
                                            <h4 className="font-semibold mb-2">Current State</h4>
                                            <div className="flex items-center gap-3">
                                                {getStateIcon(selectedDeployment.current_state)}
                                                <div>
                                                    <p className="font-medium capitalize">{selectedDeployment.current_state.replace('_', ' ')}</p>
                                                    <p className="text-sm text-muted-foreground">{selectedDeployment.last_action}</p>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Metrics */}
                                        <div className="grid grid-cols-3 gap-4">
                                            <div className="p-4 rounded-lg bg-muted/30">
                                                <p className="text-sm text-muted-foreground">P&L</p>
                                                <p className={`text-2xl font-bold ${selectedDeployment.metrics.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                    {selectedDeployment.metrics.pnl >= 0 ? '+' : ''}₹{selectedDeployment.metrics.pnl.toLocaleString()}
                                                </p>
                                            </div>
                                            <div className="p-4 rounded-lg bg-muted/30">
                                                <p className="text-sm text-muted-foreground">Total Trades</p>
                                                <p className="text-2xl font-bold">{selectedDeployment.metrics.trades}</p>
                                            </div>
                                            <div className="p-4 rounded-lg bg-muted/30">
                                                <p className="text-sm text-muted-foreground">Win Rate</p>
                                                <p className="text-2xl font-bold text-blue-400">{selectedDeployment.metrics.winRate}%</p>
                                            </div>
                                        </div>

                                        {/* Last Signal */}
                                        {selectedDeployment.last_signal && (
                                            <div className="p-4 rounded-lg border border-border/50">
                                                <div className="flex items-center justify-between">
                                                    <div>
                                                        <p className="text-sm text-muted-foreground">Last Signal</p>
                                                        <p className={`text-lg font-bold ${selectedDeployment.last_signal === 'BUY' ? 'text-green-400' :
                                                                selectedDeployment.last_signal === 'SELL' ? 'text-red-400' : 'text-gray-400'
                                                            }`}>
                                                            {selectedDeployment.last_signal}
                                                        </p>
                                                    </div>
                                                    <div className="text-right">
                                                        <p className="text-sm text-muted-foreground">Time</p>
                                                        <p className="text-sm">
                                                            {selectedDeployment.last_action_time && new Date(selectedDeployment.last_action_time).toLocaleTimeString()}
                                                        </p>
                                                    </div>
                                                </div>
                                            </div>
                                        )}
                                    </TabsContent>

                                    <TabsContent value="timeline">
                                        <div className="space-y-3">
                                            {timeline
                                                .filter(e => e.deployment_id === selectedDeployment.id)
                                                .map((event) => (
                                                    <div key={event.id} className="flex items-start gap-3 p-3 rounded-lg bg-muted/20">
                                                        {getEventIcon(event.type)}
                                                        <div className="flex-1">
                                                            <p className="text-sm">{event.message}</p>
                                                            <p className="text-xs text-muted-foreground">
                                                                {new Date(event.timestamp).toLocaleString()}
                                                            </p>
                                                        </div>
                                                    </div>
                                                ))}
                                        </div>
                                    </TabsContent>

                                    <TabsContent value="config">
                                        <div className="space-y-4">
                                            <div className="grid grid-cols-2 gap-4">
                                                <div className="p-4 rounded-lg bg-muted/20">
                                                    <p className="text-sm text-muted-foreground">Underlying</p>
                                                    <p className="font-medium">{selectedDeployment.config.underlying}</p>
                                                </div>
                                                <div className="p-4 rounded-lg bg-muted/20">
                                                    <p className="text-sm text-muted-foreground">Quantity</p>
                                                    <p className="font-medium">{selectedDeployment.config.quantity}</p>
                                                </div>
                                                <div className="p-4 rounded-lg bg-muted/20">
                                                    <p className="text-sm text-muted-foreground">Expiry</p>
                                                    <p className="font-medium">{selectedDeployment.config.expiry || 'N/A'}</p>
                                                </div>
                                                <div className="p-4 rounded-lg bg-muted/20">
                                                    <p className="text-sm text-muted-foreground">Deployed At</p>
                                                    <p className="font-medium">{new Date(selectedDeployment.deployed_at).toLocaleString()}</p>
                                                </div>
                                            </div>
                                        </div>
                                    </TabsContent>
                                </Tabs>
                            </CardContent>
                        </div>
                    </div>

                    {/* Live Feed */}
                    <div className="lg:col-span-4">
                        <div className="glass rounded-xl overflow-hidden h-full">
                            <CardHeader className="bg-gradient-to-r from-accent/10 to-primary/10 py-4">
                                <CardTitle className="text-lg font-bold flex items-center gap-2">
                                    <Activity className="h-4 w-4 text-primary animate-pulse" />
                                    Live Feed
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="p-4">
                                <div className="space-y-2 max-h-96 overflow-y-auto">
                                    {timeline.slice(0, 10).map((event) => (
                                        <div
                                            key={event.id}
                                            className="flex items-start gap-2 p-2 rounded-lg hover:bg-muted/20 transition-colors text-sm"
                                        >
                                            {getEventIcon(event.type)}
                                            <div className="flex-1 min-w-0">
                                                <p className="truncate">{event.message}</p>
                                                <p className="text-xs text-muted-foreground">
                                                    {new Date(event.timestamp).toLocaleTimeString()}
                                                </p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
