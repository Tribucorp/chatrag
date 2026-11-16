---
source: https://www.dell.com/support/kbdoc/en-us/000133536/dell-poweredge-what-is-the-default-username-and-password-for-idrac
title: iDRAC9: usuario y contraseña por defecto
---

# iDRAC9: usuario y contraseña por defecto

## Dónde está la contraseña
Los servidores se entregan con una **contraseña única de iDRAC** (usuario `root`), salvo que al comprar se pidiera la antigua por defecto. La contraseña única está impresa en la **etiqueta de información** extraíble (pull-out tag) del frontal del chasis, junto a la etiqueta de servicio.

## Si se perdió la contraseña
Con acceso físico al servidor hay varias vías:
- **iDRAC Settings** (pulsa **F2** al arrancar → iDRAC Settings → User Configuration).
- RACADM local desde el sistema operativo, OpenManage Mobile o el puerto USB de gestión.

## Buenas prácticas
- Cambia la contraseña en el primer acceso y no compartas la cuenta `root`: crea usuarios nominativos.

Datos de demo resumidos de la documentación pública de Dell; verifica siempre la versión vigente en la fuente.
