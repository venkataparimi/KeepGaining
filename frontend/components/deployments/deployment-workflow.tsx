"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
    Rocket, CheckCircle, XCircle, Clock, AlertTriangle,
    ChevronRight, ChevronLeft, Settings, Shield, Zap,
    GitBranch, Play, Pause, ArrowRight, Loader2
} from "lucide-react";
import { apiClient } from "@/lib/api/client";

interface Strategy {
    id: number;
    name: string;
    description?: string;
    status: string;
    versions?: { id: number; version: string; created_at: string }[];
}

interface DeploymentWorkflowProps {
    onComplete?: () => void;
    onCancel?: () => void;
}

type DeploymentType = 'sandbox' | 'canary' | 'production';

const STEPS = [
    { id: 1, name: 'Select Strategy', description: 'Choose strategy to deploy' },
    { id: 2, name: 'Version', description: 'Select version to deploy' },
    { id: 3, name: 'Environment', description: 'Choose deployment type' },
    { id: 4, name: 'Review', description: 'Confirm deployment' },
];

export function DeploymentWorkflow({ onComplete, onCancel }: DeploymentWorkflowProps) {
    const [currentStep, setCurrentStep] = useState(1);
    const [loading, setLoading] = useState(false);
    const [strategies, setStrategies] = useState<Strategy[]>([]);
    
    // Selection state
    const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);
    const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
    const [deploymentType, setDeploymentType] = useState<DeploymentType>('sandbox');
    const [canaryPercent, setCanaryPercent] = useState(10);
    
    // Result state
    const [deploymentResult, setDeploymentResult] = useState<{ success: boolean; message: string; id?: number } | null>(null);

    useEffect(() => {
        fetchStrategies();
    }, []);

    const fetchStrategies = async () => {
        setLoading(true);
        try {
            const data = await apiClient.listStrategiesManagement();
            setStrategies(data || []);
        } catch (error) {
            // Mock data for demo
            setStrategies([
                { id: 1, name: 'EMA Crossover', description: 'Moving average crossover strategy', status: 'active', versions: [{ id: 1, version: 'v1.0.0', created_at: '2024-11-20' }, { id: 2, version: 'v1.1.0', created_at: '2024-11-25' }] },
                { id: 2, name: 'RSI Reversal', description: 'RSI-based mean reversion', status: 'active', versions: [{ id: 3, version: 'v2.0.0', created_at: '2024-11-18' }] },
                { id: 3, name: 'Momentum Breakout', description: 'Breakout on momentum signals', status: 'active', versions: [{ id: 4, version: 'v1.0.0', created_at: '2024-11-22' }] },
            ]);
        } finally {
            setLoading(false);
        }
    };

    const handleDeploy = async () => {
        if (!selectedStrategy || !selectedVersion) return;
        
        setLoading(true);
        try {
            const result = await apiClient.createDeployment({
                strategy_id: selectedStrategy.id,
                version_id: selectedVersion,
                deployment_type: deploymentType,
                canary_percent: deploymentType === 'canary' ? canaryPercent : 0
            });
            
            setDeploymentResult({
                success: true,
                message: 'Deployment created successfully!',
                id: result.id
            });
        } catch (error) {
            setDeploymentResult({
                success: false,
                message: 'Deployment failed. Please try again.'
            });
        } finally {
            setLoading(false);
        }
    };

    const nextStep = () => setCurrentStep(prev => Math.min(prev + 1, 4));
    const prevStep = () => setCurrentStep(prev => Math.max(prev - 1, 1));

    const canProceed = () => {
        switch (currentStep) {
            case 1: return selectedStrategy !== null;
            case 2: return selectedVersion !== null;
            case 3: return true;
            case 4: return true;
            default: return false;
        }
    };

    return (
        <Card className="glass rounded-2xl overflow-hidden max-w-3xl mx-auto">
            <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10">
                <CardTitle className="flex items-center gap-2">
                    <Rocket className="h-5 w-5" />
                    New Deployment
                </CardTitle>
                <CardDescription>Deploy a strategy to live trading</CardDescription>
            </CardHeader>
            
            <CardContent className="p-6">
                {/* Progress Steps */}
                <div className="mb-8">
                    <div className="flex items-center justify-between mb-2">
                        {STEPS.map((step, idx) => (
                            <div key={step.id} className="flex items-center">
                                <div className={`flex items-center justify-center w-8 h-8 rounded-full border-2 transition-colors ${
                                    currentStep > step.id 
                                        ? 'bg-green-500 border-green-500 text-white'
                                        : currentStep === step.id
                                        ? 'border-primary bg-primary/20 text-primary'
                                        : 'border-muted-foreground/30 text-muted-foreground'
                                }`}>
                                    {currentStep > step.id ? (
                                        <CheckCircle className="h-4 w-4" />
                                    ) : (
                                        <span className="text-sm font-medium">{step.id}</span>
                                    )}
                                </div>
                                {idx < STEPS.length - 1 && (
                                    <div className={`w-16 md:w-24 h-0.5 mx-2 transition-colors ${
                                        currentStep > step.id ? 'bg-green-500' : 'bg-muted-foreground/30'
                                    }`} />
                                )}
                            </div>
                        ))}
                    </div>
                    <div className="flex justify-between text-xs text-muted-foreground px-1">
                        {STEPS.map(step => (
                            <span key={step.id} className={currentStep === step.id ? 'text-primary font-medium' : ''}>
                                {step.name}
                            </span>
                        ))}
                    </div>
                </div>

                {/* Step Content */}
                <div className="min-h-[300px]">
                    {/* Step 1: Select Strategy */}
                    {currentStep === 1 && (
                        <div className="space-y-4">
                            <h3 className="font-semibold mb-4">Select a Strategy</h3>
                            {loading ? (
                                <div className="flex items-center justify-center py-8">
                                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                                </div>
                            ) : (
                                <div className="grid gap-3">
                                    {strategies.map(strategy => (
                                        <div
                                            key={strategy.id}
                                            className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
                                                selectedStrategy?.id === strategy.id
                                                    ? 'border-primary bg-primary/10'
                                                    : 'border-border hover:border-primary/50'
                                            }`}
                                            onClick={() => setSelectedStrategy(strategy)}
                                        >
                                            <div className="flex items-center justify-between">
                                                <div>
                                                    <h4 className="font-medium">{strategy.name}</h4>
                                                    <p className="text-sm text-muted-foreground">{strategy.description}</p>
                                                </div>
                                                <Badge className="bg-green-500/20 text-green-400">
                                                    {strategy.status}
                                                </Badge>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Step 2: Select Version */}
                    {currentStep === 2 && selectedStrategy && (
                        <div className="space-y-4">
                            <h3 className="font-semibold mb-4">Select Version for {selectedStrategy.name}</h3>
                            <div className="grid gap-3">
                                {(selectedStrategy.versions || []).map(version => (
                                    <div
                                        key={version.id}
                                        className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
                                            selectedVersion === version.id
                                                ? 'border-primary bg-primary/10'
                                                : 'border-border hover:border-primary/50'
                                        }`}
                                        onClick={() => setSelectedVersion(version.id)}
                                    >
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-3">
                                                <GitBranch className="h-5 w-5 text-muted-foreground" />
                                                <div>
                                                    <h4 className="font-medium">{version.version}</h4>
                                                    <p className="text-sm text-muted-foreground">
                                                        Created: {new Date(version.created_at).toLocaleDateString()}
                                                    </p>
                                                </div>
                                            </div>
                                            {selectedVersion === version.id && (
                                                <CheckCircle className="h-5 w-5 text-primary" />
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Step 3: Deployment Type */}
                    {currentStep === 3 && (
                        <div className="space-y-4">
                            <h3 className="font-semibold mb-4">Choose Deployment Environment</h3>
                            <div className="grid gap-4">
                                <div
                                    className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
                                        deploymentType === 'sandbox'
                                            ? 'border-blue-500 bg-blue-500/10'
                                            : 'border-border hover:border-blue-500/50'
                                    }`}
                                    onClick={() => setDeploymentType('sandbox')}
                                >
                                    <div className="flex items-center gap-3">
                                        <div className="h-10 w-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
                                            <Shield className="h-5 w-5 text-blue-400" />
                                        </div>
                                        <div>
                                            <h4 className="font-medium">Sandbox</h4>
                                            <p className="text-sm text-muted-foreground">Paper trading - no real orders</p>
                                        </div>
                                    </div>
                                </div>

                                <div
                                    className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
                                        deploymentType === 'canary'
                                            ? 'border-yellow-500 bg-yellow-500/10'
                                            : 'border-border hover:border-yellow-500/50'
                                    }`}
                                    onClick={() => setDeploymentType('canary')}
                                >
                                    <div className="flex items-center gap-3">
                                        <div className="h-10 w-10 rounded-lg bg-yellow-500/20 flex items-center justify-center">
                                            <Zap className="h-5 w-5 text-yellow-400" />
                                        </div>
                                        <div className="flex-1">
                                            <h4 className="font-medium">Canary</h4>
                                            <p className="text-sm text-muted-foreground">Gradual rollout with limited capital</p>
                                        </div>
                                    </div>
                                    {deploymentType === 'canary' && (
                                        <div className="mt-4 space-y-2">
                                            <div className="flex items-center justify-between text-sm">
                                                <label htmlFor="canary-slider">Canary Percentage</label>
                                                <span className="font-medium">{canaryPercent}%</span>
                                            </div>
                                            <input
                                                id="canary-slider"
                                                type="range"
                                                min="5"
                                                max="50"
                                                value={canaryPercent}
                                                onChange={(e) => setCanaryPercent(parseInt(e.target.value))}
                                                className="w-full"
                                                aria-label="Canary deployment percentage"
                                            />
                                        </div>
                                    )}
                                </div>

                                <div
                                    className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
                                        deploymentType === 'production'
                                            ? 'border-green-500 bg-green-500/10'
                                            : 'border-border hover:border-green-500/50'
                                    }`}
                                    onClick={() => setDeploymentType('production')}
                                >
                                    <div className="flex items-center gap-3">
                                        <div className="h-10 w-10 rounded-lg bg-green-500/20 flex items-center justify-center">
                                            <Rocket className="h-5 w-5 text-green-400" />
                                        </div>
                                        <div>
                                            <h4 className="font-medium">Production</h4>
                                            <p className="text-sm text-muted-foreground">Full deployment with live trading</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Step 4: Review */}
                    {currentStep === 4 && (
                        <div className="space-y-4">
                            <h3 className="font-semibold mb-4">Review Deployment</h3>
                            
                            {deploymentResult ? (
                                <div className={`p-6 rounded-xl text-center ${
                                    deploymentResult.success 
                                        ? 'bg-green-500/10 border border-green-500/30'
                                        : 'bg-red-500/10 border border-red-500/30'
                                }`}>
                                    {deploymentResult.success ? (
                                        <CheckCircle className="h-12 w-12 text-green-400 mx-auto mb-3" />
                                    ) : (
                                        <XCircle className="h-12 w-12 text-red-400 mx-auto mb-3" />
                                    )}
                                    <p className={`font-medium ${deploymentResult.success ? 'text-green-400' : 'text-red-400'}`}>
                                        {deploymentResult.message}
                                    </p>
                                    {deploymentResult.id && (
                                        <p className="text-sm text-muted-foreground mt-2">
                                            Deployment ID: #{deploymentResult.id}
                                        </p>
                                    )}
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    <div className="p-4 rounded-xl bg-muted/30">
                                        <div className="grid grid-cols-2 gap-4 text-sm">
                                            <div>
                                                <p className="text-muted-foreground">Strategy</p>
                                                <p className="font-medium">{selectedStrategy?.name}</p>
                                            </div>
                                            <div>
                                                <p className="text-muted-foreground">Version</p>
                                                <p className="font-medium">
                                                    {selectedStrategy?.versions?.find(v => v.id === selectedVersion)?.version}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-muted-foreground">Environment</p>
                                                <p className="font-medium capitalize">{deploymentType}</p>
                                            </div>
                                            {deploymentType === 'canary' && (
                                                <div>
                                                    <p className="text-muted-foreground">Canary %</p>
                                                    <p className="font-medium">{canaryPercent}%</p>
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {deploymentType === 'production' && (
                                        <div className="p-4 rounded-xl bg-yellow-500/10 border border-yellow-500/30">
                                            <div className="flex items-start gap-3">
                                                <AlertTriangle className="h-5 w-5 text-yellow-400 shrink-0 mt-0.5" />
                                                <div>
                                                    <p className="font-medium text-yellow-400">Production Deployment</p>
                                                    <p className="text-sm text-muted-foreground">
                                                        This will deploy with live trading. Ensure you've tested in sandbox first.
                                                    </p>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    <Button 
                                        onClick={handleDeploy}
                                        className="w-full"
                                        disabled={loading}
                                    >
                                        {loading ? (
                                            <>
                                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                                Deploying...
                                            </>
                                        ) : (
                                            <>
                                                <Rocket className="h-4 w-4 mr-2" />
                                                Deploy Now
                                            </>
                                        )}
                                    </Button>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Navigation */}
                {!deploymentResult && (
                    <div className="flex items-center justify-between mt-6 pt-6 border-t border-border/50">
                        <Button
                            variant="outline"
                            onClick={currentStep === 1 ? onCancel : prevStep}
                        >
                            <ChevronLeft className="h-4 w-4 mr-1" />
                            {currentStep === 1 ? 'Cancel' : 'Back'}
                        </Button>
                        
                        {currentStep < 4 && (
                            <Button
                                onClick={nextStep}
                                disabled={!canProceed()}
                            >
                                Next
                                <ChevronRight className="h-4 w-4 ml-1" />
                            </Button>
                        )}
                    </div>
                )}

                {deploymentResult && (
                    <div className="flex justify-center mt-6 pt-6 border-t border-border/50">
                        <Button onClick={onComplete}>
                            Done
                        </Button>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
