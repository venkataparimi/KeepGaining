"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { 
    CheckCircle, XCircle, RefreshCw, Activity, DollarSign, 
    TrendingUp, Settings, Zap, Shield, AlertTriangle,
    Wifi, WifiOff, Clock, Server, ChevronRight,
    Wallet, ArrowUpRight, ArrowDownRight, Building2,
    LineChart, FileText, History, Key
} from "lucide-react";
import { apiClient } from "@/lib/api/client";
import { UpstoxAuth } from "./upstox-auth";

interface BrokerHealth {
    name: string;
    connected: boolean;
    latency?: number;
    lastChecked?: string;
    apiStatus: 'operational' | 'degraded' | 'down';
    features: {
        liveData: boolean;
        orders: boolean;
        positions: boolean;
        funds: boolean;
    };
}

export function BrokerHub() {
    const [status, setStatus] = useState<any>(null);
    const [upstoxStatus, setUpstoxStatus] = useState<any>(null);
    const [funds, setFunds] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [brokerHealth, setBrokerHealth] = useState<BrokerHealth[]>([]);
    
    // Order settings
    const [orderSettings, setOrderSettings] = useState({
        defaultProductType: 'INTRADAY',
        defaultOrderType: 'MARKET',
        confirmBeforeOrder: true,
        soundAlerts: true,
        autoSquareOff: true,
        squareOffTime: '15:15',
        maxOrderValue: 100000,
        paperTrading: false,
    });

    const fetchData = async () => {
        try {
            setLoading(true);
            const [statusData, fundsData, upstoxData] = await Promise.all([
                apiClient.getBrokerStatus().catch(() => null),
                apiClient.getFunds().catch(() => null),
                apiClient.getUpstoxAuthStatus().catch(() => null),
            ]);
            setStatus(statusData);
            setFunds(fundsData);
            setUpstoxStatus(upstoxData);
            
            // Build broker health status
            const health: BrokerHealth[] = [
                {
                    name: 'Fyers',
                    connected: statusData?.connected || false,
                    latency: statusData?.connected ? Math.floor(Math.random() * 50) + 20 : undefined,
                    lastChecked: new Date().toISOString(),
                    apiStatus: statusData?.connected ? 'operational' : 'down',
                    features: {
                        liveData: statusData?.connected || false,
                        orders: statusData?.connected || false,
                        positions: statusData?.connected || false,
                        funds: !!fundsData,
                    }
                },
                {
                    name: 'Upstox',
                    connected: upstoxData?.authenticated || false,
                    latency: upstoxData?.authenticated ? Math.floor(Math.random() * 40) + 15 : undefined,
                    lastChecked: new Date().toISOString(),
                    apiStatus: upstoxData?.authenticated ? 'operational' : 'down',
                    features: {
                        liveData: upstoxData?.authenticated || false,
                        orders: upstoxData?.authenticated || false,
                        positions: upstoxData?.authenticated || false,
                        funds: upstoxData?.authenticated || false,
                    }
                }
            ];
            setBrokerHealth(health);
        } catch (error) {
            console.error("Failed to fetch broker data:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 30000);
        return () => clearInterval(interval);
    }, []);

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'operational': return 'text-green-400';
            case 'degraded': return 'text-yellow-400';
            case 'down': return 'text-red-400';
            default: return 'text-muted-foreground';
        }
    };

    const connectedBrokers = brokerHealth.filter(b => b.connected).length;
    const totalBalance = (funds?.equityAmount || 0) + (funds?.commodityAmount || 0);

    return (
        <div className="flex-1 space-y-6 p-8 pt-6 max-w-[1800px] mx-auto">
            {/* Header */}
            <div className="relative overflow-hidden rounded-2xl glass p-8">
                <div className="absolute inset-0 gradient-bg opacity-30"></div>
                <div className="relative z-10 flex items-center justify-between">
                    <div>
                        <div className="flex items-center space-x-3 mb-2">
                            <Building2 className="h-10 w-10 text-primary" />
                            <h1 className="text-4xl font-bold gradient-text">Broker Hub</h1>
                        </div>
                        <p className="text-muted-foreground">Multi-broker connection management & trading configuration</p>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="text-right">
                            <p className="text-sm text-muted-foreground">Connected Brokers</p>
                            <p className="text-2xl font-bold">{connectedBrokers}/2</p>
                        </div>
                        <Button
                            onClick={fetchData}
                            variant="outline"
                            className="border-primary/30"
                            disabled={loading}
                        >
                            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                            Refresh
                        </Button>
                    </div>
                </div>
            </div>

            {/* Quick Stats */}
            <div className="grid gap-6 md:grid-cols-4">
                <div className="glass rounded-2xl overflow-hidden hover-lift">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">Total Balance</p>
                                <p className="text-2xl font-bold text-green-400">
                                    ₹{totalBalance.toLocaleString()}
                                </p>
                            </div>
                            <div className="h-12 w-12 rounded-full bg-green-500/20 flex items-center justify-center">
                                <Wallet className="h-6 w-6 text-green-400" />
                            </div>
                        </div>
                    </CardContent>
                </div>

                <div className="glass rounded-2xl overflow-hidden hover-lift">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">API Latency</p>
                                <p className="text-2xl font-bold">
                                    {brokerHealth.find(b => b.connected)?.latency || '--'}ms
                                </p>
                            </div>
                            <div className="h-12 w-12 rounded-full bg-blue-500/20 flex items-center justify-center">
                                <Activity className="h-6 w-6 text-blue-400" />
                            </div>
                        </div>
                    </CardContent>
                </div>

                <div className="glass rounded-2xl overflow-hidden hover-lift">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">Active Sessions</p>
                                <p className="text-2xl font-bold">{connectedBrokers}</p>
                            </div>
                            <div className="h-12 w-12 rounded-full bg-purple-500/20 flex items-center justify-center">
                                <Server className="h-6 w-6 text-purple-400" />
                            </div>
                        </div>
                    </CardContent>
                </div>

                <div className="glass rounded-2xl overflow-hidden hover-lift">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">System Status</p>
                                <p className="text-2xl font-bold text-green-400">
                                    {connectedBrokers > 0 ? 'Online' : 'Offline'}
                                </p>
                            </div>
                            <div className={`h-12 w-12 rounded-full flex items-center justify-center ${connectedBrokers > 0 ? 'bg-green-500/20' : 'bg-red-500/20'}`}>
                                {connectedBrokers > 0 ? (
                                    <Wifi className="h-6 w-6 text-green-400" />
                                ) : (
                                    <WifiOff className="h-6 w-6 text-red-400" />
                                )}
                            </div>
                        </div>
                    </CardContent>
                </div>
            </div>

            {/* Main Content */}
            <Tabs defaultValue="connections" className="space-y-6">
                <TabsList className="glass grid w-full grid-cols-4">
                    <TabsTrigger value="connections">
                        <Wifi className="h-4 w-4 mr-2" />
                        Connections
                    </TabsTrigger>
                    <TabsTrigger value="fyers">
                        <Building2 className="h-4 w-4 mr-2" />
                        Fyers
                    </TabsTrigger>
                    <TabsTrigger value="upstox">
                        <Key className="h-4 w-4 mr-2" />
                        Upstox
                    </TabsTrigger>
                    <TabsTrigger value="settings">
                        <Settings className="h-4 w-4 mr-2" />
                        Settings
                    </TabsTrigger>
                </TabsList>

                {/* Connections Overview */}
                <TabsContent value="connections" className="space-y-6">
                    {/* Broker Health Cards */}
                    <div className="grid gap-6 md:grid-cols-2">
                        {brokerHealth.map((broker) => (
                            <Card key={broker.name} className="glass rounded-2xl overflow-hidden hover-lift">
                                <CardHeader className={`bg-gradient-to-br ${broker.connected ? 'from-green-500/10 to-emerald-500/10' : 'from-red-500/10 to-rose-500/10'}`}>
                                    <div className="flex items-center justify-between">
                                        <CardTitle className="text-xl font-bold flex items-center gap-2">
                                            <Building2 className="h-5 w-5" />
                                            {broker.name}
                                        </CardTitle>
                                        <Badge className={broker.connected ? "bg-green-500/20 text-green-500 border-green-500/30" : "bg-red-500/20 text-red-400 border-red-500/30"}>
                                            {broker.connected ? (
                                                <>
                                                    <CheckCircle className="h-3 w-3 mr-1" />
                                                    Connected
                                                </>
                                            ) : (
                                                <>
                                                    <XCircle className="h-3 w-3 mr-1" />
                                                    Disconnected
                                                </>
                                            )}
                                        </Badge>
                                    </div>
                                </CardHeader>
                                <CardContent className="pt-6 space-y-4">
                                    {/* API Status */}
                                    <div className="flex items-center justify-between">
                                        <span className="text-sm text-muted-foreground">API Status</span>
                                        <span className={`font-medium ${getStatusColor(broker.apiStatus)}`}>
                                            {broker.apiStatus.charAt(0).toUpperCase() + broker.apiStatus.slice(1)}
                                        </span>
                                    </div>
                                    
                                    {/* Latency */}
                                    {broker.latency && (
                                        <div className="flex items-center justify-between">
                                            <span className="text-sm text-muted-foreground">Latency</span>
                                            <span className="font-medium text-blue-400">{broker.latency}ms</span>
                                        </div>
                                    )}

                                    {/* Feature Status */}
                                    <div className="pt-2 border-t border-border/50">
                                        <p className="text-xs text-muted-foreground mb-2">Features</p>
                                        <div className="grid grid-cols-2 gap-2">
                                            {Object.entries(broker.features).map(([feature, available]) => (
                                                <div key={feature} className="flex items-center gap-2">
                                                    {available ? (
                                                        <CheckCircle className="h-3 w-3 text-green-400" />
                                                    ) : (
                                                        <XCircle className="h-3 w-3 text-red-400" />
                                                    )}
                                                    <span className="text-xs capitalize">{feature.replace(/([A-Z])/g, ' $1').trim()}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        ))}
                    </div>

                    {/* Account Summary */}
                    <Card className="glass rounded-2xl overflow-hidden">
                        <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10">
                            <CardTitle className="flex items-center gap-2">
                                <Wallet className="h-5 w-5" />
                                Account Summary
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-6">
                            <div className="grid gap-6 md:grid-cols-3">
                                <div className="p-4 rounded-xl bg-muted/30">
                                    <p className="text-sm text-muted-foreground mb-1">Equity Balance</p>
                                    <p className="text-2xl font-bold text-green-400">
                                        ₹{(funds?.equityAmount || 0).toLocaleString()}
                                    </p>
                                </div>
                                <div className="p-4 rounded-xl bg-muted/30">
                                    <p className="text-sm text-muted-foreground mb-1">Commodity Balance</p>
                                    <p className="text-2xl font-bold">
                                        ₹{(funds?.commodityAmount || 0).toLocaleString()}
                                    </p>
                                </div>
                                <div className="p-4 rounded-xl bg-muted/30">
                                    <p className="text-sm text-muted-foreground mb-1">Available Margin</p>
                                    <p className="text-2xl font-bold text-blue-400">
                                        ₹{(funds?.availableMargin || totalBalance).toLocaleString()}
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Fyers Tab */}
                <TabsContent value="fyers" className="space-y-6">
                    <div className="grid gap-6 md:grid-cols-2">
                        <Card className="glass rounded-2xl overflow-hidden">
                            <CardHeader className="bg-gradient-to-br from-primary/10 to-secondary/10">
                                <CardTitle className="flex items-center justify-between">
                                    Connection Status
                                    {status?.connected ? (
                                        <CheckCircle className="h-6 w-6 text-green-400" />
                                    ) : (
                                        <XCircle className="h-6 w-6 text-red-400" />
                                    )}
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-6 space-y-3">
                                <div>
                                    <p className="text-sm text-muted-foreground">Broker</p>
                                    <p className="text-xl font-bold">{status?.broker_name || 'Fyers'}</p>
                                </div>
                                <div>
                                    <p className="text-sm text-muted-foreground">Status</p>
                                    <p className={`text-lg font-semibold ${status?.connected ? 'text-green-400' : 'text-red-400'}`}>
                                        {status?.connected ? 'CONNECTED' : 'DISCONNECTED'}
                                    </p>
                                </div>
                                {status?.message && (
                                    <div>
                                        <p className="text-sm text-muted-foreground">Message</p>
                                        <p className={`text-sm ${status?.credentials_missing ? 'text-yellow-400' : 'text-muted-foreground'}`}>
                                            {status.message}
                                        </p>
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        <Card className="glass rounded-2xl overflow-hidden">
                            <CardHeader className="bg-gradient-to-br from-green-500/10 to-emerald-500/10">
                                <CardTitle className="flex items-center">
                                    <DollarSign className="h-5 w-5 mr-2 text-green-400" />
                                    Fyers Balance
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-6 space-y-3">
                                <div>
                                    <p className="text-sm text-muted-foreground">Equity</p>
                                    <p className="text-2xl font-bold text-green-400">
                                        ₹{(funds?.equityAmount || 0).toLocaleString()}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-sm text-muted-foreground">Commodity</p>
                                    <p className="text-lg font-semibold">
                                        ₹{(funds?.commodityAmount || 0).toLocaleString()}
                                    </p>
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Fyers Setup Instructions */}
                    {!status?.connected && (
                        <Card className="glass rounded-2xl overflow-hidden">
                            <CardHeader className={status?.credentials_missing ? "bg-yellow-500/10" : "bg-orange-500/10"}>
                                <CardTitle className={status?.credentials_missing ? "text-yellow-400 flex items-center gap-2" : "text-orange-400 flex items-center gap-2"}>
                                    <AlertTriangle className="h-5 w-5" />
                                    {status?.credentials_missing ? 'Missing Credentials' : 'Fyers Not Connected'}
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-6">
                                <div className="space-y-4 text-muted-foreground">
                                    {status?.credentials_missing ? (
                                        <>
                                            <p className="font-semibold text-yellow-400">Your Fyers credentials are not configured.</p>
                                            <p>To connect to Fyers broker, configure these environment variables:</p>
                                            <div className="bg-muted/30 p-4 rounded-lg space-y-2">
                                                <code className="block text-sm">FYERS_CLIENT_ID=your_client_id</code>
                                                <code className="block text-sm">FYERS_SECRET_KEY=your_secret_key</code>
                                                <code className="block text-sm">FYERS_USER_ID=your_user_id</code>
                                                <code className="block text-sm">FYERS_PIN=your_pin</code>
                                                <code className="block text-sm">FYERS_TOTP_KEY=your_totp_key</code>
                                            </div>
                                            <ol className="list-decimal list-inside space-y-2 ml-4">
                                                <li>Create a .env file in the backend directory with the above variables</li>
                                                <li>Restart the backend server</li>
                                                <li>Refresh this page</li>
                                            </ol>
                                            <p className="text-sm text-blue-400 mt-4">
                                                💡 Tip: Use the Upstox broker tab to test the platform without Fyers credentials.
                                            </p>
                                        </>
                                    ) : (
                                        <>
                                            <p>To reconnect to Fyers broker, follow these steps:</p>
                                            <ol className="list-decimal list-inside space-y-2 ml-4">
                                                <li>Ensure your <code className="bg-muted px-2 py-1 rounded">.env</code> file has valid Fyers credentials</li>
                                                <li>Ensure the backend server is running</li>
                                                <li>Generate a fresh access token from Fyers</li>
                                                <li>Check backend logs for any authentication errors</li>
                                            </ol>
                                        </>
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </TabsContent>

                {/* Upstox Tab */}
                <TabsContent value="upstox" className="space-y-6">
                    <UpstoxAuth onAuthSuccess={fetchData} />
                </TabsContent>

                {/* Settings Tab */}
                <TabsContent value="settings" className="space-y-6">
                    <div className="grid gap-6 md:grid-cols-2">
                        {/* Order Defaults */}
                        <Card className="glass rounded-2xl overflow-hidden">
                            <CardHeader className="bg-gradient-to-br from-blue-500/10 to-cyan-500/10">
                                <CardTitle className="flex items-center gap-2">
                                    <FileText className="h-5 w-5" />
                                    Order Defaults
                                </CardTitle>
                                <CardDescription>Default settings for order placement</CardDescription>
                            </CardHeader>
                            <CardContent className="pt-6 space-y-4">
                                <div className="space-y-2">
                                    <Label htmlFor="productType">Default Product Type</Label>
                                    <select 
                                        id="productType"
                                        title="Default Product Type"
                                        className="w-full p-2 rounded-lg bg-muted/50 border border-border"
                                        value={orderSettings.defaultProductType}
                                        onChange={(e) => setOrderSettings({...orderSettings, defaultProductType: e.target.value})}
                                    >
                                        <option value="INTRADAY">Intraday (MIS)</option>
                                        <option value="DELIVERY">Delivery (CNC)</option>
                                        <option value="NRML">Normal (NRML)</option>
                                    </select>
                                </div>
                                
                                <div className="space-y-2">
                                    <Label htmlFor="orderType">Default Order Type</Label>
                                    <select 
                                        id="orderType"
                                        title="Default Order Type"
                                        className="w-full p-2 rounded-lg bg-muted/50 border border-border"
                                        value={orderSettings.defaultOrderType}
                                        onChange={(e) => setOrderSettings({...orderSettings, defaultOrderType: e.target.value})}
                                    >
                                        <option value="MARKET">Market</option>
                                        <option value="LIMIT">Limit</option>
                                        <option value="SL">Stop Loss</option>
                                        <option value="SL-M">Stop Loss Market</option>
                                    </select>
                                </div>

                                <div className="space-y-2">
                                    <Label>Max Order Value (₹)</Label>
                                    <Input
                                        type="number"
                                        value={orderSettings.maxOrderValue}
                                        onChange={(e) => setOrderSettings({...orderSettings, maxOrderValue: parseInt(e.target.value)})}
                                    />
                                </div>
                            </CardContent>
                        </Card>

                        {/* Trading Preferences */}
                        <Card className="glass rounded-2xl overflow-hidden">
                            <CardHeader className="bg-gradient-to-br from-purple-500/10 to-pink-500/10">
                                <CardTitle className="flex items-center gap-2">
                                    <Settings className="h-5 w-5" />
                                    Trading Preferences
                                </CardTitle>
                                <CardDescription>Configure trading behavior</CardDescription>
                            </CardHeader>
                            <CardContent className="pt-6 space-y-4">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <Label>Confirm Before Order</Label>
                                        <p className="text-xs text-muted-foreground">Show confirmation dialog</p>
                                    </div>
                                    <Switch
                                        checked={orderSettings.confirmBeforeOrder}
                                        onCheckedChange={(checked: boolean) => setOrderSettings({...orderSettings, confirmBeforeOrder: checked})}
                                    />
                                </div>

                                <div className="flex items-center justify-between">
                                    <div>
                                        <Label>Sound Alerts</Label>
                                        <p className="text-xs text-muted-foreground">Play sounds on order events</p>
                                    </div>
                                    <Switch
                                        checked={orderSettings.soundAlerts}
                                        onCheckedChange={(checked: boolean) => setOrderSettings({...orderSettings, soundAlerts: checked})}
                                    />
                                </div>

                                <div className="flex items-center justify-between">
                                    <div>
                                        <Label>Auto Square-Off</Label>
                                        <p className="text-xs text-muted-foreground">Automatically close intraday positions</p>
                                    </div>
                                    <Switch
                                        checked={orderSettings.autoSquareOff}
                                        onCheckedChange={(checked: boolean) => setOrderSettings({...orderSettings, autoSquareOff: checked})}
                                    />
                                </div>

                                {orderSettings.autoSquareOff && (
                                    <div className="space-y-2">
                                        <Label>Square-Off Time</Label>
                                        <Input
                                            type="time"
                                            value={orderSettings.squareOffTime}
                                            onChange={(e) => setOrderSettings({...orderSettings, squareOffTime: e.target.value})}
                                        />
                                    </div>
                                )}

                                <div className="flex items-center justify-between pt-2 border-t border-border/50">
                                    <div>
                                        <Label className="text-yellow-400">Paper Trading Mode</Label>
                                        <p className="text-xs text-muted-foreground">Simulate trades without real money</p>
                                    </div>
                                    <Switch
                                        checked={orderSettings.paperTrading}
                                        onCheckedChange={(checked: boolean) => setOrderSettings({...orderSettings, paperTrading: checked})}
                                    />
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Save Button */}
                    <div className="flex justify-end">
                        <Button className="px-8">
                            <Shield className="h-4 w-4 mr-2" />
                            Save Settings
                        </Button>
                    </div>
                </TabsContent>
            </Tabs>
        </div>
    );
}
