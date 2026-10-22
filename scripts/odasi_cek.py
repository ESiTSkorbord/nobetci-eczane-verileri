#!/usr/bin/env python3
"""Istanbul Eczaci Odasi nobetci listesi (ANA KAYNAK).
23 Ekim: Odasi sitesi YENILENDI. Eski tek-istek (nobetci-eczane/index.php, POST) kalkti; yeni site
ilce ilce JSON veriyor: GET /api/nobetci-eczane-web/?action=district&id=<ilceId>
(cevap: {"success":true,"data":[{sicil,ad,ilce,ilceId,adres,nobetTarih,...}],"meta":{...}}).
Yeni cevapta telefon YOK (sadece phoneTicket) -> tel bos birakilir; senkronize.py telefonu
tumlisteden isimle tamamlar. Cikti formati ESKISIYLE AYNI (data/odasi-bugun.json), senkronize.py degismez.
Sayfayi gercek tarayiciyla acar (cerez/koruma icin), sonra sayfanin icinden ilce id'lerini tarar.
Basarisiz olursa dosyaya DOKUNMAZ (eski sistem devreye girer) ve cikis kodu 0 doner."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

URL = "https://www.istanbuleczaciodasi.org.tr/nobetci-eczane/"
API = "/api/nobetci-eczane-web/?action=district&id="
ILCE_ID_ARALIK = range(1, 61)  # Istanbul ilce id'leri (Maltepe=22); bos donenler atlanir
KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CIKTI = os.path.join(KOK, "data", "odasi-bugun.json")

JS_TARA = """
async ([api, ids]) => {
  const out = [];
  for (const id of ids) {
    try {
      const r = await fetch(api + id, {headers: {"Accept": "application/json"}});
      const t = await r.text();
      out.push([id, r.status, t]);
    } catch (e) {
      out.push([id, 0, String(e).slice(0, 80)]);
    }
    await new Promise(res => setTimeout(res, 120));
  }
  return out;
}
"""


def ilce_yanitini_coz(metin):
    """Bir ilce cevabini (JSON metni) senkronize.py'nin bekledigi kayit listesine cevirir. Hata -> []."""
    try:
        d = json.loads(metin)
    except Exception:
        return []
    if not isinstance(d, dict) or not d.get("success") or not isinstance(d.get("data"), list):
        return []
    sonuc = []
    for e in d["data"]:
        if not isinstance(e, dict) or not e.get("ad"):
            continue
        adres = (e.get("adres") or "").strip()
        if not adres:
            adres = " ".join(str(x) for x in [e.get("mahalle"), e.get("caddeSokak"), e.get("binaKapi")] if x).strip()
        sonuc.append({"sicil": e.get("sicil"), "ad": str(e["ad"]).strip(), "tel": "",
                      "ilce": e.get("ilce"), "adres": adres})
    return sonuc


def cek():
    kayitlar, hatalar = {}, []
    with sync_playwright() as p:
        t = p.chromium.launch()
        s = t.new_page(viewport={"width": 1300, "height": 1400}, locale="tr-TR")
        try:
            s.goto(URL, wait_until="networkidle", timeout=60000)
            s.wait_for_timeout(2000)
        except Exception as e:
            print("[TESHIS] sayfa acilamadi: %s" % str(e)[:150])
        sonuclar = s.evaluate(JS_TARA, [API, list(ILCE_ID_ARALIK)])
        t.close()
    dolu_ilce = 0
    for ilce_id, durum, metin in sonuclar:
        if durum != 200:
            hatalar.append("id %s -> HTTP %s %s" % (ilce_id, durum, metin[:60]))
            continue
        liste = ilce_yanitini_coz(metin)
        if liste:
            dolu_ilce += 1
        for k in liste:
            kayitlar[k["sicil"] if k["sicil"] is not None else (k["ad"], k["ilce"])] = k
    print("Odasi: %d ilce dolu, %d eczane" % (dolu_ilce, len(kayitlar)))
    if hatalar:
        for h in hatalar[:6]:
            print("[TESHIS] " + h)
        print("[TESHIS] toplam %d istekte hata" % len(hatalar))
    return list(kayitlar.values())


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
    os.makedirs(os.path.dirname(CIKTI), exist_ok=True)
    with open(CIKTI, "w", encoding="utf-8") as f:
        json.dump({"zaman": z.strftime("%Y-%m-%d %H:%M"), "adet": len(liste), "eczaneler": liste},
                  f, ensure_ascii=False, indent=1)
    print("Odasi: %d eczane yazildi (%s)" % (len(liste), z.strftime("%H:%M")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
