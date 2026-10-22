#!/usr/bin/env python3
"""Istanbul Eczaci Odasi nobetci listesi (ANA KAYNAK) - 20 Ekim. (23 Ekim: TESHIS ciktisi eklendi)
Sayfayi gercek tarayiciyla (Playwright) acar, sayfanin kendi yaptigi JSON istegini
(tum Istanbul) yakalar ve data/odasi-bugun.json'a yazar. senkronize.py bunu okur.
Basarisiz olursa dosyaya DOKUNMAZ (eski sistem devreye girer) ve cikis kodu 0 doner.
Veri cekme mantigi AYNI; sadece basarisizlikta NEDEN'i log'a yazar ([TESHIS] satirlari)."""
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
    teshis = []  # her istek/cevap icin kisa not

    def yakala(r):
        try:
            if r.request.method == "POST":
                govde = ""
                try:
                    govde = r.text()
                except Exception as e:
                    govde = "<okunamadi: %s>" % str(e)[:60]
                teshis.append("POST %s -> HTTP %s, %d bayt, ilk100=%r" % (r.url[:90], r.status, len(govde), govde[:100]))
            if "nobetci-eczane/index.php" in r.url and r.request.method == "POST":
                d = json.loads(r.text())
                if isinstance(d, dict) and isinstance(d.get("eczaneler"), list):
                    sonuc["liste"] = d["eczaneler"]
                    teshis.append("  -> liste yakalandi: %d kayit" % len(d["eczaneler"]))
                else:
                    teshis.append("  -> JSON ama 'eczaneler' listesi yok; anahtarlar=%s" % (list(d.keys())[:8] if isinstance(d, dict) else type(d).__name__))
        except Exception as e:
            teshis.append("  -> yakalama hatasi: %s" % str(e)[:100])

    with sync_playwright() as p:
        t = p.chromium.launch()
        s = t.new_page(viewport={"width": 1300, "height": 1400}, locale="tr-TR")
        s.on("response", yakala)
        durum = None
        try:
            yanit = s.goto(URL, wait_until="networkidle", timeout=60000)
            durum = yanit.status if yanit else None
            s.wait_for_timeout(4000)
            baslik = s.title()
            govde = (s.inner_text("body") or "").replace("\n", " ")[:160]
            teshis.append("sayfa: HTTP %s, baslik=%r, govde=%r" % (durum, baslik, govde))
        except Exception as e:
            teshis.append("sayfa acilamadi: %s" % str(e)[:150])
        t.close()
    if "liste" not in sonuc:
        for satir in teshis[:12]:
            print("[TESHIS] " + satir)
        if not teshis:
            print("[TESHIS] hic POST istegi gorulmedi")
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
