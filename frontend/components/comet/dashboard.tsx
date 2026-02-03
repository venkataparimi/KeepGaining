"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, TrendingDown, Radio, Newspaper, MessageSquare, Users, ThumbsUp, Eye } from "lucide-react";

const sentimentData = {
    overallScore: 0.65,
    trend: "BULLISH",
    bullishPercent: 68,
    bearishPercent: 32,
    socialMentions: 12450,
    newsArticles: 234,
};

const newsItems = [
    {
        id: 1,
        title: "Tech stocks rally on AI breakthroughs",
        source: "Bloomberg",
        sentiment: 0.8,
        time: "2h ago",
        views: 15200,
        likes: 342
    },
    {
        id: 2,
        title: "Federal Reserve signals potential rate cuts",
        source: "Reuters",
        sentiment: 0.5,
        time: "4h ago",
        views: 23100,
        likes: 567
    },
    {
        id: 3,
        title: "Oil prices decline on demand concerns",
        source: "CNBC",
        sentiment: -0.2,
        time: "5h ago",
        views: 8900,
        likes: 123
    },
    {
        id: 4,
        title: "Nifty50 reaches all-time high",
        source: "MoneyControl",
        sentiment: 0.9,
        time: "7h ago",
        views: 31200,
        likes: 892
    },
];

const trendingTopics = [
    { tag: "#TechStocks", count: 3245, sentiment: 0.75 },
    { tag: "#FedPolicy", count: 2134, sentiment: 0.45 },
    { tag: "#Nifty50", count: 1876, sentiment: 0.82 },
    { tag: "#CrudeOil", count: 1234, sentiment: -0.15 },
];

export function SentimentDashboard() {
    return (
        <div className="flex-1 space-y-6 p-8 pt-6 max-w-[1600px] mx-auto">
            {/* Header */}
            <div className="relative overflow-hidden rounded-2xl glass p-8">
                <div className="absolute inset-0 gradient-bg opacity-30"></div>
                <div className="relative z-10">
                    <div className="flex items-center space-x-3 mb-2">
                        <Radio className="h-10 w-10 text-primary" />
                        <h1 className="text-4xl font-bold gradient-text">Comet</h1>
                    </div>
                    <p className="text-muted-foreground">Real-time market sentiment & social intelligence</p>
                </div>
            </div>

            {/* Metrics */}
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
                <div className="glass rounded-2xl overflow-hidden hover-lift">
                    <CardHeader className="bg-gradient-to-br from-green-500/10 to-emerald-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Overall Sentiment</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <div className="text-4xl font-bold text-green-400">{sentimentData.overallScore}</div>
                                <p className="text-sm text-muted-foreground mt-1">{sentimentData.trend}</p>
                            </div>
                            <TrendingUp className="h-12 w-12 text-green-400 opacity-50" />
                        </div>
                    </CardContent>
                </div>

                <div className="glass rounded-2xl overflow-hidden hover-lift">
                    <CardHeader className="bg-gradient-to-br from-blue-500/10 to-cyan-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Bull/Bear Ratio</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="space-y-3">
                            <div className="flex justify-between text-sm">
                                <span className="text-green-400">Bullish: {sentimentData.bullishPercent}%</span>
                                <span className="text-red-400">Bearish: {sentimentData.bearishPercent}%</span>
                            </div>
                            <div className="h-3 bg-muted rounded-full overflow-hidden flex">
                                <div
                                    className="bg-gradient-to-r from-green-400 to-emerald-400"
                                    style={{ width: `${sentimentData.bullishPercent}%` }}
                                ></div>
                                <div
                                    className="bg-gradient-to-r from-red-400 to-rose-400"
                                    style={{ width: `${sentimentData.bearishPercent}%` }}
                                ></div>
                            </div>
                        </div>
                    </CardContent>
                </div>

                <div className="glass rounded-2xl overflow-hidden hover-lift">
                    <CardHeader className="bg-gradient-to-br from-purple-500/10 to-pink-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Social Mentions</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="flex items-center justify-between">
                            <div className="text-3xl font-bold gradient-text">{sentimentData.socialMentions.toLocaleString()}</div>
                            <MessageSquare className="h-10 w-10 text-purple-400 opacity-50" />
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">Last 24 hours</p>
                    </CardContent>
                </div>

                <div className="glass rounded-2xl overflow-hidden hover-lift">
                    <CardHeader className="bg-gradient-to-br from-orange-500/10 to-amber-500/10">
                        <CardTitle className="text-sm font-medium text-muted-foreground">News Articles</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                        <div className="flex items-center justify-between">
                            <div className="text-3xl font-bold text-orange-400">{sentimentData.newsArticles}</div>
                            <Newspaper className="h-10 w-10 text-orange-400 opacity-50" />
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">Analyzed today</p>
                    </CardContent>
                </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-3">
                {/* News Feed */}
                <div className="lg:col-span-2 glass rounded-2xl overflow-hidden">
                    <CardHeader className="bg-gradient-to-r from-primary/10 to-secondary/10">
                        <CardTitle className="text-xl font-bold flex items-center">
                            <Newspaper className="h-5 w-5 mr-2" />
                            Latest Market News
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                        <div className="divide-y divide-border/50">
                            {newsItems.map((news) => (
                                <div key={news.id} className="p-4 hover:bg-primary/5 smooth-transition">
                                    <div className="flex items-start justify-between">
                                        <div className="flex-1">
                                            <h3 className="font-semibold text-foreground mb-1">{news.title}</h3>
                                            <div className="flex items-center space-x-4 text-xs text-muted-foreground">
                                                <span className="font-medium text-primary">{news.source}</span>
                                                <span>{news.time}</span>
                                                <span className="flex items-center">
                                                    <Eye className="h-3 w-3 mr-1" />
                                                    {news.views.toLocaleString()}
                                                </span>
                                                <span className="flex items-center">
                                                    <ThumbsUp className="h-3 w-3 mr-1" />
                                                    {news.likes}
                                                </span>
                                            </div>
                                        </div>
                                        <div className={`ml-4 px-3 py-1 rounded-full text-sm font-semibold ${news.sentiment > 0.3
                                                ? 'bg-green-500/20 text-green-400'
                                                : news.sentiment < -0.3
                                                    ? 'bg-red-500/20 text-red-400'
                                                    : 'bg-muted text-muted-foreground'
                                            }`}>
                                            {news.sentiment > 0 ? '+' : ''}{news.sentiment}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </div>

                {/* Trending Topics */}
                <div className="glass rounded-2xl overflow-hidden">
                    <CardHeader className="bg-gradient-to-r from-accent/10 to-primary/10">
                        <CardTitle className="text-xl font-bold flex items-center">
                            <TrendingUp className="h-5 w-5 mr-2" />
                            Trending Topics
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="pt-6">
                        <div className="space-y-4">
                            {trendingTopics.map((topic, idx) => (
                                <div key={idx} className="p-3 rounded-lg bg-primary/5 hover:bg-primary/10 smooth-transition">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="font-semibold text-primary">{topic.tag}</span>
                                        <span className={`text-sm font-semibold ${topic.sentiment > 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            {topic.sentiment > 0 ? '+' : ''}{topic.sentiment}
                                        </span>
                                    </div>
                                    <div className="flex items-center text-xs text-muted-foreground">
                                        <Users className="h-3 w-3 mr-1" />
                                        {topic.count.toLocaleString()} mentions
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </div>
            </div>
        </div>
    );
}
