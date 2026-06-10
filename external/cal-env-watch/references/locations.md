# Location Keywords

`cal_env_watch.py` 用 `LOCATION_KEYWORDS` 把 event 的 `location` 欄位 substring
比對（lowercase）後，解析成 (lat, lon, label)，再去抓最近 EPA 測站 + Open-Meteo
預報。

## 內建清單（2026-06-09 版）

| Keywords (lowercase substring match) | Lat | Lon | Label |
|---|---|---|---|
| 中科大, 中臺, 台中科大, 臺中科大, ntcust, ntcu | 24.1108 | 120.6156 | 台中科大 |
| 西屯 | 24.1614 | 120.6057 | 西屯 |
| 北屯 | 24.1826 | 120.6865 | 北屯 |
| 逢甲, fcu, fcu.edu | 24.1786 | 120.6467 | 逢甲大學 |
| 東海, thu | 24.1810 | 120.6030 | 東海大學 |
| 中興, nchu | 24.1210 | 120.6768 | 中興大學 |
| 中國醫, cmuh, 中醫大 | 24.1495 | 120.6845 | 中國醫藥大學 |
| 台中車站, 臺中車站, 台中火車站, 中區 | 24.1370 | 120.6868 | 台中車站 |
| 新光三越, 中港, 老虎城 | 24.1650 | 120.6390 | 新光三越/老虎城 |
| 勤美, 草悟道, 國美館, 西區 | 24.1423 | 120.6630 | 勤美/草悟道 |

**Default** (沒 match 到時): 24.1469, 120.6476 (台中中區) + label "台中 (default)"。

## 配對規則

```python
for keywords, coord, label in LOCATION_KEYWORDS:
    if any(k.lower() in loc.lower() for k in keywords):
        return coord[0], coord[1], label
```

- 全部 lowercase 後比對
- 任一 keyword substring 命中即 return
- 第一個 match 的優先

## 對 event location 欄位的建議格式

當用 `insert_class_schedule.py`（或任何批次新增）建立 event 時，location
欄位建議寫成：

```
臺中科技大學 (台中科大) 教室2903
```

這樣：
- 人類讀起來是「臺中科技大學...教室2903」清楚
- 「台中科大」substring 命中 keyword set → 自動 fallback 到 (24.1108, 120.6156)
- 體育課沒填教室時只寫「臺中科技大學 (台中科大)」也 match

⚠️ 注意台/臺異體字：keyword set 兩個都有，event location 用任一都 OK。

## 加新地點

要加新地點（例如「台中高工」、「中興大學附屬高中」）：

1. 在 `scripts/cal_env_watch.py` 的 `LOCATION_KEYWORDS` list 開頭插入新 tuple
2. Lat/Lon 用 Google Maps 右鍵查
3. Label 用「校名/地標名 (簡稱)」
4. 測試：`python scripts\cal_env_watch.py --dry-run` + 一個有那個 location 的 event

範例：
```python
({"台中高工", "ntct"}, (24.1423, 120.6853), "台中高工"),
```

## 沒 match 時會發生什麼

- 用 default (台中中區) 抓 AQI + 天氣
- Warning 訊息中 loc_label 會加 "→ default" 後綴讓人知道 fallback 了
- 這設計是為「少抓一筆」比「跳過」好（總比沒預警好）
