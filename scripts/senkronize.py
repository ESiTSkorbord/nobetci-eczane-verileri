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

1 Ekim notu (Enver'in bulgusu): teknikzeka.net API'si bazen bir ilcenin TUM
  nobetci eczanelerini dondurmuyor (orn. Kartal'da 5 nobetciden sadece 3'u
  geldi). Bu, API'nin kendi veri eksikligi - script'in bir hatasi degil.
  Ikinci bir kaynaktan (eczaneler.gen.tr) otomatik capraz kontrol DENENDI ama
  o site Cloudflare bot korumasi ("Just a moment...") kullaniyor, otomatik
  script'ten asla gecilemiyor - bu yuzden VAZGECILDI.

2 Ekim guncellemesi: CollectAPI'nin "dutyPharmacy" servisi ikinci kaynak
  olarak ENTEGRE EDILDI (asagida "CollectAPI entegrasyonu" bolumune bak).
  teknikzeka'nin eksik biraktigi "Yeni Sifa Eczanesi" (Maltepe) orneginde
  CollectAPI'nin dogru veriyi verdigi dogrulandi (Enver, Eczacilar
  Odasi'ndan teyit etti). teknikzeka HALA ANA/ZORUNLU kaynak - CollectAPI
  SADECE EKLEME yapar, teknikzeka basarisiz olursa guvenlik kurali (yukarida)
  aynen gecerli: hicbir dosya yazilmaz. CollectAPI basarisiz olursa veya
  anahtar tanimli degilse, sadece ekleme adimi atlanir - teknikzeka verisi
  yine de yazilir, panel hicbir zaman "CollectAPI yok diye" veri kaybetmez.
  Enver boyle bir eksiklik fark ettiginde panel uzerinden "Manuel Nobetci
  Girisi" ile o ilce icin listeyi elle girip MANUEL moda alabilir (zaten var
  olan bir ozellik) - CollectAPI entegrasyonu bunun YERINE degil, EK bir
  guvenlik katmani olarak eklendi.

