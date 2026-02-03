"use client"

import * as React from "react"

const TabsContext = React.createContext<{
    value: string
    onValueChange: (value: string) => void
} | null>(null)

interface TabsProps {
    value?: string
    defaultValue?: string
    onValueChange?: (value: string) => void
    children: React.ReactNode
    className?: string
}

function Tabs({
    value,
    defaultValue,
    onValueChange,
    children,
    className = "",
}: TabsProps) {
    const [internalValue, setInternalValue] = React.useState(defaultValue || "")
    
    const currentValue = value !== undefined ? value : internalValue
    const handleValueChange = React.useCallback((newValue: string) => {
        if (value === undefined) {
            setInternalValue(newValue)
        }
        onValueChange?.(newValue)
    }, [value, onValueChange])

    return (
        <TabsContext.Provider value={{ value: currentValue, onValueChange: handleValueChange }}>
            <div className={className}>{children}</div>
        </TabsContext.Provider>
    )
}

interface TabsListProps {
    children: React.ReactNode
    className?: string
}

function TabsList({ children, className = "" }: TabsListProps) {
    return (
        <div
            role="tablist"
            className={`inline-flex h-10 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground ${className}`}
        >
            {children}
        </div>
    )
}

interface TabsTriggerProps {
    value: string
    children: React.ReactNode
    className?: string
    disabled?: boolean
}

function TabsTrigger({ value, children, className = "", disabled = false }: TabsTriggerProps) {
    const context = React.useContext(TabsContext)
    if (!context) throw new Error("TabsTrigger must be used within Tabs")
    
    const isSelected = context.value === value

    return (
        <button
            role="tab"
            type="button"
            aria-selected={isSelected}
            disabled={disabled}
            data-state={isSelected ? "active" : "inactive"}
            onClick={() => context.onValueChange(value)}
            className={`inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm ${className}`}
        >
            {children}
        </button>
    )
}

interface TabsContentProps {
    value: string
    children: React.ReactNode
    className?: string
}

function TabsContent({ value, children, className = "" }: TabsContentProps) {
    const context = React.useContext(TabsContext)
    if (!context) throw new Error("TabsContent must be used within Tabs")
    
    if (context.value !== value) return null

    return (
        <div
            role="tabpanel"
            data-state={context.value === value ? "active" : "inactive"}
            className={`mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${className}`}
        >
            {children}
        </div>
    )
}

export { Tabs, TabsList, TabsTrigger, TabsContent }
