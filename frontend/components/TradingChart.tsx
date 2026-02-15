"use client";

import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries, HistogramSeries, LineSeries } from 'lightweight-charts';

interface ChartData {
    time: number; // Unix timestamp
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
    [key: string]: any; // For indicators
}

interface TradingChartProps {
    data: ChartData[];
    colors?: {
        backgroundColor?: string;
        lineColor?: string;
        textColor?: string;
        areaTopColor?: string;
        areaBottomColor?: string;
    };
    indicators?: string[];
    chartLabel?: string;
}

export const TradingChart: React.FC<TradingChartProps> = ({
    data,
    colors = {},
    indicators = [],
    chartLabel
}) => {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
    const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
    const indicatorSeriesRefs = useRef<{ [key: string]: ISeriesApi<"Line"> }>({});

    const {
        backgroundColor = '#131722',
        lineColor = '#2962FF',
        textColor = '#d1d4dc',
        areaTopColor = '#2962FF',
        areaBottomColor = 'rgba(41, 98, 255, 0.28)',
    } = colors;

    useEffect(() => {
        if (!chartContainerRef.current) return;

        const handleResize = () => {
            if (chartRef.current && chartContainerRef.current) {
                chartRef.current.applyOptions({
                    width: chartContainerRef.current.clientWidth,
                    height: chartContainerRef.current.clientHeight
                });
            }
        };

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: backgroundColor },
                textColor,
            },
            width: chartContainerRef.current.clientWidth,
            height: chartContainerRef.current.clientHeight,
            grid: {
                vertLines: { color: 'rgba(42, 46, 57, 0.5)' },
                horzLines: { color: 'rgba(42, 46, 57, 0.5)' },
            },
            rightPriceScale: {
                borderColor: 'rgba(197, 203, 206, 0.3)',
            },
            timeScale: {
                borderColor: 'rgba(197, 203, 206, 0.3)',
                timeVisible: true,
                secondsVisible: false,
            },
            crosshair: {
                mode: 1, // CrosshairMode.Normal
                vertLine: {
                    width: 1,
                    color: 'rgba(224, 227, 235, 0.1)',
                    style: 0,
                },
                horzLine: {
                    width: 1,
                    color: 'rgba(224, 227, 235, 0.1)',
                    style: 0,
                },
            },
        });

        chartRef.current = chart;

        // Candlestick Series
        const candlestickSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#089981',
            downColor: '#f23645',
            borderVisible: false,
            wickUpColor: '#089981',
            wickDownColor: '#f23645',
        });
        candlestickSeriesRef.current = candlestickSeries;

        // Volume Series (Overlay)
        const volumeSeries = chart.addSeries(HistogramSeries, {
            color: '#26a69a',
            priceFormat: {
                type: 'volume',
            },
            priceScaleId: '', // Overlay
        });
        volumeSeries.priceScale().applyOptions({
            scaleMargins: {
                top: 0.8, // Highest volume bar is 80% from top (at bottom 20%)
                bottom: 0,
            },
        });
        volumeSeriesRef.current = volumeSeries;

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
        };
    }, [backgroundColor, textColor]);

    useEffect(() => {
        if (candlestickSeriesRef.current && data.length > 0) {
            // Sort data by time
            const sortedData = [...data].sort((a, b) => a.time - b.time);

            const candleData = sortedData.map(d => ({
                time: d.time as Time,
                open: d.open,
                high: d.high,
                low: d.low,
                close: d.close,
            }));
            candlestickSeriesRef.current.setData(candleData);

            if (volumeSeriesRef.current) {
                const volumeData = sortedData.filter(d => d.volume !== undefined).map(d => ({
                    time: d.time as Time,
                    value: d.volume!,
                    color: d.close >= d.open ? 'rgba(8, 153, 129, 0.5)' : 'rgba(242, 54, 69, 0.5)'
                }));
                volumeSeriesRef.current.setData(volumeData);
            }

            // Handle Indicators
            if (chartRef.current) {
                const firstRow = sortedData[sortedData.length - 1];
                const dataKeys = firstRow ? Object.keys(firstRow) : [];
                const currentKeys = dataKeys.filter(k => !['time', 'open', 'high', 'low', 'close', 'volume'].includes(k));

                // 1. Add/Update Series
                currentKeys.forEach(key => {
                    let series = indicatorSeriesRefs.current[key];
                    if (!series) {
                        let color = '#2962FF';
                        if (key.match(/SMA/i)) color = '#FFA500'; // Orange
                        if (key.match(/EMA/i)) color = '#00CED1'; // Turquoise
                        if (key.match(/RSI/i)) color = '#8A2BE2'; // Violet

                        // For RSI, putting it on 'left' scale
                        const priceScaleId = key.match(/RSI/i) ? 'left' : undefined;

                        series = chartRef.current!.addSeries(LineSeries, {
                            color: color,
                            lineWidth: 2,
                            priceScaleId: priceScaleId,
                        });
                        indicatorSeriesRefs.current[key] = series;
                    }

                    const lineData = sortedData
                        .filter(d => d[key] !== undefined && d[key] !== null)
                        .map(d => ({
                            time: d.time as Time,
                            value: d[key]
                        }));

                    series.setData(lineData);
                });

                // 2. Remove Old Series
                Object.keys(indicatorSeriesRefs.current).forEach(key => {
                    if (!currentKeys.includes(key)) {
                        const series = indicatorSeriesRefs.current[key];
                        chartRef.current!.removeSeries(series);
                        delete indicatorSeriesRefs.current[key];
                    }
                });

                // Configure Left Scale if RSI exists
                if (currentKeys.some(k => k.match(/RSI/i))) {
                    chartRef.current.applyOptions({
                        leftPriceScale: {
                            visible: true,
                            borderColor: 'rgba(197, 203, 206, 0.3)',
                        },
                        rightPriceScale: {
                            visible: true,
                        }
                    });
                } else {
                    chartRef.current.applyOptions({
                        leftPriceScale: {
                            visible: false,
                        }
                    });
                }
            }
        }
    }, [data, indicators]);

    return (
        <div ref={chartContainerRef} className="w-full h-full relative">
            {chartLabel && (
                <div className="absolute top-4 left-4 z-10 bg-[#1e222d] bg-opacity-80 p-2 rounded text-sm text-white font-mono border border-[#2a2e39]">
                    {chartLabel}
                    {data.length > 0 && (
                        <span className="block text-xs text-gray-400">
                            Last: {new Date(data[data.length - 1].time * 1000).toLocaleString()}
                        </span>
                    )}
                </div>
            )}
        </div>
    );
};
