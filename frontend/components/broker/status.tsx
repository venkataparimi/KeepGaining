"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CheckCircle, XCircle, RefreshCw, Activity, DollarSign, TrendingUp, Settings } from "lucide-react";
import { apiClient } from "@/lib/api/client";
import { UpstoxAuth } from "./upstox-auth";

export function BrokerStatus() {
    const [status, setStatus] = useState<any>(null);
    const [upstoxStatus, setUpstoxStatus] = useState<any>(null);
    const [funds, setFunds] = useState<any>(null);
    const [loading, setLoading] = useState(true);

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

    return (
        <div className="flex-1 space-y-6 p-8 pt-6 max-w-[1600px] mx-auto">
            <div className="relative overflow-hidden rounded-2xl glass p-8">
                <div className="absolute inset-0 gradient-bg opacity-30"></div>
                <div className="relative z-10 flex items-center justify-between">
                    <div>
                        <h1 className="text-4xl font-bold gradient-text mb-2">Broker Management</h1>
                        <p className="text-muted-foreground">Manage broker connections and view account details</p>
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

            {/* Broker Tabs */}
            <Tabs defaultValue="overview" className="space-y-6">
                <TabsList className="grid w-full grid-cols-3 glass">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="fyers">Fyers</TabsTrigger>
                    <TabsTrigger value="upstox">Upstox</TabsTrigger>
                </TabsList>

                {/* Overview Tab */}
                <TabsContent value="overview" className="space-y-6">
                    {/* Connection Status Cards */}
                    <div className="grid gap-6 md:grid-cols-3">
                        <div className="glass rounded-2xl overflow-hidden hover-lift">
                            <CardHeader className="bg-gradient-to-br from-primary/10 to-secondary/10">
                                <CardTitle className="text-lg font-bold flex items-center justify-between">
                                    Fyers Status
                                    {status?.connected ? (
                                        <CheckCircle className="h-6 w-6 text-green-400" />
                                    ) : (
                                        <XCircle className="h-6 w-6 text-red-400" />
                                    )}
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-6">
                                <div className="space-y-3">
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
                                </div>
                            </CardContent>
                        </div>

                        <div className="glass rounded-2xl overflow-hidden hover-lift">
                            <CardHeader className="bg-gradient-to-br from-orange-500/10 to-amber-500/10">
                                <CardTitle className="text-lg font-bold flex items-center justify-between">
                                    Upstox Status
                                    {upstoxStatus?.authenticated ? (
                                        <CheckCircle className="h-6 w-6 text-green-400" />
                                    ) : (
                                        <XCircle className="h-6 w-6 text-red-400" />
                                    )}
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-6">
                                <div className="space-y-3">
                                    <div>
                                        <p className="text-sm text-muted-foreground">Broker</p>
                                        <p className="text-xl font-bold">Upstox</p>
                                    </div>
                                    <div>
                                        <p className="text-sm text-muted-foreground">Status</p>
                                        <p className={`text-lg font-semibold ${upstoxStatus?.authenticated ? 'text-green-400' : 'text-red-400'}`}>
                                            {upstoxStatus?.authenticated ? 'CONNECTED' : 'DISCONNECTED'}
                                        </p>
                                    </div>
                                    {upstoxStatus?.user_id && (
                                        <div>
                                            <p className="text-sm text-muted-foreground">User ID</p>
                                            <p className="text-sm">{upstoxStatus.user_id}</p>
                                        </div>
                                    )}
                                </div>
                            </CardContent>
                        </div>

                        <div className="glass rounded-2xl overflow-hidden hover-lift">
                            <CardHeader className="bg-gradient-to-br from-green-500/10 to-emerald-500/10">
                                <CardTitle className="text-lg font-bold flex items-center">
                                    <DollarSign className="h-5 w-5 mr-2 text-green-400" />
                                    Account Balance
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-6">
                                <div className="space-y-3">
                                    <div>
                                        <p className="text-sm text-muted-foreground">Equity</p>
                                        <p className="text-2xl font-bold text-green-400">
                                            ₹{funds?.equityAmount?.toLocaleString() || '--'}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-sm text-muted-foreground">Commodity</p>
                                        <p className="text-lg font-semibold">
                                            ₹{funds?.commodityAmount?.toLocaleString() || '0'}
                                        </p>
                                    </div>
                                </div>
                            </CardContent>
                        </div>
                    </div>
                </TabsContent>

                {/* Fyers Tab */}
                <TabsContent value="fyers" className="space-y-6">
                    <div className="grid gap-6 md:grid-cols-2">
                        <div className="glass rounded-2xl overflow-hidden">
                            <CardHeader className="bg-gradient-to-br from-primary/10 to-secondary/10">
                                <CardTitle className="text-lg font-bold flex items-center justify-between">
                                    Connection Status
                                    {status?.connected ? (
                                        <CheckCircle className="h-6 w-6 text-green-400" />
                                    ) : (
                                        <XCircle className="h-6 w-6 text-red-400" />
                                    )}
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-6">
                                <div className="space-y-3">
                                    <div>
                                        <p className="text-sm text-muted-foreground">Broker</p>
                                        <p className="text-xl font-bold">{status?.broker_name || 'Not Connected'}</p>
                                    </div>
                                    <div>
                                        <p className="text-sm text-muted-foreground">Status</p>
                                        <p className={`text-lg font-semibold ${status?.connected ? 'text-green-400' : 'text-red-400'}`}>
                                            {status?.connected ? 'CONNECTED' : 'DISCONNECTED'}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-sm text-muted-foreground">Message</p>
                                        <p className="text-sm">{status?.message || 'No connection'}</p>
                                    </div>
                                </div>
                            </CardContent>
                        </div>

                        <div className="glass rounded-2xl overflow-hidden">
                            <CardHeader className="bg-gradient-to-br from-green-500/10 to-emerald-500/10">
                                <CardTitle className="text-lg font-bold flex items-center">
                                    <DollarSign className="h-5 w-5 mr-2 text-green-400" />
                                    Account Balance
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-6">
                                <div className="space-y-3">
                                    <div>
                                        <p className="text-sm text-muted-foreground">Equity</p>
                                        <p className="text-2xl font-bold text-green-400">
                                            ₹{funds?.equityAmount?.toLocaleString() || '--'}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-sm text-muted-foreground">Commodity</p>
                                        <p className="text-lg font-semibold">
                                            ₹{funds?.commodityAmount?.toLocaleString() || '0'}
                                        </p>
                                    </div>
                                </div>
                            </CardContent>
                        </div>
                    </div>

                    {/* Connection Instructions */}
                    {!status?.connected && (
                        <div className="glass rounded-2xl overflow-hidden p-6">
                            <h3 className="text-xl font-bold mb-4 text-yellow-400">⚠️ Fyers Not Connected</h3>
                            <div className="space-y-3 text-muted-foreground">
                                <p>To connect to Fyers broker:</p>
                                <ol className="list-decimal list-inside space-y-2 ml-4">
                                    <li>Ensure your <code className="bg-muted px-2 py-1 rounded">.env</code> file has valid Fyers credentials</li>
                                    <li>Check that the backend server is running</li>
                                    <li>Verify your Fyers API credentials are active</li>
                                    <li>Check backend logs for authentication errors</li>
                                </ol>
                            </div>
                        </div>
                    )}
                </TabsContent>

                {/* Upstox Tab */}
                <TabsContent value="upstox" className="space-y-6">
                    <UpstoxAuth onAuthSuccess={fetchData} />
                </TabsContent>
            </Tabs>
        </div>
    );
}
