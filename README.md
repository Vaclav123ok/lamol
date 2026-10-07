# Hlídač slev

Dvakrát týdně (pondělí a čtvrtek ráno) projde letákové akce všech velkých českých řetězců
a upozorní na nové slevy u potravin ze seznamu.

- **Přidat potravinu:** připiš řádek do [`watchlist.txt`](watchlist.txt) (jde to i z mobilu, tužka vpravo nahoře). Kontrola se po uložení spustí hned.
- **Upozornění:** nová sleva = nové issue v tomto repu, GitHub ho pošle e-mailem. Když nic nového ve slevě není, nepřijde nic.
- **Souhrn na vyžádání:** vytvoř v repu prázdný soubor `poslat-souhrn` a přijde jeden e-mail se vším, co je právě v akci.
- **Přehled:** [`PREHLED.md`](PREHLED.md) – co je právě v akci a jak často sleva bývá.
- **Historie:** [`data/historie.csv`](data/historie.csv) – každá zachycená akce.

Čím konkrétnější název, tím přesnější výsledky (`la molisana`, `madeta máslo`). Hlídají se jen
produkty, jejichž název obsahuje všechna slova z řádku. Upozornění chodí od slevy 15 % výš
(`MIN_SLEVA` v `hlidac.py`), 30 % a víc je označeno 🔥.

Slovo s minusem (`kuře bio -nugetky`) v názvu být nesmí. Značky koncernu Mondelez (Milka, Oreo,
Toblerone, Figaro, Opavia…) se nehlídají nikdy – seznam `BLOK` v `hlidac.py`.

Zdroj dat: kupi.cz.
