"use client";

import { useState, useEffect } from "react";
import { Bell, X, AlertTriangle, TrendingUp, CheckCircle, Info } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Notification {
    id: string;
    type: 'success' | 'warning' | 'error' | 'info';
    title: string;
    message: string;
    timestamp: Date;
    read: boolean;
}

interface NotificationCenterProps {
    notifications?: Notification[];
    onDismiss?: (id: string) => void;
    onClearAll?: () => void;
}

export function NotificationCenter({ 
    notifications = [], 
    onDismiss,
    onClearAll 
}: NotificationCenterProps) {
    const [isOpen, setIsOpen] = useState(false);
    const unreadCount = notifications.filter(n => !n.read).length;

    const getIcon = (type: Notification['type']) => {
        switch (type) {
            case 'success': return <CheckCircle className="h-4 w-4 text-green-400" />;
            case 'warning': return <AlertTriangle className="h-4 w-4 text-yellow-400" />;
            case 'error': return <AlertTriangle className="h-4 w-4 text-red-400" />;
            case 'info': return <Info className="h-4 w-4 text-blue-400" />;
        }
    };

    const getBgColor = (type: Notification['type']) => {
        switch (type) {
            case 'success': return 'bg-green-500/10 border-green-500/20';
            case 'warning': return 'bg-yellow-500/10 border-yellow-500/20';
            case 'error': return 'bg-red-500/10 border-red-500/20';
            case 'info': return 'bg-blue-500/10 border-blue-500/20';
        }
    };

    return (
        <div className="relative">
            <Button
                variant="ghost"
                size="sm"
                className="relative"
                onClick={() => setIsOpen(!isOpen)}
            >
                <Bell className="h-5 w-5" />
                {unreadCount > 0 && (
                    <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 rounded-full text-xs flex items-center justify-center text-white font-bold animate-pulse">
                        {unreadCount}
                    </span>
                )}
            </Button>

            {isOpen && (
                <>
                    <div 
                        className="fixed inset-0 z-40" 
                        onClick={() => setIsOpen(false)}
                    />
                    <div className="absolute right-0 top-full mt-2 w-80 glass rounded-xl shadow-xl z-50 overflow-hidden animate-in slide-in-from-top-2">
                        <div className="p-3 border-b border-border/50 flex items-center justify-between">
                            <span className="font-semibold">Notifications</span>
                            {notifications.length > 0 && (
                                <Button 
                                    variant="ghost" 
                                    size="sm" 
                                    className="text-xs text-muted-foreground"
                                    onClick={onClearAll}
                                >
                                    Clear All
                                </Button>
                            )}
                        </div>
                        
                        <div className="max-h-80 overflow-y-auto">
                            {notifications.length === 0 ? (
                                <div className="p-6 text-center text-muted-foreground">
                                    <Bell className="h-8 w-8 mx-auto mb-2 opacity-50" />
                                    <p className="text-sm">No notifications</p>
                                </div>
                            ) : (
                                <div className="p-2 space-y-2">
                                    {notifications.map((notif) => (
                                        <div
                                            key={notif.id}
                                            className={`p-3 rounded-lg border ${getBgColor(notif.type)} ${!notif.read ? 'ring-1 ring-primary/30' : ''}`}
                                        >
                                            <div className="flex items-start gap-2">
                                                {getIcon(notif.type)}
                                                <div className="flex-1 min-w-0">
                                                    <p className="text-sm font-medium truncate">{notif.title}</p>
                                                    <p className="text-xs text-muted-foreground mt-0.5">{notif.message}</p>
                                                    <p className="text-xs text-muted-foreground mt-1">
                                                        {notif.timestamp.toLocaleTimeString()}
                                                    </p>
                                                </div>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="h-6 w-6 p-0 opacity-50 hover:opacity-100"
                                                    onClick={() => onDismiss?.(notif.id)}
                                                >
                                                    <X className="h-3 w-3" />
                                                </Button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
