# KeepGaining - Complete Setup and Run Guide

## Current Status
✅ Backend API implemented with all endpoints
✅ Fyers integration working
✅ Strategy Engine functional
✅ OMS and Risk Manager verified
✅ Frontend API client created

## Prerequisites
- ✅ Python 3.12 (installed)
- ✅ Required Python packages (installed)
- ⚠️ Node.js 20.x LTS (needs PATH configuration)
- ⚠️ npm (comes with Node.js)

## Backend Setup

### 1. Install Python Dependencies (if not done)
```powershell
cd C:\sources\KeepGaining\backend
py -3.12 -m pip install fyers-apiv3 tenacity loguru pandas python-dotenv requests pyotp pydantic pydantic-settings fastapi uvicorn sqlalchemy asyncpg greenlet
```

### 2. Configure Environment Variables
Create `backend/.env` with your Fyers credentials:
```
FYERS_CLIENT_ID=your_client_id
FYERS_SECRET_KEY=your_secret_key
FYERS_REDIRECT_URI=your_redirect_uri
FYERS_USER_ID=your_user_id
FYERS_PIN=your_pin
FYERS_TOTP_KEY=your_totp_key
```

### 3. Start Backend Server
```powershell
cd C:\sources\KeepGaining\backend
$env:PYTHONPATH = (Get-Location).Path
py -3.12 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be available at: http://localhost:8000
API Documentation (Swagger): http://localhost:8000/docs

## Frontend Setup

### 1. Fix Node.js PATH (if npm not working)
If `npm` command is not recognized after installing Node.js:

**Option A: Restart PowerShell/Command Prompt**
- Close current terminal
- Open new PowerShell as Administrator
- Verify: `node --version` and `npm --version`

**Option B: Add to PATH manually**
1. Press Win + R, type `sysdm.cpl` and press Enter
2. Go to "Advanced" tab → "Environment Variables"
3. Under "System Variables", find "Path"
4. Add: `C:\Program Files\nodejs\`
5. Restart terminal

### 2. Install Frontend Dependencies
```powershell
cd C:\sources\KeepGaining\frontend
npm install
npm install axios
```

### 3. Start Frontend Server
```powershell
cd C:\sources\KeepGaining\frontend
npm run dev
```

Frontend will be available at: http://localhost:3000

## Testing the Integration

### Backend Health Check
```powershell
# Test API is running
curl http://localhost:8000/health

# Test broker status
curl http://localhost:8000/api/broker/status

# Test strategies list
curl http://localhost:8000/api/strategies
```

### Frontend-Backend Integration
1. Open browser: http://localhost:3000
2. Check console for API errors
3. Verify Dashboard shows real data from Fyers
4. Check Strategy Editor lists available strategies

## Available API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | API health check |
| `/api/positions` | GET | Get current positions |
| `/api/strategies` | GET | List all strategies |
| `/api/strategies/deploy` | POST | Deploy a strategy |
| `/api/strategies/{id}/stop` | POST | Stop a strategy |
| `/api/orders` | GET | Get order book |
| `/api/orders/place` | POST | Place an order |
| `/api/broker/status` | GET | Broker connection status |
| `/api/broker/funds` | GET | Available funds |

## Troubleshooting

### Backend Issues
- **Module not found**: Ensure PYTHONPATH is set and all packages are installed
- **Fyers auth failed**: Check .env credentials
- **Port already in use**: Change port with `--port 8001`

### Frontend Issues
- **npm not found**: Verify Node.js installation and PATH
- **API connection failed**: Ensure backend is running on port 8000
- **CORS errors**: Backend already configured for localhost:3000

## Next Steps (Not Yet Implemented)

The following components still need manual updates:

1. **Update Frontend Components** (manual edit needed):
   - `frontend/components/dashboard/overview.tsx` - Replace mock data with API calls
   - `frontend/components/strategy/editor.tsx` - Connect to `/api/strategies`
   - `frontend/components/broker/status.tsx` - Connect to `/api/broker/status`

2. **Add Real-time Updates**: Implement WebSocket or polling for live data

3. **Add more strategies**: Extend strategy registry with additional trading strategies

## Project Structure
```
KeepGaining/
├── backend/
│   ├── app/
│   │   ├── api/          # REST API endpoints (NEW)
│   │   ├── brokers/      # Fyers integration
│   │   ├── strategies/   # Trading strategies
│   │   ├── execution/    # OMS, Risk Manager
│   │   └── main.py       # FastAPI app
│   └── scripts/          # Verification scripts
└── frontend/
    ├── components/       # UI components
    ├── lib/api/         # API client (NEW)
    └── app/             # Next.js pages
```
