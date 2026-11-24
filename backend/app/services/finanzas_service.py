"""Servicio de Cálculos Financieros y Agregaciones SQL en Tiempo Real (RF8).
Realiza consultas optimizadas con funciones agregadas nativas para el cálculo del capital total.
"""
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func, case
from app.core.periodos import anio_del_periodo
from app.models.socio import Socio
from app.models.gastos import GastoGeneral
from app.models.finanzas import FinanzaSocio, TipoMovimientoFinanciero
from app.models.actividad import Actividad
from app.models.actividad_socio import ActividadSocio, TipoActividadSocio
from app.models.rifa import Rifa
from app.models.reunion import Reunion
from app.models.prestamo import Prestamo, AbonoPrestamo, EstadoPrestamo, ESTADOS_CERRADOS
from app.schemas.dashboard import BienComunInteresPrestamo, BienComunResponse, BienComunSocioItem, CapitalTotalResponse
from app.schemas.finanzas import LiquidacionSocioItem, LiquidacionAnualResponse
from app.services.prestamos_service import (
    CUOTA_BIEN_COMUN, ZONA_COLOMBIA, cuotas_vencidas, es_regla_mora, es_segundo_prestamo, hoy_colombia,
    interes_mensual, intereses_pendientes_vencidos, periodos_interes,
)


def repartir_importe(total: Decimal, pesos: list[Decimal]) -> list[Decimal]:
    """Reparto proporcional por restos mayores, conservando cada centavo."""
    suma = sum(pesos, Decimal("0.00"))
    if suma == 0:
        return [Decimal("0.00") for _ in pesos]
    signo = Decimal("-1") if total < 0 else Decimal("1")
    importes = [abs(total) * peso / suma for peso in pesos]
    partes = [importe.quantize(Decimal("0.01"), rounding=ROUND_DOWN) for importe in importes]
    centavos = int((abs(total) - sum(partes)) / Decimal("0.01"))
    orden = sorted(range(len(pesos)), key=lambda i: importes[i] - partes[i], reverse=True)
    for i in orden[:centavos]:
        partes[i] += Decimal("0.01")
    return [parte * signo for parte in partes]


# Parte de cada interés cobrado que va al bien común:
# - Regla 7 % / 3 %: la guardada en el abono (3 de cada 10 pesos).
# - Abonos anteriores (sin ese dato): todo el interés desde la cuota #4.
# El resto del interés es del socio que tomó el préstamo (su ahorro personal).
INTERES_BIEN_COMUN = case(
    (AbonoPrestamo.interes_bien_comun.isnot(None), AbonoPrestamo.interes_bien_comun),
    (AbonoPrestamo.numero_cuota >= 4, AbonoPrestamo.monto_interes),
    else_=Decimal("0.00"),
)
INTERES_SOCIO = AbonoPrestamo.monto_interes - INTERES_BIEN_COMUN


def intereses_pendientes_bien_comun(prestamo: Prestamo, hoy: Optional[date] = None) -> tuple[Decimal, Decimal]:
    """(intereses pendientes, parte del bien común) de un préstamo.

    Pendiente = interés de meses ya vencidos que sigue sin pagarse (la misma cifra
    de "Intereses vencidos" en las Deducciones del socio). No es dinero recibido:
    solo se informa; pasa a ser cobrado cuando se registra el abono.
    """
    cero = Decimal("0.00")
    if prestamo.estado in ESTADOS_CERRADOS:
        return cero, cero
    total = intereses_pendientes_vencidos(prestamo, hoy)
    if total <= 0:
        return cero, cero
    bien_comun = cero
    if es_regla_mora(prestamo):
        for p in periodos_interes(prestamo, hoy):
            if p.vencido and p.pendiente > 0 and p.valor > 0:
                bien_comun += (p.pendiente * p.interes_bien_comun / p.valor).quantize(Decimal("0.01"))
    else:
        # Tasa fija: interés igual cada mes; al bien común desde la cuota #4
        # (o todo en el segundo préstamo del socio), igual que al cobrarlo.
        mensual = interes_mensual(prestamo, prestamo.tasa_interes)
        pagado: dict[int, Decimal] = {}
        for a in prestamo.abonos or []:
            pagado[a.numero_cuota] = pagado.get(a.numero_cuota, cero) + (a.monto_interes or cero)
        segundo = es_segundo_prestamo(prestamo)
        for n in range(1, min(cuotas_vencidas(prestamo, hoy), prestamo.numero_cuotas) + 1):
            if segundo or n >= CUOTA_BIEN_COMUN:
                bien_comun += max(cero, mensual - pagado.get(n, cero))
    return total, min(total, bien_comun)


