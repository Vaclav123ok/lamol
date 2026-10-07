import os, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36", "Accept-Language": "cs-CZ,cs;q=0.9"}
os.makedirs("debug", exist_ok=True)
log = []
for name, url in [("molisana", "https://www.kupi.cz/hledej?f=la+molisana"), ("maslo", "https://www.kupi.cz/hledej?f=maslo"), ("robots", "https://www.kupi.cz/robots.txt")]:
    try:
        r = requests.get(url, headers=H, timeout=30)
        log.append(f"{url} status={r.status_code} len={len(r.text)} final={r.url}")
        open(f"debug/{name}.html", "w", encoding="utf-8").write(r.text)
    except Exception as e:
        log.append(f"ERR {url} {e!r}")
open("debug/probe.txt", "w", encoding="utf-8").write("\n".join(log))
print("\n".join(log))
