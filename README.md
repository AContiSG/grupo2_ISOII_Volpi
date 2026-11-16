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
- Datos demo cargados al iniciar: 11 clientes, 11 productos con categoría y ~24 meses de historia (facturas, pagos parciales/totales, mora y notas de crédito), generados de forma determinística.
- **Dashboard estratégico** (`/reports/dashboard`, pestaña en la interfaz): KPIs con variación vs. período anterior, facturado vs. cobrado, deuda vencida, margen, antigüedad de deuda, cobros esperados, concentración de clientes, mix por categoría/región, stock vs. rotación y alertas automáticas.

## Cómo levantar el proyecto

**Requisitos:** Python 3.11 o superior. No hace falta instalar nada más: la interfaz web son archivos estáticos que sirve el mismo backend, y los gráficos están hechos en SVG sin librerías externas (funciona sin internet).

### 1. Crear el entorno virtual e instalar dependencias

Linux / macOS:

```bash
cd grupo2_ISOII_Volpi
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Windows (PowerShell):

```powershell
cd grupo2_ISOII_Volpi
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 2. Iniciar el servidor

```bash
uvicorn app.main:app --reload
```

Hay que ejecutarlo **desde la raíz del proyecto** (la carpeta que contiene `app/` y `web/`), porque el backend sirve la carpeta `web/` con una ruta relativa.

### 3. Abrir la aplicación

| Qué | URL |
|---|---|
| Interfaz web | http://127.0.0.1:8000/ |
| **Dashboard estratégico** (acceso directo) | http://127.0.0.1:8000/#strategy |
| Documentación interactiva de la API | http://127.0.0.1:8000/docs |

Los datos son de demostración y viven en memoria: se generan al iniciar (con ~24 meses de historia) y se reinician cada vez que se reinicia el servidor.

### Problemas frecuentes

- **`ModuleNotFoundError: No module named 'fastapi'`**: la instalación falló o el `uvicorn` que se ejecuta es el del sistema y no el del entorno virtual. Verificá con `which uvicorn` (debe apuntar a `.venv/bin/uvicorn`) o ejecutá `python -m uvicorn app.main:app --reload`.
- **El dashboard aparece vacío o sin estilos**: no estás en la raíz del proyecto, o el navegador tiene cacheados archivos viejos (Ctrl+F5).
- **El puerto 8000 está ocupado**: usá `uvicorn app.main:app --reload --port 8001`.

## Estructura

```
app/domain.py       Modelo de dominio, reglas de negocio y datos demo
app/analytics.py    Cálculos del dashboard estratégico (KPIs, series, alertas, filtros)
app/main.py         API FastAPI y servidor de la interfaz web
web/                Interfaz: index.html, app.js (operativa), dashboard.js (gráficos), tables.js (orden de tablas)
tests/              Tests de dominio y de analítica
```

## Dashboard estratégico

Pestaña pensada para liderazgo (`GET /reports/dashboard?months=12&region=...&client_id=...`):

- **Filtros globales** por región, cliente y período (6, 12 o 24 meses): recalculan todo el tablero.
- **Señales de alerta** desplegables (críticas, de atención y positivas), generadas automáticamente.
- **KPIs** con variación contra el período anterior: facturación, margen bruto, cobrado/facturado, DSO, cartera vencida y concentración en los 5 principales clientes.
- **Gráficos y tablas:** facturado vs. cobrado, deuda vencida, margen, antigüedad de deuda, cobros esperados, top clientes, categorías, regiones, clientes con deuda vencida y productos con cobertura de stock.
- Todas las tablas se ordenan haciendo clic en el encabezado, y cada gráfico tiene una vista "Ver tabla".
- **Accesibilidad:** paleta validada para daltonismo (protanopía, deuteranopía y tritanopía), contraste de texto ≥ 4,5:1, alertas, chips de stock y barras de riesgo con ícono y texto además del color y foco de teclado visible.

## Tests

```bash
pytest
```
