"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { 
    Settings, Shield, Bell, Wallet, AlertTriangle, 
    Save, RefreshCw, CheckCircle, XCircle, Loader2,
    DollarSign, TrendingDown, Ban, Moon, BarChart3
} from "lucide-react";
import { apiClient, RiskSettings, NotificationSettings } from "@/lib/api/client";

export default function SettingsPage() {
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    
    // Risk settings state
    const [riskSettings, setRiskSettings] = useState<RiskSettings>({
        max_capital_per_trade: 50000,
        max_capital_per_day: 200000,
        max_open_positions: 5,
        max_loss_per_trade: 2000,
        max_loss_per_day: 10000,
        max_drawdown_percent: 5,
        default_position_size_percent: 5,
        default_stop_loss_percent: 1,
        default_take_profit_percent: 2,
        allow_overnight_positions: false,
        allow_options_trading: true,
        allow_futures_trading: true,
    });
    
    // Notification settings state
    const [notificationSettings, setNotificationSettings] = useState<NotificationSettings>({
        email_enabled: false,
        email_address: null,
        email_on_trade: true,
        email_on_error: true,
        email_daily_summary: true,
        webhook_enabled: false,
        webhook_url: null,
        push_enabled: false,
    });

    const fetchSettings = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await apiClient.getAllSettings();
            setRiskSettings(data.risk);
            setNotificationSettings(data.notifications);
        } catch (err) {
            console.error("Failed to fetch settings:", err);
            setError("Failed to load settings. Using defaults.");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchSettings();
    }, [fetchSettings]);

    const saveRiskSettings = async () => {
        setSaving(true);
        setSaveSuccess(null);
        setError(null);
        try {
            await apiClient.updateRiskSettings(riskSettings);
            setSaveSuccess("Risk settings saved successfully!");
            setTimeout(() => setSaveSuccess(null), 3000);
        } catch (err) {
            console.error("Failed to save risk settings:", err);
            setError("Failed to save risk settings");
        } finally {
            setSaving(false);
        }
    };

    const saveNotificationSettings = async () => {
        setSaving(true);
        setSaveSuccess(null);
        setError(null);
        try {
            await apiClient.updateNotificationSettings(notificationSettings);
            setSaveSuccess("Notification settings saved successfully!");
            setTimeout(() => setSaveSuccess(null), 3000);
        } catch (err) {
            console.error("Failed to save notification settings:", err);
            setError("Failed to save notification settings");
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-screen">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        );
    }

    return (
        <div className="p-8 space-y-6 max-w-6xl mx-auto">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold gradient-text flex items-center gap-3">
                        <Settings className="h-8 w-8" />
                        Settings
                    </h1>
                    <p className="text-muted-foreground mt-1">
                        Configure your trading platform preferences and risk management
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchSettings}>
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Refresh
                </Button>
            </div>

            {/* Status Messages */}
            {saveSuccess && (
                <div className="flex items-center gap-2 p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
                    <CheckCircle className="h-5 w-5 text-green-500" />
                    <span className="text-green-500">{saveSuccess}</span>
                </div>
            )}
            {error && (
                <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                    <XCircle className="h-5 w-5 text-red-500" />
                    <span className="text-red-500">{error}</span>
                </div>
            )}

            {/* Settings Tabs */}
            <Tabs defaultValue="risk" className="space-y-6">
                <TabsList className="bg-muted/20 p-1">
                    <TabsTrigger value="risk" className="flex items-center gap-2">
                        <Shield className="h-4 w-4" />
                        Risk Management
                    </TabsTrigger>
                    <TabsTrigger value="notifications" className="flex items-center gap-2">
                        <Bell className="h-4 w-4" />
                        Notifications
                    </TabsTrigger>
                </TabsList>

                {/* Risk Management Tab */}
                <TabsContent value="risk" className="space-y-6">
                    {/* Capital Limits */}
                    <Card className="glass rounded-2xl">
                        <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10">
                            <div className="flex items-center gap-3">
                                <Wallet className="h-5 w-5 text-primary" />
                                <div>
                                    <CardTitle>Capital Limits</CardTitle>
                                    <CardDescription>Set maximum capital exposure limits</CardDescription>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="pt-6 space-y-6">
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                <div className="space-y-2">
                                    <Label>Max Capital Per Trade (₹)</Label>
                                    <Input
                                        type="number"
                                        value={riskSettings.max_capital_per_trade}
                                        onChange={(e) => setRiskSettings({
                                            ...riskSettings,
                                            max_capital_per_trade: parseFloat(e.target.value) || 0
                                        })}
                                        className="bg-muted/20"
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        Maximum capital allowed for a single trade
                                    </p>
                                </div>
                                <div className="space-y-2">
                                    <Label>Max Capital Per Day (₹)</Label>
                                    <Input
                                        type="number"
                                        value={riskSettings.max_capital_per_day}
                                        onChange={(e) => setRiskSettings({
                                            ...riskSettings,
                                            max_capital_per_day: parseFloat(e.target.value) || 0
                                        })}
                                        className="bg-muted/20"
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        Maximum total capital exposure in a day
                                    </p>
                                </div>
                                <div className="space-y-2">
                                    <Label>Max Open Positions</Label>
                                    <Input
                                        type="number"
                                        value={riskSettings.max_open_positions}
                                        onChange={(e) => setRiskSettings({
                                            ...riskSettings,
                                            max_open_positions: parseInt(e.target.value) || 0
                                        })}
                                        className="bg-muted/20"
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        Maximum simultaneous open positions
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Loss Limits */}
                    <Card className="glass rounded-2xl">
                        <CardHeader className="bg-gradient-to-r from-red-500/10 to-orange-500/10">
                            <div className="flex items-center gap-3">
                                <TrendingDown className="h-5 w-5 text-red-500" />
                                <div>
                                    <CardTitle>Loss Limits</CardTitle>
                                    <CardDescription>Define maximum acceptable losses</CardDescription>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="pt-6 space-y-6">
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                <div className="space-y-2">
                                    <Label>Max Loss Per Trade (₹)</Label>
                                    <Input
                                        type="number"
                                        value={riskSettings.max_loss_per_trade}
                                        onChange={(e) => setRiskSettings({
                                            ...riskSettings,
                                            max_loss_per_trade: parseFloat(e.target.value) || 0
                                        })}
                                        className="bg-muted/20"
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        Auto-close position at this loss
                                    </p>
                                </div>
                                <div className="space-y-2">
                                    <Label>Max Loss Per Day (₹)</Label>
                                    <Input
                                        type="number"
                                        value={riskSettings.max_loss_per_day}
                                        onChange={(e) => setRiskSettings({
                                            ...riskSettings,
                                            max_loss_per_day: parseFloat(e.target.value) || 0
                                        })}
                                        className="bg-muted/20"
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        Stop trading for the day at this loss
                                    </p>
                                </div>
                                <div className="space-y-2">
                                    <Label>Max Drawdown (%)</Label>
                                    <Input
                                        type="number"
                                        value={riskSettings.max_drawdown_percent}
                                        onChange={(e) => setRiskSettings({
                                            ...riskSettings,
                                            max_drawdown_percent: parseFloat(e.target.value) || 0
                                        })}
                                        className="bg-muted/20"
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        Pause trading when drawdown exceeds
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Position Sizing */}
                    <Card className="glass rounded-2xl">
                        <CardHeader className="bg-gradient-to-r from-blue-500/10 to-cyan-500/10">
                            <div className="flex items-center gap-3">
                                <BarChart3 className="h-5 w-5 text-blue-500" />
                                <div>
                                    <CardTitle>Default Position Sizing</CardTitle>
                                    <CardDescription>Default parameters for new strategies</CardDescription>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="pt-6 space-y-6">
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                <div className="space-y-2">
                                    <Label>Position Size (% of Capital)</Label>
                                    <Input
                                        type="number"
                                        value={riskSettings.default_position_size_percent}
                                        onChange={(e) => setRiskSettings({
                                            ...riskSettings,
                                            default_position_size_percent: parseFloat(e.target.value) || 0
                                        })}
                                        className="bg-muted/20"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Default Stop Loss (%)</Label>
                                    <Input
                                        type="number"
                                        value={riskSettings.default_stop_loss_percent}
                                        onChange={(e) => setRiskSettings({
                                            ...riskSettings,
                                            default_stop_loss_percent: parseFloat(e.target.value) || 0
                                        })}
                                        className="bg-muted/20"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Default Take Profit (%)</Label>
                                    <Input
                                        type="number"
                                        value={riskSettings.default_take_profit_percent}
                                        onChange={(e) => setRiskSettings({
                                            ...riskSettings,
                                            default_take_profit_percent: parseFloat(e.target.value) || 0
                                        })}
                                        className="bg-muted/20"
                                    />
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Trading Restrictions */}
                    <Card className="glass rounded-2xl">
                        <CardHeader className="bg-gradient-to-r from-yellow-500/10 to-amber-500/10">
                            <div className="flex items-center gap-3">
                                <Ban className="h-5 w-5 text-yellow-500" />
                                <div>
                                    <CardTitle>Trading Restrictions</CardTitle>
                                    <CardDescription>Control what types of trading are allowed</CardDescription>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="pt-6 space-y-6">
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                <div className="flex items-center justify-between p-4 bg-muted/20 rounded-lg">
                                    <div className="flex items-center gap-3">
                                        <Moon className="h-5 w-5 text-muted-foreground" />
                                        <div>
                                            <Label>Overnight Positions</Label>
                                            <p className="text-xs text-muted-foreground">
                                                Hold positions after market close
                                            </p>
                                        </div>
                                    </div>
                                    <Switch
                                        checked={riskSettings.allow_overnight_positions}
                                        onCheckedChange={(checked) => setRiskSettings({
                                            ...riskSettings,
                                            allow_overnight_positions: checked
                                        })}
                                    />
                                </div>
                                <div className="flex items-center justify-between p-4 bg-muted/20 rounded-lg">
                                    <div className="flex items-center gap-3">
                                        <DollarSign className="h-5 w-5 text-muted-foreground" />
                                        <div>
                                            <Label>Options Trading</Label>
                                            <p className="text-xs text-muted-foreground">
                                                Allow options strategies
                                            </p>
                                        </div>
                                    </div>
                                    <Switch
                                        checked={riskSettings.allow_options_trading}
                                        onCheckedChange={(checked) => setRiskSettings({
                                            ...riskSettings,
                                            allow_options_trading: checked
                                        })}
                                    />
                                </div>
                                <div className="flex items-center justify-between p-4 bg-muted/20 rounded-lg">
                                    <div className="flex items-center gap-3">
                                        <AlertTriangle className="h-5 w-5 text-muted-foreground" />
                                        <div>
                                            <Label>Futures Trading</Label>
                                            <p className="text-xs text-muted-foreground">
                                                Allow futures contracts
                                            </p>
                                        </div>
                                    </div>
                                    <Switch
                                        checked={riskSettings.allow_futures_trading}
                                        onCheckedChange={(checked) => setRiskSettings({
                                            ...riskSettings,
                                            allow_futures_trading: checked
                                        })}
                                    />
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Save Button */}
                    <div className="flex justify-end">
                        <Button 
                            onClick={saveRiskSettings} 
                            disabled={saving}
                            className="bg-gradient-to-r from-primary to-secondary"
                        >
                            {saving ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                                <Save className="h-4 w-4 mr-2" />
                            )}
                            Save Risk Settings
                        </Button>
                    </div>
                </TabsContent>

                {/* Notifications Tab */}
                <TabsContent value="notifications" className="space-y-6">
                    {/* Email Notifications */}
                    <Card className="glass rounded-2xl">
                        <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <Bell className="h-5 w-5 text-primary" />
                                    <div>
                                        <CardTitle>Email Notifications</CardTitle>
                                        <CardDescription>Configure email alerts</CardDescription>
                                    </div>
                                </div>
                                <Switch
                                    checked={notificationSettings.email_enabled}
                                    onCheckedChange={(checked) => setNotificationSettings({
                                        ...notificationSettings,
                                        email_enabled: checked
                                    })}
                                />
                            </div>
                        </CardHeader>
                        {notificationSettings.email_enabled && (
                            <CardContent className="pt-6 space-y-6">
                                <div className="space-y-2">
                                    <Label>Email Address</Label>
                                    <Input
                                        type="email"
                                        placeholder="your@email.com"
                                        value={notificationSettings.email_address || ""}
                                        onChange={(e) => setNotificationSettings({
                                            ...notificationSettings,
                                            email_address: e.target.value || null
                                        })}
                                        className="bg-muted/20 max-w-md"
                                    />
                                </div>
                                <div className="border-t border-border/50 my-4" />
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                    <div className="flex items-center justify-between p-4 bg-muted/20 rounded-lg">
                                        <div>
                                            <Label>Trade Executions</Label>
                                            <p className="text-xs text-muted-foreground">
                                                Get notified on every trade
                                            </p>
                                        </div>
                                        <Switch
                                            checked={notificationSettings.email_on_trade}
                                            onCheckedChange={(checked) => setNotificationSettings({
                                                ...notificationSettings,
                                                email_on_trade: checked
                                            })}
                                        />
                                    </div>
                                    <div className="flex items-center justify-between p-4 bg-muted/20 rounded-lg">
                                        <div>
                                            <Label>Errors & Alerts</Label>
                                            <p className="text-xs text-muted-foreground">
                                                System errors and warnings
                                            </p>
                                        </div>
                                        <Switch
                                            checked={notificationSettings.email_on_error}
                                            onCheckedChange={(checked) => setNotificationSettings({
                                                ...notificationSettings,
                                                email_on_error: checked
                                            })}
                                        />
                                    </div>
                                    <div className="flex items-center justify-between p-4 bg-muted/20 rounded-lg">
                                        <div>
                                            <Label>Daily Summary</Label>
                                            <p className="text-xs text-muted-foreground">
                                                Daily P&L report at end of day
                                            </p>
                                        </div>
                                        <Switch
                                            checked={notificationSettings.email_daily_summary}
                                            onCheckedChange={(checked) => setNotificationSettings({
                                                ...notificationSettings,
                                                email_daily_summary: checked
                                            })}
                                        />
                                    </div>
                                </div>
                            </CardContent>
                        )}
                    </Card>

                    {/* Webhook Notifications */}
                    <Card className="glass rounded-2xl">
                        <CardHeader className="bg-gradient-to-r from-green-500/10 to-emerald-500/10">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <Settings className="h-5 w-5 text-green-500" />
                                    <div>
                                        <CardTitle>Webhook Integration</CardTitle>
                                        <CardDescription>Send events to external systems</CardDescription>
                                    </div>
                                </div>
                                <Switch
                                    checked={notificationSettings.webhook_enabled}
                                    onCheckedChange={(checked) => setNotificationSettings({
                                        ...notificationSettings,
                                        webhook_enabled: checked
                                    })}
                                />
                            </div>
                        </CardHeader>
                        {notificationSettings.webhook_enabled && (
                            <CardContent className="pt-6 space-y-4">
                                <div className="space-y-2">
                                    <Label>Webhook URL</Label>
                                    <Input
                                        type="url"
                                        placeholder="https://your-webhook-endpoint.com/hook"
                                        value={notificationSettings.webhook_url || ""}
                                        onChange={(e) => setNotificationSettings({
                                            ...notificationSettings,
                                            webhook_url: e.target.value || null
                                        })}
                                        className="bg-muted/20"
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        Events will be sent as POST requests with JSON payload
                                    </p>
                                </div>
                            </CardContent>
                        )}
                    </Card>

                    {/* Push Notifications */}
                    <Card className="glass rounded-2xl">
                        <CardHeader className="bg-gradient-to-r from-purple-500/10 to-pink-500/10">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <Bell className="h-5 w-5 text-purple-500" />
                                    <div>
                                        <CardTitle>Push Notifications</CardTitle>
                                        <CardDescription>Browser push notifications</CardDescription>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <Badge variant="outline" className="text-yellow-500 border-yellow-500/30">
                                        Coming Soon
                                    </Badge>
                                    <Switch
                                        checked={notificationSettings.push_enabled}
                                        onCheckedChange={(checked) => setNotificationSettings({
                                            ...notificationSettings,
                                            push_enabled: checked
                                        })}
                                        disabled
                                    />
                                </div>
                            </div>
                        </CardHeader>
                    </Card>

                    {/* Save Button */}
                    <div className="flex justify-end">
                        <Button 
                            onClick={saveNotificationSettings} 
                            disabled={saving}
                            className="bg-gradient-to-r from-primary to-secondary"
                        >
                            {saving ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                                <Save className="h-4 w-4 mr-2" />
                            )}
                            Save Notification Settings
                        </Button>
                    </div>
                </TabsContent>
            </Tabs>
        </div>
    );
}
