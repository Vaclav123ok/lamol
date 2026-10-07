"""Hlidac slev: projde watchlist.txt, najde aktualni letakove akce na kupi.cz,
ulozi je do historie a na nove slevy upozorni pres GitHub issue (prijde e-mailem)."""
import csv, json, os, re, sys, time, unicodedata
import html as html_lib
from datetime import date
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

BASE = "https://www.kupi.cz"
MIN_SLEVA = 15          # % - mensi slevy se jen ulozi do historie, neupozornuje se na ne
ZASADNI = 30            # % - od teto hodnoty se sleva oznaci jako zasadni
HIST = "data/historie.csv"
PREHLED = "PREHLED.md"
SOUHRN = "poslat-souhrn"
COLS = ["poprve_videno", "hledano", "produkt", "obchod", "cena_kc", "baleni", "sleva_pct",
        "bezna_cena_kc", "cena_za_jednotku", "platnost", "poznamka", "id_akce", "odkaz"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "cs-CZ,cs;q=0.9"}


# Znacky koncernu Mondelez - nikdy se nehlidaji ani neoznamuji
BLOK = {"milka", "oreo", "toblerone", "figaro", "cadbury", "philadelphia", "tuc", "bebe", "belvita",
        "opavia", "fidorka", "minonky", "kolonada", "brumik", "daim", "halls", "mondelez"}


