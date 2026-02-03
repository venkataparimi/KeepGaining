"use client";

import React from 'react';

interface CodeEditorProps {
    value: string;
    onChange: (value: string | undefined) => void;
    language?: string;
    height?: string;
    readOnly?: boolean;
}

export const CodeEditor: React.FC<CodeEditorProps> = ({
    value,
    onChange,
    language = 'python',
    height = '600px',
    readOnly = false
}) => {
    // Temporary placeholder until Monaco Editor is installed
    return (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
            <div className="bg-yellow-50 border-b border-yellow-200 px-4 py-2 text-sm text-yellow-800">
                ⚠️ Monaco Editor not installed. Run: <code className="bg-yellow-100 px-2 py-1 rounded">npm install @monaco-editor/react monaco-editor</code>
            </div>
            <textarea
                value={value}
                onChange={(e) => onChange(e.target.value)}
                readOnly={readOnly}
                className="w-full p-4 font-mono text-sm bg-gray-900 text-gray-100 focus:outline-none"
                style={{ height }}
                placeholder="// Enter your strategy code here..."
            />
        </div>
    );
};