def total_gastos_generales(db: Session, anio: int) -> Decimal:
    return db.execute(
        select(func.coalesce(func.sum(GastoGeneral.monto), Decimal("0.00"))).where(GastoGeneral.anio == anio)
    ).scalar_one()


def _limites_anio(anio: int) -> tuple[datetime, datetime]:
    """Inicio y fin (exclusivo) del año en hora de Colombia, expresados en UTC."""
    inicio = datetime(anio, 1, 1, tzinfo=ZONA_COLOMBIA)
    fin = datetime(anio + 1, 1, 1, tzinfo=ZONA_COLOMBIA)
    return inicio.astimezone(timezone.utc), fin.astimezone(timezone.utc)


def _por_socio(filas) -> dict[int, dict[str, Decimal]]:
    resultado: dict[int, dict[str, Decimal]] = {}
    for socio_id, tipo, total in filas:
        resultado.setdefault(socio_id, {})[tipo] = total or Decimal("0.00")
    return resultado


class FinanzasService:
    @staticmethod
    def calcular_bien_comun(db: Session, anio: Optional[int] = None, con_pendientes: bool = False) -> BienComunResponse:
        """Consolida multas pagadas y la parte de intereses que corresponde al bien común
        (3 % de la regla 7 % / 3 %; en préstamos anteriores, intereses desde la cuarta cuota).

        Sin año usa todo el histórico; con año solo lo cobrado en ese año.
        Se reparte en partes iguales entre los socios activos.

        Solo cuenta intereses efectivamente cobrados (abonos registrados). Con
        `con_pendientes` informa además los intereses vencidos sin pagar, aparte:
        no suman al dinero total ni a la participación de los socios.
        """
        condiciones_multas = [FinanzaSocio.tipo_movimiento == TipoMovimientoFinanciero.PAGO_MULTA.value]
        condiciones_abonos = []
        if anio is not None:
            inicio, fin = _limites_anio(anio)
            condiciones_multas += [FinanzaSocio.fecha >= inicio, FinanzaSocio.fecha < fin]
            condiciones_abonos += [AbonoPrestamo.fecha_pago >= inicio, AbonoPrestamo.fecha_pago < fin]
        total_multas_pagadas = db.execute(
            select(func.coalesce(func.sum(FinanzaSocio.monto), Decimal("0.00"))).where(*condiciones_multas)
        ).scalar_one()
        total_intereses_bien_comun = db.execute(
            select(func.coalesce(func.sum(INTERES_BIEN_COMUN), Decimal("0.00")))
            .where(*condiciones_abonos)
        ).scalar_one()
        total_intereses_obtenidos = db.execute(
            select(func.coalesce(func.sum(AbonoPrestamo.monto_interes), Decimal("0.00"))).where(*condiciones_abonos)
        ).scalar_one()
        total_dinero_total = total_multas_pagadas + total_intereses_bien_comun
        socios = db.execute(
            select(Socio).where(Socio.is_active.is_(True)).order_by(Socio.nombre.asc(), Socio.id.asc())
        ).scalars().all()
        participaciones = repartir_importe(total_dinero_total, [Decimal("1") for _ in socios])

        detalle: list[BienComunInteresPrestamo] = []
        total_pendientes = Decimal("0.00")
        total_pendientes_bc = Decimal("0.00")
        if con_pendientes:
            nombres = dict(db.execute(select(Socio.id, Socio.nombre)).all())
            cobrado = {
                pid: (total or Decimal("0.00"), bc or Decimal("0.00"))
                for pid, total, bc in db.execute(
                    select(AbonoPrestamo.prestamo_id, func.sum(AbonoPrestamo.monto_interes), func.sum(INTERES_BIEN_COMUN))
                    .where(*condiciones_abonos)
                    .group_by(AbonoPrestamo.prestamo_id)
                ).all()
            }
            hoy = hoy_colombia()
            for prestamo in db.execute(select(Prestamo).order_by(Prestamo.id.asc())).scalars().all():
                pendiente, pendiente_bc = intereses_pendientes_bien_comun(prestamo, hoy)
                cobrado_total, cobrado_bc = cobrado.get(prestamo.id, (Decimal("0.00"), Decimal("0.00")))
                if not (pendiente or cobrado_total):
                    continue
                total_pendientes += pendiente
                total_pendientes_bc += pendiente_bc
                detalle.append(BienComunInteresPrestamo(
                    prestamo_id=prestamo.id,
                    socio_id=prestamo.socio_id,
                    socio_nombre=nombres.get(prestamo.socio_id) or f"Socio #{prestamo.socio_id}",
                    estado=prestamo.estado,
                    intereses_cobrados=cobrado_total,
                    intereses_cobrados_bien_comun=cobrado_bc,
                    intereses_pendientes=pendiente,
                    intereses_pendientes_bien_comun=pendiente_bc,
                ))

        return BienComunResponse(
            total_multas_recaudadas=total_multas_pagadas,
            total_intereses_obtenidos=total_intereses_obtenidos,
            total_intereses_bien_comun=total_intereses_bien_comun,
            total_intereses_pendientes=total_pendientes,
            total_intereses_pendientes_bien_comun=total_pendientes_bc,
            intereses_por_prestamo=detalle,
            total_dinero_total=total_dinero_total,
            socios=[
                BienComunSocioItem(
                    id=socio.id,
                    nombre=socio.nombre,
                    participacion=participacion,
                )
                for socio, participacion in zip(socios, participaciones)
            ],
        )

    @staticmethod
    def calcular_capital_total(db: Session) -> CapitalTotalResponse:
        """
        Cálculo financiero automatizado en tiempo real (RF8):
        Capital Total = (Aportes netos de socios)
                      + (Multas efectivamente cobradas)
                      + (Ganancias netas de actividades)
                      + (Ganancias netas de rifas)
                      + (Ganancias recaudadas en reuniones)
                      + (Intereses cobrados por préstamos)
        
        Además desglosa:
        - Cartera en circulación (total_dinero_prestado_activo)
        - Liquidez disponible en caja (capital_total - total_dinero_prestado_activo)
        """
        # 1. Aportes de socios (Aportes menos retiros)
        stmt_aportes = select(
            func.coalesce(func.sum(FinanzaSocio.monto), Decimal("0.00"))
        ).where(FinanzaSocio.tipo_movimiento == TipoMovimientoFinanciero.APORTE.value)
        total_aportes_bruto = db.execute(stmt_aportes).scalar_one()

        stmt_retiros = select(
            func.coalesce(func.sum(FinanzaSocio.monto), Decimal("0.00"))
        ).where(FinanzaSocio.tipo_movimiento == TipoMovimientoFinanciero.RETIRO_AHORRO.value)
        total_retiros = db.execute(stmt_retiros).scalar_one()

        total_aportes_netos = max(Decimal("0.00"), total_aportes_bruto - total_retiros)

        # 2. Multas cobradas (pagadas)
        stmt_multas = select(
            func.coalesce(func.sum(FinanzaSocio.monto), Decimal("0.00"))
        ).where(FinanzaSocio.tipo_movimiento == TipoMovimientoFinanciero.PAGO_MULTA.value)
        total_multas_cobradas = db.execute(stmt_multas).scalar_one()

        # 3. Ganancias de actividades
        stmt_actividades = select(
            func.coalesce(func.sum(Actividad.ganancia_neta), Decimal("0.00"))
        )
        total_ganancias_actividades = db.execute(stmt_actividades).scalar_one()

        # 4. Ganancias de rifas
        stmt_rifas = select(
            func.coalesce(func.sum(Rifa.ganancias_totales), Decimal("0.00"))
        )
        total_ganancias_rifas = db.execute(stmt_rifas).scalar_one()

        # 5. Ganancias en reuniones
        stmt_reuniones = select(
            func.coalesce(func.sum(Reunion.ganancias_reunion), Decimal("0.00"))
        )
        total_ganancias_reuniones = db.execute(stmt_reuniones).scalar_one()

        # 6. Intereses cobrados por préstamos (de la tabla de abonos)
        stmt_intereses = select(
            func.coalesce(func.sum(AbonoPrestamo.monto_interes), Decimal("0.00"))
        )
        total_intereses_prestamos = db.execute(stmt_intereses).scalar_one()

        # Capital Total
        capital_total = (
            total_aportes_netos
            + total_multas_cobradas
            + total_ganancias_actividades
            + total_ganancias_rifas
            + total_ganancias_reuniones
            + total_intereses_prestamos
        )

        # Cartera activa prestada (Saldo pendiente en la calle)
        stmt_cartera = select(
            func.coalesce(func.sum(Prestamo.saldo_pendiente), Decimal("0.00"))
        ).where(Prestamo.estado.notin_(ESTADOS_CERRADOS))
        total_dinero_prestado_activo = db.execute(stmt_cartera).scalar_one()

        # Liquidez física disponible en caja
        liquidez_disponible_caja = capital_total - total_dinero_prestado_activo

        return CapitalTotalResponse(
            total_aportes_socios=total_aportes_netos,
            total_multas_cobradas=total_multas_cobradas,
            total_ganancias_actividades=total_ganancias_actividades,
            total_ganancias_rifas=total_ganancias_rifas,
            total_ganancias_reuniones=total_ganancias_reuniones,
            total_intereses_prestamos=total_intereses_prestamos,
            capital_total=capital_total,
            total_dinero_prestado_activo=total_dinero_prestado_activo,
            liquidez_disponible_caja=liquidez_disponible_caja,
        )

    @staticmethod
    def calcular_liquidacion_anual(db: Session, anio: Optional[int] = None) -> LiquidacionAnualResponse:
        """
        Liquidación de un ciclo anual (enero a diciembre, hora de Colombia).

        Cada año empieza de cero: solo cuentan aportes, retiros, multas pagadas,
        intereses cobrados, actividades, rifas y reuniones registrados en ese año.
        Las deudas (préstamos y multas) se toman como estaban al cierre del año.

        - Socios activos: reciben su ahorro, utilidades proporcionales al ahorro
          y una parte igual del bien común.
        - Socios inactivos: solo aparecen si tienen ahorro o deudas en el año;
          se les devuelve el ahorro y se les descuenta lo que deben, pero no
          reciben utilidades ni bien común.
        """
        anio = anio or anio_del_periodo(db)
        inicio_dt, fin_dt = _limites_anio(anio)
        inicio_d, fin_d = date(anio, 1, 1), date(anio + 1, 1, 1)
        cero = Decimal("0.00")

        def suma(columna, *condiciones) -> Decimal:
            return db.execute(
                select(func.coalesce(func.sum(columna), cero)).where(*condiciones)
            ).scalar_one()

        en_anio_finanza = (FinanzaSocio.fecha >= inicio_dt, FinanzaSocio.fecha < fin_dt)
        en_anio_abono = (AbonoPrestamo.fecha_pago >= inicio_dt, AbonoPrestamo.fecha_pago < fin_dt)

        # 1. Utilidades generadas en el año por cada fuente del fondo común
        total_multas_cobradas = suma(
            FinanzaSocio.monto,
            FinanzaSocio.tipo_movimiento == TipoMovimientoFinanciero.PAGO_MULTA.value,
            *en_anio_finanza,
        )
        total_ganancias_actividades = suma(Actividad.ganancia_neta, Actividad.fecha >= inicio_d, Actividad.fecha < fin_d)
        total_ganancias_rifas = suma(Rifa.ganancias_totales, Rifa.fecha >= inicio_d, Rifa.fecha < fin_d)
        total_ganancias_reuniones = suma(Reunion.ganancias_reunion, Reunion.fecha >= inicio_d, Reunion.fecha < fin_d)
        total_intereses_prestamos = suma(AbonoPrestamo.monto_interes, *en_anio_abono)
        total_utilidades = (
            total_multas_cobradas
            + total_ganancias_actividades
            + total_ganancias_rifas
            + total_ganancias_reuniones
            + total_intereses_prestamos
        )
        total_bien_comun_general = total_multas_cobradas + suma(INTERES_BIEN_COMUN, *en_anio_abono)

        # 2. Movimientos por socio agrupados en pocas consultas
        movimientos_anio = _por_socio(db.execute(
            select(FinanzaSocio.socio_id, FinanzaSocio.tipo_movimiento, func.sum(FinanzaSocio.monto))
            .where(*en_anio_finanza)
            .group_by(FinanzaSocio.socio_id, FinanzaSocio.tipo_movimiento)
        ).all())
        # Multas: saldo acumulado hasta el cierre del año (pueden venir de años anteriores).
        movimientos_al_cierre = _por_socio(db.execute(
            select(FinanzaSocio.socio_id, FinanzaSocio.tipo_movimiento, func.sum(FinanzaSocio.monto))
            .where(
                FinanzaSocio.fecha < fin_dt,
                FinanzaSocio.tipo_movimiento.in_([
                    TipoMovimientoFinanciero.MULTA.value, TipoMovimientoFinanciero.PAGO_MULTA.value,
                ]),
            )
            .group_by(FinanzaSocio.socio_id, FinanzaSocio.tipo_movimiento)
        ).all())

        # Parte del socio de los intereses cobrados en el año (7 % de la regla 7 % / 3 %;
        # en préstamos anteriores, las tres primeras cuotas): va a su ahorro personal.
        intereses_personales = dict(db.execute(
            select(Prestamo.socio_id, func.sum(INTERES_SOCIO))
            .join(AbonoPrestamo, AbonoPrestamo.prestamo_id == Prestamo.id)
            .where(*en_anio_abono)
            .group_by(Prestamo.socio_id)
        ).all())

        # Deuda de préstamos al cierre del año: capital e interés aún no pagados.
        pagado_al_cierre = {
            prestamo_id: (capital or cero, interes or cero)
            for prestamo_id, capital, interes in db.execute(
                select(
                    AbonoPrestamo.prestamo_id,
                    func.sum(AbonoPrestamo.monto_capital),
                    func.sum(AbonoPrestamo.monto_interes),
                )
                .where(AbonoPrestamo.fecha_pago < fin_dt)
                .group_by(AbonoPrestamo.prestamo_id)
            ).all()
        }
        deuda_por_socio: dict[int, Decimal] = {}
        for prestamo in db.execute(select(Prestamo).where(Prestamo.fecha_prestamo < fin_d)).scalars():
            capital, interes = pagado_al_cierre.get(prestamo.id, (cero, cero))
            deuda = (
                max(cero, prestamo.monto_prestado - capital)
                + max(cero, prestamo.total_intereses - interes)
            )
            deuda_por_socio[prestamo.socio_id] = deuda_por_socio.get(prestamo.socio_id, cero) + deuda

        # 3. Construir la nómina de socios
        datos_socios = []
        socios = db.execute(select(Socio).order_by(Socio.nombre.asc(), Socio.id.asc())).scalars().all()
        for s in socios:
            mov = movimientos_anio.get(s.id, {})
            ahorrado = max(cero, mov.get(TipoMovimientoFinanciero.APORTE.value, cero)
                           - mov.get(TipoMovimientoFinanciero.RETIRO_AHORRO.value, cero))
            ahorrado += intereses_personales.get(s.id) or cero
            cierre = movimientos_al_cierre.get(s.id, {})
            multas_pendientes = max(cero, cierre.get(TipoMovimientoFinanciero.MULTA.value, cero)
                                    - cierre.get(TipoMovimientoFinanciero.PAGO_MULTA.value, cero))
            deuda = deuda_por_socio.get(s.id, cero)
            if not s.is_active and ahorrado == cero and deuda == cero and multas_pendientes == cero:
                continue
            datos_socios.append({
                "socio": s, "ahorrado": ahorrado, "deuda": deuda, "multas_pendientes": multas_pendientes,
            })

        total_ahorro_acumulado = sum((item["ahorrado"] for item in datos_socios), cero)
        ahorro_activos = sum((item["ahorrado"] for item in datos_socios if item["socio"].is_active), cero)

        # Rentabilidad porcentual del fondo sobre el ahorro de los socios activos
        if ahorro_activos > cero:
            rentabilidad_porcentual = ((total_utilidades / ahorro_activos) * Decimal("100.00")).quantize(Decimal("0.01"))
        else:
            rentabilidad_porcentual = cero

        # Los intereses personales ya forman parte del ahorro y el bien común se
        # asigna aparte: distribuir solo actividades, rifas y reuniones evita duplicarlos.
        # Solo los socios activos participan en utilidades y bien común.
        utilidades_por_socio = repartir_importe(
            total_ganancias_actividades + total_ganancias_rifas + total_ganancias_reuniones,
            [item["ahorrado"] if item["socio"].is_active else cero for item in datos_socios],
        )
        bien_comun_asignado = repartir_importe(
            total_bien_comun_general,
            [Decimal("1") if item["socio"].is_active else cero for item in datos_socios],
        )
        # Gastos generales del año: partes iguales solo entre socios activos.
        # Se calculan siempre a partir de los gastos guardados, así no se descuentan dos veces.
        total_gastos = total_gastos_generales(db, anio)
        gastos_asignados = repartir_importe(
            total_gastos,
            [Decimal("1") if item["socio"].is_active else cero for item in datos_socios],
        )

        socios_liquidados: list[LiquidacionSocioItem] = []
        total_deuda_descontada = cero
        total_multas_descontadas = cero
        total_gastos_descontados = cero
        gran_total_a_entregar = cero

        for item, utilidad, bien_comun_por_socio, gasto in zip(
            datos_socios, utilidades_por_socio, bien_comun_asignado, gastos_asignados,
        ):
            s = item["socio"]
            ahorrado, deuda, multas = item["ahorrado"], item["deuda"], item["multas_pendientes"]

            if s.is_active and ahorro_activos > cero and ahorrado > cero:
                participacion = ((ahorrado / ahorro_activos) * Decimal("100.00")).quantize(Decimal("0.01"))
            else:
                participacion = cero

            liquidacion_bruta = ahorrado + utilidad + bien_comun_por_socio - deuda - multas
            neto_entregar = liquidacion_bruta - gasto
            total_deuda_descontada += deuda
            total_multas_descontadas += multas
            total_gastos_descontados += gasto
            gran_total_a_entregar += neto_entregar

            socios_liquidados.append(
                LiquidacionSocioItem(
                    socio_id=s.id,
                    nombre=s.nombre,
                    cedula=s.cedula,
                    activo=s.is_active,
                    total_ahorrado=ahorrado,
                    porcentaje_participacion=participacion,
                    utilidad_ganada=utilidad,
                    bien_comun_asignado=bien_comun_por_socio,
                    deuda_prestamos=deuda,
                    multas_pendientes=multas,
                    liquidacion_antes_gastos=liquidacion_bruta,
                    gastos_generales=gasto,
                    total_neto_entregar=neto_entregar,
                )
            )

        return LiquidacionAnualResponse(
            anio=anio,
            anios_disponibles=FinanzasService.anios_con_movimientos(db),
            total_ahorro_acumulado=total_ahorro_acumulado,
            total_utilidades_generadas=total_utilidades,
            total_bien_comun_general=total_bien_comun_general,
            rentabilidad_porcentual=rentabilidad_porcentual,
            total_deuda_descontada=total_deuda_descontada,
            total_multas_descontadas=total_multas_descontadas,
            total_gastos_generales=total_gastos,
            total_gastos_descontados=total_gastos_descontados,
            socios_activos=sum(1 for item in datos_socios if item["socio"].is_active),
            gran_total_a_entregar=gran_total_a_entregar,
            socios_liquidados=socios_liquidados,
        )

    @staticmethod
    def anios_con_movimientos(db: Session) -> list[int]:
        """Años desde el primer registro hasta el actual, del más reciente al más antiguo."""
        actual = anio_del_periodo(db)
        anios = []
        for columna in (FinanzaSocio.fecha, AbonoPrestamo.fecha_pago, Prestamo.fecha_prestamo,
                        Actividad.fecha, Rifa.fecha, Reunion.fecha):
            valor = db.execute(select(func.min(columna))).scalar_one()
            if isinstance(valor, str):  # SQLite puede devolver texto en agregados
                valor = date.fromisoformat(valor[:10])
            if valor is not None:
                anios.append(valor.year)
        desde = min(min(anios, default=actual), actual)
        return list(range(actual, desde - 1, -1))


