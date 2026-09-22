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

Tazelik kontrolu (21 Eylul'de kesfedildi - Enver'in istegi geregi eklendi):
  Nobetci vardiyasi gece yarisini geciyor (orn. 19:00 -> ertesi gun 09:00), bu
  yuzden sadece "ilce eslesti mi" yeterli DEGIL - API'nin her kayitla birlikte
  dondurdugu "workdate" alani (vardiyanin GERCEKTEN basladigi tarih-saat, orn.
  "2026-09-21 19:00:00") de BUGUNUN tarihiyle eslesmek ZORUNDA. Eslesmezse
  (orn. gunduz saatlerinde hala dunku/gece bitmis vardiya donuyorsa) kayit
  gecersiz sayilir - "hic kayit yok" ile AYNI sekilde ATLANIR, mevcut dosyalar
  korunur. Bu, eskiden sadece basariyla yazilan dosyanin USTUNE "bugunun
  tarihi" etiketi konulup asil vardiyanin degisip degismedigine bakilmamasi
  riskini ortadan kaldirir.

Bu script sadece dosyalari GUNCELLER; commit/push islemini cagiran GitHub
Actions workflow'u (.github/workflows/nobetci-sync.yml) yapar.
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


def api_dan_il_verisini_cek(api_il, deneme_sayisi=3):
    """Bir il icin TUM ilcelerin nobetci listesini tek cagriyla ceker.

    22 Eylul'de Enver'in GitHub Actions loglarinda bulduğu hata: "Expecting
    value: line 1 column 1 (char 0)" - yani API'den BOS/gecersiz bir govde
    donuyordu, ama SADECE GitHub Actions'tan calisinca (Enver'in kendi
    tarayicisindan API sorunsuz calisiyordu). En olasi sebep: api.teknikzeka.net
    (kucuk/tek gelistiricili bir servis) GitHub Actions'in bilinen paylasimli
    bulut IP araliklarini kotuye-kullanim/bot koruma amaciyla engelliyor veya
    hiz sinirliyor olabilir - script tarafinda kesin olarak ayirt edemeyiz,
    bu yuzden:
      1) Gercek tarayici gibi gorunen bir User-Agent + Accept header'i
         deneniyor (bazi basit engelleme kurallari sadece "script/bot"
         gorunumlu User-Agent'lari hedef alir).
      2) Kisa bir bekleme ile (rate-limit/gecici kesinti ihtimaline karsi)
         birkac kez tekrar deneniyor.
      3) Basarisiz olursa, HATA MESAJINA gercek HTTP durum kodu + donen
         govdenin ilk 200 karakteri EKLENIYOR - boylece bir sonraki
         GitHub Actions logunda "bos govde" ile "403 Forbidden" ile "farkli
         bir hata sayfasi" arasindaki fark NET gorulebilir (eskiden sadece
         belirsiz bir JSON-parse hatasi yaziyordu).
    """
    parametreler = urllib.parse.urlencode({"islem": "nobetci", "il": api_il})
    url = f"{API_TABAN_URL}?{parametreler}"
    headers = {
        # Gercek bir tarayiciyi taklit ediyor - bazi basit bot-korumalari
        # sadece "script benzeri" User-Agent'lari hedef alir.
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }

    son_hata = None
    for deneme in range(1, deneme_sayisi + 1):
        try:
            istek = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(istek, timeout=20) as yanit:
                durum_kodu = yanit.getcode()
                govde_ham = yanit.read()
        except urllib.error.HTTPError as hata:
            durum_kodu = hata.code
            govde_ham = hata.read() if hasattr(hata, "read") else b""
            son_hata = _api_hata_mesaji(durum_kodu, govde_ham)
            if deneme < deneme_sayisi:
                time.sleep(2 * deneme)
                continue
            raise ValueError(son_hata)
        except Exception as hata:
            son_hata = f"baglanti hatasi: {hata}"
            if deneme < deneme_sayisi:
                time.sleep(2 * deneme)
                continue
            raise ValueError(son_hata)

        govde_metin = govde_ham.decode("utf-8", errors="replace").strip()
        if not govde_metin:
            son_hata = _api_hata_mesaji(durum_kodu, govde_ham)
            if deneme < deneme_sayisi:
                time.sleep(2 * deneme)
                continue
            raise ValueError(son_hata)

        try:
            veri = json.loads(govde_metin)
        except json.JSONDecodeError as hata:
            son_hata = _api_hata_mesaji(durum_kodu, govde_ham, ek=f"JSON parse hatasi: {hata}")
            if deneme < deneme_sayisi:
                time.sleep(2 * deneme)
                continue
            raise ValueError(son_hata)

        sonuc = veri.get("sonuc")
        if not isinstance(sonuc, list):
            raise ValueError(f"API yaniti beklenen bicimde degil ('sonuc' listesi yok) - govde: {govde_metin[:200]!r}")
        return sonuc

    # Buraya normalde hic gelinmemeli (dongu icinde ya return ya raise olur)
    raise ValueError(son_hata or "bilinmeyen hata")


def _api_hata_mesaji(durum_kodu, govde_ham, ek=None):
    onizleme = govde_ham[:200].decode("utf-8", errors="replace") if govde_ham else "(bos govde)"
    parcalar = [f"HTTP {durum_kodu}", f"govde onizleme: {onizleme!r}"]
    if ek:
        parcalar.append(ek)
    return " - ".join(parcalar)


def normallestir(metin):
    """Ilce adlarini karsilastirmak icin buyuk harfe cevirir ve bosluklari sadelestirir."""
    if metin is None:
        return ""
    return " ".join(str(metin).strip().upper().split())


def workdate_bugun_mu(workdate_degeri, bugun_tarih_iso):
    """API'nin "workdate" alani ("YYYY-MM-DD HH:MM:SS") gercekten BUGUNUN
    (Istanbul saatiyle) tarihine mi ait, diye bakar. Ilk 10 karakter
    ("YYYY-MM-DD") karsilastirmasi yeterli - saat kismini gormezden gelir."""
    if not workdate_degeri:
        return False
    return str(workdate_degeri)[:10] == bugun_tarih_iso


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
        bugun_tarih_iso = simdi_istanbul().strftime("%Y-%m-%d")

        # Once ilceye gore filtrele, SONRA "workdate bugune mi ait" diye tazelik
        # kontrolu yap - vardiya gece yarisini gectigi icin (bkz. dosya basindaki
        # "Tazelik kontrolu" notu) sadece ilce eslesmesi yeterli degil.
        ilce_eslesenler = [k for k in il_verisi if normallestir(k.get("district")) == hedef_ilce_norm]
        eslesenler = [k for k in ilce_eslesenler if workdate_bugun_mu(k.get("workdate"), bugun_tarih_iso)]

        if not ilce_eslesenler:
            print(f"[{etiket}] ATLANDI: '{api_ilce}' icin API'den hic nobetci kaydi donmedi. "
                  f"Mevcut dosyalar korunuyor.")
            atlanan_sayisi += 1
            continue

        if not eslesenler:
            print(f"[{etiket}] ATLANDI: '{api_ilce}' icin kayit var ama hicbirinin workdate'i "
                  f"bugune ({bugun_tarih_iso}) ait degil - vardiya henuz baslamamis/API henuz "
                  f"guncellenmemis olabilir. Mevcut dosyalar korunuyor.")
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
