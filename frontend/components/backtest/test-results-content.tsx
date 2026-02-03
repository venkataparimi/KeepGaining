"use client";

import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { EquityCurve } from '@/components/backtest/equity-curve';
import { MetricsDashboard } from '@/components/backtest/metrics-dashboard';
import { TradeLog } from '@/components/backtest/trade-log';
import { Loader2, CheckCircle, XCircle, Clock } from 'lucide-react';

export default function TestResultsContent() {
    const searchParams = useSearchParams();
    const strategyId = searchParams.get('strategy');
    const testId = searchParams.get('test');

    const [loading, setLoading] = useState(true);
    const [testData, setTestData] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (strategyId && testId) {
            loadTestResults();
            // Poll for results if test is still running
            const interval = setInterval(() => {
                if (testData?.status === 'running') {
                    loadTestResults();
                }
            }, 3000);
            return () => clearInterval(interval);
        }
    }, [strategyId, testId, testData?.status]);

    const loadTestResults = async () => {
        try {
            setLoading(true);
            const response = await fetch(
                `/api/strategy-management/${strategyId}/tests/${testId}/results`
            );
            const data = await response.json();
            setTestData(data);
            setError(null);
        } catch (err) {
            setError('Failed to load test results');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    if (loading && !testData) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-center">
                    <Loader2 className="h-12 w-12 animate-spin text-blue-600 mx-auto mb-4" />
                    <p className="text-gray-600">Loading test results...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-center">
                    <XCircle className="h-12 w-12 text-red-600 mx-auto mb-4" />
                    <p className="text-gray-600">{error}</p>
                </div>
            </div>
        );
    }

    if (!testData) {
        return null;
    }

    const getStatusBadge = () => {
        const statusConfig = {
            running: { icon: Clock, color: 'blue', text: 'Running' },
            passed: { icon: CheckCircle, color: 'green', text: 'Passed' },
            failed: { icon: XCircle, color: 'red', text: 'Failed' }
        };

        const config = statusConfig[testData.status as keyof typeof statusConfig] || statusConfig.running;
        const Icon = config.icon;

        return (
            <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium bg-${config.color}-100 text-${config.color}-700`}>
                <Icon className="h-4 w-4" />
                {config.text}
            </span>
        );
    };

    return (
        <div className="p-6 space-y-6 bg-gray-50 min-h-screen">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-800">Backtest Results</h1>
                    <p className="text-sm text-gray-500 mt-1">
                        Test ID: {testId} • Started: {new Date(testData.started_at).toLocaleString()}
                    </p>
                </div>
                {getStatusBadge()}
            </div>

            {testData.status === 'running' ? (
                <div className="bg-white rounded-lg shadow-sm p-12 text-center">
                    <Loader2 className="h-12 w-12 animate-spin text-blue-600 mx-auto mb-4" />
                    <p className="text-gray-600">Backtest in progress...</p>
                    <p className="text-sm text-gray-500 mt-2">This page will update automatically</p>
                </div>
            ) : (
                <>
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <div className="lg:col-span-2">
                            <EquityCurve
                                data={testData.results?.equity_curve || []}
                                initialCapital={100000}
                            />
                        </div>
                        <div>
                            <MetricsDashboard metrics={testData.metrics || {}} />
                        </div>
                    </div>

                    <TradeLog trades={testData.results?.trades || []} />
                </>
            )}
        </div>
    );
}
