#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NobetciEczanePano - teknikzeka.net ile CollectAPI karsilastirma scripti.

NE YAPAR (ve NE YAPMAZ):
  - Bu script senkronize.py'nin islediği hicbir dosyaya DOKUNMAZ, panelin
    kullandigi data/<il>-<ilce>.json / data/<il>-<ilce>-liste.json dosyalarini
    DEGISTIRMEZ. Tek isi: config/eczane-kaynaklari.json'daki her (il, ilce)
    icin hem teknikzeka.net'ten hem de CollectAPI'den o GUNUN nobetci
    eczanelerini cekip, isimlerini karsilastirip SADECE bir log dosyasina
    (data/karsilastirma-log.txt) insan okuyabilir bir satir eklemektir.

  - Amac: birkac gun boyunca iki kaynagin ne zaman/ne sekilde farklilastigini
    gormek, ve CollectAPI'nin teknikzeka'nin eksik kaldigi bir gunde dogru
    veriyi verip vermedigini anlamak (bkz. 2 Ekim konusmasi - Kartal'da
    "Nur Eczanesi" / "Sifa Eczanesi" eksikligi).

  - Bu script BASARISIZ OLSA DA (CollectAPI kota bitti, internet sorunu, vb.)
    panelin kullandigi asil veriyi ETKILEMEZ - sadece log'a hata satiri yazar
    ve sessizce devam eder. Ana senkronizasyonu (senkronize.py) durduracak
    veya bozacak hicbir etkisi yoktur.

  - CollectAPI UCRETSIZ pakette ayda 100 istek hakki var. Bu yuzden bu script
    GUNDE BIR KEZ calistirilmali (saatlik degil!) - ayri bir GitHub Actions
    workflow'u (.github/workflows/karsilastirma.yml) ile. 2 ilce (Kartal,
    Maltepe) x gunde 1 kez = ayda ~60 istek, 100'luk kotanin icinde kalir.

API anahtari: ortam degiskeni COLLECTAPI_KEY'den okunur (GitHub Secret olarak
eklenmeli - repo ayarlarinda hicbir yerde acikca yazilmaz).
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
except Exception:
    ISTANBUL_TZ = None

TEKNIKZEKA_URL = "https://api.teknikzeka.net/eczane/api.php"
COLLECTAPI_URL = "https://api.collectapi.com/health/dutyPharmacy"

BU_DOSYA_KLASORU = os.path.dirname(os.path.abspath(__file__))
REPO_KOKU = os.path.dirname(BU_DOSYA_KLASORU)
KONFIG_YOLU = os.path.join(REPO_KOKU, "config", "eczane-kaynaklari.json")
DATA_KLASORU = os.path.join(REPO_KOKU, "data")
LOG_YOLU = os.path.join(DATA_KLASORU, "karsilastirma-log.txt")


def simdi_istanbul():
    if ISTANBUL_TZ is not None:
        return datetime.now(ISTANBUL_TZ)
    from datetime import timedelta, timezone
    return datetime.now(timezone.utc) + timedelta(hours=3)


def normallestir(metin):
    if metin is None:
        return ""
    return " ".join(str(metin).strip().upper().split())


def workdate_bugun_mu(workdate_degeri, bugun_tarih_iso):
    if not workdate_degeri:
        return False
    return str(workdate_degeri)[:10] == bugun_tarih_iso


def teknikzeka_cek(api_il, api_ilce):
    """senkronize.py'deki ayni mantik - sadece isim listesi dondurur.
    Hata olursa None dondurur (log'a 'HATA' olarak yazilir)."""
    parametreler = urllib.parse.urlencode({"islem": "nobetci", "il": api_il})
    url = f"{TEKNIKZEKA_URL}?{parametreler}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    try:
        istek = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(istek, timeout=20) as yanit:
            govde = yanit.read().decode("utf-8", errors="replace")
        veri = json.loads(govde)
        sonuc = veri.get("sonuc")
        if not isinstance(sonuc, list):
            return None
    except Exception as hata:
        print(f"  teknikzeka HATA: {hata}")
        return None

    hedef_ilce_norm = normallestir(api_ilce)
    bugun_tarih_iso = simdi_istanbul().strftime("%Y-%m-%d")
    eslesenler = [
        k for k in sonuc
        if normallestir(k.get("district")) == hedef_ilce_norm
        and workdate_bugun_mu(k.get("workdate"), bugun_tarih_iso)
    ]
    isimler = sorted(set(normallestir(k.get("name")) for k in eslesenler if k.get("name")))
    return isimler


