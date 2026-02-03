"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Bell,
  BellOff,
  AlertTriangle,
  AlertCircle,
  CheckCircle,
  Info,
  TrendingUp,
  TrendingDown,
  Activity,
  Shield,
  Zap,
  Clock,
  RefreshCw,
  Settings,
  Mail,
  MessageSquare,
  Webhook,
  Trash2,
  Plus,
  Volume2,
  VolumeX,
} from "lucide-react";
import { apiClient } from "@/lib/api/client";

// Types
interface Alert {
  id: string;
  type: string;
  severity: "info" | "warning" | "critical";
  title: string;
  message: string;
  value?: number;
  threshold?: number;
  triggered_at: string;
  acknowledged: boolean;
  snoozed_until?: string;
}

interface AlertRule {
  id: string;
  name: string;
  type: string;
  enabled: boolean;
  threshold: number;
  comparison: "above" | "below" | "equals";
  channels: string[];
  cooldown_minutes: number;
}

interface AlertStats {
  total_alerts_today: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
  acknowledged_count: number;
  snoozed_count: number;
}

interface GreeksThresholds {
  delta_limit: number;
  gamma_limit: number;
  theta_limit: number;
  vega_limit: number;
}

interface PnLThresholds {
  profit_target: number;
  loss_limit: number;
  daily_loss_limit: number;
  drawdown_limit: number;
}

