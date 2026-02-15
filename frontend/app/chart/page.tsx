"use client";

import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { TradingChart } from '@/components/TradingChart';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";

const ChartPage = () => {
    const [symbol, setSymbol] = useState("");
    const [instrumentType, setInstrumentType] = useState("INDEX");
    const [timeFrame, setTimeFrame] = useState("1d");
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(false);

    const [dateRange, setDateRange] = useState("1Y");

    // Cascading State
    const [availableSymbols, setAvailableSymbols] = useState<string[]>([]);
    const [availableExpiries, setAvailableExpiries] = useState<string[]>([]);
    const [availableOptions, setAvailableOptions] = useState<any[]>([]);

    const [selectedExpiry, setSelectedExpiry] = useState<string>("");
    const [selectedOption, setSelectedOption] = useState<string>(""); // Holds the trading_symbol of the option
    const [selectedIndicators, setSelectedIndicators] = useState<string[]>([]);

    // Fetch Symbols when Type changes
    useEffect(() => {
        const fetchSymbols = async () => {
            try {
                const response = await axios.get('http://localhost:8001/api/master/symbols', {
                    params: { instrument_type: instrumentType }
                });
                setAvailableSymbols(response.data);
                setSymbol(""); // Reset symbol
                setAvailableExpiries([]);
                setSelectedExpiry("");
                setAvailableOptions([]);
                setSelectedOption("");
            } catch (e) {
                console.error(e);
            }
        };
        fetchSymbols();
    }, [instrumentType]);

    // Fetch Expiries when Symbol changes (for Derivatives)
    useEffect(() => {
        if (!symbol || (instrumentType !== 'OPTION' && instrumentType !== 'FUTURE')) return;

        const fetchExpiries = async () => {
            try {
                const response = await axios.get('http://localhost:8001/api/master/expiries', {
                    params: { underlying: symbol, instrument_type: instrumentType }
                });
                setAvailableExpiries(response.data);
                setSelectedExpiry("");
                setAvailableOptions([]);
                setSelectedOption("");
            } catch (e) {
                console.error(e);
            }
        };
        fetchExpiries();
    }, [symbol, instrumentType]);

    // Fetch Option Chain when Expiry changes
    useEffect(() => {
        if (!symbol || !selectedExpiry) return;

        if (instrumentType === 'OPTION') {
            const fetchOptions = async () => {
                try {
                    const response = await axios.get('http://localhost:8001/api/master/option-chain', {
                        params: { underlying: symbol, expiry_date: selectedExpiry }
                    });
                    setAvailableOptions(response.data);
                    setSelectedOption("");
                } catch (e) {
                    console.error(e);
                }
            };
            fetchOptions();
        } else if (instrumentType === 'FUTURE') {
            // For Future, we don't need an option chain, but we need to resolve the specific contract symbol
            // We can do this here or just before fetching data. Doing it here allows us to set a "selectedOption" equivalent if we wanted,
            // but for now let's just let fetchData handle it or set a state.
            // Actually, let's set selectedOption to the future trading symbol to keep logic consistent
            const fetchFutureContract = async () => {
                try {
                    const response = await axios.get('http://localhost:8001/api/master/futures-contract', {
                        params: { underlying: symbol, expiry_date: selectedExpiry }
                    });
                    // Store the actual future symbol in selectedOption
                    setSelectedOption(response.data.trading_symbol);
                } catch (e) {
                    console.error("Error fetching future contract:", e);
                    setSelectedOption("");
                }
            };
            fetchFutureContract();
        }

    }, [selectedExpiry, symbol, instrumentType]);


    const fetchData = async () => {
        // Determine the actual trading symbol to fetch based on selection
        let querySymbol = symbol;
        if (instrumentType === 'OPTION' && selectedOption) {
            querySymbol = selectedOption;
        } else if (instrumentType === 'FUTURE' && selectedOption) {
            querySymbol = selectedOption;
        }

        if (!querySymbol) return;

        setLoading(true);
        try {
            let startDate = new Date();
            if (dateRange === "1Y") startDate.setFullYear(startDate.getFullYear() - 1);
            else if (dateRange === "3Y") startDate.setFullYear(startDate.getFullYear() - 3);
            else if (dateRange === "5Y") startDate.setFullYear(startDate.getFullYear() - 5);
            else if (dateRange === "All") startDate = new Date(0); // Epoch

            const response = await axios.get('http://localhost:8001/api/historical-data/', {
                params: {
                    symbol: querySymbol,
                    instrument_type: instrumentType,
                    time_frame: timeFrame,
                    start_date: startDate.toISOString(),
                    indicators: selectedIndicators
                },
                paramsSerializer: (params) => {
                    const searchParams = new URLSearchParams();
                    Object.keys(params).forEach(key => {
                        const value = params[key];
                        if (Array.isArray(value)) {
                            value.forEach(v => searchParams.append(key, v));
                        } else if (value !== undefined && value !== null) {
                            searchParams.append(key, value);
                        }
                    });
                    return searchParams.toString();
                }
            });
            setData(response.data);
        } catch (error) {
            console.error("Error fetching data:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        // Only fetch if we have a valid selection for the type
        if (instrumentType === 'OPTION' && !selectedOption) return;
        if (instrumentType === 'FUTURE' && !selectedOption) return; // Future now relies on selectedOption (which holds trading symbol)
        if ((instrumentType === 'EQUITY' || instrumentType === 'INDEX') && !symbol) return;

        fetchData();
    }, [symbol, instrumentType, timeFrame, dateRange, selectedOption, selectedExpiry, selectedIndicators]);

    return (
        <div className="flex flex-col h-[calc(100vh-4rem)] bg-[#131722] text-gray-100">
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#2a2e39] bg-[#1e222d]">
                <div className="flex items-center space-x-4">
                    <h1 className="text-xl font-bold text-white tracking-tight">Market Analysis</h1>

                    <div className="h-6 w-px bg-[#2a2e39]" />

                    <div className="flex items-center space-x-2">
                        {/* Type Selector First */}
                        <Select value={instrumentType} onValueChange={setInstrumentType}>
                            <SelectTrigger className="w-32 h-8 bg-[#2a2e39] border-none text-white text-sm">
                                <SelectValue placeholder="Type" />
                            </SelectTrigger>
                            <SelectContent className="bg-[#1e222d] border-[#2a2e39] text-white">
                                <SelectItem value="INDEX">Index</SelectItem>
                                <SelectItem value="EQUITY">Equity</SelectItem>
                                <SelectItem value="FUTURE">Future</SelectItem>
                                <SelectItem value="OPTION">Option</SelectItem>
                            </SelectContent>
                        </Select>

                        {/* Symbol Selector */}
                        <Select value={symbol} onValueChange={setSymbol}>
                            <SelectTrigger className="w-40 h-8 bg-[#2a2e39] border-none text-white text-sm">
                                <SelectValue placeholder="Symbol" />
                            </SelectTrigger>
                            <SelectContent className="bg-[#1e222d] border-[#2a2e39] text-white h-64">
                                {availableSymbols.map((s) => (
                                    <SelectItem key={s} value={s}>{s}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        {/* Expiry Selector (For Derivatives) */}
                        {(instrumentType === 'OPTION' || instrumentType === 'FUTURE') && (
                            <Select value={selectedExpiry} onValueChange={setSelectedExpiry}>
                                <SelectTrigger className="w-32 h-8 bg-[#2a2e39] border-none text-white text-sm">
                                    <SelectValue placeholder="Expiry" />
                                </SelectTrigger>
                                <SelectContent className="bg-[#1e222d] border-[#2a2e39] text-white">
                                    {availableExpiries.map((e) => (
                                        <SelectItem key={e} value={e}>{e}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        )}

                        {/* Option Selector */}
                        {(instrumentType === 'OPTION') && (
                            <Select value={selectedOption} onValueChange={setSelectedOption}>
                                <SelectTrigger className="w-48 h-8 bg-[#2a2e39] border-none text-white text-sm">
                                    <SelectValue placeholder="Strike / Type" />
                                </SelectTrigger>
                                <SelectContent className="bg-[#1e222d] border-[#2a2e39] text-white h-64">
                                    {availableOptions.map((o) => (
                                        <SelectItem key={o.symbol} value={o.symbol}>
                                            {o.strike_price} {o.option_type}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        )}

                        <Select value={timeFrame} onValueChange={setTimeFrame}>
                            <SelectTrigger className="w-24 h-8 bg-[#2a2e39] border-none text-white text-sm">
                                <SelectValue placeholder="TF" />
                            </SelectTrigger>
                            <SelectContent className="bg-[#1e222d] border-[#2a2e39] text-white">
                                <SelectItem value="1m">1m</SelectItem>
                                <SelectItem value="3m">3m</SelectItem>
                                <SelectItem value="5m">5m</SelectItem>
                                <SelectItem value="15m">15m</SelectItem>
                                <SelectItem value="30m">30m</SelectItem>
                                <SelectItem value="1h">1H</SelectItem>
                                <SelectItem value="1d">1D</SelectItem>
                            </SelectContent>
                        </Select>

                        <Select value={dateRange} onValueChange={setDateRange}>
                            <SelectTrigger className="w-24 h-8 bg-[#2a2e39] border-none text-white text-sm">
                                <SelectValue placeholder="Range" />
                            </SelectTrigger>
                            <SelectContent className="bg-[#1e222d] border-[#2a2e39] text-white">
                                <SelectItem value="1Y">1Y</SelectItem>
                                <SelectItem value="3Y">3Y</SelectItem>
                                <SelectItem value="5Y">5Y</SelectItem>
                                <SelectItem value="All">All</SelectItem>
                            </SelectContent>
                        </Select>

                        {/* Indicators Toggle */}
                        <div className="flex items-center space-x-1">
                            {/* Display Selected Indicators as Tags */}
                            <div className="flex space-x-1">
                                {selectedIndicators.map(ind => (
                                    <button
                                        key={ind}
                                        onClick={() => setSelectedIndicators(selectedIndicators.filter(i => i !== ind))}
                                        className="px-2 py-1 text-xs rounded bg-blue-600 text-white hover:bg-red-600 flex items-center"
                                        title="Click to remove"
                                    >
                                        {ind.replace('_', ' ').toUpperCase()}
                                        <span className="ml-1 text-[10px]">✕</span>
                                    </button>
                                ))}
                            </div>

                            {/* Simple Add Indicator Dropdown */}
                            <div className="relative group">
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="bg-[#2a2e39] text-gray-400 hover:text-white"
                                >
                                    + Ind
                                </Button>
                                <div className="absolute top-full left-0 mt-1 w-48 bg-[#1e222d] border border-[#2a2e39] rounded shadow-xl hidden group-hover:block z-50 p-2">
                                    <div className="text-xs text-gray-500 mb-2 font-bold">Quick Add</div>
                                    <div className="grid grid-cols-2 gap-1">
                                        {['SMA_20', 'SMA_50', 'SMA_200', 'EMA_20', 'EMA_50', 'EMA_200', 'RSI_14'].map(val => (
                                            <button
                                                key={val}
                                                onClick={() => {
                                                    if (!selectedIndicators.includes(val.toLowerCase())) {
                                                        setSelectedIndicators([...selectedIndicators, val.toLowerCase()]);
                                                    }
                                                }}
                                                className="px-2 py-1 text-xs text-left text-gray-300 hover:bg-[#2a2e39] rounded"
                                            >
                                                {val}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="flex items-center space-x-3">
                    <Button
                        onClick={fetchData}
                        disabled={loading}
                        variant="ghost"
                        size="sm"
                        className="text-gray-400 hover:text-white hover:bg-[#2a2e39]"
                    >
                        {loading ? "Loading..." : "Refresh Data"}
                    </Button>
                </div>
            </div>

            <div className="flex-1 relative">
                <TradingChart
                    data={data}
                    indicators={selectedIndicators}
                    chartLabel={`${symbol} ${selectedExpiry ? selectedExpiry : ''} ${selectedOption ? selectedOption : ''} (${timeFrame})`}
                />
                {data.length === 0 && !loading && (
                    <div className="absolute inset-0 flex items-center justify-center text-gray-500">
                        No market data available for {symbol}
                    </div>
                )}
            </div>
        </div>
    );
};

export default ChartPage;
