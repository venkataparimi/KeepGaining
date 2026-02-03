"use client";

import React, { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Activity, Zap, Settings } from 'lucide-react';

interface BrokerStatus {
    broker_name: string;
    is_healthy: boolean;
    is_primary: boolean;
    response_time_ms: number;
    error_message?: string;
    last_checked: string;
}

export default function BrokerStatusPage() {
    const [brokers, setBrokers] = useState<BrokerStatus[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadBrokerStatuses();
        const interval = setInterval(loadBrokerStatuses, 10000); // Refresh every 10s
        return () => clearInterval(interval);
    }, []);

    const loadBrokerStatuses = async () => {
        try {
            const response = await fetch('/api/broker-management/brokers/status');
            if (!response.ok) {
                throw new Error('Failed to fetch broker statuses');
            }
            const data = await response.json();
            setBrokers(Array.isArray(data) ? data : []);
        } catch (error) {
            console.error('Failed to load broker statuses', error);
            setBrokers([]); // Set empty array on error
        } finally {
            setLoading(false);
        }
    };

    const checkHealth = async (brokerId: number) => {
        try {
            await fetch(`/api/broker-management/brokers/${brokerId}/health`);
            loadBrokerStatuses();
        } catch (error) {
            console.error('Health check failed', error);
        }
    };

    return (
        <div className="p-6 space-y-6 bg-gray-50 min-h-screen">
            <div className="flex justify-between items-center">
                <h1 className="text-2xl font-bold text-gray-800">Broker Status</h1>
                <button
                    onClick={loadBrokerStatuses}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
                >
                    <Activity className="h-4 w-4" />
                    Refresh
                </button>
            </div>

            {loading ? (
                <div className="text-center py-12">
                    <div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full mx-auto"></div>
                    <p className="text-gray-600 mt-4">Loading broker statuses...</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {brokers.map((broker, index) => (
                        <div
                            key={index}
                            className={`bg-white rounded-lg shadow-sm p-6 border-2 ${broker.is_primary ? 'border-blue-500' : 'border-transparent'
                                }`}
                        >
                            <div className="flex justify-between items-start mb-4">
                                <div>
                                    <h3 className="font-semibold text-gray-900 capitalize flex items-center gap-2">
                                        {broker.broker_name}
                                        {broker.is_primary && (
                                            <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">
                                                Primary
                                            </span>
                                        )}
                                    </h3>
                                    <p className="text-xs text-gray-500 mt-1">
                                        Last checked: {new Date(broker.last_checked).toLocaleTimeString()}
                                    </p>
                                </div>
                                {broker.is_healthy ? (
                                    <CheckCircle className="h-6 w-6 text-green-600" />
                                ) : (
                                    <XCircle className="h-6 w-6 text-red-600" />
                                )}
                            </div>

                            <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-gray-600">Status</span>
                                    <span className={`text-sm font-medium ${broker.is_healthy ? 'text-green-600' : 'text-red-600'
                                        }`}>
                                        {broker.is_healthy ? 'Healthy' : 'Unhealthy'}
                                    </span>
                                </div>

                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-gray-600 flex items-center gap-1">
                                        <Zap className="h-3 w-3" />
                                        Response Time
                                    </span>
                                    <span className="text-sm font-medium text-gray-900">
                                        {broker.response_time_ms?.toFixed(0)}ms
                                    </span>
                                </div>

                                {broker.error_message && (
                                    <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                                        <p className="text-xs text-red-700">{broker.error_message}</p>
                                    </div>
                                )}
                            </div>

                            <div className="mt-4 pt-4 border-t border-gray-200 flex gap-2">
                                <button
                                    onClick={() => checkHealth(index + 1)}
                                    className="flex-1 px-3 py-2 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
                                >
                                    Check Health
                                </button>
                                <button className="px-3 py-2 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200">
                                    <Settings className="h-4 w-4" />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {!loading && brokers.length === 0 && (
                <div className="bg-white rounded-lg shadow-sm p-12 text-center">
                    <p className="text-gray-500">No brokers configured</p>
                    <button className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                        Add Broker
                    </button>
                </div>
            )}
        </div>
    );
}
