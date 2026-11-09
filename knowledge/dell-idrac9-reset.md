---
source: https://www.dell.com/support/kbdoc/en-us/000126703/how-to-reset-the-internal-dell-remote-access-controller-idrac-on-a-poweredge-server
title: iDRAC9: reinicio y restablecimiento a valores de fábrica
---

# iDRAC9: reinicio y restablecimiento a valores de fábrica

**Reiniciar** el iDRAC (sin perder configuración) suele resolver una interfaz web que no responde. **Restablecer a fábrica** es destructivo: borra la configuración.

## Opciones de RACADM
- `racadm racreset` — reinicia el iDRAC.
- `racadm racresetcfg` — vuelve a valores de fábrica **conservando** usuarios y red.
- `racadm racresetcfg -all` — restablece todo y deja el usuario con la contraseña **de envío** (la de la etiqueta).
- `racadm racresetcfg -rc` — restablece todo y deja `root` con la contraseña antigua por defecto.

## Desde la web
En iDRAC9: **Maintenance → Diagnostics → Reset iDRAC to Default Settings**, eligiendo qué conservar.

Antes de restablecer, anota la IP y la configuración de red: tras un `-all` tendrás que volver a configurarla desde F2 (iDRAC Settings → Network).

Datos de demo resumidos de la documentación pública de Dell; verifica siempre la versión vigente en la fuente.
