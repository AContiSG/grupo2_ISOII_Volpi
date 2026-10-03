# Módulo de facturación — primera versión

MVP backend basado en la especificación de `proyecto_modulo_facturacion.md`.

## Incluido

- Clientes y catálogo de productos con stock mock.
- Emisión de facturas con numeración por tipo/punto de venta.
- Cálculo de subtotal, descuentos e IVA usando `Decimal`.
- Validación y descuento de stock.
- Pagos parciales/totales y estados del comprobante.
- Notas de crédito con reposición opcional de stock.
- Resumen de reporte y exportación CSV.
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

La interfaz permite probar el flujo completo de la primera versión: consultar el resumen, emitir facturas, registrar pagos, emitir notas de crédito, consultar clientes/productos y descargar el CSV.

## Tests

```powershell
pytest
```

## Alcance de esta iteración

La primera versión usa un repositorio en memoria para poder demostrar el flujo completo sin infraestructura adicional. Al reiniciar el proceso se pierden los datos. El siguiente incremento debe reemplazar `InMemoryStore` por SQLite/PostgreSQL, agregar autenticación/roles, PDF, auditoría persistida y una interfaz web con gráficos.
