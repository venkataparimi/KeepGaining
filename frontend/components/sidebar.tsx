"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, TrendingUp, Building2, Radio, Menu, BarChart3, LineChart, Code2, Rocket, Settings, Brain, Bot, Target, List, PieChart } from "lucide-react";
import { useState } from "react";

const navigation = [
    { name: "Dashboard", href: "/", icon: Home },
    { name: "Morning Momentum Alpha", href: "/strategy", icon: Target },
    { name: "Trade Log", href: "/trades", icon: List },
    { name: "Strategies", href: "/strategies", icon: TrendingUp },
    { name: "Strategy Editor", href: "/strategy-editor", icon: Code2 },
    { name: "AI Assistant", href: "/ai-assistant", icon: Bot },
    { name: "Deployments", href: "/deployments", icon: Rocket },
    { name: "Analytics", href: "/analytics", icon: BarChart3 },
    { name: "Strategy Trades", href: "/strategy-trades", icon: PieChart },
    { name: "Advanced Analytics", href: "/advanced-analytics", icon: Brain },
    { name: "Market", href: "/market", icon: LineChart },
    { name: "Charts", href: "/chart", icon: BarChart3 },
    { name: "Brokers", href: "/brokers", icon: Building2 },
    { name: "Comet", href: "/comet", icon: Radio },
    { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
    const pathname = usePathname();
    const [collapsed, setCollapsed] = useState(false);

    return (
        <div className={`${collapsed ? 'w-20' : 'w-64'} glass border-r border-border/50 smooth-transition flex flex-col`}>
            <div className="p-6 border-b border-border/50">
                <div className="flex items-center justify-between">
                    {!collapsed && <h2 className="text-xl font-bold gradient-text">KeepGaining</h2>}
                    <button
                        onClick={() => setCollapsed(!collapsed)}
                        className="p-2 hover:bg-primary/10 rounded-lg smooth-transition"
                        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                    >
                        <Menu className="h-5 w-5" />
                    </button>
                </div>
            </div>

            <nav className="flex-1 p-4 space-y-2">
                {navigation.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link
                            key={item.name}
                            href={item.href}
                            className={`flex items-center space-x-3 px-4 py-3 rounded-lg smooth-transition ${isActive
                                ? 'bg-gradient-to-r from-primary/20 to-secondary/20 text-primary border border-primary/30'
                                : 'hover:bg-primary/10 text-muted-foreground hover:text-foreground'
                                }`}
                        >
                            <item.icon className="h-5 w-5 flex-shrink-0" />
                            {!collapsed && <span className="font-medium">{item.name}</span>}
                        </Link>
                    );
                })}
            </nav>

            <div className="p-4 border-t border-border/50">
                <div className={`p-3 rounded-lg bg-gradient-to-r from-primary/10 to-secondary/10 ${collapsed ? 'text-center' : ''}`}>
                    <p className="text-xs text-muted-foreground">
                        {collapsed ? '●' : 'Live Trading'}
                    </p>
                </div>
            </div>
        </div>
    );
}
