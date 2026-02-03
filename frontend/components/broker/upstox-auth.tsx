"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { 
    CheckCircle, 
    XCircle, 
    Loader2, 
    Eye, 
    EyeOff, 
    RefreshCw,
    ExternalLink,
    Copy,
    Smartphone,
    Key,
    Shield,
    Zap
} from "lucide-react";
import { apiClient } from "@/lib/api/client";

interface UpstoxAuthProps {
    onAuthSuccess?: () => void;
}

interface AuthStatus {
    authenticated: boolean;
    user_id?: string;
    email?: string;
    broker?: string;
    exchanges?: string[];
    products?: string[];
    message: string;
}

interface AutomatedStatus {
    playwright_available: boolean;
    browser_installed: boolean;
    credentials_configured: boolean;
    message: string;
}

type AuthMethod = 'automated' | 'manual' | 'code';

export function UpstoxAuth({ onAuthSuccess }: UpstoxAuthProps) {
    // Auth status
    const [status, setStatus] = useState<AuthStatus | null>(null);
    const [automatedStatus, setAutomatedStatus] = useState<AutomatedStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [authInProgress, setAuthInProgress] = useState(false);
    
    // Form state
    const [authMethod, setAuthMethod] = useState<AuthMethod>('automated');
    const [mobileOrEmail, setMobileOrEmail] = useState('');
    const [pin, setPin] = useState('');
    const [totpSecret, setTotpSecret] = useState('');
    const [authCode, setAuthCode] = useState('');
    const [showPin, setShowPin] = useState(false);
    const [showTotp, setShowTotp] = useState(false);
    const [headless, setHeadless] = useState(true);
    
    // Result
    const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);
    const [authUrl, setAuthUrl] = useState('');

    // Fetch auth status on mount
    useEffect(() => {
        fetchStatus();
    }, []);

    const fetchStatus = async () => {
        setLoading(true);
        try {
            const [statusData, automatedData, urlData] = await Promise.all([
                apiClient.getUpstoxAuthStatus().catch(() => null),
                apiClient.getUpstoxAutomatedStatus().catch(() => null),
                apiClient.getUpstoxAuthUrl().catch(() => null),
            ]);
            
            setStatus(statusData);
            setAutomatedStatus(automatedData);
            setAuthUrl(urlData?.auth_url || '');
            
        } catch (error) {
            console.error('Failed to fetch auth status:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleAutomatedAuth = async () => {
        if (!mobileOrEmail || !pin) {
            setResult({ success: false, message: 'Mobile/Email and PIN are required' });
            return;
        }

        setAuthInProgress(true);
        setResult(null);

        try {
            const data = await apiClient.automatedUpstoxLogin({
                mobile_or_email: mobileOrEmail,
                pin: pin,
                totp_secret: totpSecret || undefined,
                headless: headless,
            });

            setResult({ success: data.success, message: data.message });
            
            if (data.success) {
                await fetchStatus();
                onAuthSuccess?.();
            }
        } catch (error: any) {
            setResult({ success: false, message: error.response?.data?.detail || error.message || 'Authentication failed' });
        } finally {
            setAuthInProgress(false);
        }
    };

    const handleCodeExchange = async () => {
        if (!authCode) {
            setResult({ success: false, message: 'Authorization code is required' });
            return;
        }

        setAuthInProgress(true);
        setResult(null);

        try {
            const data = await apiClient.exchangeUpstoxCode(authCode);
            setResult({ success: data.success, message: data.message });
            
            if (data.success) {
                await fetchStatus();
                onAuthSuccess?.();
            }
        } catch (error: any) {
            setResult({ success: false, message: error.response?.data?.detail || error.message || 'Code exchange failed' });
        } finally {
            setAuthInProgress(false);
        }
    };

    const copyAuthUrl = () => {
        navigator.clipboard.writeText(authUrl);
        setResult({ success: true, message: 'Auth URL copied to clipboard!' });
    };

    const openAuthUrl = () => {
        window.open(authUrl, '_blank');
    };

    const playwrightAvailable = automatedStatus?.playwright_available && automatedStatus?.browser_installed;

    if (loading) {
        return (
            <Card className="glass rounded-2xl">
                <CardContent className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="glass rounded-2xl overflow-hidden">
            <CardHeader className="bg-gradient-to-r from-orange-500/10 to-red-500/10">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-xl font-bold flex items-center gap-2">
                            Upstox Authentication
                        </CardTitle>
                        <CardDescription>
                            Connect your Upstox account for real-time data and trading
                        </CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                        {status?.authenticated ? (
                            <Badge className="bg-green-500/20 text-green-500 border-green-500/30">
                                <CheckCircle className="h-3 w-3 mr-1" />
                                Connected
                            </Badge>
                        ) : (
                            <Badge variant="destructive" className="bg-red-500/20 text-red-500 border-red-500/30">
                                <XCircle className="h-3 w-3 mr-1" />
                                Not Connected
                            </Badge>
                        )}
                        <Button variant="ghost" size="sm" onClick={fetchStatus}>
                            <RefreshCw className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            </CardHeader>
            
            <CardContent className="pt-6 space-y-6">
                {/* Status Info - API not configured */}
                {!authUrl && (
                    <div className="p-4 rounded-lg bg-yellow-500/10 border border-yellow-500/30">
                        <p className="text-sm text-yellow-500">
                            ⚠️ Upstox API credentials not configured. Set UPSTOX_API_KEY and UPSTOX_API_SECRET in backend .env file.
                        </p>
                    </div>
                )}

                {/* Auth Method Selector */}
                {!status?.authenticated && authUrl && (
                    <>
                        <div className="flex gap-2">
                            <Button
                                variant={authMethod === 'automated' ? 'default' : 'outline'}
                                onClick={() => setAuthMethod('automated')}
                                className="flex-1"
                                disabled={!playwrightAvailable}
                            >
                                <Zap className="h-4 w-4 mr-2" />
                                Automated
                            </Button>
                            <Button
                                variant={authMethod === 'manual' ? 'default' : 'outline'}
                                onClick={() => setAuthMethod('manual')}
                                className="flex-1"
                            >
                                <ExternalLink className="h-4 w-4 mr-2" />
                                Manual
                            </Button>
                            <Button
                                variant={authMethod === 'code' ? 'default' : 'outline'}
                                onClick={() => setAuthMethod('code')}
                                className="flex-1"
                            >
                                <Key className="h-4 w-4 mr-2" />
                                Use Code
                            </Button>
                        </div>

                        {!playwrightAvailable && authMethod === 'automated' && (
                            <div className="p-3 rounded-lg bg-orange-500/10 border border-orange-500/30 text-sm">
                                <p className="text-orange-500">
                                    ⚠️ Playwright not installed on server. Run: <code className="bg-muted px-1 rounded">pip install playwright && playwright install chromium</code>
                                </p>
                            </div>
                        )}

                        {/* Automated Auth Form */}
                        {authMethod === 'automated' && playwrightAvailable && (
                            <div className="space-y-4">
                                <div className="space-y-2">
                                    <Label htmlFor="mobile" className="flex items-center gap-2">
                                        <Smartphone className="h-4 w-4" />
                                        Mobile / Email
                                    </Label>
                                    <Input
                                        id="mobile"
                                        type="text"
                                        placeholder="Enter your Upstox mobile or email"
                                        value={mobileOrEmail}
                                        onChange={(e) => setMobileOrEmail(e.target.value)}
                                    />
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="pin" className="flex items-center gap-2">
                                        <Key className="h-4 w-4" />
                                        PIN
                                    </Label>
                                    <div className="relative">
                                        <Input
                                            id="pin"
                                            type={showPin ? 'text' : 'password'}
                                            placeholder="Enter your 6-digit PIN"
                                            value={pin}
                                            onChange={(e) => setPin(e.target.value)}
                                            maxLength={6}
                                        />
                                        <Button
                                            type="button"
                                            variant="ghost"
                                            size="sm"
                                            className="absolute right-2 top-1/2 -translate-y-1/2"
                                            onClick={() => setShowPin(!showPin)}
                                        >
                                            {showPin ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                        </Button>
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="totp" className="flex items-center gap-2">
                                        <Shield className="h-4 w-4" />
                                        TOTP Secret (Optional - for 2FA)
                                    </Label>
                                    <div className="relative">
                                        <Input
                                            id="totp"
                                            type={showTotp ? 'text' : 'password'}
                                            placeholder="Your TOTP secret if 2FA is enabled"
                                            value={totpSecret}
                                            onChange={(e) => setTotpSecret(e.target.value)}
                                        />
                                        <Button
                                            type="button"
                                            variant="ghost"
                                            size="sm"
                                            className="absolute right-2 top-1/2 -translate-y-1/2"
                                            onClick={() => setShowTotp(!showTotp)}
                                        >
                                            {showTotp ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                        </Button>
                                    </div>
                                </div>

                                <div className="flex items-center gap-2">
                                    <input
                                        type="checkbox"
                                        id="headless"
                                        title="Run in background headless mode"
                                        checked={headless}
                                        onChange={(e) => setHeadless(e.target.checked)}
                                        className="rounded"
                                    />
                                    <Label htmlFor="headless" className="text-sm text-muted-foreground">
                                        Run in background (headless mode)
                                    </Label>
                                </div>

                                <Button 
                                    onClick={handleAutomatedAuth} 
                                    disabled={authInProgress || !mobileOrEmail || !pin}
                                    className="w-full"
                                >
                                    {authInProgress ? (
                                        <>
                                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                            Authenticating...
                                        </>
                                    ) : (
                                        <>
                                            <Zap className="h-4 w-4 mr-2" />
                                            Connect Automatically
                                        </>
                                    )}
                                </Button>
                            </div>
                        )}

                        {/* Manual Auth */}
                        {authMethod === 'manual' && (
                            <div className="space-y-4">
                                <p className="text-sm text-muted-foreground">
                                    Click the button below to open Upstox login in a new tab. After logging in, 
                                    you'll be redirected to a callback URL. Copy the <code className="bg-muted px-1 rounded">code</code> parameter 
                                    from the URL and paste it in the "Use Code" tab.
                                </p>
                                
                                <div className="flex gap-2">
                                    <Button onClick={openAuthUrl} className="flex-1">
                                        <ExternalLink className="h-4 w-4 mr-2" />
                                        Open Upstox Login
                                    </Button>
                                    <Button variant="outline" onClick={copyAuthUrl}>
                                        <Copy className="h-4 w-4" />
                                    </Button>
                                </div>

                                <div className="p-3 rounded-lg bg-muted/30 text-xs text-muted-foreground">
                                    <p className="font-medium mb-1">After login, copy the code from:</p>
                                    <code className="block overflow-x-auto">
                                        https://your-callback-url?code=<span className="text-primary">COPY_THIS_CODE</span>
                                    </code>
                                </div>
                            </div>
                        )}

                        {/* Code Exchange */}
                        {authMethod === 'code' && (
                            <div className="space-y-4">
                                <div className="space-y-2">
                                    <Label htmlFor="code">Authorization Code</Label>
                                    <Input
                                        id="code"
                                        type="text"
                                        placeholder="Paste the authorization code here"
                                        value={authCode}
                                        onChange={(e) => setAuthCode(e.target.value)}
                                    />
                                </div>

                                <Button 
                                    onClick={handleCodeExchange} 
                                    disabled={authInProgress || !authCode}
                                    className="w-full"
                                >
                                    {authInProgress ? (
                                        <>
                                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                            Exchanging Code...
                                        </>
                                    ) : (
                                        <>
                                            <Key className="h-4 w-4 mr-2" />
                                            Exchange Code for Token
                                        </>
                                    )}
                                </Button>
                            </div>
                        )}
                    </>
                )}

                {/* Already Authenticated */}
                {status?.authenticated && (
                    <div className="p-4 rounded-lg bg-green-500/10 border border-green-500/30">
                        <div className="flex items-center gap-2 text-green-500">
                            <CheckCircle className="h-5 w-5" />
                            <span className="font-medium">Successfully connected to Upstox!</span>
                        </div>
                        <div className="mt-3 space-y-1 text-sm text-muted-foreground">
                            {status.user_id && (
                                <p>User ID: <span className="text-foreground">{status.user_id}</span></p>
                            )}
                            {status.email && (
                                <p>Email: <span className="text-foreground">{status.email}</span></p>
                            )}
                            {status.exchanges && status.exchanges.length > 0 && (
                                <p>Exchanges: <span className="text-foreground">{status.exchanges.join(', ')}</span></p>
                            )}
                        </div>
                    </div>
                )}

                {/* Result Message */}
                {result && (
                    <div className={`p-4 rounded-lg border ${
                        result.success 
                            ? 'bg-green-500/10 border-green-500/30 text-green-500' 
                            : 'bg-red-500/10 border-red-500/30 text-red-500'
                    }`}>
                        <div className="flex items-center gap-2">
                            {result.success ? (
                                <CheckCircle className="h-5 w-5" />
                            ) : (
                                <XCircle className="h-5 w-5" />
                            )}
                            <span>{result.message}</span>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
