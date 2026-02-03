"use client";

import { useMemo, useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Calendar as CalendarIcon, TrendingUp, TrendingDown, Loader2, RefreshCw, ChevronLeft, ChevronRight } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { apiClient } from "@/lib/api/client";

interface DayData {
    date: string;
    pnl: number;
    trades: number;
}

interface CalendarHeatmapProps {
    data?: DayData[];
    year?: number;
}

// Generate mock data for fallback
const generateMockData = (year: number): DayData[] => {
    const days: DayData[] = [];
    const startDate = new Date(year, 0, 1);
    const endDate = new Date(year, 11, 31);
    
    for (let d = new Date(startDate); d <= endDate; d.setDate(d.getDate() + 1)) {
        if (d.getDay() === 0 || d.getDay() === 6) continue;
        
        if (Math.random() > 0.3) {
            const pnl = (Math.random() - 0.4) * 10000;
            days.push({
                date: d.toISOString().split('T')[0],
                pnl: Math.round(pnl),
                trades: Math.floor(Math.random() * 10 + 1)
            });
        }
    }
    return days;
};

export function CalendarHeatmap({ data: propData, year: initialYear = new Date().getFullYear() }: CalendarHeatmapProps) {
    const [year, setYear] = useState(initialYear);
    const [calendarData, setCalendarData] = useState<DayData[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchData = useCallback(async () => {
        if (propData) {
            setCalendarData(propData);
            setLoading(false);
            return;
        }

        setLoading(true);
        try {
            const data = await apiClient.getDailyPnL(365);
            if (data && data.length > 0) {
                // Filter to current year
                const yearData = data.filter((d: DayData) => d.date.startsWith(String(year)));
                setCalendarData(yearData.length > 0 ? yearData : generateMockData(year));
            } else {
                setCalendarData(generateMockData(year));
            }
        } catch (error) {
            console.error("Failed to fetch daily P&L:", error);
            setCalendarData(generateMockData(year));
        } finally {
            setLoading(false);
        }
    }, [propData, year]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    // Create a map for quick lookup
    const dataMap = useMemo(() => {
        const map = new Map<string, DayData>();
        calendarData.forEach(d => map.set(d.date, d));
        return map;
    }, [calendarData]);

    // Stats
    const stats = useMemo(() => {
        const profitDays = calendarData.filter(d => d.pnl > 0).length;
        const lossDays = calendarData.filter(d => d.pnl < 0).length;
        const totalPnl = calendarData.reduce((sum, d) => sum + d.pnl, 0);
        const bestDay = calendarData.reduce((best, d) => d.pnl > best.pnl ? d : best, { date: '', pnl: -Infinity, trades: 0 });
        const worstDay = calendarData.reduce((worst, d) => d.pnl < worst.pnl ? d : worst, { date: '', pnl: Infinity, trades: 0 });
        
        return { profitDays, lossDays, totalPnl, bestDay, worstDay, totalDays: calendarData.length };
    }, [calendarData]);

    // Generate calendar grid
    const months = useMemo(() => {
        const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const result = [];

        for (let month = 0; month < 12; month++) {
            const firstDay = new Date(year, month, 1);
            const lastDay = new Date(year, month + 1, 0);
            const days = [];

            // Add empty cells for days before the first day of month
            const startPadding = firstDay.getDay();
            for (let i = 0; i < startPadding; i++) {
                days.push(null);
            }

            // Add actual days
            for (let day = 1; day <= lastDay.getDate(); day++) {
                const date = new Date(year, month, day);
                const dateStr = date.toISOString().split('T')[0];
                const dayOfWeek = date.getDay();
                
                days.push({
                    date: dateStr,
                    day,
                    isWeekend: dayOfWeek === 0 || dayOfWeek === 6,
                    data: dataMap.get(dateStr)
                });
            }

            result.push({
                name: monthNames[month],
                days
            });
        }

        return result;
    }, [year, dataMap]);

    // Get color based on P&L
    const getColor = (pnl: number | undefined) => {
        if (pnl === undefined) return 'bg-muted/20';
        
        if (pnl > 5000) return 'bg-green-500';
        if (pnl > 2000) return 'bg-green-400';
        if (pnl > 0) return 'bg-green-300/70';
        if (pnl === 0) return 'bg-muted/30';
        if (pnl > -2000) return 'bg-red-300/70';
        if (pnl > -5000) return 'bg-red-400';
        return 'bg-red-500';
    };

    return (
        <Card className="glass rounded-2xl overflow-hidden">
            <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <CalendarIcon className="h-5 w-5 text-primary" />
                        <CardTitle className="text-xl font-bold">Performance Calendar</CardTitle>
                        <div className="flex items-center gap-1">
                            <Button 
                                variant="ghost" 
                                size="sm" 
                                className="h-7 w-7 p-0"
                                onClick={() => setYear(y => y - 1)}
                            >
                                <ChevronLeft className="h-4 w-4" />
                            </Button>
                            <span className="text-sm font-medium w-12 text-center">{year}</span>
                            <Button 
                                variant="ghost" 
                                size="sm" 
                                className="h-7 w-7 p-0"
                                onClick={() => setYear(y => y + 1)}
                                disabled={year >= new Date().getFullYear()}
                            >
                                <ChevronRight className="h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-4 text-sm">
                            <div className="flex items-center gap-2">
                                <span className="w-3 h-3 rounded bg-green-400"></span>
                                <span className="text-muted-foreground">{stats.profitDays} profit days</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="w-3 h-3 rounded bg-red-400"></span>
                                <span className="text-muted-foreground">{stats.lossDays} loss days</span>
                            </div>
                        </div>
                        <Button 
                            variant="outline" 
                            size="sm"
                            onClick={() => fetchData()}
                            disabled={loading}
                        >
                            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                        </Button>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="pt-4">
                {loading ? (
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                    </div>
                ) : (
                <>
                {/* Summary Stats */}
                <div className="grid grid-cols-4 gap-4 mb-6">
                    <div className="p-3 rounded-lg bg-muted/20 text-center">
                        <p className="text-xs text-muted-foreground">Total P&L</p>
                        <p className={`text-lg font-bold ${stats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {stats.totalPnl >= 0 ? '+' : ''}₹{stats.totalPnl.toLocaleString()}
                        </p>
                    </div>
                    <div className="p-3 rounded-lg bg-muted/20 text-center">
                        <p className="text-xs text-muted-foreground">Win Rate</p>
                        <p className="text-lg font-bold text-blue-400">
                            {stats.totalDays > 0 ? ((stats.profitDays / stats.totalDays) * 100).toFixed(1) : 0}%
                        </p>
                    </div>
                    <div className="p-3 rounded-lg bg-green-500/10 text-center">
                        <p className="text-xs text-muted-foreground">Best Day</p>
                        <p className="text-lg font-bold text-green-400">
                            +₹{stats.bestDay.pnl.toLocaleString()}
                        </p>
                        <p className="text-xs text-muted-foreground">{stats.bestDay.date}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-red-500/10 text-center">
                        <p className="text-xs text-muted-foreground">Worst Day</p>
                        <p className="text-lg font-bold text-red-400">
                            ₹{stats.worstDay.pnl.toLocaleString()}
                        </p>
                        <p className="text-xs text-muted-foreground">{stats.worstDay.date}</p>
                    </div>
                </div>

                {/* Calendar Grid */}
                <TooltipProvider>
                    <div className="grid grid-cols-4 gap-4">
                        {months.map((month) => (
                            <div key={month.name} className="space-y-2">
                                <h4 className="text-sm font-medium text-muted-foreground">{month.name}</h4>
                                <div className="grid grid-cols-7 gap-1">
                                    {/* Day headers */}
                                    {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => (
                                        <div key={i} className="text-[10px] text-center text-muted-foreground">
                                            {d}
                                        </div>
                                    ))}
                                    {/* Days */}
                                    {month.days.map((day, idx) => {
                                        if (!day) {
                                            return <div key={`empty-${idx}`} className="h-4"></div>;
                                        }
                                        
                                        return (
                                            <Tooltip key={day.date}>
                                                <TooltipTrigger asChild>
                                                    <div
                                                        className={`h-4 rounded-sm cursor-pointer transition-all hover:scale-125 hover:z-10 ${
                                                            day.isWeekend 
                                                                ? 'bg-muted/10' 
                                                                : getColor(day.data?.pnl)
                                                        }`}
                                                    ></div>
                                                </TooltipTrigger>
                                                <TooltipContent className="glass border-border/50">
                                                    <div className="text-xs">
                                                        <p className="font-medium">{day.date}</p>
                                                        {day.data ? (
                                                            <>
                                                                <p className={day.data.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                                                                    P&L: {day.data.pnl >= 0 ? '+' : ''}₹{day.data.pnl.toLocaleString()}
                                                                </p>
                                                                <p className="text-muted-foreground">{day.data.trades} trades</p>
                                                            </>
                                                        ) : day.isWeekend ? (
                                                            <p className="text-muted-foreground">Weekend</p>
                                                        ) : (
                                                            <p className="text-muted-foreground">No trades</p>
                                                        )}
                                                    </div>
                                                </TooltipContent>
                                            </Tooltip>
                                        );
                                    })}
                                </div>
                            </div>
                        ))}
                    </div>
                </TooltipProvider>

                {/* Legend */}
                <div className="flex items-center justify-center gap-2 mt-6 text-xs text-muted-foreground">
                    <span>Less</span>
                    <div className="flex gap-1">
                        <div className="w-3 h-3 rounded-sm bg-red-500"></div>
                        <div className="w-3 h-3 rounded-sm bg-red-400"></div>
                        <div className="w-3 h-3 rounded-sm bg-red-300/70"></div>
                        <div className="w-3 h-3 rounded-sm bg-muted/30"></div>
                        <div className="w-3 h-3 rounded-sm bg-green-300/70"></div>
                        <div className="w-3 h-3 rounded-sm bg-green-400"></div>
                        <div className="w-3 h-3 rounded-sm bg-green-500"></div>
                    </div>
                    <span>More</span>
                </div>
                </>
                )}
            </CardContent>
        </Card>
    );
}
