import React, { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api/client';

interface StockData {
    symbol: string;
    price: number;
    change_percent: number;
    volume: number;
    oi_change_percent: number;
    delivery_percent: number;
}

interface SectorDetailsProps {
    sectorId: string;
}

export const SectorDetails: React.FC<SectorDetailsProps> = ({ sectorId }) => {
    const [stocks, setStocks] = useState<StockData[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                const result = await apiClient.getSectorStocks(sectorId);
                setStocks(result);
            } catch (error) {
                console.error("Failed to fetch sector stocks", error);
            } finally {
                setLoading(false);
            }
        };

        if (sectorId) {
            fetchData();
        }
    }, [sectorId]);

    if (!sectorId) return <div className="text-center text-gray-400 py-8">Select a sector to view details</div>;
    if (loading) return <div className="text-center text-gray-500 py-8">Loading stocks...</div>;

    return (
        <div className="bg-white rounded-lg shadow-sm border border-gray-100 overflow-hidden mt-6">
            <div className="px-6 py-4 border-b border-gray-100 bg-gray-50">
                <h3 className="font-semibold text-gray-800">{sectorId} Constituents</h3>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                    <thead className="text-xs text-gray-500 uppercase bg-gray-50">
                        <tr>
                            <th className="px-6 py-3">Symbol</th>
                            <th className="px-6 py-3 text-right">Price</th>
                            <th className="px-6 py-3 text-right">Change %</th>
                            <th className="px-6 py-3 text-right">Volume</th>
                            <th className="px-6 py-3 text-right">OI Chg %</th>
                            <th className="px-6 py-3 text-right">Delivery %</th>
                        </tr>
                    </thead>
                    <tbody>
                        {stocks.map((stock) => (
                            <tr key={stock.symbol} className="border-b hover:bg-gray-50">
                                <td className="px-6 py-4 font-medium text-gray-900">{stock.symbol}</td>
                                <td className="px-6 py-4 text-right">₹{stock.price.toLocaleString()}</td>
                                <td className={`px-6 py-4 text-right font-medium ${stock.change_percent >= 0 ? 'text-green-600' : 'text-red-600'
                                    }`}>
                                    {stock.change_percent > 0 ? '+' : ''}{stock.change_percent}%
                                </td>
                                <td className="px-6 py-4 text-right text-gray-600">
                                    {(stock.volume / 100000).toFixed(2)}L
                                </td>
                                <td className={`px-6 py-4 text-right ${stock.oi_change_percent > 0 ? 'text-blue-600' : 'text-orange-600'
                                    }`}>
                                    {stock.oi_change_percent}%
                                </td>
                                <td className="px-6 py-4 text-right text-gray-600">
                                    {stock.delivery_percent}%
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