def split_term(term):
    """'kure bio -nugetky' -> (hledany dotaz, slova ktera musi byt v nazvu, slova ktera v nazvu byt nesmi)"""
    ws = term.split()
    plus = [w for w in ws if not w.startswith("-")]
    minus = [norm(w[1:]) for w in ws if w.startswith("-") and len(w) > 1]
    return " ".join(plus), [norm(w) for w in plus], minus


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def txt(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def num(s):
    m = re.search(r"\d+(?:[.,]\d+)?", s.replace("\xa0", " ").replace(" ", ""))
    return float(m.group(0).replace(",", ".")) if m else None


def parse(html, term):
    """Vrati (pocet produktu na strance, seznam aktualnich akci odpovidajicich hledanemu vyrazu)."""
    soup = BeautifulSoup(html, "html.parser")
    groups = soup.select(".group_discounts")
    _, words, minus = split_term(term)
    out = []
    for g in groups:
        name = txt(g.select_one(".product_name strong"))
        n = norm(name)
        if not name or not all(w in n for w in words) or any(w in n for w in minus):
            continue
        if BLOK & set(re.findall(r"[a-z0-9]+", n)):
            continue
        bezna = num(txt(g.select_one(".avg_price span")))
        link = g.select_one(".product_name a")
        url = BASE + link["href"] if link and link.get("href", "").startswith("/") else ""
        for r in g.select(".discount_row"):
            cena = num(txt(r.select_one(".discount_price_value")))
            if cena is None:
                continue
            pct = num(txt(r.select_one(".discount_percentage")))
            if pct is None and bezna and bezna > cena:  # zdroj procenta neuvadi - dopocitat z bezne ceny
                pct = round((1 - cena / bezna) * 100)
            pozn = " / ".join(x for x in (txt(r.select_one(".discounts_club")),
                                          txt(r.select_one(".discount_note"))) if x)
            out.append({
                "hledano": term, "produkt": name,
                "obchod": txt(r.select_one(".discounts_shop_name")),
                "cena_kc": cena,
                "baleni": txt(r.select_one(".discount_amount")).lstrip("/ ").strip(),
                "sleva_pct": int(pct) if pct is not None else "",
                "bezna_cena_kc": bezna if bezna is not None else "",
                "cena_za_jednotku": txt(r.select_one(".price_per_unit")),
                "platnost": txt(r.select_one(".discounts_validity")),
                "poznamka": pozn,
                "id_akce": r.get("data-discount", ""),
                "odkaz": url,
            })
    return len(groups), out


def fetch(term):
    r = requests.get(f"{BASE}/hledej?f={quote_plus(split_term(term)[0])}", headers=UA, timeout=40)
    r.raise_for_status()
    if "kupi" not in r.text.lower():
        raise RuntimeError("neocekavana odpoved zdroje")
    return r.text


def read_terms():
    with open("watchlist.txt", encoding="utf-8") as f:
        seen, out = set(), []
        for line in f:
            t = line.strip()
            if t and not t.startswith("#") and norm(t) not in seen:
                seen.add(norm(t)); out.append(t)
        return out


def read_hist():
    if not os.path.exists(HIST):
        return []
    with open(HIST, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def kc(v):
    return f"{float(v):.2f}".replace(".", ",") + " Kč"


def radek(d):
    pct = f"−{d['sleva_pct']} %" if d["sleva_pct"] != "" else "—"
    bezna = kc(d["bezna_cena_kc"]) if d["bezna_cena_kc"] != "" else "—"
    flag = " 🔥" if d["sleva_pct"] != "" and int(d["sleva_pct"]) >= ZASADNI else ""
    pozn = f" ({d['poznamka']})" if d["poznamka"] else ""
    return (f"| [{d['produkt']}]({d['odkaz']}) | {d['obchod']} | **{kc(d['cena_kc'])}**{flag} | {bezna} | "
            f"{pct} | {d['baleni'] or '—'} | {d['platnost']}{pozn} |")


HEAD = ("| Produkt | Obchod | Cena | Běžná cena | Sleva | Balení | Platnost |\n"
        "|---|---|---|---|---|---|---|")


def prehled(terms, aktualni, hist):
    L = ["# Přehled hlídaných slev", "", f"Poslední kontrola: {date.today().isoformat()}", "",
         "## Právě v akci", ""]
    if aktualni:
        L += [HEAD] + [radek(d) for d in sorted(aktualni, key=lambda d: (d["produkt"], d["cena_kc"]))]
    else:
        L.append("Nic z hlídaného seznamu teď v akci není.")
    L += ["", "## Jak často bývá sleva", "",
          "| Hlídáno | Akcí v historii | Sledováno od | Nejnižší cena | Průměrně jednou za |", "|---|---|---|---|---|"]
    for t in terms:
        rows = [h for h in hist if norm(h["hledano"]) == norm(t)]
        if not rows:
            L.append(f"| {t} | 0 | — | — | — |"); continue
        od = min(h["poprve_videno"] for h in rows)
        best = min(rows, key=lambda h: float(h["cena_kc"]))
        tydny = {date.fromisoformat(h["poprve_videno"]).isocalendar()[:2] for h in rows}
        dni = (date.today() - date.fromisoformat(od)).days
        freq = f"{dni / 7 / len(tydny):.1f} týdne" if dni >= 28 else "zatím málo dat"
        L.append(f"| {t} | {len(rows)} | {od} | {kc(best['cena_kc'])} ({best['obchod']}, {best['baleni']}) | {freq} |")
    L += ["", "Zdroj dat: kupi.cz. Ceny a platnost si před nákupem ověř v letáku."]
    with open(PREHLED, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def predmet(nove, souhrn):
    top = max(nove, key=lambda d: int(d["sleva_pct"] or 0))
    hlavni = f"{top['produkt']} za {kc(top['cena_kc'])}"
    if souhrn:
        return f"Právě v akci ({len(nove)}): {hlavni} a další" if len(nove) > 1 else f"Právě v akci: {hlavni}"
    return f"Nová sleva: {hlavni}" + (f" + {len(nove) - 1} další" if len(nove) > 1 else "")


def platnost_kratce(p):
    return re.sub(r"^platí\s+", "", p).strip()


def mail_html(nove, souhrn):
    e = html_lib.escape
    karty = []
    for d in sorted(nove, key=lambda d: -int(d["sleva_pct"] or 0)):
        pct = d["sleva_pct"]
        zasadni = pct != "" and int(pct) >= ZASADNI
        stitek = (f'<span style="background:{"#c2410c" if zasadni else "#15803d"};color:#fff;border-radius:999px;'
                  f'padding:2px 9px;font-size:13px;font-weight:600;white-space:nowrap">−{pct} %</span>') if pct != "" else ""
        bezna = (f' <span style="color:#8a8f98;text-decoration:line-through;font-size:14px">{kc(d["bezna_cena_kc"])}</span>'
                 if d["bezna_cena_kc"] != "" else "")
        detail = " · ".join(x for x in (d["obchod"], d["baleni"], platnost_kratce(d["platnost"])) if x)
        extra = [d["poznamka"]] if d["poznamka"] else []
        if d.get("dalsich"):
            n = d["dalsich"]
            extra.append(f"+ {n} další nabídka" if n == 1 else f"+ {n} další nabídky" if n < 5 else f"+ {n} dalších nabídek")
        pozn = f'<div style="color:#8a8f98;font-size:13px;margin-top:2px">{e(" · ".join(extra))}</div>' if extra else ""
        karty.append(
            f'<tr><td style="padding:14px 0;border-bottom:1px solid #eceef1">'
            f'<a href="{e(d["odkaz"])}" style="color:#111827;text-decoration:none;font-size:16px;font-weight:600">{e(d["produkt"])}</a>'
            f'<div style="margin-top:6px"><span style="font-size:20px;font-weight:700;color:#111827">{kc(d["cena_kc"])}</span>'
            f'{bezna} &nbsp;{stitek}</div>'
            f'<div style="color:#4b5563;font-size:14px;margin-top:4px">{e(detail)}</div>{pozn}</td></tr>')
    nadpis = "Právě v akci" if souhrn else ("Nová sleva" if len(nove) == 1 else f"{len(nove)} nové slevy" if len(nove) < 5 else f"{len(nove)} nových slev")
    return (f'<div style="background:#f5f6f8;padding:24px 12px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;margin:0 auto;background:#fff;'
            f'border-radius:14px;padding:22px 24px"><tr><td style="font-size:13px;color:#8a8f98;letter-spacing:.04em;text-transform:uppercase">'
            f'Hlídač slev</td></tr><tr><td style="font-size:22px;font-weight:700;color:#111827;padding:4px 0 6px">{nadpis}</td></tr>'
            + "".join(karty) +
            f'<tr><td style="padding-top:14px;color:#8a8f98;font-size:12px">Zdroj: kupi.cz. Cenu a platnost si ověř v letáku.</td></tr>'
            f'</table></div>')


def mail_text(nove):
    L = []
    for d in sorted(nove, key=lambda d: -int(d["sleva_pct"] or 0)):
        pct = f" (−{d['sleva_pct']} %)" if d["sleva_pct"] != "" else ""
        L.append(f"{d['produkt']}: {kc(d['cena_kc'])}{pct}\n  {d['obchod']} · {d['baleni']} · {platnost_kratce(d['platnost'])}\n  {d['odkaz']}")
    return "\n\n".join(L) + "\n\nZdroj: kupi.cz. Cenu a platnost si ověř v letáku."


def send_mail(nove, souhrn):
    """Posle hezky e-mail pres Resend. Vraci True pri uspechu."""
    key, to = os.environ.get("RESEND_API_KEY"), os.environ.get("MAIL_TO")
    if not key or not to:
        return False
    payload = {"from": os.environ.get("MAIL_FROM", "Hlídač slev <hlidac@send.mailora.pro>"), "to": [to],
               "subject": predmet(nove, souhrn), "html": mail_html(nove, souhrn), "text": mail_text(nove)}
    r = requests.post("https://api.resend.com/emails", timeout=30, json=payload,
                      headers={"Authorization": f"Bearer {key}"})
    if r.status_code >= 300:
        print("E-mail se nepodarilo odeslat:", r.status_code, r.text[:300])
        return False
    print("E-mail odeslan:", payload["subject"])
    return True


def jednotkova(d):
    v = num(d.get("cena_za_jednotku", "") or "")
    return v if v is not None else float("inf")


def vyber(akce):
    """Jen slevy od MIN_SLEVA a z kazde hlidane polozky pouze ta nejlepsi (nejvyssi sleva, pak nejnizsi cena za jednotku)."""
    ok = [d for d in akce if d["sleva_pct"] == "" or int(d["sleva_pct"]) >= MIN_SLEVA]
    skup = {}
    for d in ok:
        skup.setdefault(norm(d["hledano"]), []).append(d)
    out = []
    for ds in skup.values():
        best = min(ds, key=lambda d: (-int(d["sleva_pct"] or 0), jednotkova(d), d["cena_kc"]))
        out.append({**best, "dalsich": len(ds) - 1})
    return out


def notify(nove, souhrn=False):
    nove = vyber(nove)
    if not nove:
        print("Zadna sleva nad prahem k oznameni."); return
    if send_mail(nove, souhrn):
        return
    token, repo = os.environ.get("GH_TOKEN"), os.environ.get("GH_REPO")
    nove = sorted(nove, key=lambda d: (d["produkt"], d["cena_kc"]))
    top = min(nove, key=lambda d: d["cena_kc"])
    title = f"Sleva: {top['produkt']} za {kc(top['cena_kc'])} ({top['obchod']})"
    if len(nove) > 1:
        title += f" + {len(nove) - 1} další"
    if souhrn:
        title = f"Souhrn: {len(nove)} hlídaných potravin právě v akci"
    uvod = "Vše, co je z hlídaného seznamu právě v akci:" if souhrn else "Nové slevy na hlídané potraviny:"
    # zminka = jediny e-mail (prirazeni issue posilalo dva)
    kdo = f"@{repo.split('/')[0]} " if repo else ""
    body = "\n".join([kdo + uvod, "", HEAD] + [radek(d) for d in nove] +
                     ["", f"🔥 = sleva {ZASADNI} % a víc. Zdroj: kupi.cz, platnost si ověř v letáku."])
    print(title + "\n" + body)
    if not token or not repo:
        print("(bez GH_TOKEN - upozorneni se neodesila)"); return
    payload = {"title": title, "body": body}
    r = requests.post(f"https://api.github.com/repos/{repo}/issues", timeout=30, data=json.dumps(payload),
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    r.raise_for_status()
    print("Upozorneni vytvoreno:", r.json().get("html_url"))


def main():
    terms = read_terms()
    hist = read_hist()
    known = {h["id_akce"] for h in hist}
    aktualni, chyby, stranek = [], [], 0
    for i, t in enumerate(terms):
        if i:
            time.sleep(3)
        try:
            n, found = parse(fetch(t), t)
            stranek += n
            aktualni += found
            print(f"{t}: {n} produktu na strance, {len(found)} aktualnich akci")
        except Exception as e:  # jedna chyba nesmi shodit zbytek seznamu
            chyby.append(f"{t}: {e!r}")
    uniq = {d["id_akce"]: d for d in aktualni if d["id_akce"]}
    nove = [d for k, d in uniq.items() if k not in known]
    today = date.today().isoformat()
    for d in nove:
        hist.append({**{k: d[k] for k in COLS if k in d}, "poprve_videno": today})
    os.makedirs("data", exist_ok=True)
    with open(HIST, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(hist)
    prehled(terms, list(uniq.values()), hist)
    k_oznameni = vyber(nove)
    if os.path.exists(SOUHRN):  # jednorazova zadost o souhrn vseho, co je prave v akci
        os.remove(SOUHRN)
        if uniq:
            notify(list(uniq.values()), souhrn=True)
    elif k_oznameni:
        notify(k_oznameni)
    else:
        print("Zadna nova sleva k oznameni.")
    if chyby or (terms and stranek == 0):
        print("CHYBY:", chyby or "zdroj nevratil zadne produkty - asi se zmenila struktura stranky")
        sys.exit(1)


if __name__ == "__main__":
    main()
