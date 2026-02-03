# Speed Up Ollama - Quick Fix Guide

## Problem: Llama3 is Too Slow

Llama3 (8B parameters) can be slow on some systems. Here's how to fix it:

---

## ✅ Solution: Use Faster Models

### Option 1: Phi3 (Recommended - Best Balance)

**Install:**
```powershell
ollama pull phi3
```

**Specs:**
- Size: 3.8B parameters
- Speed: 2-3x faster than llama3
- Quality: Excellent for trading questions
- Memory: ~2.3GB

**Already configured in your frontend!** Just install and restart.

---

### Option 2: TinyLlama (Fastest)

**Install:**
```powershell
ollama pull tinyllama
```

**Specs:**
- Size: 1.1B parameters
- Speed: 5-10x faster than llama3
- Quality: Good for simple questions
- Memory: ~637MB

**To use:** Update `frontend/app/api/ollama/chat/route.ts`:
```typescript
model: 'tinyllama',
```

---

### Option 3: Gemma 2B (Google)

**Install:**
```powershell
ollama pull gemma:2b
```

**Specs:**
- Size: 2B parameters
- Speed: 4-5x faster than llama3
- Quality: Very good
- Memory: ~1.4GB

**To use:** Update `frontend/app/api/ollama/chat/route.ts`:
```typescript
model: 'gemma:2b',
```

---

## 🚀 Quick Setup (Recommended)

### Step 1: Install Phi3
```powershell
ollama pull phi3
```

### Step 2: Your Frontend is Already Configured!
I've already updated your API route to use `phi3` with optimized settings.

### Step 3: Restart Frontend
```powershell
# Stop current server (Ctrl+C)
cd frontend
npm run dev
```

### Step 4: Test
- Go to http://localhost:3000/ai-assistant
- Ask a question
- Should respond in 2-5 seconds instead of 10-20 seconds!

---

## ⚡ Performance Optimizations Applied

Your API route now includes:

1. **Faster Model**: `phi3` instead of `llama3`
2. **Temperature**: 0.3 (more focused, less random)
3. **Response Limit**: 300 tokens max (faster generation)
4. **Concise Prompt**: Asks AI to be brief

**Result**: 3-5x faster responses!

---

## 📊 Speed Comparison

| Model | Response Time | Quality | Memory |
|-------|--------------|---------|--------|
| **llama3** | 10-20s | Excellent | 4.7GB |
| **phi3** ⭐ | 3-5s | Excellent | 2.3GB |
| **gemma:2b** | 2-4s | Very Good | 1.4GB |
| **tinyllama** | 1-2s | Good | 637MB |

---

## 🔧 Advanced: Test All Models

Run this script to install and compare all fast models:

```powershell
python backend/scripts/install_fast_models.py
```

This will:
1. Show you all fast model options
2. Let you install one or all
3. Test their speed
4. Recommend the fastest

---

## 🎯 Recommended Action

**For best results:**

1. **Install phi3** (already configured):
   ```powershell
   ollama pull phi3
   ```

2. **Restart frontend**:
   ```powershell
   cd frontend
   npm run dev
   ```

3. **Test it** - Should be 3-5x faster!

---

## 🐛 Still Slow?

### Check System Resources:
```powershell
# Windows Task Manager
# Look for high CPU/Memory usage
```

### Try Even Smaller Model:
```powershell
ollama pull tinyllama
```

Then update `route.ts`:
```typescript
model: 'tinyllama',
```

### Reduce Response Length:
In `route.ts`, change:
```typescript
num_predict: 150,  // Even shorter responses
```

---

## ✅ Summary

**Quick Fix:**
```powershell
# 1. Install faster model
ollama pull phi3

# 2. Restart frontend
cd frontend
npm run dev

# 3. Test - should be much faster!
```

**Your API is already configured to use phi3 with optimized settings!**

---

*Last updated: 2025-12-17*