export function AlertsPanel() {
  // State
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("alerts");
  
  // Alert settings
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [emailEnabled, setEmailEnabled] = useState(false);
  const [webhookEnabled, setWebhookEnabled] = useState(false);
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  
  // Thresholds
  const [greeksThresholds, setGreeksThresholds] = useState<GreeksThresholds>({
    delta_limit: 100,
    gamma_limit: 50,
    theta_limit: -5000,
    vega_limit: 10000,
  });
  
  const [pnlThresholds, setPnlThresholds] = useState<PnLThresholds>({
    profit_target: 10000,
    loss_limit: -5000,
    daily_loss_limit: -10000,
    drawdown_limit: -15,
  });
  
  // New rule form
  const [showNewRule, setShowNewRule] = useState(false);
  const [newRuleName, setNewRuleName] = useState("");
  const [newRuleType, setNewRuleType] = useState("pnl");
  const [newRuleThreshold, setNewRuleThreshold] = useState("");
  const [newRuleComparison, setNewRuleComparison] = useState<"above" | "below">("above");

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      
      // Fetch active alerts
      const alertsRes = await apiClient.get("/alerts/active");
      setAlerts(alertsRes.data.alerts || []);
      
      // Fetch alert rules
      const rulesRes = await apiClient.get("/alerts/rules");
      setRules(rulesRes.data.rules || []);
      
      // Fetch stats
      const statsRes = await apiClient.get("/alerts/stats");
      setStats(statsRes.data);
      
      // Fetch settings
      const settingsRes = await apiClient.get("/alerts/settings");
      if (settingsRes.data) {
        setSoundEnabled(settingsRes.data.sound_enabled ?? true);
        setEmailEnabled(settingsRes.data.email_enabled ?? false);
        setWebhookEnabled(settingsRes.data.webhook_enabled ?? false);
        setTelegramEnabled(settingsRes.data.telegram_enabled ?? false);
        if (settingsRes.data.greeks_thresholds) {
          setGreeksThresholds(settingsRes.data.greeks_thresholds);
        }
        if (settingsRes.data.pnl_thresholds) {
          setPnlThresholds(settingsRes.data.pnl_thresholds);
        }
      }
      
    } catch (error) {
      console.error("Failed to fetch alerts data:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000); // Refresh every 10 seconds
    return () => clearInterval(interval);
  }, [fetchData]);

  // Acknowledge alert
  const acknowledgeAlert = async (alertId: string) => {
    try {
      await apiClient.post(`/alerts/${alertId}/acknowledge`);
      setAlerts(prev => prev.map(a => 
        a.id === alertId ? { ...a, acknowledged: true } : a
      ));
    } catch (error) {
      console.error("Failed to acknowledge alert:", error);
    }
  };

  // Snooze alert
  const snoozeAlert = async (alertId: string, minutes: number) => {
    try {
      await apiClient.post(`/alerts/${alertId}/snooze`, { minutes });
      const snoozedUntil = new Date(Date.now() + minutes * 60000).toISOString();
      setAlerts(prev => prev.map(a => 
        a.id === alertId ? { ...a, snoozed_until: snoozedUntil } : a
      ));
    } catch (error) {
      console.error("Failed to snooze alert:", error);
    }
  };

  // Toggle rule
  const toggleRule = async (ruleId: string, enabled: boolean) => {
    try {
      await apiClient.patch(`/alerts/rules/${ruleId}`, { enabled });
      setRules(prev => prev.map(r => 
        r.id === ruleId ? { ...r, enabled } : r
      ));
    } catch (error) {
      console.error("Failed to toggle rule:", error);
    }
  };

  // Delete rule
  const deleteRule = async (ruleId: string) => {
    if (!confirm("Are you sure you want to delete this rule?")) return;
    
    try {
      await apiClient.delete(`/alerts/rules/${ruleId}`);
      setRules(prev => prev.filter(r => r.id !== ruleId));
    } catch (error) {
      console.error("Failed to delete rule:", error);
    }
  };

  // Create new rule
  const createRule = async () => {
    try {
      const response = await apiClient.post("/alerts/rules", {
        name: newRuleName,
        type: newRuleType,
        threshold: parseFloat(newRuleThreshold),
        comparison: newRuleComparison,
        channels: [soundEnabled && "ui", emailEnabled && "email", telegramEnabled && "telegram"].filter(Boolean),
        cooldown_minutes: 5,
      });
      
      if (response.data.rule) {
        setRules(prev => [...prev, response.data.rule]);
      }
      
      setShowNewRule(false);
      setNewRuleName("");
      setNewRuleThreshold("");
    } catch (error) {
      console.error("Failed to create rule:", error);
    }
  };

  // Save thresholds
  const saveThresholds = async () => {
    try {
      await apiClient.post("/alerts/settings", {
        sound_enabled: soundEnabled,
        email_enabled: emailEnabled,
        webhook_enabled: webhookEnabled,
        telegram_enabled: telegramEnabled,
        greeks_thresholds: greeksThresholds,
        pnl_thresholds: pnlThresholds,
      });
      alert("Settings saved!");
    } catch (error) {
      console.error("Failed to save settings:", error);
      alert("Failed to save settings");
    }
  };

  // Get severity icon
  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case "critical":
        return <AlertCircle className="h-5 w-5 text-red-500" />;
      case "warning":
        return <AlertTriangle className="h-5 w-5 text-amber-500" />;
      default:
        return <Info className="h-5 w-5 text-blue-500" />;
    }
  };

  // Get severity badge
  const getSeverityBadge = (severity: string) => {
    const config: Record<string, { variant: "default" | "secondary" | "destructive" | "outline"; className: string }> = {
      critical: { variant: "destructive", className: "bg-red-500" },
      warning: { variant: "default", className: "bg-amber-500" },
      info: { variant: "secondary", className: "bg-blue-500" },
    };
    
    const c = config[severity] || config.info;
    return (
      <Badge variant={c.variant} className={c.className}>
        {severity.toUpperCase()}
      </Badge>
    );
  };

  // Format time ago
  const timeAgo = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
    
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
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
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Bell className="h-6 w-6" />
            Alert Center
          </h2>
          <p className="text-muted-foreground">
            Real-time P&L, Greeks, and circuit breaker alerts
          </p>
        </div>
        
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setSoundEnabled(!soundEnabled)}
          >
            {soundEnabled ? (
              <Volume2 className="h-4 w-4" />
            ) : (
              <VolumeX className="h-4 w-4" />
            )}
          </Button>
          <Button variant="outline" size="sm" onClick={fetchData}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
          <Card>
            <CardContent className="pt-4">
              <div className="text-center">
                <p className="text-2xl font-bold">{stats.total_alerts_today}</p>
                <p className="text-xs text-muted-foreground">Today</p>
              </div>
            </CardContent>
          </Card>
          
          <Card className="border-red-200 bg-red-50">
            <CardContent className="pt-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-red-600">{stats.critical_count}</p>
                <p className="text-xs text-red-600">Critical</p>
              </div>
            </CardContent>
          </Card>
          
          <Card className="border-amber-200 bg-amber-50">
            <CardContent className="pt-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-amber-600">{stats.warning_count}</p>
                <p className="text-xs text-amber-600">Warning</p>
              </div>
            </CardContent>
          </Card>
          
          <Card className="border-blue-200 bg-blue-50">
            <CardContent className="pt-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-blue-600">{stats.info_count}</p>
                <p className="text-xs text-blue-600">Info</p>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="pt-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-green-600">{stats.acknowledged_count}</p>
                <p className="text-xs text-muted-foreground">Acknowledged</p>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="pt-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-purple-600">{stats.snoozed_count}</p>
                <p className="text-xs text-muted-foreground">Snoozed</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="alerts" className="flex items-center gap-2">
            <Bell className="h-4 w-4" />
            Active Alerts
            {alerts.filter(a => !a.acknowledged).length > 0 && (
              <Badge variant="destructive" className="ml-1">
                {alerts.filter(a => !a.acknowledged).length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="rules" className="flex items-center gap-2">
            <Shield className="h-4 w-4" />
            Alert Rules
          </TabsTrigger>
          <TabsTrigger value="settings" className="flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Thresholds
          </TabsTrigger>
        </TabsList>

        {/* Active Alerts Tab */}
        <TabsContent value="alerts" className="mt-4">
          <Card>
            <CardContent className="pt-6">
              {alerts.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <CheckCircle className="h-12 w-12 mx-auto mb-4 text-green-500" />
                  <p className="text-lg font-medium">All Clear!</p>
                  <p>No active alerts at the moment</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {alerts.map((alert) => (
                    <div
                      key={alert.id}
                      className={`p-4 rounded-lg border ${
                        alert.acknowledged ? 'bg-muted/50' : 
                        alert.severity === 'critical' ? 'bg-red-50 border-red-200' :
                        alert.severity === 'warning' ? 'bg-amber-50 border-amber-200' :
                        'bg-blue-50 border-blue-200'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-3">
                          {getSeverityIcon(alert.severity)}
                          <div>
                            <div className="flex items-center gap-2">
                              <h4 className="font-semibold">{alert.title}</h4>
                              {getSeverityBadge(alert.severity)}
                              {alert.acknowledged && (
                                <Badge variant="outline" className="text-green-600">
                                  <CheckCircle className="h-3 w-3 mr-1" />
                                  Ack
                                </Badge>
                              )}
                              {alert.snoozed_until && new Date(alert.snoozed_until) > new Date() && (
                                <Badge variant="outline" className="text-purple-600">
                                  <BellOff className="h-3 w-3 mr-1" />
                                  Snoozed
                                </Badge>
                              )}
                            </div>
                            <p className="text-sm text-muted-foreground mt-1">
                              {alert.message}
                            </p>
                            {alert.value !== undefined && alert.threshold !== undefined && (
                              <div className="mt-2">
                                <div className="flex items-center gap-2 text-sm">
                                  <span>Value: <strong>{alert.value.toFixed(2)}</strong></span>
                                  <span className="text-muted-foreground">|</span>
                                  <span>Threshold: <strong>{alert.threshold.toFixed(2)}</strong></span>
                                </div>
                                <Progress 
                                  value={Math.min(100, Math.abs(alert.value / alert.threshold) * 100)} 
                                  className="h-2 mt-1"
                                />
                              </div>
                            )}
                            <p className="text-xs text-muted-foreground mt-2">
                              <Clock className="h-3 w-3 inline mr-1" />
                              {timeAgo(alert.triggered_at)}
                            </p>
                          </div>
                        </div>
                        
                        <div className="flex items-center gap-2">
                          {!alert.acknowledged && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => acknowledgeAlert(alert.id)}
                            >
                              <CheckCircle className="h-4 w-4 mr-1" />
                              Ack
                            </Button>
                          )}
                          <Select onValueChange={(v) => snoozeAlert(alert.id, parseInt(v))}>
                            <SelectTrigger className="w-24">
                              <SelectValue placeholder="Snooze" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="5">5 min</SelectItem>
                              <SelectItem value="15">15 min</SelectItem>
                              <SelectItem value="30">30 min</SelectItem>
                              <SelectItem value="60">1 hour</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Alert Rules Tab */}
        <TabsContent value="rules" className="mt-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Alert Rules</CardTitle>
              <Button onClick={() => setShowNewRule(!showNewRule)}>
                <Plus className="h-4 w-4 mr-2" />
                Add Rule
              </Button>
            </CardHeader>
            <CardContent>
              {/* New Rule Form */}
              {showNewRule && (
                <div className="mb-6 p-4 border rounded-lg bg-muted/50">
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    <div className="space-y-2">
                      <Label>Name</Label>
                      <Input
                        value={newRuleName}
                        onChange={(e) => setNewRuleName(e.target.value)}
                        placeholder="Rule name"
                      />
                    </div>
                    
                    <div className="space-y-2">
                      <Label>Type</Label>
                      <Select value={newRuleType} onValueChange={setNewRuleType}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="pnl">P&L</SelectItem>
                          <SelectItem value="delta">Delta</SelectItem>
                          <SelectItem value="gamma">Gamma</SelectItem>
                          <SelectItem value="theta">Theta</SelectItem>
                          <SelectItem value="vega">Vega</SelectItem>
                          <SelectItem value="drawdown">Drawdown</SelectItem>
                          <SelectItem value="consecutive_loss">Consecutive Loss</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    
                    <div className="space-y-2">
                      <Label>Comparison</Label>
                      <Select value={newRuleComparison} onValueChange={(v) => setNewRuleComparison(v as any)}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="above">Above</SelectItem>
                          <SelectItem value="below">Below</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    
                    <div className="space-y-2">
                      <Label>Threshold</Label>
                      <Input
                        type="number"
                        value={newRuleThreshold}
                        onChange={(e) => setNewRuleThreshold(e.target.value)}
                        placeholder="Value"
                      />
                    </div>
                    
                    <div className="space-y-2 flex items-end">
                      <Button onClick={createRule} disabled={!newRuleName || !newRuleThreshold}>
                        Create Rule
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {/* Rules Table */}
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Condition</TableHead>
                    <TableHead>Channels</TableHead>
                    <TableHead>Cooldown</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rules.map((rule) => (
                    <TableRow key={rule.id}>
                      <TableCell className="font-medium">{rule.name}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{rule.type}</Badge>
                      </TableCell>
                      <TableCell>
                        {rule.comparison} {rule.threshold}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          {rule.channels.includes("email") && <Mail className="h-4 w-4" />}
                          {rule.channels.includes("telegram") && <MessageSquare className="h-4 w-4" />}
                          {rule.channels.includes("webhook") && <Webhook className="h-4 w-4" />}
                          {rule.channels.includes("ui") && <Bell className="h-4 w-4" />}
                        </div>
                      </TableCell>
                      <TableCell>{rule.cooldown_minutes}m</TableCell>
                      <TableCell>
                        <Switch
                          checked={rule.enabled}
                          onCheckedChange={(checked) => toggleRule(rule.id, checked)}
                        />
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => deleteRule(rule.id)}
                        >
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Thresholds Settings Tab */}
        <TabsContent value="settings" className="mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* P&L Thresholds */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5" />
                  P&L Thresholds
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Profit Target (₹)</Label>
                  <Input
                    type="number"
                    value={pnlThresholds.profit_target}
                    onChange={(e) => setPnlThresholds(prev => ({
                      ...prev, profit_target: parseFloat(e.target.value)
                    }))}
                  />
                  <p className="text-xs text-muted-foreground">Alert when profit reaches this amount</p>
                </div>
                
                <div className="space-y-2">
                  <Label>Loss Limit (₹)</Label>
                  <Input
                    type="number"
                    value={pnlThresholds.loss_limit}
                    onChange={(e) => setPnlThresholds(prev => ({
                      ...prev, loss_limit: parseFloat(e.target.value)
                    }))}
                  />
                  <p className="text-xs text-muted-foreground">Alert when loss reaches this amount (negative)</p>
                </div>
                
                <div className="space-y-2">
                  <Label>Daily Loss Limit (₹)</Label>
                  <Input
                    type="number"
                    value={pnlThresholds.daily_loss_limit}
                    onChange={(e) => setPnlThresholds(prev => ({
                      ...prev, daily_loss_limit: parseFloat(e.target.value)
                    }))}
                  />
                  <p className="text-xs text-muted-foreground">Circuit breaker when daily loss exceeds this</p>
                </div>
                
                <div className="space-y-2">
                  <Label>Max Drawdown (%)</Label>
                  <Input
                    type="number"
                    value={pnlThresholds.drawdown_limit}
                    onChange={(e) => setPnlThresholds(prev => ({
                      ...prev, drawdown_limit: parseFloat(e.target.value)
                    }))}
                  />
                  <p className="text-xs text-muted-foreground">Alert when drawdown exceeds this percentage</p>
                </div>
              </CardContent>
            </Card>

            {/* Greeks Thresholds */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Activity className="h-5 w-5" />
                  Greeks Thresholds
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Delta Limit</Label>
                  <Input
                    type="number"
                    value={greeksThresholds.delta_limit}
                    onChange={(e) => setGreeksThresholds(prev => ({
                      ...prev, delta_limit: parseFloat(e.target.value)
                    }))}
                  />
                  <p className="text-xs text-muted-foreground">Alert when net delta exceeds this</p>
                </div>
                
                <div className="space-y-2">
                  <Label>Gamma Limit</Label>
                  <Input
                    type="number"
                    value={greeksThresholds.gamma_limit}
                    onChange={(e) => setGreeksThresholds(prev => ({
                      ...prev, gamma_limit: parseFloat(e.target.value)
                    }))}
                  />
                  <p className="text-xs text-muted-foreground">Alert when net gamma exceeds this</p>
                </div>
                
                <div className="space-y-2">
                  <Label>Theta Limit (₹)</Label>
                  <Input
                    type="number"
                    value={greeksThresholds.theta_limit}
                    onChange={(e) => setGreeksThresholds(prev => ({
                      ...prev, theta_limit: parseFloat(e.target.value)
                    }))}
                  />
                  <p className="text-xs text-muted-foreground">Alert when theta decay exceeds this (negative)</p>
                </div>
                
                <div className="space-y-2">
                  <Label>Vega Limit (₹)</Label>
                  <Input
                    type="number"
                    value={greeksThresholds.vega_limit}
                    onChange={(e) => setGreeksThresholds(prev => ({
                      ...prev, vega_limit: parseFloat(e.target.value)
                    }))}
                  />
                  <p className="text-xs text-muted-foreground">Alert when vega exposure exceeds this</p>
                </div>
              </CardContent>
            </Card>

            {/* Notification Channels */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Bell className="h-5 w-5" />
                  Notification Channels
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Volume2 className="h-5 w-5" />
                    <Label>Sound Alerts</Label>
                  </div>
                  <Switch checked={soundEnabled} onCheckedChange={setSoundEnabled} />
                </div>
                
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Mail className="h-5 w-5" />
                    <Label>Email Notifications</Label>
                  </div>
                  <Switch checked={emailEnabled} onCheckedChange={setEmailEnabled} />
                </div>
                
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <MessageSquare className="h-5 w-5" />
                    <Label>Telegram Alerts</Label>
                  </div>
                  <Switch checked={telegramEnabled} onCheckedChange={setTelegramEnabled} />
                </div>
                
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Webhook className="h-5 w-5" />
                    <Label>Webhook Integration</Label>
                  </div>
                  <Switch checked={webhookEnabled} onCheckedChange={setWebhookEnabled} />
                </div>
              </CardContent>
            </Card>

            {/* Save Button */}
            <Card>
              <CardContent className="pt-6">
                <Button onClick={saveThresholds} className="w-full" size="lg">
                  <CheckCircle className="h-4 w-4 mr-2" />
                  Save All Settings
                </Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
