# list_available_models.py
"""列出所有可用的 Gemini 模型"""

import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ 找不到 GEMINI_API_KEY")
    exit(1)

genai.configure(api_key=api_key)

print("🔍 【列出所有可用模型】\n")
try:
    models = genai.list_models()
    
    print("✓ 支持 generateContent 的模型：\n")
    for model in models:
        if "generateContent" in model.supported_generation_methods:
            print(f"  • {model.name}")
            
except Exception as e:
    print(f"❌ 錯誤: {e}")
