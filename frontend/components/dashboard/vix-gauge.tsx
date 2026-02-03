"use client";

import { useState, useEffect } from "react";
import { Gauge } from "lucide-react";

interface VixGaugeProps {
    value?: number;
}

export function VixGauge({ value = 0 }: VixGaugeProps) {
    const [animatedValue, setAnimatedValue] = useState(0);

    useEffect(() => {
        const timer = setTimeout(() => setAnimatedValue(value), 100);
        return () => clearTimeout(timer);
    }, [value]);

    // VIX zones: Low (0-15), Normal (15-20), Elevated (20-25), High (25+)
    const getZone = () => {
        if (animatedValue < 13) return { label: 'Low', color: 'text-green-400', bg: 'bg-green-400' };
        if (animatedValue < 18) return { label: 'Normal', color: 'text-blue-400', bg: 'bg-blue-400' };
        if (animatedValue < 24) return { label: 'Elevated', color: 'text-yellow-400', bg: 'bg-yellow-400' };
        return { label: 'High', color: 'text-red-400', bg: 'bg-red-400' };
    };

    const zone = getZone();
    
    // Calculate rotation for the needle (0-40 VIX maps to -90 to 90 degrees)
    const rotation = Math.min(Math.max((animatedValue / 40) * 180 - 90, -90), 90);

    return (
        <div className="glass rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
                <Gauge className="h-4 w-4 text-purple-400" />
                <span className="text-sm font-medium text-muted-foreground">India VIX</span>
            </div>
            
            <div className="relative w-full h-24 flex justify-center">
                {/* Semi-circle gauge background */}
                <div className="absolute w-40 h-20 overflow-hidden">
                    <div className="w-40 h-40 rounded-full border-8 border-muted relative">
                        {/* Zone colors */}
                        <div className="absolute inset-0 rounded-full overflow-hidden">
                            <div 
                                className="absolute w-full h-full"
                                style={{
                                    background: `conic-gradient(
                                        from 180deg,
                                        #22c55e 0deg 67.5deg,
                                        #3b82f6 67.5deg 112.5deg,
                                        #eab308 112.5deg 157.5deg,
                                        #ef4444 157.5deg 180deg,
                                        transparent 180deg 360deg
                                    )`
                                }}
                            />
                        </div>
                    </div>
                </div>
                
                {/* Needle */}
                <div 
                    className="absolute bottom-0 w-1 h-16 origin-bottom transition-transform duration-1000 ease-out"
                    style={{ transform: `rotate(${rotation}deg)` }}
                >
                    <div className={`w-1 h-full ${zone.bg} rounded-full shadow-lg`} />
                    <div className={`absolute -bottom-1 -left-1 w-3 h-3 ${zone.bg} rounded-full`} />
                </div>
                
                {/* Center cover */}
                <div className="absolute bottom-0 w-6 h-6 bg-background rounded-full border-2 border-muted" />
            </div>
            
            {/* Value display */}
            <div className="text-center mt-2">
                <div className={`text-2xl font-bold ${zone.color}`}>
                    {animatedValue.toFixed(2)}
                </div>
                <div className={`text-xs font-medium ${zone.color}`}>
                    {zone.label} Volatility
                </div>
            </div>
            
            {/* Zone legend */}
            <div className="flex justify-between mt-3 text-xs text-muted-foreground">
                <span>0</span>
                <span className="text-green-400">Low</span>
                <span className="text-blue-400">Normal</span>
                <span className="text-yellow-400">High</span>
                <span>40</span>
            </div>
        </div>
    );
}
