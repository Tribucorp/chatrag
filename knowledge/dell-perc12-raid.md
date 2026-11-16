---
source: https://www.dell.com/support/manuals/en-us/perc-h965i-mx/perc12/summary-of-raid-levels
title: PERC 12 (H965): niveles RAID y limitaciones
---

# PERC 12 (H965): niveles RAID y limitaciones

Las controladoras PERC 12 (familia H965) y PERC 13 (H975) admiten **RAID 0, 1, 5, 6, 10, 50 y 60**.

## Discos por nivel
- **RAID 1**: exactamente 2 discos.
- **RAID 10**: de 4 a 240 discos; por encima de 32 discos se necesita *spanning*, con número **par** de spans.
- **RAID 50**: mínimo 6 discos. **RAID 60**: mínimo 8.

## Limitaciones a tener en cuenta
- **No** hay expansión de capacidad en línea en RAID 10 ni en volúmenes con span (RAID 50/60).
- **No** se admite migración de nivel RAID (RLM) en PERC 12 y posteriores: cambiar de nivel exige recrear el volumen (y restaurar copia de seguridad).
- Sacar y volver a meter un disco en la misma ranura genera un evento de **configuración ajena** (*foreign configuration*), que hay que importar o borrar desde la utilidad de la controladora o el iDRAC.

Datos de demo resumidos de la documentación pública de Dell; verifica siempre la versión vigente en la fuente.
