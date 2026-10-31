# Módulo de facturación — primera versión

MVP backend basado en la especificación de `proyecto_modulo_facturacion.md`.

## Incluido

- Clientes y catálogo de productos con stock mock.
- Emisión de facturas con numeración por tipo/punto de venta.
- Cálculo de subtotal, descuentos e IVA usando `Decimal`.
- Validación y descuento de stock.
- Pagos parciales/totales y estados del comprobante.
- Notas de crédito totales o parciales por ítem, con reposición opcional de stock.
- Condiciones de pago por factura (vencimiento, cuotas y medio pactado), separadas del medio usado en cada pago.
- Pagos excedentes rechazados explícitamente para evitar saldos inconsistentes.
- Resumen de reporte y exportación CSV.
- Filtros, orden y selección de comprobantes para exportar CSV.
- Registro de auditoría en memoria disponible en `/audit`.
- Idempotencia básica al emitir una factura.
- Datos demo cargados al iniciar.

## Ejecutar

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

La interfaz web queda disponible en `http://127.0.0.1:8000/` y la API en `http://127.0.0.1:8000/docs`.

La interfaz permite probar el flujo completo: consultar el dashboard, emitir facturas con condiciones de pago, registrar pagos con su medio real, emitir notas de crédito parciales, consultar clientes/productos, filtrar comprobantes y descargar el CSV seleccionado.

## Tests

```powershell
pytest
```
