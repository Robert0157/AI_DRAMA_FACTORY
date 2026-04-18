"""
穩健的 JSON 處理中樞 (Robust JSON Parser & Atomic Writer)
========================================================================
目標：徹底解決 LLM 幻覺導致的 JSON 格式破損問題
* clean_and_parse_json(): 暴力清洗 Markdown 標籤與未閉合括號
* atomic_write_json(): 原子寫入防護 (Atomic Writes) - 防範斷電損毀

遵循架構書 5.7 節 + 系統總體哲學規範
========================================================================
"""

import json
import re
import os
import sys
from pathlib import Path
from typing import Dict, Any


def clean_and_parse_json(text: str) -> Dict[str, Any]:
    """
    LLM 暴力清洗與 JSON 解析函式
    
    功能：
    1. 剝除 Markdown 程式碼框 (```json, ```, 等)
    2. 移除行首行尾空白符
    3. 嘗試自動補全未閉合的括號
    4. 安全解析為字典
    
    參數：
        text: LLM 回傳的原始文本（可能包含 Markdown 標籤污染）
    
    回傳：
        Dict[str, Any]: 清洗後的 JSON 字典
    
    異常：
        ValueError: JSON 無法解析時拋出，含清晰的錯誤訊息
        TypeError: 最終結果非字典時拋出
    """
    
    if not text or not isinstance(text, str):
        raise ValueError("輸入文本必須為非空字串")
    
    # ============ 第一步：剝除 Markdown 程式碼框 ============
    # 移除 ```json 與 ``` 標籤
    cleaned = re.sub(r'```(?:json)?\s*\n?', '', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n?```', '', cleaned)
    
    # 移除其他常見 Markdown 污染 (如 ` 符號、~~ 刪除線等)
    cleaned = re.sub(r'^```.*?```$', '', cleaned, flags=re.MULTILINE | re.DOTALL)
    cleaned = re.sub(r'`{1,2}', '', cleaned)
    cleaned = re.sub(r'~~', '', cleaned)
    
    # ============ 第二步：去除行首行尾空白 ============
    cleaned = cleaned.strip()
    
    # ============ 第三步：未閉合括號自動補全 ============
    # 計算開放與關閉的大括號數量
    open_braces = cleaned.count('{')
    close_braces = cleaned.count('}')
    
    # 如果開放大括號過多，自動補全
    if open_braces > close_braces:
        cleaned += '}' * (open_braces - close_braces)
    
    # 計算方括號數量 (用於陣列)
    open_brackets = cleaned.count('[')
    close_brackets = cleaned.count(']')
    
    if open_brackets > close_brackets:
        cleaned += ']' * (open_brackets - close_brackets)
    
    # ============ 第四步：安全 JSON 解析 ============
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        # 捕捉 JSON 解析錯誤，提供清晰的診斷訊息
        error_msg = (
            f"JSON 解析失敗\n"
            f"  錯誤型態：{type(e).__name__}\n"
            f"  錯誤訊息：{str(e)}\n"
            f"  清洗後文本（前 200 字元）：{cleaned[:200]}\n"
        )
        raise ValueError(error_msg)
    
    # ============ 第五步：型態驗證 ============
    if not isinstance(result, dict):
        raise TypeError(
            f"JSON 解析結果必須為字典型態，但得到 {type(result).__name__}\n"
            f"結果內容：{result}"
        )
    
    return result


def atomic_write_json(data: Dict[str, Any], file_path: str) -> None:
    """
    原子寫入防護 (Atomic Writes) - 防範斷電與磁碟瞬斷損毀
    
    流程：
    1. 將資料 json.dump 寫入 <file_path>.tmp 暫存檔
    2. 確認寫入成功（鹽驗檔案大小 > 0）
    3. 使用 os.replace() 作業系統級覆蓋原檔
    
    此方法確保在斷電或磁碟瞬斷時，原檔案不會發生 0KB 靜默損毀
    
    參數：
        data: 要寫入的 Python 字典
        file_path: 目標檔案路徑（支援相對路徑與絕對路徑）
    
    異常：
        ValueError: 若暫存檔寫入失敗或驗證失敗
        OSError: 若檔案系統操作失敗
    """
    
    if not isinstance(data, dict):
        raise ValueError(f"輸入資料必須為字典，但得到 {type(data).__name__}")
    
    if not file_path or not isinstance(file_path, str):
        raise ValueError("file_path 必須為非空字串")
    
    # ============ 步驟 1：確保目標目錄存在 ============
    file_path_obj = Path(file_path)
    file_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    # ============ 步驟 2：定義暫存檔路徑 ============
    tmp_path = str(file_path_obj) + ".tmp"
    tmp_path_obj = Path(tmp_path)
    
    # ============ 步驟 3：寫入暫存檔 ============
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        raise ValueError(
            f"寫入暫存檔失敗：{tmp_path}\n"
            f"  原因：{str(e)}"
        )
    
    # ============ 步驟 4：驗證暫存檔完整性 ============
    try:
        tmp_size = tmp_path_obj.stat().st_size
        if tmp_size == 0:
            raise ValueError("暫存檔寫入後大小為 0 位元組，寫入失敗")
        
        # 嘗試讀取並重新解析暫存檔，確認內容可還原
        with open(tmp_path, 'r', encoding='utf-8') as f:
            verify_data = json.load(f)
        
    except (IOError, json.JSONDecodeError) as e:
        # 清理失敗的暫存檔
        try:
            tmp_path_obj.unlink()
        except:
            pass
        raise ValueError(
            f"暫存檔驗證失敗：{tmp_path}\n"
            f"  原因：{str(e)}"
        )
    
    # ============ 步驟 5：原子覆蓋原檔案 ============
    try:
        # 在 Windows 上，若目標檔案已存在，os.replace() 會直接覆蓋
        # 在 macOS/Linux 上，同樣行為確保原子性
        os.replace(tmp_path, file_path)
    except OSError as e:
        # 清理失敗的暫存檔
        try:
            tmp_path_obj.unlink()
        except:
            pass
        raise OSError(
            f"原子覆蓋失敗：無法將 {tmp_path} 移動到 {file_path}\n"
            f"  原因：{str(e)}"
        )


