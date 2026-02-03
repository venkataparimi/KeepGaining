"use client";

import React, { Suspense } from 'react';
import { Loader2 } from 'lucide-react';
import TestResultsContent from '@/components/backtest/test-results-content';

export const dynamic = 'force-dynamic';

function LoadingFallback() {
    return (
        <div className="flex items-center justify-center min-h-screen">
            <div className="text-center">
                <Loader2 className="h-12 w-12 animate-spin text-blue-600 mx-auto mb-4" />
                <p className="text-gray-600">Loading test results...</p>
            </div>
        </div>
    );
}

export default function TestResultsPage() {
    return (
        <Suspense fallback={<LoadingFallback />}>
            <TestResultsContent />
        </Suspense>
    );
}
