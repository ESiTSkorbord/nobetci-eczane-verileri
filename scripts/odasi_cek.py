#!/usr/bin/env python3
"""Istanbul Eczaci Odasi nobetci listesi (ANA KAYNAK).
23 Ekim: Odasi sitesi YENILENDI. Eski tek-istek (nobetci-eczane/index.php, POST) kalkti; yeni site
ilce ilce JSON veriyor: GET /api/nobetci-eczane-web/?action=district&id=<ilceId>
(cevap: {"success":true,"data":[{sicil,ad,ilce,ilceId,adres,nobetTarih,...}],"meta":{...}}).
Yeni cevapta telefon YOK (sadece phoneTicket) -> tel bos birakilir; senkronize.py telefonu
tumlisteden isimle tamamlar. Cikti formati ESKISIYLE AYNI (data/odasi-bugun.json), senkronize.py degismez.
Sayfayi gercek tarayiciyla acar (cerez/koruma icin), sonra sayfanin icinden ilce id'lerini tarar.
23 Ekim (hafif mod): SADECE config/eczane-kaynaklari.json'daki Istanbul ilceleri cekilir (saatte ~2 istek);
ilce id'leri data/odasi-ilce-idleri.json'da onbelleklenir (yoksa/eksikse BIR KERE 1-60 taranir);
telefon sadece onbellekte (data/odasi-telefon.json, 30 gun) OLMAYAN eczaneler icin sorulur.
Basarisiz olursa dosyaya DOKUNMAZ (eski sistem devreye girer) ve cikis kodu 0 doner."""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

URL = "https://www.istanbuleczaciodasi.org.tr/nobetci-eczane/"
API = "/api/nobetci-eczane-web/?action=district&id="
ILCE_ID_ARALIK = range(1, 61)  # Istanbul ilce id'leri (Maltepe=22); bos donenler atlanir
KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CIKTI = os.path.join(KOK, "data", "odasi-bugun.json")
KONFIG = os.path.join(KOK, "config", "eczane-kaynaklari.json")
ID_ONBELLEK = os.path.join(KOK, "data", "odasi-ilce-idleri.json")
TEL_ONBELLEK = os.path.join(KOK, "data", "odasi-telefon.json")
TEL_GECERLILIK_GUN = 30

JS_TARA = r"""
async ([sablon, telSablon, basliklar, ids, telBilinen, hedefler]) => {
  const out = [];
  const bekle = ms => new Promise(res => setTimeout(res, ms));
  const bilinen = new Set(telBilinen);
  const norm = m => String(m || "").replace(/İ/g, "I").replace(/ı/g, "I").replace(/i/g, "I")
    .replace(/Ş|ş/g, "S").replace(/Ğ|ğ/g, "G").replace(/Ü|ü/g, "U").replace(/Ö|ö/g, "O").replace(/Ç|ç/g, "C")
    .trim().toUpperCase().replace(/\s+/g, " ");
  for (const id of ids) {
    const url = sablon.replace(/([?&])id=\d+/, "$1id=" + id);
    let durum = 0, metin = "", tel = {};
    try {
      const r = await fetch(url, {headers: basliklar});
      durum = r.status;
      metin = await r.text();
      if (durum === 200) {
        let d = null;
        try { d = JSON.parse(metin); } catch (e) {}
        const liste = (d && Array.isArray(d.data)) ? d.data : [];
        for (const e of liste) {
          if (!e.phoneTicket || bilinen.has(String(e.sicil)) || !hedefler.includes(norm(e.ilce))) continue;
          try {
            const pr = await fetch(telSablon, {
              method: "POST",
              headers: Object.assign({}, basliklar, {"Content-Type": "application/json"}),
              body: JSON.stringify({regionId: e.regionId, sicil: String(e.sicil), ticket: e.phoneTicket})
            });
            tel[String(e.sicil)] = [pr.status, (await pr.text()).slice(0, 400)];
          } catch (x) {
            tel[String(e.sicil)] = [0, String(x).slice(0, 80)];
          }
          await bekle(300);
        }
      }
    } catch (e) {
      metin = String(e).slice(0, 80);
    }
    out.push([id, durum, metin, tel]);
    await bekle(400);
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
                      "ilce": e.get("ilce"), "adres": adres, "bitis": e.get("dutyEndsAt") or ""})
    return sonuc


class BayatVeri(Exception):
    """Odasi cevabi var ama nobet suresi zaten bitmis (09:00 vardiya degisimi, site henuz guncellemedi)."""


def en_erken_bitis(liste):
    """Kayitlardaki dutyEndsAt'larin en erkeni (aware datetime) ya da None."""
    bitisler = []
    for k in liste:
        try:
            bitisler.append(datetime.fromisoformat(k.get("bitis") or ""))
        except Exception:
            pass
    return min(bitisler) if bitisler else None


YASAK_BASLIK = {"host", "content-length", "user-agent", "referer", "origin", "accept-encoding",
                "connection", "cookie", "priority"}


