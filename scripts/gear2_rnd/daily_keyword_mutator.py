#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
【AI 藝術總監 - 自動關鍵字變異器】

每日自動生成 50 個冷門精準搜尋關鍵字，用於 YouTube + B站礦車
結合職場痛點 + 冷門極端美學的隨機組合

模型: glm-4.5-air (旗艦文本模型)
輸出: video_input.txt (自動覆寫)
"""

import os
import sys
import requests
from pathlib import Path
from datetime import datetime
from urllib3.exceptions import InsecureRequestWarning

# 禁用 SSL 警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from common.env_manager import config
from common.atomic_io import atomic_write_text

# ============= 配置常數 =============
WORKSPACE_ROOT = Path(config.workspace_root)
VIDEO_INPUT_FILE = WORKSPACE_ROOT / "video_input.txt"
API_KEY = config.ZHIPUAI_API_KEY
ZHIPUAI_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

MODEL_NAME = "glm-4.5-air"
MAX_RETRIES = 3
RETRY_DELAY = 2

class DailyKeywordMutator:
    """每日自動關鍵字變異器 (AI 藝術總監)"""
    
    def __init__(self):
        self.api_key = API_KEY
        self.video_input_file = VIDEO_INPUT_FILE
        self.original_content = self._load_original_content()
    
    def _load_original_content(self) -> str:
        """讀取 video_input.txt 原本的內容（用於失敗時回復）"""
        if self.video_input_file.exists():
            with open(self.video_input_file, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def _fetch_realtime_trends(self) -> list:
        """利用 requests 與 BeautifulSoup 抓取實時熱搜 ($0 成本)"""
        trends = []
        print("  🌐 正在連接世界神經網路，抓取實時熱搜榜單...")
        try:
            # 這裡以 Google Trends 台灣區 RSS 為例，完全免費且無需 API Key
            url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=TW"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.content, "html.parser")
                # 提取 RSS 中的 title 標籤 (跳過第一個頻道標題)
                titles = soup.find_all("title")
                for t in titles[1:6]:  # 取 Top 5
                    # 清洗掉可能出現的雜訊
                    clean_title = t.text.strip().replace("<![CDATA[", "").replace("]]>", "")
                    trends.append(clean_title)
                    
            if trends:
                print(f"  🔥 成功捕捉今日熱搜: {', '.join(trends)}")
                return trends
        except Exception as e:
            print(f"  ⚠️ 熱搜抓取失敗: {e}")
            
        # 降級兜底方案 (如果斷網或被擋)
        print("  ⚠️ 啟用本地備用熱點池...")
        return ["人工智慧危機", "極端氣候", "全球經濟大跌", "超現實 AI", "太空殖民計畫"]  

    def _build_prompt(self) -> str:
        """【CTO 實時熱點劫持版】讓 AI 根據世界熱搜，動態發明美學與場景"""
        import random
        
        # 1. 抓取今日全網熱搜 Top 5
        trends_sample = self._fetch_realtime_trends()
        trends_text = "\n   - ".join(trends_sample)
        
        # 2. 隨機抽取少量本地痛點作為調味料 (保留我們獨特的社畜 DNA)
        pain_points_file = WORKSPACE_ROOT / "assets" / "data" / "pain_points.txt"
        pain_points_sample = ["超現實"]       
        if pain_points_file.exists():
            with open(pain_points_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            if lines:
                pain_points_sample = random.sample(lines, min(2, len(lines)))
        pain_points_text = "\n   - ".join(pain_points_sample)

        # 3. 釋放 AI 創造力的終極 Prompt
        prompt = f"""你是一位深諳網路演算法、熱衷於前衛藝術與蹭流量的 MV 導演。
我需要你發想 50 個用於 YouTube 和 Bilibili 的『極度吸睛、詭異且精準』的影片搜尋關鍵字。

【今日全網實時熱搜 Top 5 (你的創作靈感核心)】：
   - {trends_text}

【本地社畜痛點 (你的調味料)】：
   - {pain_points_text}

【你的任務與創作邏輯】：
1. 觀察上述的「熱搜話題」，並「自行發明」5 種與這些熱點形成強烈反差、或極度契合的「冷門/極端視覺美學」（例如：若熱搜是某個科技新聞，美學可以是「surreal」,「cyberpunk」或「Biopunk」）。
2. 「自行發明」5 種對應的「獨立/另類音樂風格後綴」（如：Dark Ambient, 蒙古呼麥配樂, 故障電子）。
3. 將【熱搜話題衍生的具體畫面】+【你發明的視覺美學】+【你發明的音樂風格】+【本地痛點】進行隨機且荒誕的融合。
4. 字詞必須極度精煉、適合搜尋引擎（支援中英文混合）。

例如：
Keyword="[熱搜關鍵字變體] 超現實 Lofi Type Beat"
Keyword="[熱搜關鍵字變體] 黏土動畫 融化的時鐘 獨立音樂 MV"

