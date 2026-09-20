#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NobetciEczanePano - ucuncu parti API senkronizasyon script'i.

Ne yapar:
  1) config/eczane-kaynaklari.json icindeki her (il_slug, ilce_slug) satiri icin,
     https://api.teknikzeka.net/eczane/api.php adresinden o ilin TUM ilcelerinin
     nobetci eczanelerini ceker (bir il icin tek API cagrisi yeterli - tum ilceler
     tek seferde donuyor, bu yuzden ayni ili kullanan satirlar icin sonuc cache'lenir).
  2) Ilgili ilceye ait kayitlari filtreler.
  3) Enver'in ESP32 panelinin ve Flutter uygulamasinin zaten kullandigi iki dosya
     formatinda GitHub deposundaki data/ klasorune yazar:
       - data/<il_slug>-<ilce_slug>-liste.json  -> {"eczaneler":[{"id","ad","tel","adres"}, ...]}
       - data/<il_slug>-<ilce_slug>.json        -> {"tarih":"20 Eylul Pazar", "nobetciler":[id, id, ...]}
     (id alani olarak API'nin kendi kalici "id" degeri dogrudan kullanilir.)

Guvenlik kurali (Enver'in istegi):
  Bir il/ilce icin API cagrisi basarisiz olursa VEYA o ilceye ait hic kayit
  donmezse, o (il_slug, ilce_slug) icin HICBIR DOSYA YAZILMAZ - mevcut (onceki
  basarili senkronizasyondan kalma) dosyalar oldugu gibi korunur. Boylece
  ucuncu parti API bir gun kapansa veya gecici olarak veri vermese bile panel,
  elindeki son gecerli veriyle calismaya devam eder; Enver istedigi zaman elle
  GitHub'a veri girerek (veya panel uzerinden "Manuel Nobetci Girisi" ile)
  devreye girebilir.

Bu script sadece dosyalari GUNCELLER; commit/push islemini cagiran GitHub
Actions workflow'u (.github/workflows/nobetci-sync.yml) yapar.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
except Exception:
    ISTANBUL_TZ = None

API_TABAN_URL = "https://api.teknikzeka.net/eczane/api.php"

BU_DOSYA_KLASORU = os.path.dirname(os.path.abspath(__file__))
REPO_KOKU = os.path.dirname(BU_DOSYA_KLASORU)
KONFIG_YOLU = os.path.join(REPO_KOKU, "config", "eczane-kaynaklari.json")
DATA_KLASORU = os.path.join(REPO_KOKU, "data")

# NobetciEczanePano.ino icindeki AY_ADLARI ile birebir ayni (ASCII, Turkce karakter yok)
AY_ADLARI = ["Ocak", "Subat", "Mart", "Nisan", "Mayis", "Haziran",
             "Temmuz", "Agustos", "Eylul", "Ekim", "Kasim", "Aralik"]

# Gun adlari - "tarih" alaninda ornek olarak kullanilan bicime uygun (Pazartesi...Pazar)
GUN_ADLARI = ["Pazartesi", "Sali", "Carsamba", "Persembe", "Cuma", "Cumartesi", "Pazar"]


def simdi_istanbul():
    if ISTANBUL_TZ is not None:
        return datetime.now(ISTANBUL_TZ)
    # zoneinfo yoksa (cok eski Python), UTC+3 sabit ofsetiyle yaklasik hesapla
    from datetime import timedelta, timezone
    return datetime.now(timezone.utc) + timedelta(hours=3)


def bugunun_tarih_metni():
    n = simdi_istanbul()
    ay = AY_ADLARI[n.month - 1]
    gun = GUN_ADLARI[n.weekday()]  # Pazartesi=0 ... Pazar=6
    return f"{n.day} {ay} {gun}"


def api_dan_il_verisini_cek(api_il):
    """Bir il icin TUM ilcelerin nobetci listesini tek cagriyla ceker."""
    parametreler = urllib.parse.urlencode({"islem": "nobetci", "il": api_il})
    url = f"{API_TABAN_URL}?{parametreler}"
    istek = urllib.request.Request(url, headers={"User-Agent": "NobetciEczanePano-Sync/1.0"})
    with urllib.request.urlopen(istek, timeout=20) as yanit:
        veri = json.loads(yanit.read().decode("utf-8"))
    sonuc = veri.get("sonuc")
    if not isinstance(sonuc, list):
        raise ValueError("API yaniti beklenen bicimde degil ('sonuc' listesi yok)")
    return sonuc


def normallestir(metin):
    """Ilce adlarini karsilastirmak icin buyuk harfe cevirir ve bosluklari sadelestirir."""
    if metin is None:
        return ""
    return " ".join(str(metin).strip().upper().split())


def main():
    if not os.path.isfile(KONFIG_YOLU):
        print(f"HATA: konfig dosyasi bulunamadi: {KONFIG_YOLU}", file=sys.stderr)
        sys.exit(1)

    with open(KONFIG_YOLU, "r", encoding="utf-8") as f:
        konfig = json.load(f)

    kaynaklar = konfig.get("kaynaklar", [])
    if not kaynaklar:
        print("UYARI: config/eczane-kaynaklari.json icinde hic kaynak tanimli degil, yapilacak bir sey yok.")
        return

    os.makedirs(DATA_KLASORU, exist_ok=True)

    # Ayni ili paylasan satirlar icin API'yi bir kere cagir (cache)
    il_cache = {}

    basarili_sayisi = 0
    atlanan_sayisi = 0
    tarih_metni = bugunun_tarih_metni()

    for kaynak in kaynaklar:
        il_slug = kaynak.get("il_slug")
        ilce_slug = kaynak.get("ilce_slug")
        api_il = kaynak.get("api_il")
        api_ilce = kaynak.get("api_ilce")

        etiket = f"{il_slug}-{ilce_slug}"

        if not (il_slug and ilce_slug and api_il and api_ilce):
            print(f"[{etiket}] ATLANDI: konfig satiri eksik alan iceriyor.")
            atlanan_sayisi += 1
            continue

        try:
            if api_il not in il_cache:
                print(f"[{api_il}] API'den cekiliyor...")
                il_cache[api_il] = api_dan_il_verisini_cek(api_il)
            il_verisi = il_cache[api_il]
        except Exception as hata:
            print(f"[{etiket}] ATLANDI: '{api_il}' icin API cagrisi basarisiz oldu ({hata}). "
                  f"Mevcut dosyalar korunuyor.")
            atlanan_sayisi += 1
            continue

        hedef_ilce_norm = normallestir(api_ilce)
        eslesenler = [k for k in il_verisi if normallestir(k.get("district")) == hedef_ilce_norm]

        if not eslesenler:
            print(f"[{etiket}] ATLANDI: '{api_ilce}' icin API'den hic nobetci kaydi donmedi. "
                  f"Mevcut dosyalar korunuyor.")
            atlanan_sayisi += 1
            continue

        eczaneler = []
        idler = []
        for kayit in eslesenler:
            eid = kayit.get("id")
            if eid is None:
                continue
            eczaneler.append({
                "id": eid,
                "ad": kayit.get("name", "").strip(),
                "tel": (kayit.get("phone") or "").strip(),
                "adres": (kayit.get("address") or "").strip(),
            })
            idler.append(eid)

        if not eczaneler:
            print(f"[{etiket}] ATLANDI: eslesen kayitlarda gecerli id yok. Mevcut dosyalar korunuyor.")
            atlanan_sayisi += 1
            continue

        liste_yolu = os.path.join(DATA_KLASORU, f"{il_slug}-{ilce_slug}-liste.json")
        gunluk_yolu = os.path.join(DATA_KLASORU, f"{il_slug}-{ilce_slug}.json")

        with open(liste_yolu, "w", encoding="utf-8") as f:
            json.dump({"eczaneler": eczaneler}, f, ensure_ascii=False, indent=2)

        with open(gunluk_yolu, "w", encoding="utf-8") as f:
            json.dump({"tarih": tarih_metni, "nobetciler": idler}, f, ensure_ascii=False, indent=2)

        print(f"[{etiket}] OK: {len(eczaneler)} eczane yazildi.")
        basarili_sayisi += 1

    print(f"\nOzet: {basarili_sayisi} basarili, {atlanan_sayisi} atlandi.")


if __name__ == "__main__":
    main()
