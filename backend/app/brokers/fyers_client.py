"""Fyers API client with TOTP-based authentication and rate limiting."""

import hashlib
import time
import pyotp
import base64
import hmac
import struct
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, parse_qs
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from fyers_apiv3 import fyersModel
import pandas as pd
from loguru import logger

class RateLimiter:
    """Rate limiter for Fyers API calls.
    
    Limits:
    - 10 requests per second
    - 200 requests per minute
    """
    
    def __init__(self):
        self.per_second_limit = 10
        self.per_minute_limit = 200
        self.second_requests = []
        self.minute_requests = []
    
    def wait_if_needed(self):
        """Wait if rate limits would be exceeded."""
        current_time = time.time()
        
        # Clean old requests
        self.second_requests = [t for t in self.second_requests if current_time - t < 1.0]
        self.minute_requests = [t for t in self.minute_requests if current_time - t < 60.0]
        
        # Check per-second limit
        if len(self.second_requests) >= self.per_second_limit:
            sleep_time = 1.0 - (current_time - self.second_requests[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
            self.second_requests = []
        
        # Check per-minute limit
        if len(self.minute_requests) >= self.per_minute_limit:
            sleep_time = 60.0 - (current_time - self.minute_requests[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
            self.minute_requests = []
        
        # Record this request
        current_time = time.time()
        self.second_requests.append(current_time)
        self.minute_requests.append(current_time)


class FyersClient:
    """Fyers API client with TOTP-based authentication."""
    
    def __init__(self, client_id: str, secret_key: str, redirect_uri: str, 
                 username: str, pin: str, totp_key: str, access_token: Optional[str] = None,
                 refresh_token: Optional[str] = None):
        """Initialize Fyers client.
        
        Args:
            client_id: Fyers client ID (app ID)
            secret_key: Fyers secret key (app secret)
            redirect_uri: Redirect URI for OAuth
            username: Fyers username/user ID
            pin: User PIN
            totp_key: TOTP secret key for 2FA
            access_token: Optional pre-generated access token (if provided, skips authentication)
            refresh_token: Optional refresh token for automatic token refresh (15-day validity)
        """
        self.client_id = client_id
        self.secret_key = secret_key
        self.redirect_uri = redirect_uri
        self.username = username
        self.pin = pin
        self.totp_key = totp_key
        self.refresh_token = refresh_token
        self.rate_limiter = RateLimiter()
        
        # Use manual token if provided
        if access_token:
            # Remove client_id prefix if present (SDK expects token without prefix)
            if ':' in access_token and access_token.startswith(self.client_id):
                _, self.access_token = access_token.split(':', 1)
                logger.info(f"[FyersClient] Removed client_id prefix from manual token")
            else:
                self.access_token = access_token
            
            self.token_expiry = time.time() + (6 * 3600)  # 6 hours
            logger.info(f"[FyersClient] Using manual access token")
        else:
            self.access_token = None
            self.token_expiry = None
            
            # Try to load and use refresh token first
            self.refresh_token = self._load_refresh_token()
            if self.refresh_token and self._refresh_access_token():
                logger.info("[FyersClient] Initialized with saved refresh token")
            else:
                # Initialize authentication if refresh failed or no token
                logger.info("[FyersClient] No valid token found, starting authentication...")
                self._authenticate()
        
        # Initialize Fyers model
        self.fyers = fyersModel.FyersModel(
            client_id=self.client_id,
            token=self.access_token,
            is_async=False,
            log_path=""
        )
    
    def _generate_totp(self, time_step=30, digits=6) -> str:
        """Generate TOTP code from the secret key.
        
        Args:
            time_step: Time step in seconds (default: 30)
            digits: Number of digits in TOTP (default: 6)
        
        Returns:
            6-digit TOTP code
        """
        if not self.totp_key:
            raise ValueError("TOTP Key is missing")
            
        # Handle padding if necessary
        key_str = self.totp_key.upper()
        padding = "=" * ((8 - len(key_str) % 8) % 8)
        key = base64.b32decode(key_str + padding)
        
        counter = struct.pack(">Q", int(time.time() / time_step))
        mac = hmac.new(key, counter, 'sha1').digest()
        offset = mac[-1] & 0x0F
        binary = struct.unpack(">L", mac[offset : offset + 4])[0] & 0x7FFFFFFF
        return str(binary)[-digits:].zfill(digits)
    
    def _refresh_access_token(self):
        """Refresh access token using refresh token.
        
        Uses the /api/v3/validate-refresh-token endpoint to get a new access token
        without requiring manual authentication. Refresh token is valid for 15 days.
        
        Returns:
            bool: True if refresh successful, False otherwise
        """
        try:
            if not self.refresh_token:
                logger.info(f"[FyersClient] No refresh token available, need full authentication")
                return False
            
            logger.info(f"[FyersClient] Attempting to refresh access token...")
            
            # Calculate appIdHash
            app_id_hash = hashlib.sha256(f"{self.client_id}:{self.secret_key}".encode()).hexdigest()
            
            # Prepare refresh request
            refresh_data = {
                "grant_type": "refresh_token",
                "appIdHash": app_id_hash,
                "refresh_token": self.refresh_token,
                "pin": self.pin
            }
            
            # Call refresh endpoint
            response = requests.post(
                "https://api-t1.fyers.in/api/v3/validate-refresh-token",
                json=refresh_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 200:
                logger.error(f"[FyersClient] Refresh failed (status={response.status_code}): {response.text}")
                return False
            
            result = response.json()
            
            if result.get('s') == 'ok':
                # Update access token - SDK expects token WITHOUT prefix
                self.access_token = result['access_token']
                self.token_expiry = time.time() + (6 * 3600)  # 6 hours
                
                # Update Fyers model with new token
                self.fyers = fyersModel.FyersModel(
                    client_id=self.client_id,
                    token=self.access_token,
                    is_async=False,
                    log_path=""
                )
                
                logger.success(f"[FyersClient] Access token refreshed successfully!")
                return True
            else:
                logger.error(f"[FyersClient] Refresh failed: {result.get('message', 'Unknown error')}")
                return False
                
        except Exception as e:
            logger.error(f"[FyersClient] Error refreshing token: {e}")
            return False
    
    def _authenticate(self):
        """Authenticate using OAuth v3 flow with refresh token support.
        
        Flow:
        1. Use TOTP-based login to get auth_code
        2. Exchange auth_code for access_token AND refresh_token
        3. Store refresh_token for future use (15-day validity)
        """
        try:
            logger.info(f"[FyersClient] Starting OAuth v3 authentication flow...")
            
            # Set up headers
            headers = {
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
            }
            
            s = requests.Session()
            s.headers.update(headers)
            
            # Step 1: Send login OTP
            # Note: The user provided code uses 'fy_id' which is likely the username
            data1 = f'{{"fy_id":"{base64.b64encode(self.username.encode()).decode()}","app_id":"2"}}'
            r1 = s.post("https://api-t2.fyers.in/vagator/v2/send_login_otp_v2", data=data1, headers={"content-type": "application/json"})
            
            if r1.status_code != 200:
                raise Exception(f"Login OTP request failed (status={r1.status_code}): {r1.text}")
            
            request_key = r1.json()["request_key"]
            logger.info(f"[FyersClient] Step 1: Login OTP request sent")
            
            # Step 2: Verify TOTP
            totp_code = self._generate_totp()
            data2 = f'{{"request_key":"{request_key}","otp":{totp_code}}}'
            r2 = s.post("https://api-t2.fyers.in/vagator/v2/verify_otp", data=data2, headers={"content-type": "application/json"})
            
            if r2.status_code != 200:
                raise Exception(f"TOTP verification failed (status={r2.status_code}): {r2.text}")
            
            request_key = r2.json()["request_key"]
            logger.info(f"[FyersClient] Step 2: TOTP verified")
            
            # Step 3: Verify PIN
            data3 = f'{{"request_key":"{request_key}","identity_type":"pin","identifier":"{base64.b64encode(self.pin.encode()).decode()}"}}'
            r3 = s.post("https://api-t2.fyers.in/vagator/v2/verify_pin_v2", data=data3, headers={"content-type": "application/json"})
            
            if r3.status_code != 200:
                raise Exception(f"PIN verification failed: {r3.text}")
            
            logger.info(f"[FyersClient] Step 3: PIN verified")
            
            # Step 4: Get authorization code using v3 endpoint
            # Note: r3.json()['data']['access_token'] is the VAGATOR token, not API token
            vagator_token = r3.json()['data']['access_token']
            auth_headers = {
                "authorization": f"Bearer {vagator_token}",
                "content-type": "application/json; charset=UTF-8"
            }
            data4 = f'{{"fyers_id":"{self.username}","app_id":"{self.client_id[:-4]}","redirect_uri":"{self.redirect_uri}","appType":"100","code_challenge":"","state":"abcdefg","scope":"","nonce":"","response_type":"code","create_cookie":true}}'
            r4 = s.post("https://api-t1.fyers.in/api/v3/token", headers=auth_headers, data=data4)
            
            logger.info(f"[FyersClient] Step 4: Authorization request status={r4.status_code}")
            
            if r4.status_code == 503:
                raise Exception("Fyers API is temporarily unavailable (503).")
            
            if r4.status_code != 308:
                raise Exception(f"Authorization code request failed (status={r4.status_code}): {r4.text}")
            
            parsed = urlparse(r4.json()["Url"])
            auth_code = parse_qs(parsed.query)["auth_code"][0]
            logger.info(f"[FyersClient] Step 4: Authorization code obtained")
            
            # Step 5: Exchange auth code for access token AND refresh token using v3 API
            app_id_hash = hashlib.sha256(f"{self.client_id}:{self.secret_key}".encode()).hexdigest()
            
            token_data = {
                "grant_type": "authorization_code",
                "appIdHash": app_id_hash,
                "code": auth_code
            }
            
            r5 = s.post("https://api-t1.fyers.in/api/v3/validate-authcode", 
                       json=token_data,
                       headers={"Content-Type": "application/json"})
            
            if r5.status_code != 200:
                raise Exception(f"Token generation failed (status={r5.status_code}): {r5.text}")
            
            response = r5.json()
            
            if response.get('s') == 'ok':
                self.access_token = response['access_token']
                self.refresh_token = response.get('refresh_token')
                self.token_expiry = time.time() + (6 * 3600)
                
                logger.success(f"[FyersClient] Authentication successful!")
                
                self.fyers = fyersModel.FyersModel(
                    client_id=self.client_id,
                    token=self.access_token,
                    is_async=False,
                    log_path=""
                )
                
                self._save_refresh_token()
            else:
                raise Exception(f"Token generation failed: {response.get('message', 'Unknown error')}")
                
        except Exception as e:
            raise Exception(f"Failed to authenticate: {str(e)}")
    
    def _save_refresh_token(self):
        """Save refresh token to file for persistence across sessions."""
        try:
            token_file = Path("data/.refresh_token")
            token_file.parent.mkdir(parents=True, exist_ok=True)
            
            token_data = {
                "refresh_token": self.refresh_token,
                "created_at": time.time(),
                "expires_at": time.time() + (15 * 24 * 3600)  # 15 days
            }
            
            with open(token_file, 'w') as f:
                import json
                json.dump(token_data, f)
            
            logger.info(f"[FyersClient] Refresh token saved to {token_file}")
        except Exception as e:
            logger.warning(f"[FyersClient] Warning: Could not save refresh token: {e}")
    
    def _load_refresh_token(self):
        """Load refresh token from file if available."""
        try:
            token_file = Path("data/.refresh_token")
            
            if not token_file.exists():
                return None
            
            with open(token_file, 'r') as f:
                import json
                token_data = json.load(f)
            
            if time.time() < token_data.get('expires_at', 0):
                logger.info(f"[FyersClient] Loaded valid refresh token from file")
                return token_data.get('refresh_token')
            else:
                logger.info(f"[FyersClient] Refresh token expired")
                return None
                
        except Exception as e:
            logger.error(f"[FyersClient] Could not load refresh token: {e}")
            return None
    
    def _ensure_valid_token(self):
        """Ensure access token is valid, re-authenticate if needed."""
        # Check if token expires in less than 30 minutes
        if self.token_expiry and time.time() + 1800 < self.token_expiry:
            return  # Token still valid
        
        logger.info(f"[FyersClient] Token expiring soon or expired, attempting refresh...")
        
        if not self.refresh_token:
            self.refresh_token = self._load_refresh_token()
        
        if self.refresh_token and self._refresh_access_token():
            return
        
        logger.info(f"[FyersClient] Refresh token unavailable or expired, performing full authentication...")
        self._authenticate()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, Exception))
    )
    def fetch_historical_data(
        self,
        symbol: str,
        resolution: str,
        range_from: str,
        range_to: str,
        cont_flag: str = "1",
        oi_flag: str = "1"
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data from Fyers API."""
        self._ensure_valid_token()
        self.rate_limiter.wait_if_needed()
        
        data_params = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": "1",  # YYYY-MM-DD format
            "range_from": range_from,
            "range_to": range_to,
            "cont_flag": cont_flag,
            "oi_flag": oi_flag
        }
        
        try:
            response = self.fyers.history(data=data_params)
            
            if response.get('s') == 'no_data':
                logger.warning(f"[FyersClient] No data available for {symbol} in range {range_from} to {range_to}")
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            
            if response.get('s') != 'ok':
                error_msg = response.get('message', 'Unknown error')
                raise Exception(f"API error: {error_msg}")
            
            candles = response.get('candles', [])
            
            if not candles:
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            
            if candles and len(candles) > 0:
                actual_columns = len(candles[0])
                
                if actual_columns == 6:
                    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['oi'] = 0
                elif actual_columns == 7:
                    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
                else:
                    raise Exception(f"Unexpected number of columns: {actual_columns}")
            else:
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
            df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Kolkata')
            df['timestamp'] = df['timestamp'].dt.tz_localize(None)
            
            return df
            
        except Exception as e:
            logger.error(f"[FyersClient] Error fetching data for {symbol}: {str(e)}")
            raise

    # ... (Include other methods like get_option_chain, etc. from user code)
    # For brevity, I will assume the user wants the full code. 
    # I will paste the rest of the methods provided by the user.

    def fetch_historical_data_chunked(self, symbol: str, resolution: str, range_from: str, range_to: str, oi_flag: str = "1") -> pd.DataFrame:
        from dateutil.relativedelta import relativedelta
        from dateutil.parser import parse
        
        start_date = parse(range_from)
        end_date = parse(range_to)
        
        is_intraday = resolution not in ['D', 'W', 'M']
        chunk_days = 90 if is_intraday else 350
        
        all_data = []
        current_start = start_date
        
        while current_start < end_date:
            current_end = min(current_start + relativedelta(days=chunk_days), end_date)
            chunk_from = current_start.strftime('%Y-%m-%d')
            chunk_to = current_end.strftime('%Y-%m-%d')
            
            chunk_df = self.fetch_historical_data(symbol, resolution, chunk_from, chunk_to, oi_flag=oi_flag)
            if not chunk_df.empty:
                all_data.append(chunk_df)
            current_start = current_end + relativedelta(days=1)
        
        if not all_data:
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
        
        combined_df = pd.concat(all_data, ignore_index=True)
        combined_df = combined_df.drop_duplicates(subset=['timestamp'], keep='first')
        combined_df = combined_df.sort_values('timestamp').reset_index(drop=True)
        return combined_df

    def get_option_chain(self, symbol: str, expiry_timestamp: Optional[int] = None, strike_count: int = 10) -> Dict[str, Any]:
        self.rate_limiter.wait_if_needed()
        data = {"symbol": symbol, "strikecount": strike_count}
        if expiry_timestamp:
            data["timestamp"] = expiry_timestamp
        
        response = self.fyers.optionchain(data=data)
        if response.get('s') != 'ok':
            raise Exception(f"Failed to fetch option chain: {response.get('message')}")
        return response

    def get_option_chain_symbols(self, symbol: str, expiry_timestamp: Optional[int] = None, strike_count: int = 10) -> List[str]:
        chain_data = self.get_option_chain(symbol, expiry_timestamp, strike_count)
        option_symbols = []
        if 'data' in chain_data and 'optionsChain' in chain_data['data']:
            for strike_data in chain_data['data']['optionsChain']:
                if strike_data.get('strike_price') == -1: continue
                if 'symbol' in strike_data: option_symbols.append(strike_data['symbol'])
        return option_symbols

    def get_available_expiries(self, symbol: str) -> List[Dict[str, Any]]:
        chain_data = self.get_option_chain(symbol, expiry_timestamp=None, strike_count=1)
        expiries = []
        if 'data' in chain_data and 'expiryData' in chain_data['data']:
            for expiry in chain_data['data']['expiryData']:
                expiries.append({
                    'timestamp': expiry.get('timestamp'),
                    'date': expiry.get('date'),
                    'expiry': expiry.get('expiry')
                })
        return expiries

    def generate_monthly_expiries(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        from datetime import datetime, timedelta
        import calendar
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        expiries = []
        current = start_dt.replace(day=1)
        while current <= end_dt:
            last_day = calendar.monthrange(current.year, current.month)[1]
            last_date = current.replace(day=last_day)
            while last_date.weekday() != 3: last_date -= timedelta(days=1)
            if start_dt <= last_date <= end_dt:
                expiry_timestamp = int(last_date.replace(hour=10, minute=0, second=0).timestamp())
                expiries.append({'timestamp': expiry_timestamp, 'date': last_date.strftime('%d-%m-%Y'), 'expiry': str(expiry_timestamp)})
            if current.month == 12: current = current.replace(year=current.year + 1, month=1)
            else: current = current.replace(month=current.month + 1)
        return list(reversed(expiries))

    def generate_historical_option_symbols(self, base_symbol: str, expiry_date: str, expiry_timestamp: int, strike_count: int = 5, base_strike: Optional[int] = None, strike_step: int = 10) -> List[str]:
        from datetime import datetime
        symbol_name = base_symbol.split(':')[1].split('-')[0]
        expiry_dt = datetime.strptime(expiry_date, '%d-%m-%Y')
        expiry_str = expiry_dt.strftime('%y%b').upper()
        
        if base_strike is None:
            try:
                spot_df = self.fetch_historical_data_chunked(base_symbol, 'D', expiry_dt.strftime('%Y-%m-%d'), expiry_dt.strftime('%Y-%m-%d'), '0')
                if not spot_df.empty:
                    spot_price = spot_df.iloc[-1]['close']
                    base_strike = round(spot_price / strike_step) * strike_step
                else:
                    base_strike = 850
            except: base_strike = 700
            
        strikes = [base_strike + (i * strike_step) for i in range(-strike_count, strike_count + 1)]
        option_symbols = []
        for strike in strikes:
            option_symbols.extend([f"NSE:{symbol_name}{expiry_str}{strike}CE", f"NSE:{symbol_name}{expiry_str}{strike}PE"])
        return option_symbols

    def get_profile(self) -> Dict[str, Any]:
        self._ensure_valid_token()
        return self.fyers.get_profile()
    
    def get_funds(self) -> Dict[str, Any]:
        self._ensure_valid_token()
        return self.fyers.funds()
    
    def get_holdings(self) -> Dict[str, Any]:
        self._ensure_valid_token()
        return self.fyers.holdings()
    
    def get_positions(self) -> Dict[str, Any]:
        self._ensure_valid_token()
        return self.fyers.positions()
    
    def get_orders(self) -> Dict[str, Any]:
        self._ensure_valid_token()
        return self.fyers.orderbook()
    
    def get_market_status(self) -> Dict[str, Any]:
        self._ensure_valid_token()
        return self.fyers.market_status()
    
    def place_order(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_valid_token()
        return self.fyers.place_order(data=data)

    def cancel_order(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_valid_token()
        return self.fyers.cancel_order(data=data)

    def get_quotes(self, symbols: List[str]) -> Dict[str, Any]:
        self._ensure_valid_token()
        data = {"symbols": ",".join(symbols)}
        return self.fyers.quotes(data=data)

    def modify_order(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_valid_token()
        return self.fyers.modify_order(data=data)
