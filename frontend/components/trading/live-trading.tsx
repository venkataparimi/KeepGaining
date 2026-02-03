"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Play,
  Square,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  XCircle,
  TrendingUp,
  TrendingDown,
  Activity,
  DollarSign,
  Clock,
  Shield,
  Zap,
  Eye,
  EyeOff,
} from "lucide-react";
import { apiClient } from "@/lib/api/client";

// Types
interface LiveSession {
  session_id: string;
  broker: string;
  started_at: string;
  capital: number;
  sandbox_mode: boolean;
  is_active: boolean;
  orders_placed: number;
  orders_filled: number;
  orders_cancelled: number;
  realized_pnl: number;
  unrealized_pnl: number;
}

interface Position {
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  stop_loss?: number;
  target?: number;
  trailing_sl?: boolean;
}

interface Order {
  order_id: string;
  broker_order_id?: string;
  symbol: string;
  side: string;
  order_type: string;
  quantity: number;
  price?: number;
  trigger_price?: number;
  status: string;
  filled_quantity: number;
  average_price?: number;
  placed_at: string;
  updated_at: string;
}

interface BrokerStatus {
  name: string;
  connected: boolean;
  authenticated: boolean;
  last_heartbeat?: string;
}

export function LiveTradingPanel() {
  // State
  const [session, setSession] = useState<LiveSession | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [brokers, setBrokers] = useState<BrokerStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  
  // Form state for starting session
  const [selectedBroker, setSelectedBroker] = useState<string>("fyers");
  const [sandboxMode, setSandboxMode] = useState(true);
  const [capital, setCapital] = useState("100000");
  const [requireConfirmation, setRequireConfirmation] = useState(true);
  
  // Order form state
  const [showOrderForm, setShowOrderForm] = useState(false);
  const [orderSymbol, setOrderSymbol] = useState("");
  const [orderSide, setOrderSide] = useState<"BUY" | "SELL">("BUY");
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT" | "SL" | "SL-M">("MARKET");
  const [orderQuantity, setOrderQuantity] = useState("1");
  const [orderPrice, setOrderPrice] = useState("");
  const [orderStopLoss, setOrderStopLoss] = useState("");
  const [orderTarget, setOrderTarget] = useState("");
  
  // WebSocket for real-time updates
  const wsRef = useRef<WebSocket | null>(null);

  // Fetch initial data
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      
      // Fetch session status
      const statusRes = await apiClient.get("/live/status");
      if (statusRes.data.session) {
        setSession(statusRes.data.session);
      }
      
      // Fetch positions
      const positionsRes = await apiClient.get("/live/positions");
      setPositions(positionsRes.data.positions || []);
      
      // Fetch recent orders
      const ordersRes = await apiClient.get("/live/orders");
      setOrders(ordersRes.data.orders || []);
      
      // Fetch broker status
      const brokerRes = await apiClient.get("/broker/status");
      setBrokers(brokerRes.data.brokers || []);
      
    } catch (error) {
      console.error("Failed to fetch live trading data:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Refresh every 5 seconds
    return () => clearInterval(interval);
  }, [fetchData]);

  // WebSocket connection for real-time order updates
  useEffect(() => {
    if (!session?.is_active) return;
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/live/stream/connect`;
    
    try {
      wsRef.current = new WebSocket(wsUrl);
      
      wsRef.current.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === "order_update") {
          setOrders(prev => {
            const idx = prev.findIndex(o => o.order_id === data.order.order_id);
            if (idx >= 0) {
              const updated = [...prev];
              updated[idx] = data.order;
              return updated;
            }
            return [data.order, ...prev];
          });
        } else if (data.type === "position_update") {
          setPositions(data.positions);
        } else if (data.type === "pnl_update") {
          setSession(prev => prev ? {
            ...prev,
            realized_pnl: data.realized_pnl,
            unrealized_pnl: data.unrealized_pnl
          } : null);
        }
      };
      
      wsRef.current.onerror = (error) => {
        console.error("WebSocket error:", error);
      };
      
    } catch (error) {
      console.error("Failed to connect WebSocket:", error);
    }
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [session?.is_active]);

  // Start live trading session
  const startSession = async () => {
    try {
      setStarting(true);
      
      const response = await apiClient.post("/live/start", {
        broker: selectedBroker,
        sandbox_mode: sandboxMode,
        capital: parseFloat(capital),
        require_confirmation: requireConfirmation,
      });
      
      if (response.data.session) {
        setSession(response.data.session);
      }
      
    } catch (error: any) {
      console.error("Failed to start session:", error);
      alert(error.response?.data?.detail || "Failed to start live trading session");
    } finally {
      setStarting(false);
    }
  };

  // Stop live trading session
  const stopSession = async () => {
    if (!confirm("Are you sure you want to stop live trading? All open positions will remain open.")) {
      return;
    }
    
    try {
      setStopping(true);
      
      await apiClient.post("/live/stop", {
        square_off_positions: false,
      });
      
      setSession(null);
      
    } catch (error: any) {
      console.error("Failed to stop session:", error);
      alert(error.response?.data?.detail || "Failed to stop live trading session");
    } finally {
      setStopping(false);
    }
  };

  // Place order
  const placeOrder = async () => {
    try {
      const orderData = {
        symbol: orderSymbol,
        side: orderSide,
        order_type: orderType,
        quantity: parseInt(orderQuantity),
        price: orderPrice ? parseFloat(orderPrice) : undefined,
        stop_loss: orderStopLoss ? parseFloat(orderStopLoss) : undefined,
        target: orderTarget ? parseFloat(orderTarget) : undefined,
      };
      
      const response = await apiClient.post("/live/orders/place", orderData);
      
      if (response.data.order) {
        setOrders(prev => [response.data.order, ...prev]);
        setShowOrderForm(false);
        // Reset form
        setOrderSymbol("");
        setOrderQuantity("1");
        setOrderPrice("");
        setOrderStopLoss("");
        setOrderTarget("");
      }
      
    } catch (error: any) {
      console.error("Failed to place order:", error);
      alert(error.response?.data?.detail || "Failed to place order");
    }
  };

  // Cancel order
  const cancelOrder = async (orderId: string) => {
    try {
      await apiClient.post(`/live/orders/${orderId}/cancel`);
      setOrders(prev => prev.map(o => 
        o.order_id === orderId ? { ...o, status: "CANCELLED" } : o
      ));
    } catch (error: any) {
      console.error("Failed to cancel order:", error);
      alert(error.response?.data?.detail || "Failed to cancel order");
    }
  };

  // Reconcile positions
  const reconcilePositions = async () => {
    try {
      const response = await apiClient.post("/live/reconcile");
      if (response.data.positions) {
        setPositions(response.data.positions);
      }
      alert("Positions reconciled with broker");
    } catch (error: any) {
      console.error("Failed to reconcile:", error);
      alert(error.response?.data?.detail || "Failed to reconcile positions");
    }
  };

  // Format currency
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  // Get status badge
  const getStatusBadge = (status: string) => {
    const statusConfig: Record<string, { variant: "default" | "secondary" | "destructive" | "outline"; icon: React.ReactNode }> = {
      "PENDING": { variant: "secondary", icon: <Clock className="h-3 w-3" /> },
      "OPEN": { variant: "outline", icon: <Activity className="h-3 w-3" /> },
      "COMPLETE": { variant: "default", icon: <CheckCircle className="h-3 w-3" /> },
      "FILLED": { variant: "default", icon: <CheckCircle className="h-3 w-3" /> },
      "CANCELLED": { variant: "secondary", icon: <XCircle className="h-3 w-3" /> },
      "REJECTED": { variant: "destructive", icon: <XCircle className="h-3 w-3" /> },
    };
    
    const config = statusConfig[status] || { variant: "outline" as const, icon: null };
    
    return (
      <Badge variant={config.variant} className="flex items-center gap-1">
        {config.icon}
        {status}
      </Badge>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Session Status */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Live Trading</h2>
          <p className="text-muted-foreground">
            Real-time order execution with Fyers & Upstox
          </p>
        </div>
        
        <div className="flex items-center gap-4">
          {session?.is_active ? (
            <>
              <Badge variant="default" className="bg-green-500 text-white px-3 py-1">
                <Activity className="h-4 w-4 mr-1 animate-pulse" />
                LIVE {session.sandbox_mode && "(SANDBOX)"}
              </Badge>
              <Button variant="destructive" onClick={stopSession} disabled={stopping}>
                {stopping ? (
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Square className="h-4 w-4 mr-2" />
                )}
                Stop Trading
              </Button>
            </>
          ) : (
            <Badge variant="secondary" className="px-3 py-1">
              <Square className="h-4 w-4 mr-1" />
              STOPPED
            </Badge>
          )}
        </div>
      </div>

      {/* Session Config / Start Panel */}
      {!session?.is_active && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5" />
              Start Live Trading Session
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              <div className="space-y-2">
                <Label>Broker</Label>
                <Select value={selectedBroker} onValueChange={setSelectedBroker}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select broker" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fyers">Fyers</SelectItem>
                    <SelectItem value="upstox">Upstox</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div className="space-y-2">
                <Label>Capital (₹)</Label>
                <Input
                  type="number"
                  value={capital}
                  onChange={(e) => setCapital(e.target.value)}
                  placeholder="100000"
                />
              </div>
              
              <div className="space-y-2">
                <Label>Mode</Label>
                <div className="flex items-center space-x-2 pt-2">
                  <Switch
                    checked={sandboxMode}
                    onCheckedChange={setSandboxMode}
                  />
                  <Label className="text-sm">
                    {sandboxMode ? (
                      <span className="text-amber-600 flex items-center gap-1">
                        <Shield className="h-4 w-4" /> Sandbox Mode
                      </span>
                    ) : (
                      <span className="text-red-600 flex items-center gap-1">
                        <AlertTriangle className="h-4 w-4" /> Real Money
                      </span>
                    )}
                  </Label>
                </div>
              </div>
              
              <div className="space-y-2">
                <Label>Order Confirmation</Label>
                <div className="flex items-center space-x-2 pt-2">
                  <Switch
                    checked={requireConfirmation}
                    onCheckedChange={setRequireConfirmation}
                  />
                  <Label className="text-sm text-muted-foreground">
                    {requireConfirmation ? "Required" : "Auto-execute"}
                  </Label>
                </div>
              </div>
            </div>
            
            <div className="mt-6 flex justify-end">
              <Button onClick={startSession} disabled={starting} size="lg">
                {starting ? (
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Play className="h-4 w-4 mr-2" />
                )}
                Start Live Trading
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Active Session Stats */}
      {session?.is_active && (
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Capital</p>
                  <p className="text-2xl font-bold">{formatCurrency(session.capital)}</p>
                </div>
                <DollarSign className="h-8 w-8 text-muted-foreground" />
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Realized P&L</p>
                  <p className={`text-2xl font-bold ${session.realized_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {formatCurrency(session.realized_pnl)}
                  </p>
                </div>
                {session.realized_pnl >= 0 ? (
                  <TrendingUp className="h-8 w-8 text-green-600" />
                ) : (
                  <TrendingDown className="h-8 w-8 text-red-600" />
                )}
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Unrealized P&L</p>
                  <p className={`text-2xl font-bold ${session.unrealized_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {formatCurrency(session.unrealized_pnl)}
                  </p>
                </div>
                <Activity className="h-8 w-8 text-muted-foreground" />
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Orders</p>
                  <p className="text-2xl font-bold">
                    {session.orders_filled}/{session.orders_placed}
                  </p>
                </div>
                <CheckCircle className="h-8 w-8 text-muted-foreground" />
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Broker</p>
                  <p className="text-2xl font-bold capitalize">{session.broker}</p>
                </div>
                <Zap className="h-8 w-8 text-muted-foreground" />
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Positions Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Open Positions ({positions.length})</CardTitle>
          <Button variant="outline" size="sm" onClick={reconcilePositions}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Reconcile
          </Button>
        </CardHeader>
        <CardContent>
          {positions.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No open positions
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead className="text-right">Entry</TableHead>
                  <TableHead className="text-right">LTP</TableHead>
                  <TableHead className="text-right">P&L</TableHead>
                  <TableHead className="text-right">SL</TableHead>
                  <TableHead className="text-right">Target</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {positions.map((pos, idx) => (
                  <TableRow key={idx}>
                    <TableCell className="font-medium">{pos.symbol}</TableCell>
                    <TableCell>
                      <Badge variant={pos.side === "LONG" ? "default" : "destructive"}>
                        {pos.side}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">{pos.quantity}</TableCell>
                    <TableCell className="text-right">₹{pos.entry_price.toFixed(2)}</TableCell>
                    <TableCell className="text-right">₹{pos.current_price.toFixed(2)}</TableCell>
                    <TableCell className={`text-right font-medium ${pos.unrealized_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {formatCurrency(pos.unrealized_pnl)}
                    </TableCell>
                    <TableCell className="text-right text-red-600">
                      {pos.stop_loss ? `₹${pos.stop_loss.toFixed(2)}` : '-'}
                      {pos.trailing_sl && <span className="text-xs ml-1">(TSL)</span>}
                    </TableCell>
                    <TableCell className="text-right text-green-600">
                      {pos.target ? `₹${pos.target.toFixed(2)}` : '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Orders Section */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Orders</CardTitle>
          {session?.is_active && (
            <Button onClick={() => setShowOrderForm(!showOrderForm)}>
              {showOrderForm ? (
                <>
                  <EyeOff className="h-4 w-4 mr-2" />
                  Hide Form
                </>
              ) : (
                <>
                  <Eye className="h-4 w-4 mr-2" />
                  Place Order
                </>
              )}
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {/* Order Form */}
          {showOrderForm && (
            <div className="mb-6 p-4 border rounded-lg bg-muted/50">
              <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
                <div className="space-y-2">
                  <Label>Symbol</Label>
                  <Input
                    value={orderSymbol}
                    onChange={(e) => setOrderSymbol(e.target.value.toUpperCase())}
                    placeholder="NIFTY24DEC24500CE"
                  />
                </div>
                
                <div className="space-y-2">
                  <Label>Side</Label>
                  <Select value={orderSide} onValueChange={(v) => setOrderSide(v as "BUY" | "SELL")}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="BUY">BUY</SelectItem>
                      <SelectItem value="SELL">SELL</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="space-y-2">
                  <Label>Type</Label>
                  <Select value={orderType} onValueChange={(v) => setOrderType(v as any)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="MARKET">MARKET</SelectItem>
                      <SelectItem value="LIMIT">LIMIT</SelectItem>
                      <SelectItem value="SL">SL</SelectItem>
                      <SelectItem value="SL-M">SL-M</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="space-y-2">
                  <Label>Quantity</Label>
                  <Input
                    type="number"
                    value={orderQuantity}
                    onChange={(e) => setOrderQuantity(e.target.value)}
                    placeholder="1"
                  />
                </div>
                
                <div className="space-y-2">
                  <Label>Price</Label>
                  <Input
                    type="number"
                    value={orderPrice}
                    onChange={(e) => setOrderPrice(e.target.value)}
                    placeholder="Market"
                    disabled={orderType === "MARKET"}
                  />
                </div>
                
                <div className="space-y-2">
                  <Label>Stop Loss</Label>
                  <Input
                    type="number"
                    value={orderStopLoss}
                    onChange={(e) => setOrderStopLoss(e.target.value)}
                    placeholder="Optional"
                  />
                </div>
              </div>
              
              <div className="mt-4 flex justify-end gap-2">
                <Button variant="outline" onClick={() => setShowOrderForm(false)}>
                  Cancel
                </Button>
                <Button onClick={placeOrder} disabled={!orderSymbol || !orderQuantity}>
                  Place Order
                </Button>
              </div>
            </div>
          )}

          {/* Orders Table */}
          {orders.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No orders yet
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="text-right">Filled</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.slice(0, 20).map((order) => (
                  <TableRow key={order.order_id}>
                    <TableCell className="text-sm text-muted-foreground">
                      {new Date(order.placed_at).toLocaleTimeString()}
                    </TableCell>
                    <TableCell className="font-medium">{order.symbol}</TableCell>
                    <TableCell>
                      <Badge variant={order.side === "BUY" ? "default" : "destructive"}>
                        {order.side}
                      </Badge>
                    </TableCell>
                    <TableCell>{order.order_type}</TableCell>
                    <TableCell className="text-right">{order.quantity}</TableCell>
                    <TableCell className="text-right">
                      {order.price ? `₹${order.price.toFixed(2)}` : 'MKT'}
                    </TableCell>
                    <TableCell className="text-right">
                      {order.filled_quantity}/{order.quantity}
                      {order.average_price && (
                        <span className="text-xs text-muted-foreground ml-1">
                          @ ₹{order.average_price.toFixed(2)}
                        </span>
                      )}
                    </TableCell>
                    <TableCell>{getStatusBadge(order.status)}</TableCell>
                    <TableCell>
                      {(order.status === "PENDING" || order.status === "OPEN") && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => cancelOrder(order.order_id)}
                        >
                          <XCircle className="h-4 w-4 text-red-500" />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
