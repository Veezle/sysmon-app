"""Kolektory metrik: jeden modul na oblast, ne na metriku.

`system` tak sám nese uptime, kernel, teploty, load i jméno uživatele.

Konvence "každý se brání sám" (dict s klíčem `available: False`) platí pro
kolektory, které teprve přijdou — net, disk, ports, gpu, battery, docker.
`system` a `processes` jsou zapsaná výjimka přenesená ze sysmonu: vracejí
`None`, částečný dict, nebo rovnou seznam, takže se na nich `["available"]`
indexovat nesmí a render musí počítat s `null`.
"""
