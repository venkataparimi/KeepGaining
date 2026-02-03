"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { 
    MessageSquare, 
    TrendingUp, 
    TrendingDown, 
    Minus,
    RefreshCw,
    Newspaper,
    Twitter,
    Hash,
    Globe,
    AlertCircle,
    ArrowUp,
    ArrowDown
} from "lucide-react";
import { apiClient, SentimentData, SentimentSource } from "@/lib/api/client";

interface SentimentTrend {
    date: string;
    sentiment: number;
    volume: number;
}

export function SentimentPanel() {
    const [sentiment, setSentiment] = useState<SentimentData | null>(null);
    const [sources, setSources] = useState<SentimentSource[]>([]);
    const [trend, setTrend] = useState<SentimentTrend[]>([]);
    const [selectedSymbol, setSelectedSymbol] = useState<string>("NIFTY");
    const [loading, setLoading] = useState(false);

    const symbols = ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN"];

    useEffect(() => {
        if (selectedSymbol) {
            loadSentimentData();
        }
    }, [selectedSymbol]);

    const loadSentimentData = async () => {
        setLoading(true);
        try {
            const [sentimentData, sourcesData, trendData] = await Promise.all([
                apiClient.getSentiment(selectedSymbol),
                apiClient.getSentimentSources(selectedSymbol),
                apiClient.getSentimentTrend(selectedSymbol, 7),
            ]);
            setSentiment(sentimentData);
            setSources(sourcesData);
            setTrend(trendData.trend);
        } catch (error) {
            console.error("Failed to load sentiment data:", error);
        } finally {
            setLoading(false);
        }
    };

    const getSentimentColor = (value: number) => {
        if (value >= 0.6) return "text-green-500";
        if (value >= 0.4) return "text-yellow-500";
        if (value >= 0.2) return "text-orange-500";
        return "text-red-500";
    };

    const getSentimentBgColor = (value: number) => {
        if (value >= 0.6) return "bg-green-100 dark:bg-green-900/30";
        if (value >= 0.4) return "bg-yellow-100 dark:bg-yellow-900/30";
        if (value >= 0.2) return "bg-orange-100 dark:bg-orange-900/30";
        return "bg-red-100 dark:bg-red-900/30";
    };

    const getSentimentIcon = (label: string) => {
        switch (label) {
            case "very_bullish":
            case "bullish":
                return <TrendingUp className="h-5 w-5 text-green-500" />;
            case "very_bearish":
            case "bearish":
                return <TrendingDown className="h-5 w-5 text-red-500" />;
            default:
                return <Minus className="h-5 w-5 text-yellow-500" />;
        }
    };

    const getSourceIcon = (source: string) => {
        switch (source.toLowerCase()) {
            case "news":
                return <Newspaper className="h-4 w-4" />;
            case "twitter":
                return <Twitter className="h-4 w-4" />;
            case "reddit":
                return <Hash className="h-4 w-4" />;
            default:
                return <Globe className="h-4 w-4" />;
        }
    };

    const formatSentimentLabel = (label: string) => {
        return label.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold flex items-center gap-2">
                        <MessageSquare className="h-6 w-6 text-blue-500" />
                        Sentiment Analysis
                    </h2>
                    <p className="text-muted-foreground">
                        Market sentiment from news, social media, and financial data
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Select value={selectedSymbol} onValueChange={setSelectedSymbol}>
                        <SelectTrigger className="w-[150px]">
                            <SelectValue placeholder="Select symbol" />
                        </SelectTrigger>
                        <SelectContent>
                            {symbols.map((s) => (
                                <SelectItem key={s} value={s}>{s}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <Button variant="outline" onClick={loadSentimentData} disabled={loading}>
                        <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    </Button>
                </div>
            </div>

            {sentiment && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* Overall Sentiment Card */}
                    <Card className={getSentimentBgColor(sentiment.overall_sentiment)}>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm font-medium">Overall Sentiment</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="flex items-center justify-between">
                                <div>
                                    <div className={`text-3xl font-bold ${getSentimentColor(sentiment.overall_sentiment)}`}>
                                        {(sentiment.overall_sentiment * 100).toFixed(0)}%
                                    </div>
                                    <div className="flex items-center gap-2 mt-1">
                                        {getSentimentIcon(sentiment.sentiment_label)}
                                        <span className="text-sm font-medium">
                                            {formatSentimentLabel(sentiment.sentiment_label)}
                                        </span>
                                    </div>
                                </div>
                                <div className={`flex items-center gap-1 text-sm ${
                                    sentiment.sentiment_change_24h >= 0 ? 'text-green-500' : 'text-red-500'
                                }`}>
                                    {sentiment.sentiment_change_24h >= 0 ? (
                                        <ArrowUp className="h-4 w-4" />
                                    ) : (
                                        <ArrowDown className="h-4 w-4" />
                                    )}
                                    {Math.abs(sentiment.sentiment_change_24h * 100).toFixed(1)}%
                                    <span className="text-muted-foreground text-xs">24h</span>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* News Sentiment Card */}
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm font-medium flex items-center gap-2">
                                <Newspaper className="h-4 w-4" />
                                News Sentiment
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className={`text-2xl font-bold ${getSentimentColor(sentiment.news_sentiment)}`}>
                                {(sentiment.news_sentiment * 100).toFixed(0)}%
                            </div>
                            <div className="text-sm text-muted-foreground mt-1">
                                {sentiment.news_count} articles analyzed
                            </div>
                            <Progress 
                                value={sentiment.news_sentiment * 100} 
                                className="h-2 mt-2" 
                            />
                        </CardContent>
                    </Card>

                    {/* Social Sentiment Card */}
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm font-medium flex items-center gap-2">
                                <Twitter className="h-4 w-4" />
                                Social Sentiment
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className={`text-2xl font-bold ${getSentimentColor(sentiment.social_sentiment)}`}>
                                {(sentiment.social_sentiment * 100).toFixed(0)}%
                            </div>
                            <div className="text-sm text-muted-foreground mt-1">
                                {sentiment.social_mentions.toLocaleString()} mentions
                            </div>
                            <Progress 
                                value={sentiment.social_sentiment * 100} 
                                className="h-2 mt-2" 
                            />
                        </CardContent>
                    </Card>
                </div>
            )}

            <Tabs defaultValue="sources" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="sources">Sources</TabsTrigger>
                    <TabsTrigger value="trend">Trend</TabsTrigger>
                    <TabsTrigger value="topics">Trending Topics</TabsTrigger>
                </TabsList>

                <TabsContent value="sources">
                    <Card>
                        <CardHeader>
                            <CardTitle>Sentiment by Source</CardTitle>
                            <CardDescription>
                                Breakdown of sentiment from different data sources
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            {sources.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground">
                                    <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-20" />
                                    <p>No source data available</p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    {sources.map((source) => (
                                        <div
                                            key={source.source}
                                            className="p-4 border rounded-lg space-y-3"
                                        >
                                            <div className="flex items-center justify-between">
                                                <div className="flex items-center gap-2">
                                                    {getSourceIcon(source.source)}
                                                    <span className="font-medium capitalize">{source.source}</span>
                                                    <Badge variant="secondary" className="text-xs">
                                                        {source.volume} items
                                                    </Badge>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <span className={`text-lg font-semibold ${getSentimentColor(source.sentiment)}`}>
                                                        {(source.sentiment * 100).toFixed(0)}%
                                                    </span>
                                                    <Badge variant="outline" className="text-xs">
                                                        {(source.confidence * 100).toFixed(0)}% conf
                                                    </Badge>
                                                </div>
                                            </div>
                                            <Progress value={source.sentiment * 100} className="h-2" />
                                            
                                            {source.headlines.length > 0 && (
                                                <div className="pt-2 border-t">
                                                    <div className="text-xs text-muted-foreground mb-2">Recent Headlines</div>
                                                    <div className="space-y-1">
                                                        {source.headlines.slice(0, 3).map((headline, idx) => (
                                                            <div key={idx} className="text-sm truncate">
                                                                • {headline}
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="trend">
                    <Card>
                        <CardHeader>
                            <CardTitle>Sentiment Trend (7 Days)</CardTitle>
                            <CardDescription>
                                How sentiment has changed over the past week
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            {trend.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground">
                                    <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-20" />
                                    <p>No trend data available</p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    {/* Simple bar chart representation */}
                                    <div className="flex items-end justify-between h-32 gap-2">
                                        {trend.map((day, idx) => (
                                            <div 
                                                key={idx} 
                                                className="flex-1 flex flex-col items-center gap-1"
                                            >
                                                <div 
                                                    className={`w-full rounded-t ${getSentimentBgColor(day.sentiment)}`}
                                                    style={{ height: `${day.sentiment * 100}%` }}
                                                />
                                                <span className="text-xs text-muted-foreground">
                                                    {new Date(day.date).toLocaleDateString('en-US', { weekday: 'short' })}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                    
                                    {/* Trend details */}
                                    <div className="grid grid-cols-7 gap-2 pt-4 border-t">
                                        {trend.map((day, idx) => (
                                            <div key={idx} className="text-center">
                                                <div className={`text-sm font-semibold ${getSentimentColor(day.sentiment)}`}>
                                                    {(day.sentiment * 100).toFixed(0)}%
                                                </div>
                                                <div className="text-xs text-muted-foreground">
                                                    {day.volume} mentions
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="topics">
                    <Card>
                        <CardHeader>
                            <CardTitle>Trending Topics</CardTitle>
                            <CardDescription>
                                Most discussed topics related to {selectedSymbol}
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            {sentiment?.trending_topics && sentiment.trending_topics.length > 0 ? (
                                <div className="flex flex-wrap gap-2">
                                    {sentiment.trending_topics.map((topic, idx) => (
                                        <Badge 
                                            key={idx} 
                                            variant={idx < 3 ? "default" : "secondary"}
                                            className="text-sm py-1 px-3"
                                        >
                                            <Hash className="h-3 w-3 mr-1" />
                                            {topic}
                                        </Badge>
                                    ))}
                                </div>
                            ) : (
                                <div className="text-center py-8 text-muted-foreground">
                                    <Hash className="h-12 w-12 mx-auto mb-4 opacity-20" />
                                    <p>No trending topics found</p>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}
