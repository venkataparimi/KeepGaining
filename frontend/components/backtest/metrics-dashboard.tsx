"use client";

import React from 'react';
import { TrendingUp, TrendingDown, Target, DollarSign, Percent, BarChart3 } from 'lucide-react';

interface Metrics {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number;
    total_pnl: number;
    total_return_percent: number;
    avg_win: number;
    avg_loss: number;
    profit_factor: number;
    max_drawdown_percent: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    final_capital: number;
    total_commission: number;
    total_slippage: number;
}

interface MetricsDashboardProps {
    metrics: Metrics;
}

export const MetricsDashboard: React.FC<MetricsDashboardProps> = ({ metrics }) => {
    if (!metrics) {
        return (
            <div className="bg-white rounded-lg shadow-sm p-6 text-center text-gray-500">
                No metrics available
            </div>
        );
    }

    const metricCards = [
        {
            label: 'Total Return',
            value: `${metrics.total_return_percent >= 0 ? '+' : ''}${metrics.total_return_percent}%`,
            icon: DollarSign,
            color: metrics.total_return_percent >= 0 ? 'green' : 'red'
        },
        {
            label: 'Win Rate',
            value: `${metrics.win_rate}%`,
            icon: Target,
            color: metrics.win_rate >= 50 ? 'green' : 'orange'
        },
        {
            label: 'Sharpe Ratio',
            value: metrics.sharpe_ratio.toFixed(2),
            icon: BarChart3,
            color: metrics.sharpe_ratio >= 1 ? 'green' : metrics.sharpe_ratio >= 0 ? 'orange' : 'red'
        },
        {
            label: 'Profit Factor',
            value: metrics.profit_factor.toFixed(2),
            icon: TrendingUp,
            color: metrics.profit_factor >= 1.5 ? 'green' : metrics.profit_factor >= 1 ? 'orange' : 'red'
        },
        {
            label: 'Max Drawdown',
            value: `-${metrics.max_drawdown_percent}%`,
            icon: TrendingDown,
            color: metrics.max_drawdown_percent <= 10 ? 'green' : metrics.max_drawdown_percent <= 20 ? 'orange' : 'red'
        },
        {
            label: 'Total Trades',
            value: metrics.total_trades.toString(),
            icon: Percent,
            color: 'blue'
        }
    ];

    const getColorClasses = (color: string) => {
        const colors = {
            green: 'bg-green-50 text-green-600 border-green-200',
            red: 'bg-red-50 text-red-600 border-red-200',
            orange: 'bg-orange-50 text-orange-600 border-orange-200',
            blue: 'bg-blue-50 text-blue-600 border-blue-200'
        };
        return colors[color as keyof typeof colors] || colors.blue;
    };

    return (
        <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm p-6">
                <h3 className="text-lg font-semibold text-gray-800 mb-4">Performance Metrics</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    {metricCards.map((card, index) => {
                        const Icon = card.icon;
                        return (
                            <div key={index} className={`p-4 rounded-lg border ${getColorClasses(card.color)}`}>
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-xs font-medium opacity-75">{card.label}</span>
                                    <Icon className="h-4 w-4 opacity-75" />
                                </div>
                                <div className="text-2xl font-bold">{card.value}</div>
                            </div>
                        );
                    })}
                </div>
            </div>

            <div className="bg-white rounded-lg shadow-sm p-6">
                <h3 className="text-lg font-semibold text-gray-800 mb-4">Trade Statistics</h3>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <div className="text-sm text-gray-500">Winning Trades</div>
                        <div className="text-xl font-semibold text-green-600">{metrics.winning_trades}</div>
                        <div className="text-xs text-gray-500 mt-1">Avg Win: ₹{metrics.avg_win.toLocaleString()}</div>
                    </div>
                    <div>
                        <div className="text-sm text-gray-500">Losing Trades</div>
                        <div className="text-xl font-semibold text-red-600">{metrics.losing_trades}</div>
                        <div className="text-xs text-gray-500 mt-1">Avg Loss: ₹{metrics.avg_loss.toLocaleString()}</div>
                    </div>
                    <div>
                        <div className="text-sm text-gray-500">Total P&L</div>
                        <div className={`text-xl font-semibold ${metrics.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                            ₹{metrics.total_pnl.toLocaleString()}
                        </div>
                    </div>
                    <div>
                        <div className="text-sm text-gray-500">Final Capital</div>
                        <div className="text-xl font-semibold text-gray-900">₹{metrics.final_capital.toLocaleString()}</div>
                    </div>
                </div>
            </div>

            <div className="bg-white rounded-lg shadow-sm p-6">
                <h3 className="text-lg font-semibold text-gray-800 mb-4">Cost Analysis</h3>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <div className="text-sm text-gray-500">Total Commission</div>
                        <div className="text-lg font-semibold text-gray-900">₹{metrics.total_commission.toLocaleString()}</div>
                    </div>
                    <div>
                        <div className="text-sm text-gray-500">Total Slippage</div>
                        <div className="text-lg font-semibold text-gray-900">₹{metrics.total_slippage.toLocaleString()}</div>
                    </div>
                </div>
            </div>
        </div>
    );
};
