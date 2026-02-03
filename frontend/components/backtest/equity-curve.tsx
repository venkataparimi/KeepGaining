"use client";

import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Area, ComposedChart } from 'recharts';
import { TrendingUp, TrendingDown, Activity } from 'lucide-react';

interface EquityPoint {
    timestamp: string;
    equity: number;
    drawdown: number;
}

interface EquityCurveProps {
    data: EquityPoint[];
    initialCapital: number;
}

export const EquityCurve: React.FC<EquityCurveProps> = ({ data, initialCapital }) => {
    if (!data || data.length === 0) {
        return (
            <div className="bg-white rounded-lg shadow-sm p-6 text-center text-gray-500">
                No equity curve data available
            </div>
        );
    }

    const finalEquity = data[data.length - 1]?.equity || initialCapital;
    const totalReturn = ((finalEquity - initialCapital) / initialCapital) * 100;
    const maxDrawdown = Math.max(...data.map(d => d.drawdown));

    return (
        <div className="bg-white rounded-lg shadow-sm p-6 space-y-6">
            <div className="flex justify-between items-center">
                <h3 className="text-lg font-semibold text-gray-800">Equity Curve</h3>
                <div className="flex gap-4">
                    <div className="text-right">
                        <div className="text-xs text-gray-500">Total Return</div>
                        <div className={`text-lg font-semibold ${totalReturn >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                            {totalReturn >= 0 ? '+' : ''}{totalReturn.toFixed(2)}%
                        </div>
                    </div>
                    <div className="text-right">
                        <div className="text-xs text-gray-500">Max Drawdown</div>
                        <div className="text-lg font-semibold text-red-600">
                            -{maxDrawdown.toFixed(2)}%
                        </div>
                    </div>
                </div>
            </div>

            <ResponsiveContainer width="100%" height={400}>
                <ComposedChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis
                        dataKey="timestamp"
                        tick={{ fontSize: 12 }}
                        tickFormatter={(value) => new Date(value).toLocaleDateString()}
                    />
                    <YAxis
                        yAxisId="left"
                        tick={{ fontSize: 12 }}
                        label={{ value: 'Equity (₹)', angle: -90, position: 'insideLeft' }}
                    />
                    <YAxis
                        yAxisId="right"
                        orientation="right"
                        tick={{ fontSize: 12 }}
                        label={{ value: 'Drawdown (%)', angle: 90, position: 'insideRight' }}
                    />
                    <Tooltip
                        contentStyle={{ backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px' }}
                        formatter={(value: any, name: string) => {
                            if (name === 'equity') return [`₹${Number(value).toLocaleString()}`, 'Equity'];
                            if (name === 'drawdown') return [`${Number(value).toFixed(2)}%`, 'Drawdown'];
                            return value;
                        }}
                        labelFormatter={(label) => new Date(label).toLocaleString()}
                    />
                    <Legend />
                    <Line
                        yAxisId="left"
                        type="monotone"
                        dataKey="equity"
                        stroke="#3b82f6"
                        strokeWidth={2}
                        dot={false}
                        name="Equity"
                    />
                    <Area
                        yAxisId="right"
                        type="monotone"
                        dataKey="drawdown"
                        fill="#ef4444"
                        fillOpacity={0.2}
                        stroke="#ef4444"
                        strokeWidth={1}
                        name="Drawdown"
                    />
                </ComposedChart>
            </ResponsiveContainer>

            <div className="grid grid-cols-3 gap-4 pt-4 border-t border-gray-200">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-blue-50 rounded-lg">
                        <Activity className="h-5 w-5 text-blue-600" />
                    </div>
                    <div>
                        <div className="text-xs text-gray-500">Initial Capital</div>
                        <div className="text-sm font-semibold text-gray-900">
                            ₹{initialCapital.toLocaleString()}
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-green-50 rounded-lg">
                        <TrendingUp className="h-5 w-5 text-green-600" />
                    </div>
                    <div>
                        <div className="text-xs text-gray-500">Final Equity</div>
                        <div className="text-sm font-semibold text-gray-900">
                            ₹{finalEquity.toLocaleString()}
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-red-50 rounded-lg">
                        <TrendingDown className="h-5 w-5 text-red-600" />
                    </div>
                    <div>
                        <div className="text-xs text-gray-500">Peak Drawdown</div>
                        <div className="text-sm font-semibold text-gray-900">
                            -{maxDrawdown.toFixed(2)}%
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
