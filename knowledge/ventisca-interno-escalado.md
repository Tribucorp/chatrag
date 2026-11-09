---
source: kb://ventisca/interno/escalado
title: Procedimiento interno de escalado (N1 → N2 → fabricante)
acl: soporte
---

# Procedimiento interno de escalado (N1 → N2 → fabricante)

**Uso interno de soporte.**

1. **N1** valida la etiqueta de servicio, la cobertura de garantía y que el cliente adjuntó la recopilación SupportAssist. Si falta, se pide antes de nada.
2. N1 revisa el log de eventos (SEL / Lifecycle Log) del TSR. Disco o fuente averiados con garantía vigente: se abre directamente la sustitución con el fabricante.
3. Se escala a **N2** si: hay errores de memoria corregibles repetidos, configuración ajena en la PERC, el servidor no pasa el POST o el problema persiste tras actualizar firmware.
4. **N2** decide si abrir caso con Dell. Al abrirlo, adjunta siempre el TSR y anota el número de caso de Dell en nuestro ticket.
5. Nunca restablecer el iDRAC a fábrica (`racresetcfg -all`) en remoto sin acordar con el cliente cómo recuperar la red.

Documento de la empresa FICTICIA Ventisca TI, creado para la demo. No describe a ninguna empresa real.