def calcular_total_ahorrado_socio(db: Session, socio_id: int) -> dict[str, Decimal | bool]:
    """Total ahorrado por un socio: ahorros y beneficios acumulados, sin duplicados.

    Toma los registros reales del año que se consulta (cada año guarda sus datos):
    - aportes_mensuales: aportes menos retiros de ahorro (igual que el recuadro
      "Aportes mensuales").
    - ganancias_intereses: parte del socio de los intereses de sus préstamos
      (7 % de la regla 7 % / 3 %; cuotas 1 a 3 en préstamos anteriores; $0 en el
      segundo préstamo, cuyo interés es 100 % del bien común).
    - ganancias_actividades: suma de las líneas "Otra" del apartado Actividades del
      socio (lo que él mismo vendió o ganó en cada actividad).
    - ganancias_rifa_interna: suma de las líneas "Rifa interna" del socio.
    - ganancias de rifas grandes/pequeñas y de reuniones: se reparten entre los
      socios activos en proporción a su ahorro (aportes + intereses), igual que la
      liquidación anual. Las rifas internas del apartado Eventos no se suman aquí:
      lo que gana cada socio en ellas se registra en sus líneas de rifa interna.
    - bien_comun: parte igual del bien común (multas pagadas e intereses del bien
      común) entre los socios activos, igual que el apartado Bien común.
    Cada peso se cuenta una sola vez: el interés del bien común no suma también
    como interés del socio, y las ganancias de eventos se reparten una vez.
    """
    cero = Decimal("0.00")
    movimientos = _por_socio(db.execute(
        select(FinanzaSocio.socio_id, FinanzaSocio.tipo_movimiento, func.sum(FinanzaSocio.monto))
        .where(FinanzaSocio.tipo_movimiento.in_([
            TipoMovimientoFinanciero.APORTE.value, TipoMovimientoFinanciero.RETIRO_AHORRO.value,
        ]))
        .group_by(FinanzaSocio.socio_id, FinanzaSocio.tipo_movimiento)
    ).all())
    intereses = dict(db.execute(
        select(Prestamo.socio_id, func.sum(INTERES_SOCIO))
        .join(AbonoPrestamo, AbonoPrestamo.prestamo_id == Prestamo.id)
        .group_by(Prestamo.socio_id)
    ).all())
    socios = db.execute(select(Socio).order_by(Socio.nombre.asc(), Socio.id.asc())).scalars().all()

    def aportes_de(sid: int) -> Decimal:
        mov = movimientos.get(sid, {})
        return max(cero, mov.get(TipoMovimientoFinanciero.APORTE.value, cero)
                   - mov.get(TipoMovimientoFinanciero.RETIRO_AHORRO.value, cero))

    pesos = [
        (aportes_de(s.id) + (intereses.get(s.id) or cero)) if s.is_active else cero
        for s in socios
    ]
    indice = next((i for i, s in enumerate(socios) if s.id == socio_id), None)

    def parte(total: Decimal) -> Decimal:
        if indice is None:
            return cero
        return repartir_importe(total, pesos)[indice]

    lineas = dict(db.execute(
        select(ActividadSocio.tipo, func.sum(ActividadSocio.ganancia))
        .where(ActividadSocio.socio_id == socio_id)
        .group_by(ActividadSocio.tipo)
    ).all())
    total_rifas = db.execute(
        select(func.coalesce(func.sum(Rifa.ganancias_totales), cero)).where(Rifa.tipo != "INTERNA")
    ).scalar_one()
    total_reuniones = db.execute(select(func.coalesce(func.sum(Reunion.ganancias_reunion), cero))).scalar_one()
    bien_comun = next(
        (item.participacion for item in FinanzasService.calcular_bien_comun(db).socios if item.id == socio_id), cero,
    )
    datos = {
        "aportes_mensuales": aportes_de(socio_id),
        "ganancias_intereses": intereses.get(socio_id) or cero,
        "ganancias_actividades": lineas.get(TipoActividadSocio.OTRA) or cero,
        "ganancias_rifa_interna": lineas.get(TipoActividadSocio.RIFA_INTERNA) or cero,
        "ganancias_rifas": parte(total_rifas),
        "ganancias_reuniones": parte(total_reuniones),
        "bien_comun": bien_comun,
    }
    datos["total"] = sum(datos.values(), cero)
    datos["activo"] = bool(indice is not None and socios[indice].is_active)
    return datos


