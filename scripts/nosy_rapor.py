#!/usr/bin/env python3
"""NosyAPI <-> bizim yayinlanan liste uyusmazlik raporu.
SADECE rapor yazar: data/ klasorune DOKUNMAZ, panele bir etkisi yoktur.
config/eczane-kaynaklari.json'daki her ilce icin:
  - NosyAPI'den nobetci listesini ceker (ilce basina 1 kredi)
  - data/<il>-<ilce>-liste.json (bizim yayinlanan liste) ile telefondan eslestirir
  - farki test/nosy-rapor.txt dosyasina ekler, ham yaniti test/nosy-gecmis/ altina saklar."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ANAHTAR = os.environ.get("NOSY_KEY", "").strip()
TABAN = "https://www.nosyapi.com/apiv2/service/pharmacies-on-duty"
RAPOR = "test/nosy-rapor.txt"


def simdi_istanbul():
    return datetime.now(timezone(timedelta(hours=3)))


def normallestir(metin):
    if metin is None:
        return ""
    metin = str(metin).strip()
    metin = metin.replace("İ", "I").replace("ı", "I").replace("i", "I")
    return " ".join(metin.upper().split())


def isim_anahtari(metin):
    parcalar = normallestir(metin).split()
    while len(parcalar) > 1 and parcalar[-1] in ("ECZANESI", "ECZANE", "ECZ", "ECZ."):
        parcalar.pop()
    return " ".join(parcalar)


def telefon_normallestir(ham):
    r = "".join(ch for ch in str(ham or "") if ch.isdigit())
    if len(r) == 11 and r[0] == "0":
        r = r[1:]
    elif len(r) == 12 and r[:2] == "90":
        r = r[2:]
    return r if len(r) == 10 else ""


def json_oku(yol, varsayilan):
    try:
        with open(yol, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return varsayilan


def nosy_cek(api_il, api_ilce):
    url = TABAN + "?" + urllib.parse.urlencode({"city": api_il, "district": api_ilce})
    r = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + ANAHTAR,
        "Accept": "application/json",
        "User-Agent": "nobetci-eczane-rapor/1.0",
    })
    try:
        with urllib.request.urlopen(r, timeout=30) as s:
            return s.status, json.loads(s.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, None
    except Exception as e:
        return 0, {"hata": str(e)}


def kayitlar(veri):
    if isinstance(veri, dict):
        for k in ("data", "result", "results", "pharmacies"):
            v = veri.get(k)
            if isinstance(v, list):
                return v
    return []


def anahtarlar(ad, tel):
    return (telefon_normallestir(tel), isim_anahtari(ad))


def eslesir(a, b):
    """Telefon varsa telefon, yoksa isim esler."""
    if a[0] and b[0]:
        return a[0] == b[0]
    return bool(a[1]) and a[1] == b[1]


def main():
    if not ANAHTAR:
        print("NOSY_KEY tanimli degil.")
        sys.exit(1)
    config = json_oku("config/eczane-kaynaklari.json", {"kaynaklar": []})
    zaman = simdi_istanbul()
    zaman_metni = zaman.strftime("%Y-%m-%d %H:%M")
    dosya_oneki = zaman.strftime("%Y-%m-%d_%H%M")
    os.makedirs("test/nosy-gecmis", exist_ok=True)
    satirlar = ["", "=== %s ===" % zaman_metni]
    fark_var = False

    for k in config.get("kaynaklar", []):
        il, ilce = k["il_slug"], k["ilce_slug"]
        etiket = "%s-%s" % (il, ilce)
        kod, veri = nosy_cek(k["api_il"], k["api_ilce"])
        with open("test/nosy-gecmis/%s_%s.json" % (dosya_oneki, etiket), "w", encoding="utf-8") as f:
            json.dump({"alindi": zaman_metni, "http": kod, "yanit": veri}, f,
                      ensure_ascii=False, indent=1)
        if kod != 200 or not isinstance(veri, dict) or veri.get("status") != "success":
            satirlar.append("[%s] NOSY HATA http=%s  %s" % (etiket, kod, (veri or {}).get("messageTR", "")))
            continue
        nosy = [(n.get("pharmacyName", ""), n.get("phone", "")) for n in kayitlar(veri)]
        bizim_veri = json_oku("data/%s-liste.json" % etiket, {})
        bizim = [(b.get("ad", ""), b.get("tel", "")) for b in bizim_veri.get("eczaneler", [])]

        nosy_k = [anahtarlar(a, t) for a, t in nosy]
        bizim_k = [anahtarlar(a, t) for a, t in bizim]
        sadece_nosy = [nosy[i][0] for i, a in enumerate(nosy_k) if not any(eslesir(a, b) for b in bizim_k)]
        sadece_bizim = [bizim[i][0] for i, b in enumerate(bizim_k) if not any(eslesir(a, b) for a in nosy_k)]

        durum = "UYUSUYOR" if not sadece_nosy and not sadece_bizim else "FARK VAR"
        if durum == "FARK VAR":
            fark_var = True
        satirlar.append("[%s] %s | Nosy=%d bizim=%d | kredi=%s" % (
            etiket, durum, len(nosy), len(bizim), veri.get("creditUsed")))
        if sadece_nosy:
            satirlar.append("    Sadece NOSY'de var : " + ", ".join(sadece_nosy))
        if sadece_bizim:
            satirlar.append("    Sadece BIZDE var   : " + ", ".join(sadece_bizim))

    metin = "\n".join(satirlar)
    print(metin)
    with open(RAPOR, "a", encoding="utf-8") as f:
        f.write(metin + "\n")
    if fark_var:
        print("\n>>> FARK VAR: Odasi listesine bakilmali.")


if __name__ == "__main__":
    main()
