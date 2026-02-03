---
description: Setup and run local AI model for strategy analysis
---

# Setup Local AI for Strategy Analysis

This workflow sets up **Ollama** to run local LLMs (like Llama 3 or DeepSeek) to analyze market data and suggest strategies without using external API tokens.

## 1. Install Ollama
// turbo
```powershell
winget install Ollama.Ollama
```

## 2. Verify Installation
Restart your terminal after installation to ensure `ollama` is in your PATH.

```powershell
ollama --version
```

## 3. Start Ollama Server
You need to run the Ollama server in a separate terminal or background.
```powershell
ollama serve
```

## 4. Pull a Model
We will use `misral` or `llama3` for analysis.
```powershell
ollama pull llama3
```

## 5. Test Integration
Run the Python test script to verify we can talk to the local model.
```powershell
python backend/scripts/test_local_ai.py
```
