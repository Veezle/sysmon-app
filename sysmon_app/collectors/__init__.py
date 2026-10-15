"""Kolektory metrik: jeden modul na oblast, ne na metriku.

`system` tak sám nese uptime, kernel, teploty, load i jméno uživatele.

Konvence "každý se brání sám" platí pro kolektory, které mohou selhat jako
celek: místo výjimky vracejí dict s `available: False` (a `error`, když ho
nesou). Dnes je to `disk`. Ostatní ji nemají a `["available"]` na nich
spadne: `net` vrací prostý dict, `system` dict částečný (třeba `nvme_temp`
prostě chybí) a `processes` prostý seznam. Render proto musí počítat
s `null` i s chybějícím klíčem.

Třída, nebo funkce: třída tam, kde je potřeba předchozí vzorek nebo cache
(`net`, `disk`), prostá funkce tam, kde jde o čisté čtení (`system`,
`processes`).

Kolektor se neupravuje proto, aby konvenci splnil — ze sysmonu se přenáší
beze změny, i když se tím od ostatních liší.
"""
