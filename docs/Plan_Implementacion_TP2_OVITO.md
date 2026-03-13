# Plan de implementacion TP2 adaptado a OVITO

## Resumen

- Se mantiene Python y alcance de TP completo, pero el simulador pasara a emitir trayectorias `extended XYZ` listas para abrir en OVITO sin remapeos manuales.
- El pipeline queda dividido en `simulacion -> trayectoria OVITO-ready -> analisis -> demos en OVITO -> informe/presentacion`.
- La visualizacion en OVITO usara la propiedad `Velocity` para flechas, `Vector Color` precomputada para colorear por angulo y `Particle Type`/`Color`/`Radius` para distinguir al lider.

## Fases y subplanes

1. **Fase 0 - Base del proyecto**: armar un paquete Python con CLI `simulate`, `batch`, `analyze` y una convencion de salidas por corrida (`scenario`, `eta`, `seed`).
2. **Fase 1 - Motor Vicsek estandar**: implementar el caso A con `L=10`, `rho=4`, `N=400`, `r=1`, `v=0.03`, `dt=1`, contorno periodico, actualizacion simultanea y promedio angular con `atan2(sum(sin), sum(cos))`.
3. **Fase 1.1 - Vecinos**: empezar con calculo all-pairs vectorizado y dejar cell-list como mejora condicionada a performance; no cambia el formato de salida.
4. **Fase 2 - Lideres**: mantener `N=400` total en A, B y C; en B una particula se convierte en lider de direccion fija aleatoria; en C una particula sigue una circunferencia de radio `R=5` centrada en `(5,5)` con `omega=0.006 rad/paso` para tener rapidez tangencial `0.03`.
5. **Fase 3 - Exportador OVITO-ready**: cada corrida genera una unica trayectoria multi-frame en `extended XYZ`, porque OVITO soporta multiples frames en un mismo archivo, celda periodica y columnas extra.
6. **Fase 3.1 - Schema del archivo**: cada frame tendra:
   - Linea 1: `N`
   - Linea 2: `Lattice="10 0 0 0 10 0 0 0 1" pbc="T T F" Time=<t> Properties=id:I:1:type:I:1:pos:R:3:velo:R:3:radius:R:1:color:R:3:vector_color:R:3`
   - Luego `N` filas con `id`, `type`, `x y 0`, `vx vy 0`, `radius`, `color_r color_g color_b`, `vector_color_r vector_color_g vector_color_b`
7. **Fase 3.2 - Convenciones visuales**: usar `z=0` para todas las particulas y espesor de celda `1`; no usar un formato 2D ad hoc. El lider tendra `type=2`, color fijo contrastante y radio un poco mayor; las particulas normales tendran `type=1` y color neutro.
8. **Fase 3.3 - Color de flechas**: calcular en el simulador el color RGB de cada velocidad a partir del angulo `theta` usando una rueda HSV y escribirlo en `vector_color`; asi OVITO ya abre la trayectoria con las flechas listas para colorearse por direccion sin depender de modifiers custom.
9. **Fase 4 - Helper para demos**: agregar un script corto de carga para OVITO que abra la trayectoria, active el visual element de `Velocity`, configure escala/ancho de flechas y deje guardada una escena base reutilizable para las demos; el flujo manual en GUI seguira siendo posible sin el script.
10. **Fase 5 - Observable y analisis**: mantener el analisis fuera de OVITO; calcular `va(t)=|sum_i v_i|/(Nv)`, detectar regimen estacionario con corridas piloto y producir resumenes por corrida y luego `mean +- std` entre seeds.
11. **Fase 5.1 - Barrido de ruido**: usar una grilla gruesa de `eta` y refinar solo la zona de transicion; en A, B y C usar los mismos `eta`, seeds y ventana estacionaria para que las comparaciones sean limpias.
12. **Fase 6 - Resultados obligatorios**: por escenario generar 2 demos OVITO representativas, unas pocas curvas `va(t)` para justificar el estacionario y una curva `eta vs <va>` con barras de error; luego una figura comparativa unica con A, B y C.
13. **Fase 7 - Opcionales**: recien despues de cerrar `rho=4`, repetir el pipeline para `rho=2` y `rho=8` si queda tiempo.
14. **Fase 8 - Entregables**: usar OVITO para capturar los frames fijos que iran en el PDF de presentacion; las animaciones reales se muestran en vivo o se publican con link externo. En la seccion de Implementacion de presentacion/informe se describe solo el motor, no el postproceso OVITO.

## Interfaces y salidas

- `SimulationConfig`: `L`, `rho`, `N`, `r`, `v`, `dt`, `eta`, `steps`, `seed`, `scenario`, `leader_spec`.
- `LeaderSpec`: `none`, `fixed(theta0)`, `circular(center_x, center_y, radius, omega)`.
- Salida primaria por corrida: `trajectory.extxyz`.
- Salida de analisis por corrida: resumen con `scenario, eta, seed, t_start, t_end, va_mean_stationary`.
- Salida agregada: tabla comparativa para graficar `eta vs <va> +- error`.

## Pruebas y criterios de aceptacion

- Verificar que una trayectoria de prueba abra en OVITO sin mapear columnas manualmente.
- Verificar que OVITO reconozca la celda periodica y la secuencia temporal desde un unico archivo multi-frame.
- Verificar que el visual element de `Velocity` muestre flechas correctas y que `vector_color` coloree las flechas por direccion.
- Verificar que el lider sea distinguible a simple vista en todos los frames por tipo/color/radio sin ocultar la codificacion angular de las flechas.
- Validar reproducibilidad por seed y consistencia de IDs entre frames.
- Validar comportamiento fisico minimo: `va` alto a bajo ruido y bajo a ruido alto en el caso estandar.
- Validar que cada escenario entregue exactamente los tres productos obligatorios: demo OVITO, `va(t)` representativa y curva `eta vs <va> +- error`.

## Supuestos y referencias tecnicas

- Se usara solo funcionalidad estandar de OVITO compatible con importacion `extended XYZ`, visualizacion de vectores y coloracion explicita por `Vector Color`.
- El lider cuenta dentro de `N=400` y dentro del calculo de `va`.
- Las barras de error seran el desvio estandar entre realizaciones del observable escalar ya promediado en regimen estacionario.
- Base tecnica OVITO:
  - [XYZ file reader](https://docs.ovito.org/reference/file_formats/input/xyz.html)
  - [Vectors](https://docs.ovito.org/reference/pipelines/visual_elements/vectors.html)
  - [Assign color](https://docs.ovito.org/reference/pipelines/modifiers/assign_color.html)
