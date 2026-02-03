"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { 
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import { 
    Building2, 
    CheckCircle2, 
    XCircle, 
    AlertCircle,
    RefreshCw,
    Link,
    Unlink,
    Wallet,
    ArrowUpRight,
    ArrowDownRight,
    Clock,
    MoreHorizontal,
    Plus
} from "lucide-react";
import { 
    apiClient, 
    BrokerStatus, 
    UnifiedPosition, 
    UnifiedOrder,
    PortfolioSummaryMultiBroker 
} from "@/lib/api/client";

export function MultiBrokerManager() {
    const [brokers, setBrokers] = useState<BrokerStatus[]>([]);
    const [positions, setPositions] = useState<UnifiedPosition[]>([]);
    const [orders, setOrders] = useState<UnifiedOrder[]>([]);
    const [portfolio, setPortfolio] = useState<PortfolioSummaryMultiBroker | null>(null);
    const [loading, setLoading] = useState(false);
    const [connectDialogOpen, setConnectDialogOpen] = useState(false);
    const [selectedBroker, setSelectedBroker] = useState<string>("");
    const [credentials, setCredentials] = useState<Record<string, string>>({});

    const brokerConfigs: Record<string, { name: string; fields: string[]; icon: string }> = {
        fyers: { name: "Fyers", fields: ["client_id", "secret_key", "redirect_uri"], icon: "🟢" },
        upstox: { name: "Upstox", fields: ["api_key", "api_secret", "redirect_uri"], icon: "🔵" },
        zerodha: { name: "Zerodha", fields: ["api_key", "api_secret"], icon: "🟠" },
        angelone: { name: "Angel One", fields: ["api_key", "client_id", "password", "totp_secret"], icon: "🔴" },
    };

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [brokersData, positionsData, ordersData, portfolioData] = await Promise.all([
                apiClient.getBrokersStatus(),
                apiClient.getUnifiedPositions(),
                apiClient.getUnifiedOrders(),
                apiClient.getMultiBrokerPortfolioSummary(),
            ]);
            setBrokers(brokersData);
            setPositions(positionsData);
            setOrders(ordersData);
            setPortfolio(portfolioData);
        } catch (error) {
            console.error("Failed to load broker data:", error);
        } finally {
            setLoading(false);
        }
    };

    const connectBroker = async () => {
        if (!selectedBroker) return;
        try {
            await apiClient.connectBroker(selectedBroker, credentials);
            await loadData();
            setConnectDialogOpen(false);
            setCredentials({});
            setSelectedBroker("");
        } catch (error) {
            console.error("Failed to connect broker:", error);
        }
    };

    const disconnectBroker = async (brokerId: string) => {
        try {
            await apiClient.disconnectBroker(brokerId);
            await loadData();
        } catch (error) {
            console.error("Failed to disconnect broker:", error);
        }
    };

    const reconcilePositions = async () => {
        try {
            const result = await apiClient.reconcilePositions();
            if (result.discrepancies.length > 0) {
                alert(`Found ${result.discrepancies.length} discrepancies`);
            } else {
                alert("All positions reconciled successfully");
            }
            await loadData();
        } catch (error) {
            console.error("Failed to reconcile positions:", error);
        }
    };

    const getStatusColor = (broker: BrokerStatus) => {
        if (broker.is_connected && broker.is_authenticated) return "bg-green-500";
        if (broker.is_connected) return "bg-yellow-500";
        return "bg-gray-400";
    };

    const getStatusText = (broker: BrokerStatus) => {
        if (broker.is_connected && broker.is_authenticated) return "Connected";
        if (broker.is_connected) return "Authenticating";
        return "Disconnected";
    };

    const formatCurrency = (value: number) => {
        return new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        }).format(value);
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold flex items-center gap-2">
                        <Building2 className="h-6 w-6 text-purple-500" />
                        Multi-Broker Manager
                    </h2>
                    <p className="text-muted-foreground">
                        Unified view of all connected brokers, positions, and orders
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Dialog open={connectDialogOpen} onOpenChange={setConnectDialogOpen}>
                        <DialogTrigger asChild>
                            <Button>
                                <Plus className="h-4 w-4 mr-2" />
                                Connect Broker
                            </Button>
                        </DialogTrigger>
                        <DialogContent>
                            <DialogHeader>
                                <DialogTitle>Connect Broker</DialogTitle>
                                <DialogDescription>
                                    Enter your broker API credentials to connect
                                </DialogDescription>
                            </DialogHeader>
                            <div className="space-y-4 py-4">
                                <div className="space-y-2">
                                    <Label>Select Broker</Label>
                                    <Select value={selectedBroker} onValueChange={setSelectedBroker}>
                                        <SelectTrigger>
                                            <SelectValue placeholder="Choose a broker" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {Object.entries(brokerConfigs).map(([id, config]) => (
                                                <SelectItem key={id} value={id}>
                                                    {config.icon} {config.name}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                
                                {selectedBroker && brokerConfigs[selectedBroker]?.fields.map((field) => (
                                    <div key={field} className="space-y-2">
                                        <Label className="capitalize">{field.replace(/_/g, ' ')}</Label>
                                        <Input
                                            type={field.includes('secret') || field.includes('password') ? 'password' : 'text'}
                                            value={credentials[field] || ''}
                                            onChange={(e) => setCredentials({ ...credentials, [field]: e.target.value })}
                                            placeholder={`Enter ${field.replace(/_/g, ' ')}`}
                                        />
                                    </div>
                                ))}
                            </div>
                            <DialogFooter>
                                <Button variant="outline" onClick={() => setConnectDialogOpen(false)}>
                                    Cancel
                                </Button>
                                <Button onClick={connectBroker} disabled={!selectedBroker}>
                                    <Link className="h-4 w-4 mr-2" />
                                    Connect
                                </Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>
                    <Button variant="outline" onClick={loadData} disabled={loading}>
                        <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    </Button>
                </div>
            </div>

            {/* Portfolio Summary */}
            {portfolio && (
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm font-medium flex items-center gap-2">
                                <Wallet className="h-4 w-4" />
                                Total Available
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold text-green-500">
                                {formatCurrency(portfolio.total_margin_available)}
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm font-medium">Margin Used</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold">
                                {formatCurrency(portfolio.total_margin_used)}
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm font-medium">Total Positions</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold">
                                {portfolio.total_positions}
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm font-medium">Total P&L</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className={`text-2xl font-bold ${portfolio.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                                {formatCurrency(portfolio.total_pnl)}
                                <span className="text-sm font-normal ml-1">
                                    ({portfolio.total_pnl_percent >= 0 ? '+' : ''}{portfolio.total_pnl_percent.toFixed(2)}%)
                                </span>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}

            <Tabs defaultValue="brokers" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="brokers">Brokers</TabsTrigger>
                    <TabsTrigger value="positions">Positions</TabsTrigger>
                    <TabsTrigger value="orders">Orders</TabsTrigger>
                </TabsList>

                <TabsContent value="brokers">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {brokers.length === 0 ? (
                            <Card className="col-span-full">
                                <CardContent className="text-center py-12 text-muted-foreground">
                                    <Building2 className="h-16 w-16 mx-auto mb-4 opacity-20" />
                                    <p>No brokers connected</p>
                                    <p className="text-sm">Click "Connect Broker" to get started</p>
                                </CardContent>
                            </Card>
                        ) : (
                            brokers.map((broker) => (
                                <Card key={broker.broker_id}>
                                    <CardHeader className="pb-2">
                                        <div className="flex items-center justify-between">
                                            <CardTitle className="flex items-center gap-2">
                                                <span>{brokerConfigs[broker.broker_id]?.icon || '🔹'}</span>
                                                {broker.broker_name}
                                            </CardTitle>
                                            <div className="flex items-center gap-2">
                                                <div className={`h-2 w-2 rounded-full ${getStatusColor(broker)}`} />
                                                <span className="text-sm text-muted-foreground">
                                                    {getStatusText(broker)}
                                                </span>
                                            </div>
                                        </div>
                                    </CardHeader>
                                    <CardContent className="space-y-4">
                                        {broker.is_connected ? (
                                            <>
                                                <div className="grid grid-cols-2 gap-4">
                                                    <div>
                                                        <div className="text-xs text-muted-foreground">Available</div>
                                                        <div className="text-lg font-semibold text-green-500">
                                                            {formatCurrency(broker.margin_available)}
                                                        </div>
                                                    </div>
                                                    <div>
                                                        <div className="text-xs text-muted-foreground">Used</div>
                                                        <div className="text-lg font-semibold">
                                                            {formatCurrency(broker.margin_used)}
                                                        </div>
                                                    </div>
                                                </div>

                                                <div className="flex flex-wrap gap-1">
                                                    {broker.capabilities.map((cap) => (
                                                        <Badge key={cap} variant="secondary" className="text-xs">
                                                            {cap}
                                                        </Badge>
                                                    ))}
                                                </div>

                                                {broker.last_heartbeat && (
                                                    <div className="text-xs text-muted-foreground flex items-center gap-1">
                                                        <Clock className="h-3 w-3" />
                                                        Last sync: {new Date(broker.last_heartbeat).toLocaleTimeString()}
                                                    </div>
                                                )}

                                                <Button 
                                                    variant="outline" 
                                                    size="sm" 
                                                    className="w-full"
                                                    onClick={() => disconnectBroker(broker.broker_id)}
                                                >
                                                    <Unlink className="h-4 w-4 mr-2" />
                                                    Disconnect
                                                </Button>
                                            </>
                                        ) : (
                                            <div className="text-center py-4">
                                                {broker.error_message ? (
                                                    <div className="text-red-500 text-sm mb-2">
                                                        <AlertCircle className="h-4 w-4 inline mr-1" />
                                                        {broker.error_message}
                                                    </div>
                                                ) : (
                                                    <div className="text-muted-foreground text-sm">
                                                        Not connected
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>
                            ))
                        )}
                    </div>
                </TabsContent>

                <TabsContent value="positions">
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle>Unified Positions</CardTitle>
                                    <CardDescription>All positions across connected brokers</CardDescription>
                                </div>
                                <Button variant="outline" size="sm" onClick={reconcilePositions}>
                                    <RefreshCw className="h-4 w-4 mr-2" />
                                    Reconcile
                                </Button>
                            </div>
                        </CardHeader>
                        <CardContent>
                            {positions.length === 0 ? (
                                <div className="text-center py-12 text-muted-foreground">
                                    <Wallet className="h-16 w-16 mx-auto mb-4 opacity-20" />
                                    <p>No open positions</p>
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    <div className="grid grid-cols-8 gap-4 px-4 py-2 text-xs text-muted-foreground font-medium border-b">
                                        <div>Symbol</div>
                                        <div>Broker</div>
                                        <div className="text-right">Qty</div>
                                        <div className="text-right">Avg Price</div>
                                        <div className="text-right">LTP</div>
                                        <div className="text-right">P&L</div>
                                        <div className="text-right">P&L %</div>
                                        <div>Type</div>
                                    </div>
                                    {positions.map((pos) => (
                                        <div 
                                            key={pos.position_id}
                                            className="grid grid-cols-8 gap-4 px-4 py-3 hover:bg-muted/50 rounded-lg items-center"
                                        >
                                            <div className="font-medium">{pos.symbol}</div>
                                            <div>
                                                <Badge variant="outline" className="text-xs">
                                                    {pos.broker_name}
                                                </Badge>
                                            </div>
                                            <div className={`text-right ${pos.quantity > 0 ? 'text-green-500' : 'text-red-500'}`}>
                                                {pos.quantity > 0 ? '+' : ''}{pos.quantity}
                                            </div>
                                            <div className="text-right">{pos.average_price.toFixed(2)}</div>
                                            <div className="text-right">{pos.ltp.toFixed(2)}</div>
                                            <div className={`text-right font-medium ${pos.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                                                {formatCurrency(pos.pnl)}
                                            </div>
                                            <div className={`text-right ${pos.pnl_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                                                {pos.pnl_percent >= 0 ? '+' : ''}{pos.pnl_percent.toFixed(2)}%
                                            </div>
                                            <div>
                                                <Badge variant={pos.is_intraday ? "default" : "secondary"} className="text-xs">
                                                    {pos.is_intraday ? 'Intraday' : 'Delivery'}
                                                </Badge>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="orders">
                    <Card>
                        <CardHeader>
                            <CardTitle>Recent Orders</CardTitle>
                            <CardDescription>Order history across all brokers</CardDescription>
                        </CardHeader>
                        <CardContent>
                            {orders.length === 0 ? (
                                <div className="text-center py-12 text-muted-foreground">
                                    <Clock className="h-16 w-16 mx-auto mb-4 opacity-20" />
                                    <p>No recent orders</p>
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    <div className="grid grid-cols-9 gap-4 px-4 py-2 text-xs text-muted-foreground font-medium border-b">
                                        <div>Symbol</div>
                                        <div>Broker</div>
                                        <div>Side</div>
                                        <div className="text-right">Qty</div>
                                        <div className="text-right">Price</div>
                                        <div>Type</div>
                                        <div>Status</div>
                                        <div className="text-right">Filled</div>
                                        <div>Time</div>
                                    </div>
                                    {orders.map((order) => (
                                        <div 
                                            key={order.order_id}
                                            className="grid grid-cols-9 gap-4 px-4 py-3 hover:bg-muted/50 rounded-lg items-center text-sm"
                                        >
                                            <div className="font-medium">{order.symbol}</div>
                                            <div>
                                                <Badge variant="outline" className="text-xs">
                                                    {order.broker_name}
                                                </Badge>
                                            </div>
                                            <div>
                                                <Badge 
                                                    variant={order.side === 'BUY' ? 'default' : 'destructive'}
                                                    className="text-xs"
                                                >
                                                    {order.side === 'BUY' ? (
                                                        <ArrowUpRight className="h-3 w-3 mr-1" />
                                                    ) : (
                                                        <ArrowDownRight className="h-3 w-3 mr-1" />
                                                    )}
                                                    {order.side}
                                                </Badge>
                                            </div>
                                            <div className="text-right">{order.quantity}</div>
                                            <div className="text-right">{order.price.toFixed(2)}</div>
                                            <div className="text-xs text-muted-foreground">{order.order_type}</div>
                                            <div>
                                                <Badge 
                                                    variant={
                                                        order.status === 'COMPLETE' ? 'default' :
                                                        order.status === 'REJECTED' ? 'destructive' :
                                                        'secondary'
                                                    }
                                                    className="text-xs"
                                                >
                                                    {order.status === 'COMPLETE' && <CheckCircle2 className="h-3 w-3 mr-1" />}
                                                    {order.status === 'REJECTED' && <XCircle className="h-3 w-3 mr-1" />}
                                                    {order.status}
                                                </Badge>
                                            </div>
                                            <div className="text-right">
                                                {order.filled_quantity}/{order.quantity}
                                            </div>
                                            <div className="text-xs text-muted-foreground">
                                                {new Date(order.placed_at).toLocaleTimeString()}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}