def _norm(m):
    m = str(m or "").strip().replace("İ", "I").replace("ı", "I").replace("i", "I")
    m = m.translate(str.maketrans("ŞşĞğÜüÖöÇç", "SsGgUuOoCc"))
    return " ".join(m.upper().split())


def json_oku(yol, varsayilan):
    try:
        with open(yol, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return varsayilan


def hedef_ilceler():
    """Config'teki Istanbul ilceleri (normallestirilmis ad listesi)."""
    k = json_oku(KONFIG, {}).get("kaynaklar", [])
    return sorted({_norm(x.get("api_ilce")) for x in k if _norm(x.get("api_il")) == "ISTANBUL" and x.get("api_ilce")})


def telefon_coz(metin):
    """Telefon cevabindan (JSON, sekli bilinmiyor) 10 haneli numarayi cikarir; bulamazsa ''.
    Once 'phone/tel' iceren anahtarlara, sonra herhangi bir string/liste degerine bakar."""
    import re
    try:
        d = json.loads(metin)
    except Exception:
        d = metin

    def rakamlar(v):
        r = "".join(c for c in str(v) if c.isdigit())
        if len(r) == 11 and r[0] == "0":
            r = r[1:]
        elif len(r) == 12 and r[:2] == "90":
            r = r[2:]
        return r if len(r) == 10 else ""

    def tara(v, anahtarli):
        if isinstance(v, dict):
            for k, x in v.items():
                kl = str(k).lower()
                bulunan = tara(x, anahtarli or "phone" in kl or "tel" in kl or "number" in kl or "numara" in kl)
                if bulunan:
                    return bulunan
        elif isinstance(v, list):
            for x in v:
                bulunan = tara(x, anahtarli)
                if bulunan:
                    return bulunan
        elif isinstance(v, (str, int)) and not isinstance(v, bool):
            if anahtarli or isinstance(v, str):
                return rakamlar(v)
        return ""

    return tara(d, False)


def cek():
    hedefler = hedef_ilceler()
    if not hedefler:
        print("[TESHIS] config'te Istanbul ilcesi yok - atlandi.")
        return []
    idler = json_oku(ID_ONBELLEK, {})
    eksik = [h for h in hedefler if h not in idler]
    tel_onbellek = json_oku(TEL_ONBELLEK, {})
    bugun = (datetime.now(timezone(timedelta(hours=3)))).date()
    gecerli_tel = {}
    for sicil, v in tel_onbellek.items():
        try:
            yas = (bugun - datetime.strptime(v.get("tarih", ""), "%Y-%m-%d").date()).days
        except Exception:
            continue
        if yas <= TEL_GECERLILIK_GUN and v.get("tel"):
            gecerli_tel[str(sicil)] = v

    taranacak = list(ILCE_ID_ARALIK) if eksik else sorted({int(idler[h]) for h in hedefler})
    yakalanan, gorulen = {}, []

    def istek(r):
        if "/api/nobetci-eczane-web/" in r.url:
            gorulen.append("%s [basliklar: %s]" % (r.url[:110], ",".join(sorted(r.headers.keys()))[:200]))
            if "url" not in yakalanan and "action=district" in r.url:
                yakalanan["url"] = r.url
                yakalanan["basliklar"] = {k: v for k, v in r.headers.items()
                                          if k.lower() not in YASAK_BASLIK and not k.lower().startswith("sec-")
                                          and not k.startswith(":")}

    with sync_playwright() as p:
        t = p.chromium.launch()
        s = t.new_page(viewport={"width": 1300, "height": 1400}, locale="tr-TR")
        s.on("request", istek)
        try:
            s.goto(URL + "?ilce=22", wait_until="networkidle", timeout=60000)
            s.wait_for_timeout(3000)
        except Exception as e:
            print("[TESHIS] sayfa acilamadi: %s" % str(e)[:150])
        if "url" not in yakalanan:
            print("[TESHIS] sayfa kendi ilce istegini yapmadi; gorulen API istekleri:")
            for g in gorulen[:8]:
                print("[TESHIS]   " + g)
            t.close()
            return []
        tel_url = re.sub(r"action=district&id=\d+", "action=phone", yakalanan["url"])
        sonuclar = s.evaluate(JS_TARA, [yakalanan["url"], tel_url, yakalanan["basliklar"], taranacak,
                                        sorted(gecerli_tel.keys()), hedefler])
        t.close()

    kayitlar, hatalar, bulunan_idler = {}, [], {}
    tel_ok, tel_onb, tel_yok, tel_ornek = 0, 0, 0, []
    for ilce_id, durum, metin, tel_cevaplari in sonuclar:
        if durum != 200:
            hatalar.append("id %s -> HTTP %s %s" % (ilce_id, durum, metin[:200]))
            continue
        liste = ilce_yanitini_coz(metin)
        if liste:
            bulunan_idler[_norm(liste[0]["ilce"])] = ilce_id
        for k in liste:
            if _norm(k["ilce"]) not in hedefler:
                continue
            sic = str(k["sicil"])
            if sic in gecerli_tel:
                k["tel"] = gecerli_tel[sic]["tel"]
                tel_onb += 1
            else:
                durum_tel, cevap = (tel_cevaplari.get(sic) or [0, ""])
                numara = telefon_coz(cevap) if durum_tel == 200 else ""
                if numara:
                    k["tel"] = numara
                    tel_onbellek[sic] = {"tel": numara, "tarih": bugun.strftime("%Y-%m-%d")}
                    tel_ok += 1
                else:
                    tel_yok += 1
                    if len(tel_ornek) < 2:
                        tel_ornek.append("sicil %s -> HTTP %s %r" % (k["sicil"], durum_tel, cevap[:120]))
            kayitlar[k["sicil"] if k["sicil"] is not None else (k["ad"], k["ilce"])] = k

    # ilce id onbellegini guncelle (sadece hedef ilceler)
    degisti = False
    for h in hedefler:
        if h in bulunan_idler and idler.get(h) != bulunan_idler[h]:
            idler[h] = bulunan_idler[h]
            degisti = True
    if degisti:
        os.makedirs(os.path.dirname(ID_ONBELLEK), exist_ok=True)
        with open(ID_ONBELLEK, "w", encoding="utf-8") as f:
            json.dump(idler, f, ensure_ascii=False, indent=1)
    # telefon onbellegi (30 gunden eskiler atilir)
    tel_onbellek = {k: v for k, v in tel_onbellek.items()
                    if isinstance(v, dict) and v.get("tel")}
    os.makedirs(os.path.dirname(TEL_ONBELLEK), exist_ok=True)
    with open(TEL_ONBELLEK, "w", encoding="utf-8") as f:
        json.dump(tel_onbellek, f, ensure_ascii=False, indent=1)

    print("Odasi: %s ilceleri, %d eczane | telefon: %d onbellekten, %d yeni alindi, %d alinamadi%s"
          % (",".join(hedefler), len(kayitlar), tel_onb, tel_ok, tel_yok, " | id taramasi yapildi" if eksik else ""))
    for o in tel_ornek:
        print("[TESHIS] telefon alinamadi: " + o)
    # her hedef ilce icin cevap alinmis olmali (aksi halde dosyaya yazma)
    eksik_kalan = [h for h in hedefler if h not in bulunan_idler and h not in idler]
    if eksik_kalan:
        print("[TESHIS] id bulunamayan ilce: %s" % ",".join(eksik_kalan))
        return []
    if hatalar:
        for h in hatalar[:3]:
            print("[TESHIS] " + h)
        print("[TESHIS] toplam %d istekte hata" % len(hatalar))
        return []
    sonuc = list(kayitlar.values())
    bitis = en_erken_bitis(sonuc)
    if bitis is not None and datetime.now(timezone.utc) >= bitis:
        raise BayatVeri("nobet suresi bitmis (bitis=%s)" % bitis.isoformat())
    return sonuc


def vardiya_penceresi_mi():
    """Istanbul saatiyle 08:55-09:45 (sabah vardiya degisimi; Pazar/tatilde tam gun nobet de burada biter) ve
    18:55-19:45 (gunduz/gece ayri yayinlanirsa): Odasi bu araliklara yakin guncelliyor (09:01 .. 09:15 ..)."""
    t = datetime.now(timezone(timedelta(hours=3)))
    dk = t.hour * 60 + t.minute
    return (8 * 60 + 55 <= dk <= 9 * 60 + 45) or (18 * 60 + 55 <= dk <= 19 * 60 + 45)


def main():
    liste = None
    bayat, hata = 0, 0
    while True:
        # Vardiya penceresinde (09:00 civari) Odasi guncellenene kadar 3 dk arayla en cok 12 kez (~35 dk) bekle;
        # pencere disinda 3 kez, 75 sn arayla. Her bekleme sadece "nobet suresi bitmis" durumunda olur.
        pencere = vardiya_penceresi_mi()
        limit, aralik = (12, 180) if pencere else (3, 75)
        try:
            liste = cek()
            if liste:
                break
            hata += 1
        except BayatVeri as e:
            bayat += 1
            print("Odasi henuz guncellenmedi (deneme %d/%d): %s" % (bayat, limit, e))
            if bayat >= limit:
                liste = None
                break
            time.sleep(aralik)
            continue
        except Exception as e:
            hata += 1
            print("Odasi cekme hatasi (deneme %d): %s" % (hata, str(e)[:200]))
        if hata >= 3:
            break
    if not liste:
        print("Odasi verisi alinamadi/supheli (%s kayit) - dosya degistirilmedi." % (len(liste) if liste else 0))
        return 0
    z = datetime.now(timezone(timedelta(hours=3)))
    os.makedirs(os.path.dirname(CIKTI), exist_ok=True)
    with open(CIKTI, "w", encoding="utf-8") as f:
        bitis = en_erken_bitis(liste)
        json.dump({"zaman": z.strftime("%Y-%m-%d %H:%M"), "adet": len(liste),
                   "gecerli_kadar": bitis.isoformat() if bitis else "", "eczaneler": liste},
                  f, ensure_ascii=False, indent=1)
    print("Odasi: %d eczane yazildi (%s)" % (len(liste), z.strftime("%H:%M")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
