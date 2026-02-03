"use client"

import * as React from "react"

interface TooltipProviderProps {
    children: React.ReactNode
    delayDuration?: number
}

const TooltipContext = React.createContext<{
    delayDuration: number
}>({ delayDuration: 200 })

function TooltipProvider({ children, delayDuration = 200 }: TooltipProviderProps) {
    return (
        <TooltipContext.Provider value={{ delayDuration }}>
            {children}
        </TooltipContext.Provider>
    )
}

interface TooltipProps {
    children: React.ReactNode
    open?: boolean
    defaultOpen?: boolean
    onOpenChange?: (open: boolean) => void
}

function Tooltip({ children }: TooltipProps) {
    const [isOpen, setIsOpen] = React.useState(false)
    
    return (
        <div 
            className="relative inline-block"
            onMouseEnter={() => setIsOpen(true)}
            onMouseLeave={() => setIsOpen(false)}
        >
            {React.Children.map(children, child => {
                if (React.isValidElement(child)) {
                    if (child.type === TooltipTrigger) {
                        return child
                    }
                    if (child.type === TooltipContent) {
                        return isOpen ? child : null
                    }
                }
                return child
            })}
        </div>
    )
}

interface TooltipTriggerProps {
    children: React.ReactNode
    asChild?: boolean
    className?: string
}

function TooltipTrigger({ children, asChild, className = "" }: TooltipTriggerProps) {
    if (asChild && React.isValidElement(children)) {
        return children
    }
    return <span className={className}>{children}</span>
}

interface TooltipContentProps {
    children: React.ReactNode
    className?: string
    side?: "top" | "right" | "bottom" | "left"
    sideOffset?: number
}

function TooltipContent({ 
    children, 
    className = "",
    side = "top",
}: TooltipContentProps) {
    const positionClasses = {
        top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
        bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
        left: "right-full top-1/2 -translate-y-1/2 mr-2",
        right: "left-full top-1/2 -translate-y-1/2 ml-2",
    }

    return (
        <div
            role="tooltip"
            className={`absolute z-50 overflow-hidden rounded-md border bg-popover px-3 py-1.5 text-sm text-popover-foreground shadow-md animate-in fade-in-0 zoom-in-95 ${positionClasses[side]} ${className}`}
        >
            {children}
        </div>
    )
}

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider }
