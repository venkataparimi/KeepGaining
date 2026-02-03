"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { 
    Brain, 
    TrendingUp, 
    TrendingDown, 
    Activity, 
    RefreshCw, 
    Play,
    CheckCircle2,
    XCircle,
    AlertTriangle,
    Zap
} from "lucide-react";
import { apiClient, MLModelStatus, MLSignalEnhancement } from "@/lib/api/client";

interface PredictionResult {
    symbol: string;
    prediction: number;
    probability: number;
    confidence: number;
    features: Record<string, number>;
}

export function MLDashboard() {
    const [models, setModels] = useState<MLModelStatus[]>([]);
    const [selectedSymbol, setSelectedSymbol] = useState<string>("");
    const [prediction, setPrediction] = useState<PredictionResult | null>(null);
    const [enhancement, setEnhancement] = useState<MLSignalEnhancement | null>(null);
    const [loading, setLoading] = useState(false);
    const [trainingSymbol, setTrainingSymbol] = useState<string>("");
    const [isTraining, setIsTraining] = useState(false);

    const symbols = ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"];

    useEffect(() => {
        loadModels();
    }, []);

    const loadModels = async () => {
        try {
            const data = await apiClient.getMLModelStatus();
            setModels(data);
        } catch (error) {
            console.error("Failed to load ML models:", error);
        }
    };

    const getPrediction = async () => {
        if (!selectedSymbol) return;
        setLoading(true);
        try {
            const data = await apiClient.getMLPrediction(selectedSymbol);
            setPrediction(data);
        } catch (error) {
            console.error("Failed to get prediction:", error);
        } finally {
            setLoading(false);
        }
    };

    const enhanceSignal = async () => {
        if (!selectedSymbol) return;
        setLoading(true);
        try {
            const data = await apiClient.enhanceSignal(selectedSymbol, 0.5);
            setEnhancement(data);
        } catch (error) {
            console.error("Failed to enhance signal:", error);
        } finally {
            setLoading(false);
        }
    };

    const trainModel = async () => {
        if (!trainingSymbol) return;
        setIsTraining(true);
        try {
            await apiClient.trainMLModel(trainingSymbol);
            await loadModels();
        } catch (error) {
            console.error("Failed to train model:", error);
        } finally {
            setIsTraining(false);
        }
    };

    const getSignalColor = (value: number) => {
        if (value >= 0.7) return "text-green-500";
        if (value >= 0.3) return "text-yellow-500";
        return "text-red-500";
    };

    const getSignalLabel = (value: number) => {
        if (value >= 0.7) return "Strong Buy";
        if (value >= 0.55) return "Buy";
        if (value >= 0.45) return "Neutral";
        if (value >= 0.3) return "Sell";
        return "Strong Sell";
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold flex items-center gap-2">
                        <Brain className="h-6 w-6 text-purple-500" />
                        ML Signal Enhancement
                    </h2>
                    <p className="text-muted-foreground">
                        Machine learning powered signal analysis and prediction
                    </p>
                </div>
                <Button variant="outline" onClick={loadModels}>
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Refresh
                </Button>
            </div>

            <Tabs defaultValue="predict" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="predict">Predict</TabsTrigger>
                    <TabsTrigger value="models">Models</TabsTrigger>
                    <TabsTrigger value="train">Train</TabsTrigger>
                </TabsList>

                <TabsContent value="predict" className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Signal Prediction Card */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <Zap className="h-5 w-5 text-yellow-500" />
                                    Signal Prediction
                                </CardTitle>
                                <CardDescription>
                                    Get ML-powered buy/sell prediction for a symbol
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="flex gap-2">
                                    <Select value={selectedSymbol} onValueChange={setSelectedSymbol}>
                                        <SelectTrigger className="flex-1">
                                            <SelectValue placeholder="Select symbol" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {symbols.map((s) => (
                                                <SelectItem key={s} value={s}>{s}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <Button onClick={getPrediction} disabled={loading || !selectedSymbol}>
                                        {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : "Predict"}
                                    </Button>
                                </div>

                                {prediction && (
                                    <div className="space-y-4 pt-4 border-t">
                                        <div className="flex items-center justify-between">
                                            <span className="text-sm text-muted-foreground">Prediction</span>
                                            <div className={`text-2xl font-bold ${getSignalColor(prediction.probability)}`}>
                                                {getSignalLabel(prediction.probability)}
                                            </div>
                                        </div>
                                        
                                        <div className="space-y-2">
                                            <div className="flex justify-between text-sm">
                                                <span>Probability</span>
                                                <span>{(prediction.probability * 100).toFixed(1)}%</span>
                                            </div>
                                            <Progress value={prediction.probability * 100} className="h-2" />
                                        </div>

                                        <div className="space-y-2">
                                            <div className="flex justify-between text-sm">
                                                <span>Confidence</span>
                                                <span>{(prediction.confidence * 100).toFixed(1)}%</span>
                                            </div>
                                            <Progress value={prediction.confidence * 100} className="h-2" />
                                        </div>

                                        <div className="pt-2 border-t">
                                            <span className="text-sm text-muted-foreground">Key Features</span>
                                            <div className="grid grid-cols-2 gap-2 mt-2">
                                                {Object.entries(prediction.features).slice(0, 6).map(([key, value]) => (
                                                    <div key={key} className="flex justify-between text-xs">
                                                        <span className="text-muted-foreground">{key}</span>
                                                        <span>{typeof value === 'number' ? value.toFixed(2) : value}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        {/* Signal Enhancement Card */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <Activity className="h-5 w-5 text-blue-500" />
                                    Signal Enhancement
                                </CardTitle>
                                <CardDescription>
                                    Enhance trading signals with ML confidence scoring
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="flex gap-2">
                                    <Select value={selectedSymbol} onValueChange={setSelectedSymbol}>
                                        <SelectTrigger className="flex-1">
                                            <SelectValue placeholder="Select symbol" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {symbols.map((s) => (
                                                <SelectItem key={s} value={s}>{s}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <Button onClick={enhanceSignal} disabled={loading || !selectedSymbol}>
                                        {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : "Enhance"}
                                    </Button>
                                </div>

                                {enhancement && (
                                    <div className="space-y-4 pt-4 border-t">
                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="text-center p-3 bg-muted rounded-lg">
                                                <div className="text-xs text-muted-foreground mb-1">Original Signal</div>
                                                <div className="text-xl font-semibold">
                                                    {(enhancement.original_signal * 100).toFixed(0)}%
                                                </div>
                                            </div>
                                            <div className="text-center p-3 bg-primary/10 rounded-lg">
                                                <div className="text-xs text-muted-foreground mb-1">Enhanced Signal</div>
                                                <div className={`text-xl font-semibold ${getSignalColor(enhancement.enhanced_signal)}`}>
                                                    {(enhancement.enhanced_signal * 100).toFixed(0)}%
                                                </div>
                                            </div>
                                        </div>

                                        <div className="space-y-2">
                                            <div className="flex justify-between text-sm">
                                                <span>Model Confidence</span>
                                                <span>{(enhancement.confidence * 100).toFixed(1)}%</span>
                                            </div>
                                            <Progress value={enhancement.confidence * 100} className="h-2" />
                                        </div>

                                        <div className="pt-2">
                                            <span className="text-sm text-muted-foreground">Features Used</span>
                                            <div className="flex flex-wrap gap-1 mt-2">
                                                {enhancement.features_used.map((feature) => (
                                                    <Badge key={feature} variant="secondary" className="text-xs">
                                                        {feature}
                                                    </Badge>
                                                ))}
                                            </div>
                                        </div>

                                        <div className="text-xs text-muted-foreground">
                                            Model: {enhancement.model_version}
                                        </div>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </div>
                </TabsContent>

                <TabsContent value="models" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle>Trained Models</CardTitle>
                            <CardDescription>
                                Overview of all ML models and their performance metrics
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            {models.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground">
                                    <Brain className="h-12 w-12 mx-auto mb-4 opacity-20" />
                                    <p>No models trained yet</p>
                                    <p className="text-sm">Train a model to see it here</p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    {models.map((model) => (
                                        <div
                                            key={model.model_id}
                                            className="flex items-center justify-between p-4 border rounded-lg"
                                        >
                                            <div className="flex items-center gap-4">
                                                <div className={`p-2 rounded-full ${model.is_active ? 'bg-green-100' : 'bg-gray-100'}`}>
                                                    {model.is_active ? (
                                                        <CheckCircle2 className="h-5 w-5 text-green-600" />
                                                    ) : (
                                                        <XCircle className="h-5 w-5 text-gray-400" />
                                                    )}
                                                </div>
                                                <div>
                                                    <div className="font-medium">{model.symbol}</div>
                                                    <div className="text-sm text-muted-foreground">
                                                        {model.model_type} • {model.samples_used.toLocaleString()} samples
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="grid grid-cols-4 gap-6 text-center">
                                                <div>
                                                    <div className="text-xs text-muted-foreground">Accuracy</div>
                                                    <div className="font-semibold">{(model.accuracy * 100).toFixed(1)}%</div>
                                                </div>
                                                <div>
                                                    <div className="text-xs text-muted-foreground">Precision</div>
                                                    <div className="font-semibold">{(model.precision * 100).toFixed(1)}%</div>
                                                </div>
                                                <div>
                                                    <div className="text-xs text-muted-foreground">Recall</div>
                                                    <div className="font-semibold">{(model.recall * 100).toFixed(1)}%</div>
                                                </div>
                                                <div>
                                                    <div className="text-xs text-muted-foreground">F1 Score</div>
                                                    <div className="font-semibold">{(model.f1_score * 100).toFixed(1)}%</div>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="train" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Play className="h-5 w-5 text-green-500" />
                                Train New Model
                            </CardTitle>
                            <CardDescription>
                                Train a new ML model for signal prediction
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="flex gap-2">
                                <Select value={trainingSymbol} onValueChange={setTrainingSymbol}>
                                    <SelectTrigger className="flex-1">
                                        <SelectValue placeholder="Select symbol to train" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {symbols.map((s) => (
                                            <SelectItem key={s} value={s}>{s}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                                <Button 
                                    onClick={trainModel} 
                                    disabled={isTraining || !trainingSymbol}
                                    className="min-w-[120px]"
                                >
                                    {isTraining ? (
                                        <>
                                            <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                                            Training...
                                        </>
                                    ) : (
                                        <>
                                            <Play className="h-4 w-4 mr-2" />
                                            Train Model
                                        </>
                                    )}
                                </Button>
                            </div>

                            <div className="bg-muted p-4 rounded-lg">
                                <h4 className="font-medium mb-2 flex items-center gap-2">
                                    <AlertTriangle className="h-4 w-4 text-yellow-500" />
                                    Training Information
                                </h4>
                                <ul className="text-sm text-muted-foreground space-y-1">
                                    <li>• Training uses historical price data and technical indicators</li>
                                    <li>• Models are trained with RandomForest and XGBoost ensemble</li>
                                    <li>• Training may take 1-5 minutes depending on data volume</li>
                                    <li>• Models are automatically validated with cross-validation</li>
                                </ul>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}
