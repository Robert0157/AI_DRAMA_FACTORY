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
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


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
    # 移除 ```json / ```python / ``` 等任意語言標籤的開頭圍欄
    # 【v15.12.1 RCA 修正】舊版 (?:json)? 僅匹配 json，LLM 以 ```python 包裝時留下 python\nimport json\nmetadata = 前綴
    cleaned = re.sub(r'```[a-zA-Z0-9_+-]*\s*\n?', '', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n?```', '', cleaned)
    
    # 移除其他常見 Markdown 污染 (如 ` 符號、~~ 刪除線等)
    cleaned = re.sub(r'^```.*?```$', '', cleaned, flags=re.MULTILINE | re.DOTALL)
    cleaned = re.sub(r'`{1,2}', '', cleaned)
    cleaned = re.sub(r'~~', '', cleaned)

    # ============ 第二步：去除行首行尾空白 ============
    cleaned = cleaned.strip()

    # ============ 第二步 bis：定位首個 '{' 截斷 LLM 前置說明文字 ============
    # 【v15.10/11 RCA 修正】應對 MiniMax/Gemini 回傳 "Sure! Here is the JSON:..." 前綴
    # 舊版 _clean_json_response 有此步驟，新版 clean_and_parse_json 遺漏導致頻繁 JSONDecodeError
    brace_start = cleaned.find('{')
    if brace_start > 0:
        cleaned = cleaned[brace_start:]

    # ============ 第二‧九步：Python 語法正規化 ============
    # 【v15.12.1 RCA 修正】LLM 以 ```python 包裝時，布林值與 None 用 Python 大寫語法
    # 導致 JSON 解析「Expecting value」(e.g. True → true, False → false, None → null)
    # \b 確保不誤替換字串值中的 True/False 子字串（如 "TrueColor"）
    cleaned = re.sub(r'\bTrue\b',  'true',  cleaned)
    cleaned = re.sub(r'\bFalse\b', 'false', cleaned)
    cleaned = re.sub(r'\bNone\b',  'null',  cleaned)
    # 去除 Python dict/list 尾隨逗號（,} 或 ,]），JSON 不允許
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

    # ============ 第三步：未閉合括號自動補全 ============
    # 【v15.12.1 RCA 修正】字串感知掃描器：不計算字串值內的 [ ] { }
    # 修正根因：description 含 [Your Live Stream URL] 等方括號時，舊版 str.count() 計數偏高
    # 導致自動補的 ] 插入到未閉合字串值中，Phase A/B/C 三階段全失敗。
    _open_sq = _close_sq = _open_cu = _close_cu = 0
    _in_str = _esc = False
    for _ch in cleaned:
        if _esc:
            _esc = False
            continue
        if _ch == '\\' and _in_str:
            _esc = True
            continue
        if _ch == '"':
            _in_str = not _in_str
            continue
        if not _in_str:
            if _ch == '[':   _open_sq  += 1
            elif _ch == ']': _close_sq += 1
            elif _ch == '{': _open_cu  += 1
            elif _ch == '}': _close_cu += 1
    # JSON 截斷於字串值中間時，先補 " 關閉字串，再補結構括號
    if _in_str:
        cleaned += '"'
    if _open_sq > _close_sq:
        cleaned += ']' * (_open_sq - _close_sq)
    if _open_cu > _close_cu:
        cleaned += '}' * (_open_cu - _close_cu)
    
    # ============ 第四步：安全 JSON 解析 ============
    # 【v15.10/11 RCA 修正】三階段解析：
    #   Phase A — 標準嚴格模式（strict=True）
    #   Phase B — 容錯模式（strict=False）：應對 LLM 在字串值中插入 literal newline/tab
    #   Phase C — 迭代式未跳脫引號修復：應對 LLM 在 prompt 欄位插入未跳脫 "
    #             "Expecting ',' delimiter" 錯誤的根本原因（surreal/dark 風格高頻觸發）
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            result = json.JSONDecoder(strict=False).decode(cleaned)
        except json.JSONDecodeError as _e_b:
            # Phase C: 逐一修復未跳脫雙引號（最多 40 次）
            _fixed = cleaned
            _result_c = None
            _dec = json.JSONDecoder(strict=False)
            for _i in range(40):
                try:
                    _result_c = _dec.decode(_fixed)
                    break
                except json.JSONDecodeError as _e_c:
                    if _e_c.pos < len(_fixed) and _fixed[_e_c.pos] == '"':
                        # 直接命中：錯誤位置就是多餘的 "
                        _fixed = _fixed[:_e_c.pos] + '\\"' + _fixed[_e_c.pos + 1:]
                    elif 'delimiter' in str(_e_c):
                        # 「Expecting ',' delimiter」型態：字串提前結束，錯誤位置前可能有空白
                        # 向後掃描跳過空白，找到最近的 " 並跳脫
                        _back = _e_c.pos - 1
                        while _back >= 0 and _fixed[_back] in ' \t\r\n':
                            _back -= 1
                        if _back >= 0 and _fixed[_back] == '"':
                            _fixed = _fixed[:_back] + '\\"' + _fixed[_back + 1:]
                        else:
                            break  # 非引號型錯誤，無法繼續修復
                    else:
                        break  # 非引號錯誤，無法繼續自動修復
            if _result_c is not None:
                result = _result_c
            else:
                # 三階段均失敗，提供清晰的診斷訊息
                error_msg = (
                    f"JSON 解析失敗\n"
                    f"  錯誤型態：{type(_e_b).__name__}\n"
                    f"  錯誤訊息：{str(_e_b)}\n"
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


def parse_llm_json_response(
    response_text: str,
    max_retries_on_decode_error: int = 0,
    log_context: str = "",
) -> dict:
    """
    【v15.10 統一入口】全產線 LLM JSON 解析唯一通道。
    
    功能：
    1. 三重清洗（Markdown + 前置文字截斷 + 括號補全）
    2. 失敗重試機制（呼叫方按需啟用）
    3. 統一落地日誌
    
    參數：
        response_text: LLM 回傳原始文字
        max_retries_on_decode_error: JSON 解碼失敗時自動補全括號的重試次數（預設 0）
        log_context: 日誌上下文標籤（如 "MiniMax", "Gemini", "Zhipu"）
    
    回傳：
        dict: 清洗後的 JSON 字典
    
    異常：
        ValueError: JSON 無法解析時拋出，含清晰診斷訊息
    """
    if not response_text or not isinstance(response_text, str):
        raise ValueError("LLM 回應必須為非空字串")

    result = None
    last_error = None

    for attempt in range(max_retries_on_decode_error + 1):
        try:
            # 步驟 1-3：委派給核心清洗函式
            result = clean_and_parse_json(response_text)
            break
        except (ValueError, TypeError) as e:
            last_error = e
            if attempt < max_retries_on_decode_error:
                # 嘗試更激進的清洗：移除所有控制字元後再試
                import time, random
                response_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', response_text)
                backoff = min(2 ** attempt, 5) + random.uniform(0, 0.5)
                if log_context:
                    logger.warning(
                        "[%s] JSON 解析失敗 (attempt %d/%d)，%.1fs 後重試: %s",
                        log_context, attempt + 1, max_retries_on_decode_error, backoff, str(e)[:120]
                    )
                time.sleep(backoff)
            else:
                if log_context:
                    logger.error(
                        "[%s] JSON 最終解析失敗 (%d attempts): %s",
                        log_context, max_retries_on_decode_error + 1, str(e)[:200]
                    )

    if result is not None:
        return result

    raise ValueError(
        f"LLM JSON 解析最終失敗 ({log_context}): {last_error}\n"
        f"清洗後文本前 300 字元: {response_text[:300]}"
    )


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
