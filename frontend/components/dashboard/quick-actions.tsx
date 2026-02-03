"use client";

import { AlertTriangle, TrendingUp, Pause, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface QuickActionsProps {
    onSquareOffAll?: () => void;
    onPauseTrading?: () => void;
    onEmergencyExit?: () => void;
    hasPositions: boolean;
    isPaused?: boolean;
}

export function QuickActions({ 
    onSquareOffAll, 
    onPauseTrading, 
    onEmergencyExit,
    hasPositions,
    isPaused = false
}: QuickActionsProps) {
    return (
        <div className="flex flex-wrap gap-2">
            <Button
                variant="outline"
                size="sm"
                className="border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/10 hover:border-yellow-500/50"
                onClick={onPauseTrading}
            >
                <Pause className="h-4 w-4 mr-2" />
                {isPaused ? 'Resume Trading' : 'Pause Trading'}
            </Button>
            
            <Button
                variant="outline"
                size="sm"
                className="border-orange-500/30 text-orange-400 hover:bg-orange-500/10 hover:border-orange-500/50"
                onClick={onSquareOffAll}
                disabled={!hasPositions}
            >
                <XCircle className="h-4 w-4 mr-2" />
                Square Off All
            </Button>
            
            <Button
                variant="outline"
                size="sm"
                className="border-red-500/30 text-red-400 hover:bg-red-500/10 hover:border-red-500/50"
                onClick={onEmergencyExit}
            >
                <AlertTriangle className="h-4 w-4 mr-2" />
                Emergency Exit
            </Button>
        </div>
    );
}
