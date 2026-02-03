"use client";

import React, { useState, useEffect } from 'react';
import { CodeEditor } from '@/components/strategy/code-editor';
import { apiClient } from '@/lib/api/client';
import { Plus, Save, History, Play, GitBranch } from 'lucide-react';

interface Strategy {
    id: number;
    name: string;
    description: string;
    status: string;
    created_at: string;
    current_version_id: number;
}

export default function StrategyManagementPage() {
    const [strategies, setStrategies] = useState<Strategy[]>([]);
    const [selectedStrategy, setSelectedStrategy] = useState<any>(null);
    const [code, setCode] = useState('');
    const [versions, setVersions] = useState<any[]>([]);
    const [showVersionHistory, setShowVersionHistory] = useState(false);
    const [commitMessage, setCommitMessage] = useState('');

    useEffect(() => {
        loadStrategies();
    }, []);

    const loadStrategies = async () => {
        try {
            const data = await apiClient.listStrategiesManagement();
            setStrategies(data);
        } catch (error) {
            console.error('Failed to load strategies', error);
        }
    };

    const loadStrategy = async (id: number) => {
        try {
            const strategy = await apiClient.getStrategyManagement(id);
            setSelectedStrategy(strategy);
            setCode(strategy.current_version?.code || '');

            const versionList = await apiClient.listStrategyVersions(id);
            setVersions(versionList);
        } catch (error) {
            console.error('Failed to load strategy', error);
        }
    };

    const saveVersion = async () => {
        if (!selectedStrategy || !commitMessage) {
            alert('Please enter a commit message');
            return;
        }

        try {
            await apiClient.createStrategyVersion(selectedStrategy.id, {
                code,
                commit_message: commitMessage
            });
            setCommitMessage('');
            loadStrategy(selectedStrategy.id);
            alert('Version saved successfully');
        } catch (error) {
            console.error('Failed to save version', error);
            alert('Failed to save version');
        }
    };

    const runTest = async (testType: string) => {
        if (!selectedStrategy) return;

        try {
            await apiClient.runStrategyTest(selectedStrategy.id, testType);
            alert(`${testType} test started`);
        } catch (error) {
            console.error('Failed to run test', error);
        }
    };

    return (
        <div className="p-6 space-y-6 bg-gray-50 min-h-screen">
            <div className="flex justify-between items-center">
                <h1 className="text-2xl font-bold text-gray-800">Strategy Management</h1>
                <button className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                    <Plus className="h-4 w-4" />
                    New Strategy
                </button>
            </div>

            <div className="grid grid-cols-12 gap-6">
                {/* Strategy List */}
                <div className="col-span-3 bg-white rounded-lg shadow-sm p-4">
                    <h2 className="font-semibold text-gray-700 mb-4">Strategies</h2>
                    <div className="space-y-2">
                        {strategies.map((strategy) => (
                            <div
                                key={strategy.id}
                                onClick={() => loadStrategy(strategy.id)}
                                className={`p-3 rounded-lg cursor-pointer transition-colors ${selectedStrategy?.id === strategy.id
                                        ? 'bg-blue-50 border border-blue-200'
                                        : 'hover:bg-gray-50 border border-transparent'
                                    }`}
                            >
                                <div className="font-medium text-gray-900">{strategy.name}</div>
                                <div className="text-xs text-gray-500 mt-1">{strategy.status}</div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Editor */}
                <div className="col-span-9 space-y-4">
                    {selectedStrategy ? (
                        <>
                            <div className="bg-white rounded-lg shadow-sm p-4">
                                <div className="flex justify-between items-center mb-4">
                                    <div>
                                        <h2 className="text-lg font-semibold text-gray-800">
                                            {selectedStrategy.name}
                                        </h2>
                                        <p className="text-sm text-gray-500">{selectedStrategy.description}</p>
                                    </div>
                                    <div className="flex gap-2">
                                        <button
                                            onClick={() => setShowVersionHistory(!showVersionHistory)}
                                            className="flex items-center gap-2 px-3 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                                        >
                                            <History className="h-4 w-4" />
                                            History
                                        </button>
                                        <button
                                            onClick={() => runTest('backtest')}
                                            className="flex items-center gap-2 px-3 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                                        >
                                            <Play className="h-4 w-4" />
                                            Test
                                        </button>
                                    </div>
                                </div>

                                <CodeEditor
                                    value={code}
                                    onChange={(value) => setCode(value || '')}
                                    height="500px"
                                />

                                <div className="mt-4 flex gap-3">
                                    <input
                                        type="text"
                                        placeholder="Commit message..."
                                        value={commitMessage}
                                        onChange={(e) => setCommitMessage(e.target.value)}
                                        className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                    />
                                    <button
                                        onClick={saveVersion}
                                        className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
                                    >
                                        <Save className="h-4 w-4" />
                                        Save Version
                                    </button>
                                </div>
                            </div>

                            {showVersionHistory && (
                                <div className="bg-white rounded-lg shadow-sm p-4">
                                    <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                                        <GitBranch className="h-4 w-4" />
                                        Version History
                                    </h3>
                                    <div className="space-y-2">
                                        {versions.map((version) => (
                                            <div
                                                key={version.id}
                                                className="p-3 border border-gray-200 rounded-lg hover:bg-gray-50"
                                            >
                                                <div className="flex justify-between items-start">
                                                    <div>
                                                        <div className="font-medium text-gray-900">
                                                            Version {version.version_number}
                                                        </div>
                                                        <div className="text-sm text-gray-600 mt-1">
                                                            {version.commit_message}
                                                        </div>
                                                    </div>
                                                    <div className="text-xs text-gray-500">
                                                        {new Date(version.created_at).toLocaleString()}
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </>
                    ) : (
                        <div className="bg-white rounded-lg shadow-sm p-12 text-center text-gray-500">
                            Select a strategy to edit
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
