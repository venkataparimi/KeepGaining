"use client";

import React, { useState } from 'react';
import { ArrowUpCircle, ArrowDownCircle, Filter } from 'lucide-react';

interface Trade {
    entry_time: string;
    exit_time: string;
    symbol: string;
    side: string;
    entry_price: number;
    exit_price: number;
    quantity: number;
    pnl: number;
    pnl_percent: number;
    commission: number;
    slippage: number;
}

interface TradeLogProps {
    trades: Trade[];
}

export const TradeLog: React.FC<TradeLogProps> = ({ trades }) => {
    const [filter, setFilter] = useState<'all' | 'winners' | 'losers'>('all');

    if (!trades || trades.length === 0) {
        return (
            <div className="bg-white rounded-lg shadow-sm p-6 text-center text-gray-500">
                No trades available
            </div>
        );
    }

    const filteredTrades = trades.filter(trade => {
        if (filter === 'winners') return trade.pnl > 0;
        if (filter === 'losers') return trade.pnl <= 0;
        return true;
    });

    return (
        <div className="bg-white rounded-lg shadow-sm p-6">
            <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold text-gray-800">Trade Log</h3>
                <div className="flex gap-2">
                    <button
                        onClick={() => setFilter('all')}
                        className={`px-3 py-1 rounded-lg text-sm ${filter === 'all'
                                ? 'bg-blue-600 text-white'
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                            }`}
                    >
                        All ({trades.length})
                    </button>
                    <button
                        onClick={() => setFilter('winners')}
                        className={`px-3 py-1 rounded-lg text-sm ${filter === 'winners'
                                ? 'bg-green-600 text-white'
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                            }`}
                    >
                        Winners ({trades.filter(t => t.pnl > 0).length})
                    </button>
                    <button
                        onClick={() => setFilter('losers')}
                        className={`px-3 py-1 rounded-lg text-sm ${filter === 'losers'
                                ? 'bg-red-600 text-white'
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                            }`}
                    >
                        Losers ({trades.filter(t => t.pnl <= 0).length})
                    </button>
                </div>
            </div>

            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b border-gray-200">
                        <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Entry</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Exit</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Symbol</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Side</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Entry Price</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Exit Price</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Qty</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">P&L</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">P&L %</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Commission</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                        {filteredTrades.map((trade, index) => (
                            <tr key={index} className="hover:bg-gray-50">
                                <td className="px-4 py-3 text-gray-600">
                                    {new Date(trade.entry_time).toLocaleString('en-IN', {
                                        month: 'short',
                                        day: 'numeric',
                                        hour: '2-digit',
                                        minute: '2-digit'
                                    })}
                                </td>
                                <td className="px-4 py-3 text-gray-600">
                                    {new Date(trade.exit_time).toLocaleString('en-IN', {
                                        month: 'short',
                                        day: 'numeric',
                                        hour: '2-digit',
                                        minute: '2-digit'
                                    })}
                                </td>
                                <td className="px-4 py-3 font-medium text-gray-900">{trade.symbol}</td>
                                <td className="px-4 py-3">
                                    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${trade.side === 'BUY'
                                            ? 'bg-green-100 text-green-700'
                                            : 'bg-red-100 text-red-700'
                                        }`}>
                                        {trade.side === 'BUY' ? (
                                            <ArrowUpCircle className="h-3 w-3" />
                                        ) : (
                                            <ArrowDownCircle className="h-3 w-3" />
                                        )}
                                        {trade.side}
                                    </span>
                                </td>
                                <td className="px-4 py-3 text-right text-gray-900">₹{trade.entry_price.toFixed(2)}</td>
                                <td className="px-4 py-3 text-right text-gray-900">₹{trade.exit_price.toFixed(2)}</td>
                                <td className="px-4 py-3 text-right text-gray-600">{trade.quantity}</td>
                                <td className={`px-4 py-3 text-right font-semibold ${trade.pnl >= 0 ? 'text-green-600' : 'text-red-600'
                                    }`}>
                                    {trade.pnl >= 0 ? '+' : ''}₹{trade.pnl.toFixed(2)}
                                </td>
                                <td className={`px-4 py-3 text-right font-semibold ${trade.pnl_percent >= 0 ? 'text-green-600' : 'text-red-600'
                                    }`}>
                                    {trade.pnl_percent >= 0 ? '+' : ''}{trade.pnl_percent.toFixed(2)}%
                                </td>
                                <td className="px-4 py-3 text-right text-gray-600">₹{trade.commission.toFixed(2)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