def _partes_por_item(total_socio: Decimal, montos: list[Decimal], pesos: list[Decimal], indice: Optional[int]) -> list[Decimal]:
    """Parte del socio en cada registro, ajustada para sumar exactamente su total.

    Repartir registro por registro puede diferir en centavos del reparto del total;
    la diferencia se asigna al registro de mayor valor para no descuadrar.
    """
    cero = Decimal("0.00")
    if indice is None or not montos:
        return [cero for _ in montos]
    partes = [repartir_importe(monto, pesos)[indice] for monto in montos]
    diferencia = total_socio - sum(partes, cero)
    if diferencia:
        mayor = max(range(len(montos)), key=lambda i: abs(montos[i]))
        partes[mayor] += diferencia
    return partes


def detalle_impresion_socio(db: Session, socio_id: int, deducciones) -> dict:
    """Datos de la hoja imprimible del socio (estilo de la planilla en papel).

    Usa los mismos totales del recuadro "Total ahorrado" y de "Deducciones":
    solo los separa por mes y por registro, sin volver a sumar nada.
    """
    cero = Decimal("0.00")
    anio = anio_del_periodo(db)
    totales = calcular_total_ahorrado_socio(db, socio_id)

    # Orden de socios igual al de la liquidación (para repartir los gastos generales).
    socios = db.execute(select(Socio).order_by(Socio.nombre.asc(), Socio.id.asc())).scalars().all()
    indice = next((i for i, s in enumerate(socios) if s.id == socio_id), None)
    activo = bool(indice is not None and socios[indice].is_active)

    def mes_de(valor) -> Optional[int]:
        fecha = valor
        if isinstance(fecha, datetime):
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            fecha = fecha.astimezone(ZONA_COLOMBIA).date()
        return fecha.month if fecha and fecha.year == anio else None

    # Cuotas (aportes) por mes del año.
    meses = {m: {"cuota": cero, "rifa_interna": cero} for m in range(1, 13)}
    otros_aportes = cero
    retiros = cero
    for mov in db.execute(select(FinanzaSocio).where(FinanzaSocio.socio_id == socio_id)).scalars():
        if mov.tipo_movimiento == TipoMovimientoFinanciero.RETIRO_AHORRO.value:
            retiros += mov.monto
            continue
        if mov.tipo_movimiento != TipoMovimientoFinanciero.APORTE.value:
            continue
        mes = None
        if mov.periodo and mov.periodo[:4] == str(anio):
            mes = int(mov.periodo[5:7])
        elif not mov.periodo:
            mes = mes_de(mov.fecha)
        if mes:
            meses[mes]["cuota"] += mov.monto
        else:
            otros_aportes += mov.monto

    # Líneas del apartado Actividades del socio: las rifas internas van en su mes
    # (columna R. interna, al lado de la cuota) y las demás en la columna Actividad.
    lista_actividades = []
    for a in db.execute(
        select(ActividadSocio).where(ActividadSocio.socio_id == socio_id).order_by(ActividadSocio.id.asc())
    ).scalars():
        if a.tipo == TipoActividadSocio.RIFA_INTERNA and a.mes in meses:
            meses[a.mes]["rifa_interna"] += a.ganancia
        else:
            lista_actividades.append({
                "nombre": a.nombre, "cantidad_vendida": a.cantidad_vendida,
                "valor_unidad": a.valor_unidad, "ganancia": a.ganancia,
            })

    # Deducciones: deudas pendientes + parte del socio en los gastos generales del año.
    gastos = db.execute(
        select(GastoGeneral).where(GastoGeneral.anio == anio).order_by(GastoGeneral.id.asc())
    ).scalars().all()
    pesos_gastos = [Decimal("1") if s.is_active else cero for s in socios]
    total_gasto_socio = (
        repartir_importe(total_gastos_generales(db, anio), pesos_gastos)[indice] if activo else cero
    )
    partes_gastos = _partes_por_item(total_gasto_socio, [g.monto for g in gastos], pesos_gastos, indice if activo else None)
    filas_deducciones = [
        {"concepto": "Préstamos", "valor": deducciones.total_capital_pendiente},
        {"concepto": "Intereses", "valor": deducciones.total_intereses_pendientes},
        {"concepto": "Multas", "valor": deducciones.total_multas_pendientes},
    ] + [{"concepto": g.descripcion, "valor": parte} for g, parte in zip(gastos, partes_gastos)]

    total_deducciones = sum((f["valor"] for f in filas_deducciones), cero)
    # Total a recibir = Total ahorrado - deducciones. No descuenta el capital de los
    # préstamos pendientes (fila "Préstamos"): solo intereses vencidos, multas y la
    # parte del socio en los gastos generales.
    deducciones_a_descontar = total_deducciones - deducciones.total_capital_pendiente
    return {
        "anio": anio,
        "meses": [{"mes": m, **valores} for m, valores in meses.items()],
        "otros_aportes": otros_aportes,
        "retiros": retiros,
        "actividades": lista_actividades,
        "deducciones": filas_deducciones,
        "total_deducciones": total_deducciones,
        "deducciones_a_descontar": deducciones_a_descontar,
        "total_a_recibir": totales["total"] - deducciones_a_descontar,
        "total_ahorrado": totales,
    }
