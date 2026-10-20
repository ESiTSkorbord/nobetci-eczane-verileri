#!/usr/bin/env python3
"""Istanbul Eczaci Odasi nobetci sayfasi DENEME (2. surum) - sadece okur, data/ klasorune dokunmaz.
Gercek tarayici ile sayfayi acar, ilce menusune gercekten tiklayip ilceyi secer,
gorunen metni, ekran goruntusunu ve sayfanin yaptigi AG ISTEKLERINI (veri nereden geliyor) test/odasi/ altina yazar."""
import os
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

URL = "https://www.istanbuleczaciodasi.org.tr/nobetci-eczane/"
ILCELER = ["Kartal", "Maltepe"]
CIKTI = "test/odasi"


def main():
    zaman = datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d_%H%M")
    os.makedirs(CIKTI, exist_ok=True)
    istekler = []

    with sync_playwright() as p:
        tarayici = p.chromium.launch()
        sayfa = tarayici.new_page(viewport={"width": 1300, "height": 1400}, locale="tr-TR")

        def yanit_yakala(r):
            try:
                url = r.url
                if "yandex" in url or "google" in url or "facebook" in url or "twitter" in url:
                    return
                tur = r.headers.get("content-type", "")
                satir = "%s %s %s" % (r.status, r.request.method, url)
                istekler.append(satir)
                if any(x in tur for x in ("json", "text/plain", "text/html", "javascript")) and "n.min.js" not in url:
                    govde = r.text()
                    if len(govde) < 200000:
                        ad = "%s/%s_xhr_%d.txt" % (CIKTI, zaman, len(istekler))
                        with open(ad, "w", encoding="utf-8") as f:
                            f.write(satir + "\n\n" + govde)
            except Exception as e:
                istekler.append("yakalama hatasi: %s" % e)

        sayfa.on("response", yanit_yakala)
        sayfa.goto(URL, wait_until="networkidle", timeout=60000)
        sayfa.wait_for_timeout(3000)

        for ilce in ILCELER:
            print("\n=== %s ===" % ilce)
            try:
                # jQuery UI selectmenu: gorunen dugmeye tikla, acilan listeden ilceyi sec
                sayfa.locator("#ilce-button, .ui-selectmenu-button").first.click(timeout=10000)
                sayfa.wait_for_timeout(800)
                sayfa.locator("ul.ui-menu li, .ui-selectmenu-menu li").filter(has_text=ilce).first.click(timeout=10000)
                sayfa.wait_for_timeout(6000)
            except Exception as e:
                print("secim hatasi:", str(e)[:300])
            govde = sayfa.inner_text("body")
            with open("%s/%s_%s.txt" % (CIKTI, zaman, ilce.lower()), "w", encoding="utf-8") as f:
                f.write(govde)
            sayfa.screenshot(path="%s/%s_%s.png" % (CIKTI, zaman, ilce.lower()))
            print(govde[:2500])

        tarayici.close()

    with open("%s/%s_aglar.txt" % (CIKTI, zaman), "w", encoding="utf-8") as f:
        f.write("\n".join(istekler))
    print("\n--- Ag istekleri ---")
    print("\n".join(istekler[:60]))


if __name__ == "__main__":
    main()
