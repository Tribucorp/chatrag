---
source: https://www.dell.com/support/kbdoc/en-us/000134013/dell-poweredge-update-the-firmware-of-single-system-components-remotely-using-the-idrac
title: Actualizar BIOS y firmware de un PowerEdge
---

# Actualizar BIOS y firmware de un PowerEdge

## Orden recomendado
1. Lee las notas de la versión: algunas CPU (p. ej. Xeon de 5.ª generación en R660/R760) exigen un BIOS mínimo.
2. Actualiza primero el **iDRAC**, después **BIOS** y luego controladoras (PERC), NIC y discos.
3. Exporta antes una recopilación SupportAssist y la configuración del servidor.

## Vías de actualización
- **iDRAC9 web**: Maintenance → System Update → Manual Update, con *Location Type* local; sube el paquete (DUP), pulsa Install y sigue el progreso en Job Queue. El nombre del fichero DUP no debe tener espacios. Para el firmware del iDRAC se recomienda el DUP de Windows de 64 bits (.exe), que el iDRAC acepta aunque el servidor no tenga Windows.
- **iDRAC9 por HTTPS**: actualiza contra el catálogo en línea de Dell (requiere salida a internet).
- **Lifecycle Controller (F10)**: Firmware Update, desde USB, red o repositorio.
- Desde el sistema operativo con los paquetes DUP de Dell para Windows o Linux.

Programa una ventana de mantenimiento: las actualizaciones de BIOS y de controladora suelen requerir reinicio.

Datos de demo resumidos de la documentación pública de Dell; verifica siempre la versión vigente en la fuente.
