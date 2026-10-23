#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
广州好去处 - GitHub Actions 自动刷新脚本
功能：抓取广州未来7天天气（Open-Meteo 免费API，无需key），
      重写 index.html 的天气卡与更新日期。
无第三方依赖；网络失败/解析失败时直接退出 0、不提交。
"""
import json, re, sys, urllib.request, datetime

INDEX_HTML = "index.html"
LAT, LON = 23.13, 113.26

WMO = {0:"晴",1:"大部晴",2:"多云",3:"阴",45:"雾",48:"雾凇",
       51:"小毛毛雨",53:"毛毛雨",55:"大毛毛雨",56:"冻雨",57:"冻雨",
       61:"小雨",63:"中雨",65:"大雨",66:"冻雨",67:"冻雨",
       71:"小雪",73:"中雪",75:"大雪",77:"雪粒",80:"小阵雨",
       81:"阵雨",82:"强阵雨",85:"小阵雪",86:"大阵雪",95:"雷暴",
       96:"雷暴伴冰雹",99:"雷暴伴冰雹"}

def fetch_weather():
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%.2f&longitude=%.2f"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           "&timezone=Asia%%2FShanghai&forecast_days=7" % (LAT, LON))
    req = urllib.request.Request(url, headers={"User-Agent":"gz-haochuqu/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def day_label(date_str):
    m, d = date_str[5:].split("-")
    return "%d/%d" % (int(m), int(d))

def main():
    try:
        data = fetch_weather()
        d = data["daily"]
    except Exception as e:
        print("[skip] weather fetch failed:", e)
        return 0

    days = list(zip(d["time"], d["weather_code"],
                     d["temperature_2m_max"], d["temperature_2m_min"],
                     d["precipitation_probability_max"]))
    # days[0]=今天，前段=后3天(d1-d3)，后段=d4-d6
    front = days[1:4]; back = days[4:7]

    def avg(xs): return sum(xs)/len(xs)
    f_rain = avg([x[4] for x in front]); b_rain = avg([x[4] for x in back])
    f_tmax = avg([x[2] for x in front]); b_tmax = avg([x[2] for x in back])

    def score(rain, tmax):
        s = 96 - rain*0.55 - max(0, tmax-32)*1.6 - max(0, 18-tmax)*0.8
        return max(55, min(98, round(s)))
    f_score, b_score = score(f_rain, f_tmax), score(b_rain, b_tmax)

    # 天气描述文案
    def seg_text(seg):
        labels = [WMO.get(c, "天气") for _, c, _, _, _ in seg]
        temps = "%d–%d℃" % (min(x[3] for x in seg), max(x[2] for x in seg))
        rainmax = max(x[4] for x in seg)
        kinds = set(labels)
        rainy = any(("雨" in k) for k in kinds)
        dates = "%s–%s" % (day_label(seg[0][0]), day_label(seg[-1][0]))
        if rainy and rainmax >= 40:
            return "🌧 %s（%s）有雨，降水概率约%d%%" % (dates, temps, rainmax), \
                   "出门带伞，雨中活动选室内展/市集更稳妥"
        elif rainy:
            return "🌦 %s（%s）局部小雨，降水概率约%d%%" % (dates, temps, rainmax), \
                   "随身带把折叠伞，午后偏热注意补水"
        else:
            return "☀️ %s（%s）晴好少雨" % (dates, temps), \
                   "适合户外古街/公园/citywalk，注意防晒"

    f_title, f_advice = seg_text(front)
    b_title, b_advice = seg_text(back)

    rain_share = round(f_rain)
    sun_share = 100 - rain_share

    # 详情：逐日
    lines = []
    for date_str, code, tmax, tmin, pr in days[1:]:
        lines.append("%s %s %d–%d℃（降水概率%d%%）" % (
            day_label(date_str), WMO.get(code,""), tmin, tmax, pr))
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")
    detail = "；".join(lines[:3]) + "。<br>" + "；".join(lines[3:]) + "。<br>"
    if rain_share >= 40:
        detail += "前段有雨优先安排展览/电影/市集等室内活动，后段转晴后适合户外出行。"
    else:
        detail += "整段天气晴好适宜，昼夜温差渐大，早晚加件薄外套即可。"

    tip = ("前段有雨室内优先 → 后段晴好户外最佳" if rain_share >= 40
           else "整段适合出门，周末安排户外或室内都从容")

    html = open(INDEX_HTML, encoding="utf-8").read()
    orig = html

    # 1) UPDATED 日期
    html = re.sub(r"const UPDATED = '\d{4}-\d{2}-\d{2}';",
                  "const UPDATED = '%s';" % today, html)
    # 2) 指数
    html = re.sub(r'<span class="weather-index">前段 <b>\d+</b> · 后段 <b>\d+</b>/100</span>',
                  '<span class="weather-index">前段 <b>%d</b> · 后段 <b>%d</b>/100</span>' % (f_score, b_score),
                  html)
    # 3) 两个 slot
    new_slots = (
        '<div class="weather-slot rain">\n'
        '          <span class="slot-t">%s</span>\n'
        '          %s\n'
        '        </div>\n'
        '        <div class="weather-slot sun">\n'
        '          <span class="slot-t">%s</span>\n'
        '          %s\n'
        '        </div>' % (f_title, f_advice, b_title, b_advice))
    html, n = re.subn(
        r'<div class="weather-slot rain">.*?</div>\s*<div class="weather-slot sun">.*?</div>',
        lambda m: new_slots, html, count=1, flags=re.S)
    if n != 1: print("[warn] weather slots anchor not matched")
    # 4) 晴好进度条
    html = re.sub(r'<div class="weather-bar-seg rain" style="width:\d+%;"></div>',
                  '<div class="weather-bar-seg rain" style="width:%d%%;"></div>' % rain_share, html)
    html = re.sub(r'<div class="weather-bar-seg sun" style="width:\d+%;"></div>',
                  '<div class="weather-bar-seg sun" style="width:%d%%;"></div>' % sun_share, html)
    # 5) tip
    html = re.sub(r'<div class="weather-tip">.*?</div>',
                  '<div class="weather-tip">%s</div>' % tip, html, count=1, flags=re.S)
    # 6) detail
    html = re.sub(r'(<div class="weather-detail" id="weatherDetail">).*?(</div>)',
                  lambda m: m.group(1) + detail + m.group(2), html, count=1, flags=re.S)

    if html != orig:
        open(INDEX_HTML, "w", encoding="utf-8").write(html)
        print("[ok] weather refreshed: front=%d back=%d rain_share=%d date=%s"
              % (f_score, b_score, rain_share, today))
    else:
        print("[skip] no change")
    return 0

if __name__ == "__main__":
    sys.exit(main())
