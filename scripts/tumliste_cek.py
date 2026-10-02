#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NobetciEczanePano - bir ilcenin TUM eczanelerini (sadece nobetci olanlari
degil) ceken script.

Amac: Flutter uygulamasindaki "Manuel Nobetci Girisi" ekranini, eczaciyi
tek tek elle yazmak yerine alfabetik bir TIKLENEBILIR LISTE haline getirmek
(2 Ekim konusmasi - Enver'in onerisi). Bu script o checklist'in veri
kaynagini hazirlar.

Ne yapar:
  config/eczane-kaynaklari.json icindeki HER (il_slug, ilce_slug) satiri
  icin - yani SADECE panelin fiilen kurulu oldugu ilceler icin, TUM
  Turkiye icin DEGIL - teknikzeka.net'in "tumu=1" parametresini kullanarak
  o ilcenin TUM eczanelerini (nobetci olsun olmasin) ceker ve
  data/<il_slug>-<ilce_slug>-tumliste.json dosyasina alfabetik sirali
  yazar:
    {"eczaneler": [{"id","ad","tel","adres"}, ...]}  (ad'a gore A-Z sirali)

  Panel sayisi Turkiye geneline yayildikca, config dosyasina yeni bir
  (il_slug, ilce_slug) satiri eklendikce, bu script otomatik olarak SADECE
  o yeni ilcenin listesini de cekmeye baslar - asla "tum Turkiye" tek
  seferde cekilmez, her panel sadece kendi ilcesinin (tipik 100-300
  eczane) listesiyle sinirli kalir.

Guvenlik kurali (senkronize.py ile AYNI prensip):
  Bir ilce icin cekim basarisiz olursa veya hic kayit donmezse, o ilce icin
  HICBIR DOSYA YAZILMAZ - mevcut (onceki basarili cekimden kalma) dosya
  oldugu gibi korunur.

  Bu script senkronize.py'nin ISLEDIGI HICBIR DOSYAYA DOKUNMAZ (farkli dosya
  adi: "-tumliste.json" vs "-liste.json"/"-.json") - nobetci verisi/panel
  akisi bu scriptten TAMAMEN BAGIMSIZDIR. Bu script calismasa/hata verse
  bile nobetci senkronizasyonunu ETKILEMEZ.

  Tam liste sik degismez (yeni eczane acilmadikca), bu yuzden bu script
  GUNLUK/SAATLIK degil, SEYREK (haftada 1 + elle tetiklenebilir) calisir.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

API_TABAN_URL = "https://api.teknikzeka.net/eczane/api.php"

BU_DOSYA_KLASORU = os.path.dirname(os.path.abspath(__file__))
REPO_KOKU = os.path.dirname(BU_DOSYA_KLASORU)
KONFIG_YOLU = os.path.join(REPO_KOKU, "config", "eczane-kaynaklari.json")
DATA_KLASORU = os.path.join(REPO_KOKU, "data")


def normallestir(metin):
    """senkronize.py'deki ile AYNI - Turkce I/i/İ/ı farkini kanonik hale getirir."""
    if metin is None:
        return ""
    metin = str(metin).strip()
    metin = metin.replace("İ", "I").replace("ı", "I").replace("i", "I")
    return " ".join(metin.upper().split())


def tum_eczaneleri_cek(api_il, api_ilce, deneme_sayisi=3):
    """Bir ilcenin TUM eczanelerini ceker ("tumu=1" - sadece nobetci olanlar degil).

    Basarili olursa liste doner (bos liste de olabilir - o ilcede gercekten
    kayit yoksa). Basarisiz olursa ValueError firlatir (cagiran taraf
    yakalayip dosyayi KORUR)."""
    parametreler = urllib.parse.urlencode({
        "islem": "nobetci",
        "il": api_il,
        "ilce": api_ilce,
        "tumu": "1",
    })
    url = f"{API_TABAN_URL}?{parametreler}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }

    son_hata = None
    for deneme in range(1, deneme_sayisi + 1):
        try:
            istek = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(istek, timeout=20) as yanit:
                govde_ham = yanit.read()
        except urllib.error.HTTPError as hata:
            onizleme = (hata.read()[:200].decode("utf-8", errors="replace") if hasattr(hata, "read") else "")
            son_hata = f"HTTP {hata.code} - govde onizleme: {onizleme!r}"
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
            son_hata = "bos govde"
            if deneme < deneme_sayisi:
                time.sleep(2 * deneme)
                continue
            raise ValueError(son_hata)

        try:
            veri = json.loads(govde_metin)
        except json.JSONDecodeError as hata:
            son_hata = f"JSON parse hatasi: {hata} - govde: {govde_metin[:200]!r}"
            if deneme < deneme_sayisi:
                time.sleep(2 * deneme)
                continue
            raise ValueError(son_hata)

        sonuc = veri.get("sonuc")
        if not isinstance(sonuc, list):
            raise ValueError(f"API yaniti beklenen bicimde degil ('sonuc' listesi yok) - govde: {govde_metin[:200]!r}")
        return sonuc

    raise ValueError(son_hata or "bilinmeyen hata")


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

    basarili_sayisi = 0
    atlanan_sayisi = 0

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

        print(f"[{etiket}] '{api_ilce}' icin TUM eczaneler cekiliyor...")
        try:
            sonuc = tum_eczaneleri_cek(api_il, api_ilce)
        except Exception as hata:
            print(f"[{etiket}] ATLANDI: cekim basarisiz oldu ({hata}). Mevcut dosya korunuyor.")
            atlanan_sayisi += 1
            continue

        # Guvenlik icin ilceye gore tekrar filtrele (API zaten ilce parametresiyle
        # filtrelemis olmali ama senkronize.py'deki ayni temkinli yaklasimi
        # koruyoruz - beklenmedik fazladan kayit gelirse ayiklanir).
        hedef_ilce_norm = normallestir(api_ilce)
        ilce_eslesenler = [k for k in sonuc if normallestir(k.get("district")) == hedef_ilce_norm]

        if not ilce_eslesenler:
            print(f"[{etiket}] ATLANDI: '{api_ilce}' icin hic eczane kaydi donmedi. Mevcut dosya korunuyor.")
            atlanan_sayisi += 1
            continue

        eczaneler = []
        for kayit in ilce_eslesenler:
            eid = kayit.get("id")
            if eid is None:
                continue
            eczaneler.append({
                "id": eid,
                "ad": (kayit.get("name") or "").strip(),
                "tel": (kayit.get("phone") or "").strip(),
                "adres": (kayit.get("address") or "").strip(),
            })

        if not eczaneler:
            print(f"[{etiket}] ATLANDI: eslesen kayitlarda gecerli id yok. Mevcut dosya korunuyor.")
            atlanan_sayisi += 1
            continue

        # Alfabetik sirala (Turkce karakterlere gore degil, basit metin sirasina
        # gore - Flutter tarafinda gosterim icin yeterli, sayi az oldugundan
        # (100-300 civari) performans sorunu olmaz).
        eczaneler.sort(key=lambda e: e["ad"])

        tumliste_yolu = os.path.join(DATA_KLASORU, f"{il_slug}-{ilce_slug}-tumliste.json")
        with open(tumliste_yolu, "w", encoding="utf-8") as f:
            json.dump({"eczaneler": eczaneler}, f, ensure_ascii=False, indent=2)

        print(f"[{etiket}] OK: {len(eczaneler)} eczane yazildi (tumliste).")
        basarili_sayisi += 1

    print(f"\nOzet: {basarili_sayisi} basarili, {atlanan_sayisi} atlandi.")


if __name__ == "__main__":
    main()
