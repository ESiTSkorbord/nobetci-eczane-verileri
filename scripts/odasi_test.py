#!/usr/bin/env python3
"""Istanbul Eczaci Odasi nobetci sayfasi DENEME - sadece okur, data/ klasorune dokunmaz.
Gercek tarayici (Chromium) ile sayfayi acar, ilceyi secer, gorunen metni + ekran goruntusunu test/odasi/ altina yazar."""
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

URL = "https://www.istanbuleczaciodasi.org.tr/nobetci-eczane/"
ILCELER = ["KARTAL", "MALTEPE"]


def norm(s):
    s = (s or "").strip()
    s = s.replace("İ", "I").replace("ı", "I").replace("i", "I")
    return " ".join(s.upper().split())


def main():
    zaman = datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d_%H%M")
    os.makedirs("test/odasi", exist_ok=True)
    with sync_playwright() as p:
        tarayici = p.chromium.launch()
        sayfa = tarayici.new_page(viewport={"width": 1300, "height": 2400}, locale="tr-TR")
        yanit = sayfa.goto(URL, wait_until="networkidle", timeout=60000)
        print("HTTP:", yanit.status if yanit else None, "baslik:", sayfa.title())
        sayfa.wait_for_timeout(3000)
        secenekler = sayfa.evaluate(
            """() => Array.from(document.querySelectorAll('select')).map(s => ({
                 id: s.id, name: s.name, secenekler: Array.from(s.options).map(o => ({d: o.value, t: o.text}))}))""")
        print("select sayisi:", len(secenekler))
        for s in secenekler:
            print("  select id=%r name=%r secenek=%d" % (s["id"], s["name"], len(s["secenekler"])))
        for ilce in ILCELER:
            sonuc = None
            for idx, s in enumerate(secenekler):
                for o in s["secenekler"]:
                    if norm(o["t"]) == ilce or norm(o["d"]) == ilce:
                        sonuc = (idx, o)
            if not sonuc:
                print("[%s] ilce secenegi bulunamadi" % ilce)
                continue
            idx, o = sonuc
            sayfa.locator("select").nth(idx).select_option(value=o["d"])
            sayfa.wait_for_timeout(6000)
            govde = sayfa.inner_text("body")
            with open("test/odasi/%s_%s.txt" % (zaman, ilce.lower()), "w", encoding="utf-8") as f:
                f.write(govde)
            with open("test/odasi/%s_%s.html" % (zaman, ilce.lower()), "w", encoding="utf-8") as f:
                f.write(sayfa.content())
            sayfa.screenshot(path="test/odasi/%s_%s.png" % (zaman, ilce.lower()), full_page=True)
            print("\n=== %s ===" % ilce)
            print(govde[:3000])
        tarayici.close()


if __name__ == "__main__":
    main()
