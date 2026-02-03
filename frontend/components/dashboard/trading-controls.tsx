"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { apiClient } from "@/lib/api/client";
import { Brain, Activity } from "lucide-react";

export function TradingControls() {
    const [config, setConfig] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadConfig();
    }, []);

    const loadConfig = async () => {
        try {
            const data = await apiClient.getConfig();
            setConfig(data);
        } catch (error) {
            console.error("Failed to load config", error);
        } finally {
            setLoading(false);
        }
    };

    const toggleAIValidation = async (enabled: boolean) => {
        try {
            // Optimistic update
            setConfig((prev: any) => ({ ...prev, ai_validation_enabled: enabled }));
            
            await apiClient.updateConfig({ ai_validation_enabled: enabled });
            console.log(`AI Validation ${enabled ? 'Enabled' : 'Disabled'}`);
        } catch (error) {
            // Revert on failure
            setConfig((prev: any) => ({ ...prev, ai_validation_enabled: !enabled }));
            console.error("Failed to update configuration", error);
        }
    };

    if (loading) return null;

    return (
        <Card>
            <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Activity className="h-4 w-4" />
                    Trading Controls
                </CardTitle>
            </CardHeader>
            <CardContent>
                <div className="flex items-center justify-between space-x-2">
                    <div className="flex flex-col space-y-1">
                        <Label htmlFor="ai-validation" className="flex items-center gap-2 font-medium">
                            <Brain className="h-4 w-4 text-purple-500" />
                            Comet AI Validation
                        </Label>
                        <span className="text-xs text-muted-foreground">
                            Validate signals with Perplexity Pro
                        </span>
                    </div>
                    <Switch
                        id="ai-validation"
                        checked={config?.ai_validation_enabled || false}
                        onCheckedChange={toggleAIValidation}
                    />
                </div>
            </CardContent>
        </Card>
    );
}
