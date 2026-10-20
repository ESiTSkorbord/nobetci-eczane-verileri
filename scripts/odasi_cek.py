#!/usr/bin/env python3
"""Istanbul Eczaci Odasi nobetci listesi (ANA KAYNAK) - 20 Ekim.
Sayfayi gercek tarayiciyla (Playwright) acar, sayfanin kendi yaptigi JSON istegini
(tum Istanbul) yakalar ve data/odasi-bugun.json'a yazar. senkronize.py bunu okur.
Basarisiz olursa dosyaya DOKUNMAZ (eski sistem devreye girer) ve cikis kodu 0 doner."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

URL = "https://www.istanbuleczaciodasi.org.tr/nobetci-eczane/"
KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CIKTI = os.path.join(KOK, "data", "odasi-bugun.json")


def cek():
    sonuc = {}

    def yakala(r):
        try:
            if "nobetci-eczane/index.php" in r.url and r.request.method == "POST":
                d = json.loads(r.text())
                if isinstance(d, dict) and isinstance(d.get("eczaneler"), list):
                    sonuc["liste"] = d["eczaneler"]
        except Exception:
            pass

    with sync_playwright() as p:
        t = p.chromium.launch()
        s = t.new_page(viewport={"width": 1300, "height": 1400}, locale="tr-TR")
        s.on("response", yakala)
        s.goto(URL, wait_until="networkidle", timeout=60000)
        s.wait_for_timeout(4000)
        t.close()
    return sonuc.get("liste")


def main():
    liste = None
    for deneme in range(3):
        try:
            liste = cek()
        except Exception as e:
            print("Odasi cekme hatasi (deneme %d): %s" % (deneme + 1, str(e)[:200]))
        if liste and len(liste) >= 20:
            break
    if not liste or len(liste) < 20:
        print("Odasi verisi alinamadi/supheli (%s kayit) - dosya degistirilmedi." % (len(liste) if liste else 0))
        return 0
    z = datetime.now(timezone(timedelta(hours=3)))
    eczaneler = [{"sicil": e.get("sicil"), "ad": (e.get("eczane_ad") or "").strip(), "tel": e.get("eczane_tel"),
                  "ilce": e.get("ilce"),
                  "adres": " ".join(x for x in [e.get("mahalle"), e.get("cadde_sokak"), e.get("bina_kapi")] if x).strip()}
                 for e in liste]
    os.makedirs(os.path.dirname(CIKTI), exist_ok=True)
    with open(CIKTI, "w", encoding="utf-8") as f:
        json.dump({"zaman": z.strftime("%Y-%m-%d %H:%M"), "adet": len(eczaneler), "eczaneler": eczaneler},
                  f, ensure_ascii=False, indent=1)
    print("Odasi: %d eczane yazildi (%s)" % (len(eczaneler), z.strftime("%H:%M")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
