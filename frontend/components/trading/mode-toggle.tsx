"use client";

import React, { useState, useEffect } from 'react';
import { Power, AlertTriangle, CheckCircle, TrendingUp, DollarSign } from 'lucide-react';

interface TradingModeToggleProps {
    strategyId: number;
}

export const TradingModeToggle: React.FC<TradingModeToggleProps> = ({ strategyId }) => {
    const [currentMode, setCurrentMode] = useState<'paper' | 'live'>('paper');
    const [session, setSession] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [showConfirmation, setShowConfirmation] = useState(false);
    const [switchReason, setSwitchReason] = useState('');

    useEffect(() => {
        loadCurrentMode();
    }, [strategyId]);

    const loadCurrentMode = async () => {
        try {
            const response = await fetch(`/api/trading-mode/mode/${strategyId}`);
            const data = await response.json();
            setCurrentMode(data.mode);
            setSession(data.session);
        } catch (error) {
            console.error('Failed to load trading mode', error);
        }
    };

    const handleModeSwitch = async (toMode: 'paper' | 'live') => {
        if (toMode === 'live') {
            setShowConfirmation(true);
            return;
        }

        await switchMode(toMode);
    };

    const switchMode = async (toMode: 'paper' | 'live') => {
        setLoading(true);
        try {
            const response = await fetch('/api/trading-mode/switch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    strategy_id: strategyId,
                    to_mode: toMode,
                    reason: switchReason
                })
            });

            const data = await response.json();

            if (data.success) {
                setCurrentMode(toMode);
                setSession(data.session);
                setShowConfirmation(false);
                setSwitchReason('');
            } else if (data.requires_approval) {
                alert('Switch to LIVE mode requires approval. Request submitted.');
                setShowConfirmation(false);
            }
        } catch (error) {
            console.error('Failed to switch mode', error);
            alert('Failed to switch trading mode');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="bg-white rounded-lg shadow-sm p-6">
            <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-semibold text-gray-800">Trading Mode</h3>
                <div className={`px-4 py-2 rounded-full font-semibold ${currentMode === 'live'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-blue-100 text-blue-700'
                    }`}>
                    {currentMode === 'live' ? '🔴 LIVE' : '📝 PAPER'}
                </div>
            </div>

            {/* Mode Toggle */}
            <div className="grid grid-cols-2 gap-4 mb-6">
                <button
                    onClick={() => handleModeSwitch('paper')}
                    disabled={currentMode === 'paper' || loading}
                    className={`p-4 rounded-lg border-2 transition-all ${currentMode === 'paper'
                            ? 'border-blue-500 bg-blue-50'
                            : 'border-gray-200 hover:border-blue-300'
                        } ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                    <div className="text-center">
                        <div className="text-2xl mb-2">📝</div>
                        <div className="font-semibold text-gray-900">Paper Trading</div>
                        <div className="text-xs text-gray-500 mt-1">Risk-free testing</div>
                    </div>
                </button>

                <button
                    onClick={() => handleModeSwitch('live')}
                    disabled={currentMode === 'live' || loading}
                    className={`p-4 rounded-lg border-2 transition-all ${currentMode === 'live'
                            ? 'border-green-500 bg-green-50'
                            : 'border-gray-200 hover:border-green-300'
                        } ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                    <div className="text-center">
                        <div className="text-2xl mb-2">🔴</div>
                        <div className="font-semibold text-gray-900">Live Trading</div>
                        <div className="text-xs text-gray-500 mt-1">Real capital</div>
                    </div>
                </button>
            </div>

            {/* Session Stats */}
            {session && (
                <div className="grid grid-cols-3 gap-4 pt-4 border-t border-gray-200">
                    <div>
                        <div className="text-xs text-gray-500">Capital</div>
                        <div className="text-lg font-semibold text-gray-900">
                            ₹{session.current_capital?.toLocaleString()}
                        </div>
                    </div>
                    <div>
                        <div className="text-xs text-gray-500">Trades</div>
                        <div className="text-lg font-semibold text-gray-900">
                            {session.total_trades}
                        </div>
                    </div>
                    <div>
                        <div className="text-xs text-gray-500">P&L</div>
                        <div className={`text-lg font-semibold ${session.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'
                            }`}>
                            {session.total_pnl >= 0 ? '+' : ''}₹{session.total_pnl?.toFixed(2)}
                        </div>
                    </div>
                </div>
            )}

            {/* Live Trading Confirmation Modal */}
            {showConfirmation && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="p-2 bg-red-100 rounded-lg">
                                <AlertTriangle className="h-6 w-6 text-red-600" />
                            </div>
                            <h3 className="text-lg font-semibold text-gray-900">
                                Switch to Live Trading?
                            </h3>
                        </div>

                        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
                            <p className="text-sm text-yellow-800">
                                <strong>Warning:</strong> You are about to switch to LIVE trading mode.
                                This will use real capital and execute actual trades.
                            </p>
                        </div>

                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Reason for switching (optional)
                            </label>
                            <textarea
                                value={switchReason}
                                onChange={(e) => setSwitchReason(e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                rows={3}
                                placeholder="e.g., Strategy tested successfully in paper mode"
                            />
                        </div>

                        <div className="flex gap-3">
                            <button
                                onClick={() => setShowConfirmation(false)}
                                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={() => switchMode('live')}
                                disabled={loading}
                                className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium disabled:opacity-50"
                            >
                                {loading ? 'Switching...' : 'Confirm Live Trading'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