# ============ 示範用法與單元測試 ============
if __name__ == "__main__":
    print("=" * 70)
    print("JSON 穩健處理中樞 - 單元測試")
    print("=" * 70)
    
    # ==================== 測試 1：基礎 Markdown 清洗 ====================
    print("\n【測試 1】基礎 Markdown 清洗 - 帶有 ```json 標籤")
    print("-" * 70)
    
    dirty_json_1 = """```json
{
    "title": "AI 短劇製造廠",
    "version": "7.8",
    "features": ["RPA", "DOM Sentinel", "Atomic Writes"]
}
```"""
    
    print(f"輸入（汙染）：\n{dirty_json_1}\n")
    
    try:
        result_1 = clean_and_parse_json(dirty_json_1)
        print(f"✅ 清洗成功：{result_1}\n")
    except Exception as e:
        print(f"❌ 錯誤：{e}\n")
    
    # ==================== 測試 2：未閉合括號自動補全 ====================
    print("【測試 2】未閉合括號自動補全")
    print("-" * 70)
    
    dirty_json_2 = """
    ```json
    {
        "status": "active",
        "items": [
            {"id": 1, "name": "item1"},
            {"id": 2, "name": "item2"
    ```
    """
    
    print(f"輸入（缺括號）：\n{dirty_json_2}\n")
    
    try:
        result_2 = clean_and_parse_json(dirty_json_2)
        print(f"✅ 清洗成功（自動補全括號）：\n{json.dumps(result_2, ensure_ascii=False, indent=2)}\n")
    except Exception as e:
        print(f"❌ 錯誤：{e}\n")
    
    # ==================== 測試 3：複雜嵌套結構 ====================
    print("【測試 3】複雜嵌套結構 + Markdown 污染")
    print("-" * 70)
    
    dirty_json_3 = """```json
{
    "project": "AI_DRAMA_FACTORY",
    "config": {
        "video_codec": "h264_videotoolbox",
        "paths": {
            "workspace": "/Volumes/AI_Workspace",
            "scripts": ["gear1_prod", "gear2_rnd", "common"]
        }
    }
}
```"""
    
    print(f"輸入（嵌套 + 污染）：\n{dirty_json_3}\n")
    
    try:
        result_3 = clean_and_parse_json(dirty_json_3)
        print(f"✅ 清洗成功：\n{json.dumps(result_3, ensure_ascii=False, indent=2)}\n")
    except Exception as e:
        print(f"❌ 錯誤：{e}\n")
    
    # ==================== 測試 4：原子寫入 - 建立 test.json ====================
    print("【測試 4】原子寫入防護 - 建立 test.json")
    print("-" * 70)
    
    test_data = {
        "project": "AI_DRAMA_FACTORY",
        "version": "7.8",
        "timestamp": "2026-03-27",
        "modules": {
            "gear1_prod": "RPA 與視覺生成",
            "gear2_rnd": "研發與風格分析",
            "common": "共用工具與基建"
        },
        "safety_features": [
            "Atomic Writes (原子寫入)",
            "JSON 暴力清洗",
            "WAL 模式防鎖死",
            "DOM 哨兵監控"
        ]
    }
    
    test_file_path = str(Path(__file__).parent / "test.json")
    
    print(f"準備寫入檔案：{test_file_path}\n")
    print(f"資料內容：\n{json.dumps(test_data, ensure_ascii=False, indent=2)}\n")
    
    try:
        atomic_write_json(test_data, test_file_path)
        print(f"✅ 原子寫入成功\n")
        
        # ============ 驗證：讀取並檢查檔案 ============
        print("【驗證】讀取檔案content...")
        with open(test_file_path, 'r', encoding='utf-8') as f:
            read_back = json.load(f)
        
        verify_match = read_back == test_data
        print(f"{'✅' if verify_match else '❌'} 檔案內容驗證：{'一致' if verify_match else '不一致'}")
        print(f"讀取回來的資料：\n{json.dumps(read_back, ensure_ascii=False, indent=2)}\n")
        
        # ============ 檢查是否生成暫存檔 ============
        tmp_file_path = test_file_path + ".tmp"
        if Path(tmp_file_path).exists():
            print(f"⚠️  警告：暫存檔仍存在（應已清理）：{tmp_file_path}")
        else:
            print(f"✅ 暫存檔已正確清理\n")
        
    except Exception as e:
        print(f"❌ 錯誤：{e}\n")
    
    # ==================== 測試 5：邊界案例 - 錯誤處理 ====================
    print("【測試 5】邊界案例 - 非字典結果")
    print("-" * 70)
    
    bad_json = '["this", "is", "array"]'
    print(f"輸入（陣列而非字典）：{bad_json}\n")
    
    try:
        result_5 = clean_and_parse_json(bad_json)
        print(f"❌ 不應該成功：{result_5}")
    except TypeError as e:
        print(f"✅ 正確拋出 TypeError：{str(e)[:80]}...\n")
    except Exception as e:
        print(f"❌ 意外的異常型態：{type(e).__name__}: {e}\n")
    
    print("=" * 70)
    print("所有測試完成")
    print("=" * 70)
