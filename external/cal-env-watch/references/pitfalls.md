# Pitfalls — 實際上線踩過的坑

## 1. Cron 環境沒有 npm-global PATH

**症狀**：cron 跑的時候 `openclaw` 指令找不到。

**原因**：cron 子進程的 PATH 通常不含 `C:\Users\<user>\AppData\Roaming\npm`。

**解法**（`cal_env_watch.py` 內）：

```python
oc = shutil.which('openclaw')
if not oc:
    # 試 npm-global shim
    candidates = [
        Path(os.environ.get('APPDATA', '')) / 'npm' / 'openclaw.cmd',
        Path(os.environ.get('APPDATA', '')) / 'npm' / 'openclaw.ps1',
        Path(os.environ.get('APPDATA', '')) / 'npm' / 'openclaw',
    ]
    for c in candidates:
        if c.exists():
            oc = str(c)
            break
```

## 2. Windows cp950/cp936 emoji crash

**症狀**：`subprocess.run(['openclaw', 'message', 'send', ...])` 收到 emoji 訊
息時，Python 解析 stderr 拋 `UnicodeDecodeError`。

**解法**：

```python
result = subprocess.run(
    [...],
    capture_output=True,
    text=True,
    encoding='utf-8',       # ← 關鍵
    errors='replace',       # ← 關鍵
    timeout=30,
)
```

外加主程式最上面：
```python
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
```

## 3. LLM agent 把回應當訊息送出去

**症狀**：cron 用 LLM agent 跑 `cal_env_watch.py` 時，LLM 的回答（"我跑了，
沒有警告"之類）會被 cron 的 delivery 機制自動送 Telegram，跟腳本自己送的
訊息雙重洗版。

**解法**：cron 設 `delivery.mode = "none"`，並在 prompt 明確告訴 agent
"只跑一行指令、貼結果就好，不要自己寫訊息"。

## 4. Cron delivery 沒配 target

**症狀**：cron 設了 `delivery.mode = "announce"` 但沒給 `--to`，會 fail-closed
整個 job 失敗。

**解法**：兩種選項：
- A) `delivery.mode = "none"`（腳本自己送 Telegram，**推薦**）
- B) `delivery.mode = "announce"` + `--channel telegram --to <chat_id> --announce`
  （LLM agent 寫一段總結送 Telegram）

A 是預設；只有當 LLM 要寫「今天 AQI 摘要」這種 human 友善總結時才用 B。

## 5. RRULE UNTIL 用 UTC，差 8 小時

**症狀**：預期 `UNTIL=20260626T235959Z` 跑到 6/26 23:59:59 +08，但 Google
Calendar 把它當 UTC 解讀，6/26 16:00 之後就不觸發。

**解法**：台灣時區要扣 8 小時。`UNTIL=20260626T155959Z` 才是 6/26 23:59:59 +08。

`insert_class_schedule.py` 內：
```python
UNTIL_UTC = "20260626T155959Z"  # 6/26 23:59:59 +08 in UTC
```

## 6. OAuth scope 升級要重 consent

**症狀**：把 `calendar.readonly` 的 refresh_token 直接拿來跑 write API，
Google 會回 403 insufficient scope。

**解法**：一定要跑完整 OAuth flow（`oauth_calendar_write.py`），新發的
refresh_token 才有 write 權限。**不要試著在現有 token 上加 scope** —
Google 不會自動合併。

## 7. Location 沒 match 用 default

**症狀**：event location 寫「台北市信義區」，LOCATION_KEYWORDS 全沒 match，
腳本用 default (台中中區) 抓 AQI，結果完全無關。

**解法**：
- 看到 warning 訊息中 loc_label 有 "→ default" 後綴就知道 fallback 了
- 解決：把那個地點加進 LOCATION_KEYWORDS

## 8. 連假/颱風假事件不觸發

**症狀**：event 在行事曆但被官方取消（例如颱風假），cal_env_watch 還是會發
警告。

**解法**：`fetch_calendar_events` 已經有 `if ev.get("status") == "cancelled":
continue`，但「沒改成 cancelled 但實際不上課」的情況（學校自己宣佈）抓不
到。要嘛手動刪 event，要嘛暫時加 keyword 跳過那段日期。

## 9. 行程 ID 太長塞不下 dedup state

**症狀**：(理論上) recurring event 展開後每個 occurrence 有自己的 instance
ID，state 檔案可能爆。

**現況**：實際上還沒遇過（課程表每週幾個 events × 學期 18 週 = 162 個 entries
就差不多）。如果遇到，state 改用 `event["id"].split('_')[0]` (去掉後面的日期)
當 key。
