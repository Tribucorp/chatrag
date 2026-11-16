---
source: https://www.dell.com/support/kbdoc/en-us/000126308/export-a-supportassist-collection-via-idrac9
title: Cómo exportar una recopilación SupportAssist (TSR)
---

# Cómo exportar una recopilación SupportAssist (TSR)

La recopilación **SupportAssist** (antes *Tech Support Report*, TSR) reúne logs del sistema, del RAID y del hardware. Es lo primero que pide soporte ante un fallo.

## Desde la web del iDRAC9
1. Entra en el iDRAC → **Maintenance → SupportAssist**.
2. Pulsa **Collect** (o *Start a Collection*) y elige qué incluir.
3. Guárdalo en local o en un recurso compartido CIFS/NFS.
- Los datos de **SO y aplicaciones** requieren el iDRAC Service Module (iSM) instalado.
- Desde iDRAC9 7.0 ya no se envía directamente a Dell desde la interfaz: descárgalo y adjúntalo al caso.

## Con RACADM (iDRAC9)
```
racadm techsupreport collect -t SysInfo,TTYLog
racadm jobqueue view
racadm techsupreport export -f tsr.zip
```
Por SSH remoto usa `-l` con una ruta de red en lugar de un fichero local.

## Sin acceso al iDRAC
Arranca con **F10** (Lifecycle Controller) → **Hardware Diagnostics → Export SupportAssist Collection**, a un USB FAT32 o a un recurso de red.

Datos de demo resumidos de la documentación pública de Dell; verifica siempre la versión vigente en la fuente.
