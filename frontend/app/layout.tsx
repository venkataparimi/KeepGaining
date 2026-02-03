import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
    title: "KeepGaining Trading Platform",
    description: "Advanced Algorithmic Trading Dashboard",
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en">
            <body className={inter.className}>
                <div className="flex h-screen overflow-hidden">
                    <Sidebar />
                    <main className="flex-1 overflow-y-auto bg-background">
                        {children}
                    </main>
                </div>
            </body>
        </html>
    );
}
