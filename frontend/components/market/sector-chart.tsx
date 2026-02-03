import React, { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api/client';

interface SectorData {
    sector: string;
    change_percent: number;
    volume_million: number;
    advances: number;
    declines: number;
    trend: string;
}

interface SectorChartProps {
    onSectorSelect: (sector: string) => void;
}

export const SectorChart: React.FC<SectorChartProps> = ({ onSectorSelect }) => {
    const [data, setData] = useState<SectorData[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const result = await apiClient.getSectorPerformance();
                setData(result);
            } catch (error) {
                console.error("Failed to fetch sector data", error);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 60000); // Refresh every minute
        return () => clearInterval(interval);
    }, []);

    if (loading) return <div className="p-4 text-center text-gray-500">Loading sectors...</div>;

    return (
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-100">
            <h2 className="text-lg font-semibold mb-4 text-gray-800">Sector Performance</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {data.map((sector) => (
                    <div
                        key={sector.sector}
                        onClick={() => onSectorSelect(sector.sector)}
                        className={`p-4 rounded-lg cursor-pointer transition-all hover:scale-105 ${sector.change_percent >= 0
                                ? 'bg-green-50 border border-green-100 hover:shadow-green-100'
                                : 'bg-red-50 border border-red-100 hover:shadow-red-100'
                            }`}
                    >
                        <div className="flex justify-between items-start mb-2">
                            <span className="font-medium text-gray-700 truncate" title={sector.sector}>
                                {sector.sector}
                            </span>
                            <span className={`text-sm font-bold ${sector.change_percent >= 0 ? 'text-green-600' : 'text-red-600'
                                }`}>
                                {sector.change_percent > 0 ? '+' : ''}{sector.change_percent}%
                            </span>
                        </div>

                        <div className="flex justify-between text-xs text-gray-500 mt-2">
                            <span>Vol: {sector.volume_million}M</span>
                            <span className="flex gap-1">
                                <span className="text-green-600">{sector.advances}</span>/
                                <span className="text-red-600">{sector.declines}</span>
                            </span>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};