def collectapi_cek(api_key, api_il, api_ilce):
    """CollectAPI dutyPharmacy'den isim listesi dondurur. Hata/kota biterse None."""
    parametreler = urllib.parse.urlencode({"il": api_il, "ilce": api_ilce})
    url = f"{COLLECTAPI_URL}?{parametreler}"
    headers = {
        "authorization": f"apikey {api_key}",
        "content-type": "application/json",
    }
    try:
        istek = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(istek, timeout=20) as yanit:
            govde = yanit.read().decode("utf-8", errors="replace")
        veri = json.loads(govde)
        if not veri.get("success"):
            print(f"  CollectAPI HATA: success=false - {govde[:200]!r}")
            return None
        sonuc = veri.get("result", [])
    except Exception as hata:
        print(f"  CollectAPI HATA: {hata}")
        return None

    isimler = sorted(set(normallestir(k.get("name")) for k in sonuc if k.get("name")))
    return isimler


def log_satiri_ekle(metin):
    os.makedirs(DATA_KLASORU, exist_ok=True)
    with open(LOG_YOLU, "a", encoding="utf-8") as f:
        f.write(metin + "\n")


def main():
    api_key = os.environ.get("COLLECTAPI_KEY", "").strip()
    if not api_key:
        print("UYARI: COLLECTAPI_KEY ortam degiskeni tanimli degil, karsilastirma atlaniyor.")
        return

    if not os.path.isfile(KONFIG_YOLU):
        print(f"HATA: konfig dosyasi bulunamadi: {KONFIG_YOLU}", file=sys.stderr)
        return

    with open(KONFIG_YOLU, "r", encoding="utf-8") as f:
        konfig = json.load(f)
    kaynaklar = konfig.get("kaynaklar", [])

    zaman_damgasi = simdi_istanbul().strftime("%Y-%m-%d %H:%M")

    for kaynak in kaynaklar:
        il_slug = kaynak.get("il_slug")
        ilce_slug = kaynak.get("ilce_slug")
        api_il = kaynak.get("api_il")
        api_ilce = kaynak.get("api_ilce")
        etiket = f"{il_slug}-{ilce_slug}"

        if not (il_slug and ilce_slug and api_il and api_ilce):
            continue

        print(f"[{etiket}] karsilastiriliyor...")
        teknikzeka_isimler = teknikzeka_cek(api_il, api_ilce)
        time.sleep(1)
        collectapi_isimler = collectapi_cek(api_key, api_il, api_ilce)

        if teknikzeka_isimler is None and collectapi_isimler is None:
            log_satiri_ekle(f"{zaman_damgasi} | {etiket} | ikisi de HATA verdi, karsilastirma yapilamadi.")
            continue

        tz_metin = ", ".join(teknikzeka_isimler) if teknikzeka_isimler is not None else "HATA"
        ca_metin = ", ".join(collectapi_isimler) if collectapi_isimler is not None else "HATA"

        if teknikzeka_isimler is not None and collectapi_isimler is not None:
            fark_var = set(teknikzeka_isimler) != set(collectapi_isimler)
            fark_etiketi = "FARK VAR" if fark_var else "ayni"
        else:
            fark_etiketi = "karsilastirilamadi (biri hata)"

        satir = (
            f"{zaman_damgasi} | {etiket} | {fark_etiketi} | "
            f"teknikzeka({len(teknikzeka_isimler) if teknikzeka_isimler is not None else '-'}): {tz_metin} | "
            f"collectapi({len(collectapi_isimler) if collectapi_isimler is not None else '-'}): {ca_metin}"
        )
        log_satiri_ekle(satir)
        print(f"  -> {fark_etiketi}")

    print("Karsilastirma tamamlandi.")


if __name__ == "__main__":
    main()
