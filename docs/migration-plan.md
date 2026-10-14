# Plan de migración por dominio

| Dominio | Estado | Criterio para avanzar | Rollback |
|---|---|---|---|
| Afiliaciones | DUAL | 0 discrepancias y latencia < 200 ms durante 48 horas | Ejecutar ./rollback.sh affiliations |
| Retiros | LEGACY | 100% de retiros reconciliados en LOGMOV sin duplicados en 24 horas | Reconfigurar subsidios-app para invocar sp_registrar_retiro directamente |
| Empresas | LEGACY | Validación exitosa de conteo de miembros en 3 empresas piloto | Revertir gateway a consulta directa sobre tabla EMPRESA |

Siguiente dominio: Retiros