請嚴格遵守輸出格式，為每個關鍵字分配一個「0.01% 到 100% 的生成機率 (Probability)」，藉此確保你給出的選項具有極端的統計多樣性。共 50 行，最後一行加上 end：
Probability=[機率]% | Keyword="[你生成的關鍵字]"
...
end"""
        return prompt

    def _call_glm4_plus(self, prompt: str) -> str:
        """呼叫 GLM-4.5-air 旗艦模型"""
        
        for attempt in range(MAX_RETRIES):
            try:
                payload = {
                    "model": MODEL_NAME,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.95, # 🚀 CTO 修改：暴力調高溫度，強迫產生創意變異
                    "top_p": 0.9,
                }
                
                response = requests.post(
                    ZHIPUAI_API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    verify=False,
                    timeout=120
                )
                
                if response.status_code != 200:
                    raise Exception(f"API 返回錯誤: {response.status_code}")
                
                result = response.json()
                return result['choices'][0]['message']['content']
            
            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    print(f"  ⏳ API 超時，重試 {attempt + 1}/{MAX_RETRIES}...")
                    import time
                    time.sleep(RETRY_DELAY)
                else:
                    raise Exception(f"API 超時失敗（{attempt + 1}/{MAX_RETRIES} 次嘗試）")
            
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    print(f"  ⚠️  API 呼叫失敗，重試 {attempt + 1}/{MAX_RETRIES}: {str(e)[:80]}")
                    import time
                    time.sleep(RETRY_DELAY)
                else:
                    raise Exception(f"API 最終失敗: {e}")
        
        return ""
    
    def _parse_keywords(self, response_text: str) -> list:
        """解析 API 回應，提取關鍵字"""
        keywords = []
        
        for line in response_text.split('\n'):
            line = line.strip()
            
            # 尋找包含 Keyword="..." 格式的行
            if 'Keyword="' in line and line.endswith('"'):
                # 切割出 Keyword= 後面的內容
                parts = line.split('Keyword="')
                if len(parts) > 1:
                    keyword = parts[1][:-1]  # 移除末尾的 "
                    if keyword:
                        keywords.append(keyword)
            elif line.lower() == "end":
                break
        
        return keywords
    
    def _save_keywords(self, keywords: list) -> bool:
        """將關鍵字寫入 video_input.txt"""
        try:
            text = "".join([f'Keyword="{keyword}"\n' for keyword in keywords]) + "end\n"
            atomic_write_text(self.video_input_file, text)
            
            return True
        except Exception as e:
            print(f"❌ 檔案寫入失敗: {e}")
            return False
    
    def _restore_original(self):
        """如果失敗，恢復原始內容"""
        try:
            atomic_write_text(self.video_input_file, self.original_content)
            print(f"✅ 已恢復原始 video_input.txt 內容")
        except Exception as e:
            print(f"⚠️  恢復原始內容失敗: {e}")
    
    def generate(self):
        """主流程：生成並更新關鍵字"""
        
        print("="*70)
        print("🎬 AI 藝術總監 - 每日自動關鍵字變異器")
        print("="*70 + "\n")
        
        if not self.api_key:
            print("❌ 環境變數 ZHIPUAI_API_KEY 未設置")
            return False
        
        try:
            # 1. 構建 Prompt
            print("🧠 構建藝術導演 Prompt...")
            prompt = self._build_prompt()
            print(f"✅ Prompt 構建完成 ({len(prompt)} 字元)")
            
            # 2. 呼叫 GLM-4-Plus
            print("\n🤖 調用 GLM-4.5-air 旗艦模型...")
            response = self._call_glm4_plus(prompt)
            
            if not response:
                raise Exception("模型返回空回應")
            
            print(f"✅ 模型回應成功 ({len(response)} 字元)")
            
            # 3. 解析關鍵字
            print("\n📝 解析關鍵字格式...")
            keywords = self._parse_keywords(response)
            
            if not keywords:
                raise Exception("無法解析出任何關鍵字（格式不符）")
            
            print(f"✅ 成功提取 {len(keywords)} 個關鍵字:")
            for idx, kw in enumerate(keywords, 1):
                print(f"   {idx:2d}. {kw}")
            
            # 4. 寫入檔案
            print("\n💾 寫入 video_input.txt...")
            if self._save_keywords(keywords):
                print(f"✅ 檔案更新成功: {self.video_input_file}")
            else:
                raise Exception("檔案寫入失敗")
            
            print("\n" + "="*70)
            print("🎉 關鍵字變異完成！")
            print("="*70 + "\n")
            
            return True
        
        except Exception as e:
            print(f"\n❌ 執行失敗: {e}")
            print("\n⚠️  正在恢復原始 video_input.txt...")
            self._restore_original()
            
            print("\n" + "="*70)
            print("❌ 關鍵字變異失敗（已保護原始檔案）")
            print("="*70 + "\n")
            
            return False


def main():
    """主程式"""
    mutator = DailyKeywordMutator()
    success = mutator.generate()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
