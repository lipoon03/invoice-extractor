"""Environment-driven evaluation configuration; never place API keys here."""
import os

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
# Minimum thinking configuration. Gemini 3 models use "minimal"; Gemini 2.5 uses budget 0.
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "minimal")
OLLAMA_MODELS = [
    item.strip() for item in os.getenv("OLLAMA_MODELS", "llama3,qwen3-8b,qwen3.5:9b").split(",")
    if item.strip()
]
OLLAMA_TIMEOUT_SECONDS = 60.0
GEMINI_TIMEOUT_SECONDS = 60.0
