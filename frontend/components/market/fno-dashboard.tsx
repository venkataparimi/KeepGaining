import React, { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api/client';

interface FnoStock {
    symbol: string;
    price: number;
    change_percent: number;
    oi_change_percent: number;
    volume_shock: boolean;
    buildup: string;
}

interface FnoData {
    top_gainers: FnoStock[];
    top_losers: FnoStock[];
    oi_gainers: FnoStock[];
    oi_losers: FnoStock[];
    volume_shockers: FnoStock[];
}

export const FnoDashboard: React.FC = () => {
    const [data, setData] = useState<FnoData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const result = await apiClient.getFnoMovers();
                setData(result);
            } catch (error) {
                console.error("Failed to fetch F&O data", error);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 30000); // Refresh every 30s
        return () => clearInterval(interval);
    }, []);

    if (loading) return <div className="p-4 text-center text-gray-500">Loading F&O Analytics...</div>;
    if (!data) return null;

    const Widget = ({ title, stocks, type }: { title: string, stocks: FnoStock[], type: 'price' | 'oi' }) => (
        <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-100">
            <h3 className="font-semibold text-gray-800 mb-3 border-b pb-2">{title}</h3>
            <div className="space-y-2">
                {stocks.map((stock) => (
                    <div key={stock.symbol} className="flex justify-between items-center text-sm">
                        <div>
                            <div className="font-medium text-gray-900">{stock.symbol}</div>
                            <div className="text-xs text-gray-500">₹{stock.price.toLocaleString()}</div>
                        </div>
                        <div className="text-right">
                            <div className={`font-bold ${stock.change_percent >= 0 ? 'text-green-600' : 'text-red-600'
                                }`}>
                                {stock.change_percent > 0 ? '+' : ''}{stock.change_percent}%
                            </div>
                            <div className="text-xs text-gray-500">
                                OI: {stock.oi_change_percent > 0 ? '+' : ''}{stock.oi_change_percent}%
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );

    return (
        <div className="space-y-6">
            <h2 className="text-xl font-bold text-gray-800">F&O Market Pulse</h2>

            {/* Price Movers */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                <Widget title="Top Gainers" stocks={data.top_gainers} type="price" />
                <Widget title="Top Losers" stocks={data.top_losers} type="price" />
                <Widget title="Volume Shockers" stocks={data.volume_shockers} type="price" />
            </div>

            {/* OI Analysis */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-100">
                    <h3 className="font-semibold text-gray-800 mb-3 border-b pb-2">Long Buildup (Price ↑ OI ↑)</h3>
                    <div className="space-y-2">
                        {data.oi_gainers.filter(s => s.change_percent > 0).slice(0, 5).map(stock => (
                            <div key={stock.symbol} className="flex justify-between items-center text-sm">
                                <span className="font-medium">{stock.symbol}</span>
                                <span className="text-green-600 font-bold">+{stock.oi_change_percent}% OI</span>
                            </div>
                        ))}
                    </div>
                </div>
                <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-100">
                    <h3 className="font-semibold text-gray-800 mb-3 border-b pb-2">Short Covering (Price ↑ OI ↓)</h3>
                    <div className="space-y-2">
                        {data.oi_losers.filter(s => s.change_percent > 0).slice(0, 5).map(stock => (
                            <div key={stock.symbol} className="flex justify-between items-center text-sm">
                                <span className="font-medium">{stock.symbol}</span>
                                <span className="text-orange-600 font-bold">{stock.oi_change_percent}% OI</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
};
