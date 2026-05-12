# SKILL.md — AQI Knowledge Base

## Purpose

Authoritative reference material on air-quality thresholds, health effects,
and Taiwan-specific standards. The `analyst` and `advisor` agents should
prefer answers grounded in these documents over general training knowledge.

## What lives in `docs/`

| File | Source | License |
|------|--------|---------|
| `who-aqg-2021.pdf` | https://iris.who.int/handle/10665/345329 | CC BY-NC-SA 3.0 IGO |
| `epa-naaqs.html` | https://www.epa.gov/criteria-air-pollutants/naaqs-table | US Public Domain |
| `taiwan-aqi-standard.html` | https://airtw.moenv.gov.tw/CHT/Information/Standard/AirQualityIndicator.aspx | Taiwan ODL v1.0 |
| `lancet-2023-pm25-cv.html` | https://www.thelancet.com/journals/lanplh/article/PIIS2542-5196(23)00047-5/fulltext | Article-specific (often CC BY 4.0) |

Run `scripts/build_knowledge.bat` (Windows) or `scripts/build_knowledge.sh`
to fetch these into `docs/`.

## How agents should use this skill

When asked about:

- **AQI threshold definitions** → cite Taiwan AQI 標準 (taiwan-aqi-standard).
- **PM2.5 daily / annual limits** → WHO AQG 2021 (5 / 15 μg/m³) and US EPA NAAQS (35 / 12 μg/m³). Cite both side-by-side when relevant.
- **Health effects of PM2.5** → WHO AQG 2021 chapter on PM2.5, plus Lancet 2023 for cardiovascular-specific data (3-5× pulmonary deposition under vigorous exercise at elevated PM2.5).
- **Sensitive groups (老人 / 幼童 / 氣喘 / 心血管 / 孕婦)** → WHO AQG 2021 sensitive populations annex.

## Citation format (required)

When an agent answers using this skill, end the response with:

```
📚 引用：
- WHO AQG 2021, Chapter X
- Taiwan AQI 標準（環境部）
```

Do NOT cite documents not in this `docs/` folder. If the user asks about
something not covered (e.g., specific pollutant we don't have a doc on),
the agent must say "本知識庫沒有這項資訊" rather than guess.

## Rebuild index

If you add/replace files in `docs/`, OpenClaw will re-index on next agent
turn. To force immediate reindex:

```
openclaw memory reindex --skill aqi-knowledge
```

(Skill-aware reindex command — verify exact flag on your OpenClaw version.)