CollectAPI entegrasyonu (kota tasarrufu):
  CollectAPI ucretsiz pakette ayda sadece 100 istek hakki var. Saatlik
  calisan bu script'in HER calismasinda CollectAPI'yi cagirmak (gunde 24 kez
  x ilce sayisi) kotayi gunler icinde tuketir. Bu yuzden CollectAPI sonucu
  GUNLUK ONBELLEGE ALINIR: data/<il>-<ilce>-collectapi-onbellek.json
  dosyasina o GUNUN (Istanbul saatiyle) collectapi sonucu yazilir; ayni gun
  icindeki sonraki calismalar API'yi TEKRAR CAGIRMAZ, onbellekten okur.
  Boylece gunde il/ilce basina sadece 1 CollectAPI istegi harcanir (2 ilce
  icin ayda ~60 istek - ucretsiz kotanin icinde). "teknikzeka'da olmayan
  CollectAPI kaydi" farki HER calismada onbellekteki veriyle YENIDEN
  hesaplanir (API'ye tekrar sormadan) - boylece gun icinde teknikzeka'nin
  nobetciyi "yakaladigi" bir an olursa cift kayit olusmaz.
  CollectAPI'den eklenen her eczane data/collectapi-eklenenler-log.txt
  dosyasina kaydedilir (seffaflik/izlenebilirlik icin).

11 Ekim guncellemesi (Enver'in bulgusu): teknikzeka API'si Pazar sabahi 09:00'da
  yeni vardiyaya gecmiyor, test sayfasi (UYANDIR_URL) elle acilinca guncelleniyor.
  Yeni davranis:
  - Tam gun nobet gunlerinde (Pazar, resmi tatil, diniTatiller.txt) 09:00-09:20
    arasi YOGUN mod: veri eskiyse test sayfasini acip en fazla 5 dk yeniden dener,
    CollectAPI'ye (yedek kaynak) de sorar, sonucu data/sync-durum.json'a yazar
    (uygulama bunu ana ekranda gosterir).
  - Diger saatlerde HAFIF yeniden deneme (en fazla 2 dk): tam gun gunlerinde
    10:00'dan, diger gunlerde 14:00'dan sonra.
  - teknikzeka ESKI/YOK ve yedek kaynak ONCEKI LISTEDEN FARKLI ise yedek kaynak
    ANA kaynak olur (ID'ler ilcenin tumliste.json'undan eslestirilir).
  - Yedek kaynak onceki listeyle AYNIYSA "henuz guncellenmemis" sayilir, dunku
    liste yeni nobetci diye yazilmaz.
  - 2028 vb. bayramlar: sadece diniTatiller.txt'ye eklenir, kod degismez.

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
import zlib
from datetime import datetime, date

try:
    from zoneinfo import ZoneInfo
    ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
except Exception:
    ISTANBUL_TZ = None

API_TABAN_URL = "https://api.teknikzeka.net/eczane/api.php"
COLLECTAPI_URL = "https://api.collectapi.com/health/dutyPharmacy"

BU_DOSYA_KLASORU = os.path.dirname(os.path.abspath(__file__))
REPO_KOKU = os.path.dirname(BU_DOSYA_KLASORU)
KONFIG_YOLU = os.path.join(REPO_KOKU, "config", "eczane-kaynaklari.json")
DATA_KLASORU = os.path.join(REPO_KOKU, "data")
EKLENENLER_LOG_YOLU = os.path.join(DATA_KLASORU, "collectapi-eklenenler-log.txt")
DUZELTME_YOLU = os.path.join(DATA_KLASORU, "duzeltmeler.json")  # 12 Ekim: kaynaktaki yanlis tel/adres/ad elle duzeltme
HARIC_YOLU = os.path.join(DATA_KLASORU, "haric-eczaneler.json")  # 12 Ekim: elle hariç tutulan (hatali) eczaneler

# CollectAPI'ye bu saatten (Istanbul yerel saati) ONCE hic sorulmaz - Enver'in
# istegi (2 Ekim): gunun ilk saatlerinde veri henuz tam/guncel olmayabiliyor.
COLLECTAPI_EN_ERKEN_SAAT = 15  # 11 Ekim: Enver'in istegiyle 14 -> 15

# 11 Ekim guncellemesi - UYANDIR + YENIDEN DENE + YEDEK KAYNAK
UYANDIR_URL = "https://api.teknikzeka.net/eczane/"   # Enver'in elle actigi TEST SAYFASI
DINI_TATIL_YOLU = os.path.join(REPO_KOKU, "diniTatiller.txt")  # ESP'nin okudugu AYNI dosya
DURUM_YOLU = os.path.join(DATA_KLASORU, "sync-durum.json")     # uygulamanin okudugu durum dosyasi
RESMI_TATILLER = {(1, 1), (4, 23), (5, 1), (5, 19), (7, 15), (8, 30), (10, 29)}  # firmware ile AYNI
YOGUN_PENCERE_DK = 20        # tam gun nobet gunlerinde 09:00-09:20 arasi calisma = YOGUN mod
YOGUN_MAX_SN = 300           # YOGUN: en fazla 5 dk uyandirma/yeniden deneme
YOGUN_ARALIK_SN = 45
HAFIF_MAX_SN = 120           # HAFIF: en fazla 2 dk
HAFIF_ARALIK_SN = 60
YOGUN_GUNLUK_CAGRI_SINIRI = 2  # CollectAPI kota korumasi (ilce basina, sabah modu)

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
    """Ilce/isim karsilastirmak icin buyuk harfe cevirir ve bosluklari sadelestirir.

    Python'un yerlesik str.upper() Turkce'ye duyarli DEGIL: "i".upper() ->
    ASCII "I" doner, Turkce noktali "I" (yani "İ") degil. Iki farkli
    kaynaktan (teknikzeka / CollectAPI) gelen ayni eczane ismi farkli
    sekilde Turkce harflerle yazilmis olabilir (orn. "YAKACIK" / "YAKACİK") -
    bu fark yuzunden ayni eczane "farkli/yeni" sanilmasin diye "I/İ/ı/i"
    harflerinin hepsi TEK bir kanonik harfe ("I") cevrilip SONRA geri kalani
    upper() yapilir."""
    if metin is None:
        return ""
    metin = str(metin).strip()
    metin = metin.replace("İ", "I").replace("ı", "I").replace("i", "I")
    # 20 Ekim: s/ş, g/ğ, u/ü, o/ö, c/ç farki yuzunden ayni eczane (PASAOGLU / PAŞAOĞLU)
    # iki kayit sanilmasin diye Turkce harfler ASCII karsiliklarina katlanir.
    metin = metin.translate(str.maketrans("ŞşĞğÜüÖöÇç", "SsGgUuOoCc"))
    return " ".join(metin.upper().split())


def isim_anahtari(metin):
    """Eczane ismini KARSILASTIRMA icin sadelestirir: normallestir + sondaki 'ECZANESI'/
    'ECZANE'/'ECZ.' eki atilir. 12 Ekim: teknikzeka 'CINAR', CollectAPI 'CINAR ECZANESI'
    yazdigi icin ayni eczane iki ayri kayit sanilip listeye cift ekleniyordu."""
    n = normallestir(metin)
    parcalar = n.split()
    while len(parcalar) > 1 and parcalar[-1] in ("ECZANESI", "ECZANE", "ECZ", "ECZ."):
        parcalar.pop()
    return " ".join(parcalar)


def telefon_normallestir(ham):
    """Karsilastirma icin telefonu sade 10 rakama indirir ("0"/"90" ulke
    kodu onekleri atilir). 3 Ekim: isim bazli eslestirme ("YELKEN" ile
    "YELKEN ECZANESI" gibi) yeterli degildi - CollectAPI ayni eczaneyi
    teknikzeka'dan FARKLI yazilmis bir isimle dondurebiliyor, bu da panelde
    AYNI eczanenin IKI KERE gorunmesine yol aciyordu. Telefon numarasi
    (ulke kodu/basta sifir farki disinda) HER ZAMAN aynidir, bu yuzden asil
    eslestirme anahtari artik bu - isim eslestirmesi SADECE ek bir guvenlik
    katmani olarak duruyor (telefon bos/eksikse hala ise yarar)."""
    rakamlar = "".join(ch for ch in str(ham or "") if ch.isdigit())
    if len(rakamlar) == 11 and rakamlar[0] == "0":
        rakamlar = rakamlar[1:]
    elif len(rakamlar) == 12 and rakamlar[:2] == "90":
        rakamlar = rakamlar[2:]
    return rakamlar if len(rakamlar) == 10 else ""


def sentetik_id_uret(isim_norm):
    """CollectAPI kayitlarinin kendi 'id' alani yok - panelin/Flutter uygulamasinin
    beklediği 'id' formatini saglamak icin isimden SABIT (deterministik) bir
    sentetik id uretilir. zlib.crc32 kullanilir - Python'un yerlesik hash()
    FONKSIYONU KULLANILMAZ, cunku hash() PYTHONHASHSEED ile process basina
    rastgele tuzlanir, yani ayni isim icin her calistirmada FARKLI deger
    doner - bu da panelde ayni eczanenin surekli "yeni" kayit gibi
    gorunmesine/ID kaymasina yol acar. 9_000_000 araligi teknikzeka'nin
    kendi id'leriyle (genelde kucuk sayilar) cakismasin diye secildi."""
    return 9_000_000 + (zlib.crc32(isim_norm.encode("utf-8")) % 900_000)


def collectapi_il_ilce_cek(api_key, api_il, api_ilce, deneme_sayisi=2):
    """CollectAPI dutyPharmacy'den bir ilcenin BUGUNKU nobetci listesini ceker.

    2 Ekim'de GitHub Actions'tan ilk denemede "HTTP 403 Forbidden" alindi,
    Enver'in kendi bilgisayarindan (PowerShell) ayni anahtarla sorunsuzdu -
    teknikzeka'da daha once yasanan "bulut IP / script User-Agent engeli"
    durumunun benzeri. Gercek tarayici gibi gorunen User-Agent/Accept
    eklenerek cozuldu (karsilastirma scriptinde de ayni cozum kullanildi).

    Basarili olursa [{"ad","tel","adres"}, ...] listesi doner.
    Basarisiz olursa None doner (CAGIRAN TARAF bunu "bu calismada ekleme
    yapilamadi" olarak yorumlar - teknikzeka verisini ASLA etkilemez)."""
    parametreler = urllib.parse.urlencode({"il": api_il, "ilce": api_ilce})
    url = f"{COLLECTAPI_URL}?{parametreler}"
    headers = {
        "authorization": f"apikey {api_key}",
        "content-type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    for deneme in range(1, deneme_sayisi + 1):
        try:
            istek = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(istek, timeout=20) as yanit:
                govde = yanit.read().decode("utf-8", errors="replace")
            veri = json.loads(govde)
            if not veri.get("success"):
                print(f"  CollectAPI: success=false - {govde[:200]!r}")
                return None
            sonuc = veri.get("result", [])
            return [
                {
                    "ad": (k.get("name") or "").strip(),
                    "tel": (k.get("phone") or "").strip(),
                    "adres": (k.get("address") or "").strip(),
                }
                for k in sonuc if k.get("name")
            ]
        except Exception as hata:
            print(f"  CollectAPI HATA (deneme {deneme}/{deneme_sayisi}): {hata}")
            if deneme < deneme_sayisi:
                time.sleep(2 * deneme)
                continue
            return None
    return None


def collectapi_onbellek_oku(onbellek_yolu, bugun_tarih_iso):
    """Bugune ait gecerli bir onbellek varsa CollectAPI sonucunu (liste) dondurur,
    yoksa None dondurur (cagiran taraf tazeden cekmesi gerektigini anlar)."""
    if not os.path.isfile(onbellek_yolu):
        return None
    try:
        with open(onbellek_yolu, "r", encoding="utf-8") as f:
            veri = json.load(f)
    except Exception:
        return None
    if veri.get("tarih_iso") != bugun_tarih_iso:
        return None
    return veri.get("collectapi_sonuc")  # None (basarisiz gun) veya liste olabilir


def collectapi_onbellek_yaz(onbellek_yolu, bugun_tarih_iso, sonuc):
    """sonuc: basarili cekimde liste, basarisiz cekimde None (aynI gun icinde
    tekrar tekrar basarisiz denemeyle kota tuketilmesin diye basarisizlik da
    onbellege yazilir - o gun bir daha denenmez, ertesi gun otomatik tekrar dener)."""
    os.makedirs(os.path.dirname(onbellek_yolu), exist_ok=True)
    with open(onbellek_yolu, "w", encoding="utf-8") as f:
        json.dump({"tarih_iso": bugun_tarih_iso, "collectapi_sonuc": sonuc}, f, ensure_ascii=False, indent=2)


def eklenen_log_yaz(zaman_damgasi, etiket, ad):
    os.makedirs(DATA_KLASORU, exist_ok=True)
    with open(EKLENENLER_LOG_YOLU, "a", encoding="utf-8") as f:
        f.write(f"{zaman_damgasi} | {etiket} | CollectAPI'den eklendi (teknikzeka'da yoktu): {ad}\n")


def workdate_bugun_mu(workdate_degeri, bugun_tarih_iso):
    """API'nin "workdate" alani ("YYYY-MM-DD HH:MM:SS") gercekten BUGUNUN
    (Istanbul saatiyle) tarihine mi ait, diye bakar. Ilk 10 karakter
    ("YYYY-MM-DD") karsilastirmasi yeterli - saat kismini gormezden gelir."""
    if not workdate_degeri:
        return False
    return str(workdate_degeri)[:10] == bugun_tarih_iso


# ---------------------------------------------------------------------------
# 11 Ekim guncellemesi: UYANDIR + YENIDEN DENE + YEDEK KAYNAK + DURUM DOSYASI
# ---------------------------------------------------------------------------

def dini_tatil_araliklarini_oku():
    """Repo kokundeki diniTatiller.txt'yi okur (ESP'nin okudugu AYNI dosya).
    Satir formati: "YYYY-MM-DD,YYYY-MM-DD,Aciklama". "#" ile baslayan/bos
    satirlar atlanir. Yeni yilin (orn. 2028) bayram tarihleri bu dosyaya
    eklenince kod DEGISMEDEN otomatik devreye girer."""
    araliklar = []
    if not os.path.isfile(DINI_TATIL_YOLU):
        return araliklar
    try:
        with open(DINI_TATIL_YOLU, "r", encoding="utf-8") as f:
            for satir in f:
                satir = satir.strip()
                if not satir or satir.startswith("#"):
                    continue
                parcalar = satir.split(",")
                if len(parcalar) < 2:
                    continue
                try:
                    bas = date.fromisoformat(parcalar[0].strip())
                    bit = date.fromisoformat(parcalar[1].strip())
                except ValueError:
                    continue
                araliklar.append((bas, bit))
    except Exception as hata:
        print(f"UYARI: diniTatiller.txt okunamadi ({hata}), sadece pazar/resmi tatiller sayilacak.")
    return araliklar


def tam_gun_nobet_gunu_mu(gun):
    """Pazar, resmi tatil (sabit tarihli) veya diniTatiller.txt'deki bir
    aralik gunu mu? Bu gunlerde nobet sabah 09:00'da yeni vardiyaya gecer."""
    if gun.weekday() == 6:
        return True
    if (gun.month, gun.day) in RESMI_TATILLER:
        return True
    for bas, bit in dini_tatil_araliklarini_oku():
        if bas <= gun <= bit:
            return True
    return False


def bekleme_politikasi(simdi):
    """(en_fazla_bekleme_sn, deneme_araligi_sn, yogun_mod) dondurur.
    YOGUN: tam gun nobet gunlerinde 09:00-09:20 arasi calisma (vardiya degisimi).
    HAFIF: tam gun gunlerinde 10:00'dan sonra, diger gunlerde 14:00'dan sonra.
    Digerlerinde (hafta ici sabah vb.) API'nin guncel olmamasi NORMAL - bekleme yok."""
    tam = tam_gun_nobet_gunu_mu(simdi.date())
    if tam and simdi.hour == 9 and simdi.minute < YOGUN_PENCERE_DK:
        return YOGUN_MAX_SN, YOGUN_ARALIK_SN, True
    if tam and simdi.hour >= 10:
        return HAFIF_MAX_SN, HAFIF_ARALIK_SN, False
    if (not tam) and simdi.hour >= 14:
        return HAFIF_MAX_SN, HAFIF_ARALIK_SN, False
    return 0, 0, False


def test_sayfasini_uyandir():
    """teknikzeka'nin TEST SAYFASINI acar (Enver'in elle yaptigi islem - sayfa
    ziyareti API'nin verisini yeniliyor gibi gorunuyor). Hata onemsenmez."""
    try:
        istek = urllib.request.Request(UYANDIR_URL, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*",
        })
        with urllib.request.urlopen(istek, timeout=20) as yanit:
            yanit.read(2048)
        print("  Test sayfasi acildi (API uyandirma).")
    except Exception as hata:
        print(f"  Test sayfasi acilamadi ({hata}) - onemli degil.")


def ilceler_taze_mi(il_verisi, ilce_norm_listesi, bugun_iso):
    for ilce_norm in ilce_norm_listesi:
        if not any(normallestir(k.get("district")) == ilce_norm and
                   workdate_bugun_mu(k.get("workdate"), bugun_iso) for k in il_verisi):
            return False
    return True


def il_verisini_taze_cek(api_il, ilce_norm_listesi, bugun_iso, max_sn, aralik_sn):
    """Ilk cagri basarisizsa hata firlatir (cagiran yedek kaynaga gecer).
    Veri eskiyse (max_sn > 0 ise) test sayfasini acip aralik_sn arayla yeniden
    dener; sure dolunca eldeki son veriyi dondurur."""
    veri = api_dan_il_verisini_cek(api_il)
    if max_sn <= 0:
        return veri
    baslangic = time.time()
    deneme = 0
    while not ilceler_taze_mi(veri, ilce_norm_listesi, bugun_iso):
        gecen = time.time() - baslangic
        if gecen + aralik_sn > max_sn:
            print(f"  [{api_il}] {int(gecen)} sn icinde guncel veri gelmedi, bekleme sona erdi.")
            break
        deneme += 1
        print(f"  [{api_il}] veri henuz bugune ait degil - uyandirma + yeniden deneme {deneme} ({int(gecen)} sn gecti)")
        test_sayfasini_uyandir()
        time.sleep(aralik_sn)
        try:
            veri = api_dan_il_verisini_cek(api_il)
        except Exception as hata:
            print(f"  yeniden deneme basarisiz: {hata}")
    return veri


def json_oku(yol, varsayilan):
    try:
        with open(yol, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return varsayilan


def onceki_liste_oku(liste_yolu):
    veri = json_oku(liste_yolu, {})
    liste = veri.get("eczaneler") if isinstance(veri, dict) else None
    return liste if isinstance(liste, list) else []


def onceki_idler_oku(gunluk_yolu):
    veri = json_oku(gunluk_yolu, {})
    idler = veri.get("nobetciler") if isinstance(veri, dict) else None
    return set(idler) if isinstance(idler, list) else set()


def tumliste_oku(il_slug, ilce_slug):
    veri = json_oku(os.path.join(DATA_KLASORU, f"{il_slug}-{ilce_slug}-tumliste.json"), {})
    liste = veri.get("eczaneler") if isinstance(veri, dict) else None
    return liste if isinstance(liste, list) else []


def tumlisteden_bul(aday, tumliste):
    """CollectAPI kaydini ilcenin tam listesindeki GERCEK kayitla eslestirir
    (once telefon, sonra isim) - boylece 'kendi eczanem' ID'si bozulmaz."""
    aday_tel = telefon_normallestir(aday.get("tel"))
    aday_isim = isim_anahtari(aday.get("ad"))
    if aday_tel:
        for k in tumliste:
            if telefon_normallestir(k.get("tel")) == aday_tel:
                return k
    if aday_isim:
        for k in tumliste:
            if isim_anahtari(k.get("ad")) == aday_isim:
                return k
    return None


def collectapi_yedek_al(api_key, il_slug, ilce_slug, api_il, api_ilce, bugun_iso, simdi, yogun):
    """Yedek kaynak sonucu (liste) ya da None.
    YOGUN modda (vardiya degisimi sabahi): saat kapisi YOK, gunde en fazla
    YOGUN_GUNLUK_CAGRI_SINIRI cagri (kota korumasi), sonuc 'sabah' onbellegine yazilir.
    Diger modlarda: eski davranis - COLLECTAPI_EN_ERKEN_SAAT'ten sonra gunde 1 cagri."""
    if not api_key:
        return None
    if yogun:
        yol = os.path.join(DATA_KLASORU, f"{il_slug}-{ilce_slug}-collectapi-sabah.json")
        onb = json_oku(yol, {})
        if onb.get("tarih_iso") != bugun_iso:
            onb = {"tarih_iso": bugun_iso, "cagri_sayisi": 0, "son_sonuc": None}
        if onb.get("cagri_sayisi", 0) >= YOGUN_GUNLUK_CAGRI_SINIRI:
            print(f"[{il_slug}-{ilce_slug}] CollectAPI sabah cagri siniri doldu, onbellekteki sonuc kullaniliyor.")
            return onb.get("son_sonuc")
        print(f"[{il_slug}-{ilce_slug}] CollectAPI (vardiya sabahi) cekiliyor...")
        sonuc = collectapi_il_ilce_cek(api_key, api_il, api_ilce)
        onb["cagri_sayisi"] = onb.get("cagri_sayisi", 0) + 1
        if sonuc is not None:
            onb["son_sonuc"] = sonuc
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(onb, f, ensure_ascii=False, indent=2)
        return sonuc if sonuc is not None else onb.get("son_sonuc")

    onbellek_yolu = os.path.join(DATA_KLASORU, f"{il_slug}-{ilce_slug}-collectapi-onbellek.json")
    bugune_ait = json_oku(onbellek_yolu, {}).get("tarih_iso") == bugun_iso
    if bugune_ait:
        return collectapi_onbellek_oku(onbellek_yolu, bugun_iso)
    if simdi.hour < COLLECTAPI_EN_ERKEN_SAAT:
        return None
    print(f"[{il_slug}-{ilce_slug}] CollectAPI onbellegi bugune ait degil, tazeden cekiliyor...")
    sonuc = collectapi_il_ilce_cek(api_key, api_il, api_ilce)
    collectapi_onbellek_yaz(onbellek_yolu, bugun_iso, sonuc)
    return sonuc


def haric_listesi_oku(etiket):
    """data/haric-eczaneler.json -> {"istanbul-maltepe": [63607, "BIR ECZANE ADI"], ...}
    Bir ilce icin listedeki id (sayi) ya da ad (metin) eslesen eczaneler nobetci listesine
    HIC alinmaz (kaynak API hatali ilce veriyorsa). Dosya yoksa/bozuksa bos doner.
    Doner: (id_kumesi, normallesmis_isim_kumesi)"""
    veri = json_oku(HARIC_YOLU, {})
    girdiler = veri.get(etiket, []) if isinstance(veri, dict) else []
    idler, isimler = set(), set()
    for g in girdiler:
        if isinstance(g, bool):
            continue
        if isinstance(g, dict):
            # {"id": 15659, "bitis": "2026-10-15"} -> bitis tarihinden (dahil) sonra hariclik OTOMATIK kalkar
            bitis = g.get("bitis")
            if isinstance(bitis, str) and bitis.strip():
                try:
                    if simdi_istanbul().date() > date.fromisoformat(bitis.strip()):
                        continue
                except ValueError:
                    pass
            g = g.get("id") if g.get("id") is not None else g.get("ad")
            if g is None or isinstance(g, bool):
                continue
        if isinstance(g, int):
            idler.add(g)
        elif isinstance(g, str) and g.strip():
            if g.strip().isdigit():
                idler.add(int(g.strip()))
            else:
                isimler.add(isim_anahtari(g))
    return idler, isimler


def haric_olanlari_cikar(eczaneler, idler, etiket):
    """Hariç listesindeki eczaneleri yerinde cikarir; cikarilan sayisini dondurur."""
    haric_idler, haric_isimler = haric_listesi_oku(etiket)
    if not haric_idler and not haric_isimler:
        return 0
    kalan, kalan_idler, cikan = [], [], 0
    for e in eczaneler:
        if e.get("id") in haric_idler or isim_anahtari(e.get("ad")) in haric_isimler:
            cikan += 1
            print(f"[{etiket}] HARIC TUTULDU (haric-eczaneler.json): {e.get('ad')} (id {e.get('id')})")
            continue
        kalan.append(e)
        kalan_idler.append(e.get("id"))
    eczaneler[:] = kalan
    idler[:] = kalan_idler
    return cikan


def duzeltmeleri_uygula(eczaneler, etiket):
    """data/duzeltmeler.json -> {"istanbul-maltepe": {"15650": {"adres": "...", "tel": "...", "ad": "..."}}}
    Kaynak API'nin yanlis/eski yazdigi alanlari ID'ye gore ezer (sadece verilen alanlar).
    Dosya yoksa/bozuksa hicbir sey yapmaz. Uygulanan kayit sayisini dondurur."""
    veri = json_oku(DUZELTME_YOLU, {})
    ilce = veri.get(etiket, {}) if isinstance(veri, dict) else {}
    if not isinstance(ilce, dict) or not ilce:
        return 0
    uygulanan = 0
    for e in eczaneler:
        d = ilce.get(str(e.get("id")))
        if not isinstance(d, dict):
            continue
        # Istege bagli "bitis": "YYYY-MM-DD" -> duzeltme bu tarihten (dahil) sonra OTOMATIK devre disi
        # (kaynak API'nin SADECE o gun yanlis yazdigi kayitlar icin; kalici duzeltmelerde "bitis" yazilmaz).
        bitis = d.get("bitis")
        if isinstance(bitis, str) and bitis.strip():
            try:
                if simdi_istanbul().date() > date.fromisoformat(bitis.strip()):
                    continue
            except ValueError:
                pass
        for alan in ("ad", "tel", "adres"):
            if isinstance(d.get(alan), str) and d[alan].strip():
                e[alan] = d[alan].strip()
        uygulanan += 1
        print(f"[{etiket}] DUZELTME uygulandi (duzeltmeler.json): id {e.get('id')}")
    return uygulanan


def yedegi_listeye_ekle(eczaneler, idler, yedek_sonuc, tumliste, etiket, neden):
    """Yedek kaynaktaki, listede OLMAYAN eczaneleri ekler (telefon/isim eslesmesi).
    Eklenen sayisini dondurur."""
    mevcut_isimler = {isim_anahtari(e["ad"]) for e in eczaneler}
    mevcut_tel = {telefon_normallestir(e["tel"]) for e in eczaneler if telefon_normallestir(e["tel"])}
    zaman_damgasi = simdi_istanbul().strftime("%Y-%m-%d %H:%M")
    eklenen = 0
    for aday in yedek_sonuc:
        isim_norm = isim_anahtari(aday.get("ad"))
        tel_norm = telefon_normallestir(aday.get("tel"))
        if not isim_norm:
            continue
        if (tel_norm and tel_norm in mevcut_tel) or isim_norm in mevcut_isimler:
            continue
        gercek = tumlisteden_bul(aday, tumliste)
        if gercek is not None and gercek.get("id") is not None:
            kayit = {"id": gercek["id"], "ad": gercek.get("ad") or aday["ad"],
                     "tel": gercek.get("tel") or aday["tel"], "adres": gercek.get("adres") or aday["adres"]}
        else:
            kayit = {"id": sentetik_id_uret(normallestir(aday.get("ad"))), "ad": aday["ad"], "tel": aday["tel"], "adres": aday["adres"]}
        if kayit["id"] in idler:
            continue
        eczaneler.append(kayit)
        idler.append(kayit["id"])
        mevcut_isimler.add(isim_norm)
        if tel_norm:
            mevcut_tel.add(tel_norm)
        eklenen += 1
        print(f"[{etiket}] CollectAPI'den EKLENDI ({neden}): {aday['ad']}")
        eklenen_log_yaz(zaman_damgasi, etiket, aday["ad"])
    return eklenen


def durum_dosyasini_yaz(durumlar, simdi):
    os.makedirs(DATA_KLASORU, exist_ok=True)
    with open(DURUM_YOLU, "w", encoding="utf-8") as f:
        json.dump({
            "tarih": simdi.strftime("%Y-%m-%d"),
            "zaman": simdi_istanbul().strftime("%H:%M"),
            "ilceler": durumlar,
        }, f, ensure_ascii=False, indent=2)
    print(f"Durum dosyasi yazildi: {DURUM_YOLU}")


ODASI_YOLU = os.path.join(DATA_KLASORU, "odasi-bugun.json")  # scripts/odasi_cek.py yazar
ODASI_MAX_YAS_DK = 45
ODASI_SENTETIK_ID_TABANI = 8_000_000  # + Odasi sicil no (tumlistede olmayan eczaneler icin)


def odasi_verisini_oku(simdi):
    """Odasi dosyasi BUGUNE ait ve taze ise eczane listesini, degilse None dondurur."""
    veri = json_oku(ODASI_YOLU, {})
    if not isinstance(veri, dict) or not isinstance(veri.get("eczaneler"), list):
        return None
    zaman = str(veri.get("zaman") or "")
    try:
        z = datetime.strptime(zaman, "%Y-%m-%d %H:%M")
    except Exception:
        return None
    if zaman[:10] != simdi.strftime("%Y-%m-%d"):
        print(f"Odasi verisi BUGUNE ait degil ({zaman}) - eski sisteme donuluyor.")
        return None
    yas_dk = (simdi.replace(tzinfo=None) - z).total_seconds() / 60
    if yas_dk > ODASI_MAX_YAS_DK:
        print(f"Odasi verisi eski ({int(yas_dk)} dk) - eski sisteme donuluyor.")
        return None
    return veri["eczaneler"]


def odasi_ilce_listesi(odasi_eczaneler, api_ilce, tumliste, etiket):
    """Odasi kayitlarindan ilcenin (eczaneler, idler) listesini kurar.
    Tumlistede (telefon/isim) eslesen eczanenin id/ad/adres'i KORUNUR (panelde bugunku
    gorunum bozulmasin); eslesmeyenler icin Odasi bilgisi + sentetik id (8_000_000+sicil)."""
    hedef = normallestir(api_ilce)
    eczaneler, idler, gorulen_tel = [], [], set()
    for e in odasi_eczaneler:
        if normallestir(e.get("ilce")) != hedef:
            continue
        tel = telefon_normallestir(e.get("tel"))
        if tel and tel in gorulen_tel:
            continue
        aday = {"ad": e.get("ad"), "tel": e.get("tel"), "adres": e.get("adres")}
        gercek = tumlisteden_bul(aday, tumliste)
        if gercek is not None and gercek.get("id") is not None:
            kayit = {"id": gercek["id"], "ad": gercek.get("ad") or aday["ad"],
                     "tel": gercek.get("tel") or aday["tel"], "adres": gercek.get("adres") or aday["adres"]}
        else:
            sicil = e.get("sicil")
            eid = ODASI_SENTETIK_ID_TABANI + int(sicil) if str(sicil).isdigit() else sentetik_id_uret(normallestir(e.get("ad")))
            kayit = {"id": eid, "ad": (aday["ad"] or "").strip(), "tel": (aday["tel"] or "").strip(),
                     "adres": (aday["adres"] or "").strip()}
            print(f"[{etiket}] Odasi'ndan tumlistede OLMAYAN eczane: {kayit['ad']} (id {eid})")
        if kayit["id"] in idler:
            continue
        if tel:
            gorulen_tel.add(tel)
        eczaneler.append(kayit)
        idler.append(kayit["id"])
    return eczaneler, idler


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

    simdi = simdi_istanbul()
    bugun_tarih_iso = simdi.strftime("%Y-%m-%d")
    max_sn, aralik_sn, yogun = bekleme_politikasi(simdi)
    if os.environ.get("YOGUN_ZORLA", "").strip() == "1":
        # TEST icin: workflow'a gecici olarak YOGUN_ZORLA: "1" ortam degiskeni eklenirse
        # saat/gun ne olursa olsun yogun mod calisir (durum dosyasi da yazilir).
        max_sn, aralik_sn, yogun = YOGUN_MAX_SN, YOGUN_ARALIK_SN, True
    print(f"Mod: {'YOGUN (tam gun nobeti vardiya sabahi)' if yogun else 'normal'} - "
          f"eski veride en fazla {max_sn} sn uyandirma/yeniden deneme.")

    collectapi_key = os.environ.get("COLLECTAPI_KEY", "").strip()

    il_ilceleri = {}
    for k in kaynaklar:
        if k.get("api_il") and k.get("api_ilce"):
            il_ilceleri.setdefault(k["api_il"], []).append(normallestir(k["api_ilce"]))

    odasi_verisi = odasi_verisini_oku(simdi)
    print("Odasi verisi: " + (f"{len(odasi_verisi)} kayit (ANA KAYNAK)" if odasi_verisi else "YOK - eski sistem (teknikzeka+CollectAPI)"))

    il_cache = {}
    durumlar = {}
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

        # --- 20 Ekim: ANA KAYNAK = Istanbul Eczaci Odasi (scripts/odasi_cek.py) ---
        if odasi_verisi:
            o_eczaneler, o_idler = odasi_ilce_listesi(odasi_verisi, api_ilce, tumliste_oku(il_slug, ilce_slug), etiket)
            if o_eczaneler:
                haric_olanlari_cikar(o_eczaneler, o_idler, etiket)
                duzeltmeleri_uygula(o_eczaneler, etiket)
                liste_yolu = os.path.join(DATA_KLASORU, f"{il_slug}-{ilce_slug}-liste.json")
                gunluk_yolu = os.path.join(DATA_KLASORU, f"{il_slug}-{ilce_slug}.json")
                onceki_idler = onceki_idler_oku(gunluk_yolu)
                with open(liste_yolu, "w", encoding="utf-8") as f:
                    json.dump({"eczaneler": o_eczaneler}, f, ensure_ascii=False, indent=2)
                with open(gunluk_yolu, "w", encoding="utf-8") as f:
                    json.dump({"tarih": tarih_metni, "nobetciler": o_idler}, f, ensure_ascii=False, indent=2)
                durumlar[etiket] = {"durum": "guncellendi", "kaynak": "odasi", "eczane_sayisi": len(o_eczaneler),
                                    "eklenen": 0, "liste_degisti": set(o_idler) != onceki_idler}
                print(f"[{etiket}] OK (odasi): {len(o_eczaneler)} eczane yazildi.")
                basarili_sayisi += 1
                continue
            print(f"[{etiket}] Odasi'nda bu ilce icin kayit yok - eski sisteme donuluyor.")

        if api_il not in il_cache:
            print(f"[{api_il}] API'den cekiliyor...")
            try:
                il_cache[api_il] = il_verisini_taze_cek(api_il, il_ilceleri[api_il], bugun_tarih_iso, max_sn, aralik_sn)
            except Exception as hata:
                print(f"[{etiket}] teknikzeka API cagrisi basarisiz ({hata}) - yedek kaynak denenecek.")
                il_cache[api_il] = []
        il_verisi = il_cache[api_il]

        hedef_ilce_norm = normallestir(api_ilce)
        ilce_eslesenler = [k for k in il_verisi if normallestir(k.get("district")) == hedef_ilce_norm]
        eslesenler = [k for k in ilce_eslesenler if workdate_bugun_mu(k.get("workdate"), bugun_tarih_iso)]

        liste_yolu = os.path.join(DATA_KLASORU, f"{il_slug}-{ilce_slug}-liste.json")
        gunluk_yolu = os.path.join(DATA_KLASORU, f"{il_slug}-{ilce_slug}.json")
        onceki_liste = onceki_liste_oku(liste_yolu)
        onceki_idler = onceki_idler_oku(gunluk_yolu)
        onceki_tel = {telefon_normallestir(e.get("tel")) for e in onceki_liste if telefon_normallestir(e.get("tel"))}
        onceki_isimler = {isim_anahtari(e.get("ad")) for e in onceki_liste}

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
        teknikzeka_taze = bool(eczaneler)

        if teknikzeka_taze:
            print(f"[{etiket}] teknikzeka verisi GUNCEL ({len(eczaneler)} eczane).")
        elif ilce_eslesenler:
            print(f"[{etiket}] teknikzeka: kayit var ama workdate bugune ({bugun_tarih_iso}) ait degil (API henuz guncellenmemis).")
        else:
            print(f"[{etiket}] teknikzeka: '{api_ilce}' icin hic kayit donmedi.")

        # --- YEDEK KAYNAK (CollectAPI) ---
        yedek_sonuc = collectapi_yedek_al(collectapi_key, il_slug, ilce_slug, api_il, api_ilce,
                                          bugun_tarih_iso, simdi, yogun)
        yedek_degisti = False
        if yedek_sonuc:
            cr_tel = {telefon_normallestir(a.get("tel")) for a in yedek_sonuc if telefon_normallestir(a.get("tel"))}
            cr_isimler = {isim_anahtari(a.get("ad")) for a in yedek_sonuc}
            if not onceki_liste:
                yedek_degisti = True
            elif cr_tel and onceki_tel:
                yedek_degisti = (cr_tel != onceki_tel)
            else:
                yedek_degisti = (cr_isimler != onceki_isimler)
            print(f"[{etiket}] CollectAPI {len(yedek_sonuc)} kayit dondu; onceki listeden "
                  f"{'FARKLI (guncellenmis gorunuyor)' if yedek_degisti else 'AYNI (henuz guncellenmemis olabilir)'}.")

        kaynak_etiketi = None
        eklenen = 0
        not_metni = None
        if teknikzeka_taze:
            kaynak_etiketi = "teknikzeka"
            if yedek_sonuc and (yedek_degisti or not yogun):
                eklenen = yedegi_listeye_ekle(eczaneler, idler, yedek_sonuc, tumliste_oku(il_slug, ilce_slug), etiket, "teknikzeka'da yoktu")
                if eklenen:
                    kaynak_etiketi = "teknikzeka+collectapi"
            elif yedek_sonuc and yogun and not yedek_degisti:
                not_metni = "yedek kaynak henuz guncellenmemis"
        elif yedek_sonuc and yedek_degisti:
            tumliste = tumliste_oku(il_slug, ilce_slug)
            eklenen = yedegi_listeye_ekle(eczaneler, idler, yedek_sonuc, tumliste, etiket,
                                          "teknikzeka guncel degil - ANA KAYNAK olarak")
            if eczaneler:
                kaynak_etiketi = "collectapi"

        haric_olanlari_cikar(eczaneler, idler, etiket)
        duzeltmeleri_uygula(eczaneler, etiket)

        if kaynak_etiketi is None:
            print(f"[{etiket}] ATLANDI: guncel veri alinamadi (ne teknikzeka ne yedek). Mevcut dosyalar korunuyor.")
            atlanan_sayisi += 1
            durumlar[etiket] = {"durum": "guncellenemedi"}
            continue

        with open(liste_yolu, "w", encoding="utf-8") as f:
            json.dump({"eczaneler": eczaneler}, f, ensure_ascii=False, indent=2)
        with open(gunluk_yolu, "w", encoding="utf-8") as f:
            json.dump({"tarih": tarih_metni, "nobetciler": idler}, f, ensure_ascii=False, indent=2)

        durumlar[etiket] = {
            "durum": "guncellendi",
            "kaynak": kaynak_etiketi,
            "eczane_sayisi": len(eczaneler),
            "eklenen": eklenen,
            "liste_degisti": set(idler) != onceki_idler,
        }
        if not_metni:
            durumlar[etiket]["not"] = not_metni

        print(f"[{etiket}] OK ({kaynak_etiketi}): {len(eczaneler)} eczane yazildi.")
        basarili_sayisi += 1

    if yogun:
        durum_dosyasini_yaz(durumlar, simdi)

    print(f"\nOzet: {basarili_sayisi} basarili, {atlanan_sayisi} atlandi.")


if __name__ == "__main__":
    main()
