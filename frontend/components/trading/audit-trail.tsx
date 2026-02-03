"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  ScrollText,
  Search,
  Filter,
  Download,
  RefreshCw,
  Clock,
  Activity,
  ShoppingCart,
  TrendingUp,
  AlertTriangle,
  Settings,
  ChevronDown,
  ChevronUp,
  Eye,
  Calendar,
} from "lucide-react";
import { apiClient } from "@/lib/api/client";

// Types
interface AuditLog {
  id: string;
  timestamp: string;
  level: "INFO" | "WARNING" | "ERROR" | "CRITICAL" | "DEBUG";
  category: "trade" | "order" | "position" | "risk" | "system";
  action: string;
  details: Record<string, any>;
  user_id?: string;
  session_id?: string;
  correlation_id?: string;
}

interface AuditStats {
  total_logs_today: number;
  trades_executed: number;
  orders_placed: number;
  risk_events: number;
  system_events: number;
  errors_count: number;
}

interface FilterState {
  level: string;
  category: string;
  search: string;
  startDate: string;
  endDate: string;
}

export function AuditTrailPanel() {
  // State
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("all");
  
  // Filters
  const [filters, setFilters] = useState<FilterState>({
    level: "all",
    category: "all",
    search: "",
    startDate: "",
    endDate: "",
  });
  const [showFilters, setShowFilters] = useState(false);

  // Fetch logs
  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true);
      
      const params = new URLSearchParams();
      params.append("page", page.toString());
      params.append("limit", "50");
      
      if (filters.level !== "all") params.append("level", filters.level);
      if (filters.category !== "all") params.append("category", filters.category);
      if (filters.search) params.append("search", filters.search);
      if (filters.startDate) params.append("start_date", filters.startDate);
      if (filters.endDate) params.append("end_date", filters.endDate);
      
      // Map tab to category filter
      if (activeTab !== "all") {
        params.set("category", activeTab);
      }
      
      const response = await apiClient.get(`/audit/logs?${params.toString()}`);
      setLogs(response.data.logs || []);
      setTotalPages(response.data.total_pages || 1);
      
      // Fetch stats
      const statsRes = await apiClient.get("/audit/stats");
      setStats(statsRes.data);
      
    } catch (error) {
      console.error("Failed to fetch audit logs:", error);
    } finally {
      setLoading(false);
    }
  }, [page, filters, activeTab]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // Export logs
  const exportLogs = async (format: "csv" | "json") => {
    try {
      const params = new URLSearchParams();
      params.append("format", format);
      if (filters.startDate) params.append("start_date", filters.startDate);
      if (filters.endDate) params.append("end_date", filters.endDate);
      if (filters.category !== "all") params.append("category", filters.category);
      
      const response = await apiClient.get(`/audit/export?${params.toString()}`, {
        responseType: "blob",
      });
      
      const blob = new Blob([response.data], { 
        type: format === "csv" ? "text/csv" : "application/json" 
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit_log_${new Date().toISOString().split('T')[0]}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      
    } catch (error) {
      console.error("Failed to export logs:", error);
      alert("Failed to export logs");
    }
  };

  // Get level badge
  const getLevelBadge = (level: string) => {
    const config: Record<string, { variant: "default" | "secondary" | "destructive" | "outline"; className: string }> = {
      CRITICAL: { variant: "destructive", className: "bg-red-600" },
      ERROR: { variant: "destructive", className: "" },
      WARNING: { variant: "default", className: "bg-amber-500" },
      INFO: { variant: "secondary", className: "" },
      DEBUG: { variant: "outline", className: "" },
    };
    
    const c = config[level] || config.INFO;
    return (
      <Badge variant={c.variant} className={c.className}>
        {level}
      </Badge>
    );
  };

  // Get category icon
  const getCategoryIcon = (category: string) => {
    switch (category) {
      case "trade":
        return <TrendingUp className="h-4 w-4 text-green-500" />;
      case "order":
        return <ShoppingCart className="h-4 w-4 text-blue-500" />;
      case "position":
        return <Activity className="h-4 w-4 text-purple-500" />;
      case "risk":
        return <AlertTriangle className="h-4 w-4 text-amber-500" />;
      case "system":
        return <Settings className="h-4 w-4 text-gray-500" />;
      default:
        return <ScrollText className="h-4 w-4" />;
    }
  };

  // Format timestamp
  const formatTimestamp = (ts: string) => {
    const date = new Date(ts);
    return {
      date: date.toLocaleDateString(),
      time: date.toLocaleTimeString(),
    };
  };

  // Format details for display
  const formatDetails = (details: Record<string, any>) => {
    return Object.entries(details).map(([key, value]) => (
      <div key={key} className="flex gap-2 text-sm">
        <span className="font-medium text-muted-foreground">{key}:</span>
        <span className="font-mono">
          {typeof value === "object" ? JSON.stringify(value) : String(value)}
        </span>
      </div>
    ));
  };

  if (loading && logs.length === 0) {
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
            <ScrollText className="h-6 w-6" />
            Audit Trail
          </h2>
          <p className="text-muted-foreground">
            Complete history of all trading activities and system events
          </p>
        </div>
        
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => exportLogs("csv")}>
            <Download className="h-4 w-4 mr-2" />
            CSV
          </Button>
          <Button variant="outline" size="sm" onClick={() => exportLogs("json")}>
            <Download className="h-4 w-4 mr-2" />
            JSON
          </Button>
          <Button variant="outline" size="sm" onClick={fetchLogs}>
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
                <p className="text-2xl font-bold">{stats.total_logs_today}</p>
                <p className="text-xs text-muted-foreground">Total Today</p>
              </div>
            </CardContent>
          </Card>
          
          <Card className="border-green-200 bg-green-50">
            <CardContent className="pt-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-green-600">{stats.trades_executed}</p>
                <p className="text-xs text-green-600">Trades</p>
              </div>
            </CardContent>
          </Card>
          
          <Card className="border-blue-200 bg-blue-50">
            <CardContent className="pt-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-blue-600">{stats.orders_placed}</p>
                <p className="text-xs text-blue-600">Orders</p>
              </div>
            </CardContent>
          </Card>
          
          <Card className="border-amber-200 bg-amber-50">
            <CardContent className="pt-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-amber-600">{stats.risk_events}</p>
                <p className="text-xs text-amber-600">Risk Events</p>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="pt-4">
              <div className="text-center">
                <p className="text-2xl font-bold">{stats.system_events}</p>
                <p className="text-xs text-muted-foreground">System</p>
              </div>
            </CardContent>
          </Card>
          
          <Card className="border-red-200 bg-red-50">
            <CardContent className="pt-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-red-600">{stats.errors_count}</p>
                <p className="text-xs text-red-600">Errors</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <Button
              variant="ghost"
              onClick={() => setShowFilters(!showFilters)}
              className="flex items-center gap-2"
            >
              <Filter className="h-4 w-4" />
              Filters
              {showFilters ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
            
            {/* Quick search */}
            <div className="flex items-center gap-2">
              <Search className="h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search logs..."
                className="w-64"
                value={filters.search}
                onChange={(e) => setFilters(prev => ({ ...prev, search: e.target.value }))}
              />
            </div>
          </div>
        </CardHeader>
        
        {showFilters && (
          <CardContent className="border-t pt-4">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div className="space-y-2">
                <Label>Level</Label>
                <Select
                  value={filters.level}
                  onValueChange={(v) => setFilters(prev => ({ ...prev, level: v }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="All levels" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Levels</SelectItem>
                    <SelectItem value="CRITICAL">Critical</SelectItem>
                    <SelectItem value="ERROR">Error</SelectItem>
                    <SelectItem value="WARNING">Warning</SelectItem>
                    <SelectItem value="INFO">Info</SelectItem>
                    <SelectItem value="DEBUG">Debug</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div className="space-y-2">
                <Label>Category</Label>
                <Select
                  value={filters.category}
                  onValueChange={(v) => setFilters(prev => ({ ...prev, category: v }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="All categories" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Categories</SelectItem>
                    <SelectItem value="trade">Trades</SelectItem>
                    <SelectItem value="order">Orders</SelectItem>
                    <SelectItem value="position">Positions</SelectItem>
                    <SelectItem value="risk">Risk</SelectItem>
                    <SelectItem value="system">System</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div className="space-y-2">
                <Label>From Date</Label>
                <Input
                  type="date"
                  value={filters.startDate}
                  onChange={(e) => setFilters(prev => ({ ...prev, startDate: e.target.value }))}
                />
              </div>
              
              <div className="space-y-2">
                <Label>To Date</Label>
                <Input
                  type="date"
                  value={filters.endDate}
                  onChange={(e) => setFilters(prev => ({ ...prev, endDate: e.target.value }))}
                />
              </div>
              
              <div className="space-y-2 flex items-end">
                <Button
                  variant="outline"
                  onClick={() => setFilters({
                    level: "all",
                    category: "all",
                    search: "",
                    startDate: "",
                    endDate: "",
                  })}
                >
                  Clear Filters
                </Button>
              </div>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Logs Table with Tabs */}
      <Card>
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <CardHeader>
            <TabsList>
              <TabsTrigger value="all" className="flex items-center gap-2">
                <ScrollText className="h-4 w-4" />
                All
              </TabsTrigger>
              <TabsTrigger value="trade" className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4" />
                Trades
              </TabsTrigger>
              <TabsTrigger value="order" className="flex items-center gap-2">
                <ShoppingCart className="h-4 w-4" />
                Orders
              </TabsTrigger>
              <TabsTrigger value="position" className="flex items-center gap-2">
                <Activity className="h-4 w-4" />
                Positions
              </TabsTrigger>
              <TabsTrigger value="risk" className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                Risk
              </TabsTrigger>
              <TabsTrigger value="system" className="flex items-center gap-2">
                <Settings className="h-4 w-4" />
                System
              </TabsTrigger>
            </TabsList>
          </CardHeader>
          
          <CardContent>
            {logs.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                <ScrollText className="h-12 w-12 mx-auto mb-4" />
                <p>No logs found</p>
              </div>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[160px]">Timestamp</TableHead>
                      <TableHead className="w-[80px]">Level</TableHead>
                      <TableHead className="w-[100px]">Category</TableHead>
                      <TableHead>Action</TableHead>
                      <TableHead className="w-[80px]"></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {logs.map((log) => {
                      const ts = formatTimestamp(log.timestamp);
                      const isExpanded = expandedLog === log.id;
                      
                      return (
                        <>
                          <TableRow 
                            key={log.id}
                            className={`cursor-pointer hover:bg-muted/50 ${isExpanded ? 'bg-muted/50' : ''}`}
                            onClick={() => setExpandedLog(isExpanded ? null : log.id)}
                          >
                            <TableCell>
                              <div className="flex items-center gap-2">
                                <Clock className="h-3 w-3 text-muted-foreground" />
                                <div className="text-sm">
                                  <div className="font-medium">{ts.time}</div>
                                  <div className="text-xs text-muted-foreground">{ts.date}</div>
                                </div>
                              </div>
                            </TableCell>
                            <TableCell>{getLevelBadge(log.level)}</TableCell>
                            <TableCell>
                              <div className="flex items-center gap-2">
                                {getCategoryIcon(log.category)}
                                <span className="capitalize">{log.category}</span>
                              </div>
                            </TableCell>
                            <TableCell className="font-medium">{log.action}</TableCell>
                            <TableCell>
                              <Button variant="ghost" size="sm">
                                <Eye className="h-4 w-4" />
                              </Button>
                            </TableCell>
                          </TableRow>
                          
                          {isExpanded && (
                            <TableRow key={`${log.id}-details`}>
                              <TableCell colSpan={5} className="bg-muted/30">
                                <div className="p-4 space-y-3">
                                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                                    {log.session_id && (
                                      <div>
                                        <span className="text-muted-foreground">Session:</span>
                                        <span className="ml-2 font-mono text-xs">{log.session_id}</span>
                                      </div>
                                    )}
                                    {log.correlation_id && (
                                      <div>
                                        <span className="text-muted-foreground">Correlation:</span>
                                        <span className="ml-2 font-mono text-xs">{log.correlation_id}</span>
                                      </div>
                                    )}
                                    {log.user_id && (
                                      <div>
                                        <span className="text-muted-foreground">User:</span>
                                        <span className="ml-2">{log.user_id}</span>
                                      </div>
                                    )}
                                  </div>
                                  
                                  <div className="border-t pt-3">
                                    <h4 className="text-sm font-semibold mb-2">Details</h4>
                                    <div className="bg-background rounded p-3 space-y-1">
                                      {formatDetails(log.details)}
                                    </div>
                                  </div>
                                </div>
                              </TableCell>
                            </TableRow>
                          )}
                        </>
                      );
                    })}
                  </TableBody>
                </Table>
                
                {/* Pagination */}
                <div className="flex items-center justify-between mt-4">
                  <p className="text-sm text-muted-foreground">
                    Page {page} of {totalPages}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                      disabled={page === 1}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                      disabled={page === totalPages}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Tabs>
      </Card>
    </div>
  );
}
