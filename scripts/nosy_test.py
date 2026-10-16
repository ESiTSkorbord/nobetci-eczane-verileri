#!/usr/bin/env python3
"""NosyAPI deneme scripti - SADECE test. data/ klasorune dokunmaz.
Kartal ve Maltepe icin nobetci listesini ceker, test/ klasorune yazar.
Her calistirmada yalnizca 2 istek atar (kredi harcamamak icin)."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ANAHTAR = os.environ.get("NOSY_KEY", "").strip()
TABAN = "https://www.nosyapi.com/apiv2/service/pharmacies-on-duty"
ILCELER = [("istanbul", "kartal"), ("istanbul", "maltepe")]


def istek(url):
    r = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + ANAHTAR,
        "Accept": "application/json",
        "User-Agent": "nobetci-eczane-test/1.0",
    })
    try:
        with urllib.request.urlopen(r, timeout=30) as s:
            return s.status, dict(s.headers), s.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, {}, "HATA: %s" % e


def kayitlari_bul(veri):
    """Yanit sekli belli olmadigi icin listeyi tahminle bulur."""
    if isinstance(veri, list):
        return veri
    if isinstance(veri, dict):
        for k in ("data", "result", "results", "pharmacies"):
            v = veri.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                alt = kayitlari_bul(v)
                if alt:
                    return alt
    return []


def main():
    if not ANAHTAR:
        print("NOSY_KEY tanimli degil. Secret eklenmemis.")
        sys.exit(1)
    os.makedirs("test", exist_ok=True)
    simdi = datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d %H:%M")
    print("Istanbul saati:", simdi)
    for il, ilce in ILCELER:
        url = TABAN + "?" + urllib.parse.urlencode({"city": il, "district": ilce})
        kod, baslik, govde = istek(url)
        print("\n=== %s-%s  HTTP %s ===" % (il, ilce, kod))
        for b in baslik:
            if "credit" in b.lower() or "kredi" in b.lower() or "ratelimit" in b.lower():
                print("  baslik %s: %s" % (b, baslik[b]))
        try:
            veri = json.loads(govde)
        except Exception:
            print("JSON degil, ham yanit (ilk 600 karakter):")
            print(govde[:600])
            continue
        if isinstance(veri, dict):
            for k, v in veri.items():
                if not isinstance(v, (list, dict)):
                    print("  %s: %s" % (k, v))
        liste = kayitlari_bul(veri)
        print("Kayit sayisi:", len(liste))
        for k in liste:
            if isinstance(k, dict):
                print("  -", json.dumps(k, ensure_ascii=False)[:300])
        with open("test/nosy-%s-%s.json" % (il, ilce), "w", encoding="utf-8") as f:
            json.dump({"alindi": simdi, "http": kod, "yanit": veri},
                      f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
