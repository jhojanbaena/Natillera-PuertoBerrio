"""Servicio de Cálculos Financieros y Agregaciones SQL en Tiempo Real (RF8).
Realiza consultas optimizadas con funciones agregadas nativas para el cálculo del capital total.
"""
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models.socio import Socio
from app.models.finanzas import FinanzaSocio, TipoMovimientoFinanciero
from app.models.actividad import Actividad
from app.models.rifa import Rifa
from app.models.reunion import Reunion
from app.models.prestamo import Prestamo, AbonoPrestamo, EstadoPrestamo
from app.schemas.dashboard import BienComunResponse, BienComunSocioItem, CapitalTotalResponse
from app.schemas.finanzas import LiquidacionSocioItem, LiquidacionAnualResponse
from app.services.prestamos_service import ZONA_COLOMBIA, hoy_colombia


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
    def calcular_bien_comun(db: Session, anio: Optional[int] = None) -> BienComunResponse:
        """Consolida multas pagadas e intereses cobrados desde la cuarta cuota.

        Sin año usa todo el histórico; con año solo lo cobrado en ese año.
        Se reparte en partes iguales entre los socios activos.
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
            select(func.coalesce(func.sum(AbonoPrestamo.monto_interes), Decimal("0.00")))
            .where(AbonoPrestamo.numero_cuota >= 4, *condiciones_abonos)
        ).scalar_one()
        total_intereses_obtenidos = db.execute(
            select(func.coalesce(func.sum(AbonoPrestamo.monto_interes), Decimal("0.00"))).where(*condiciones_abonos)
        ).scalar_one()
        total_dinero_total = total_multas_pagadas + total_intereses_bien_comun
        socios = db.execute(
            select(Socio).where(Socio.is_active.is_(True)).order_by(Socio.nombre.asc(), Socio.id.asc())
        ).scalars().all()
        participaciones = repartir_importe(total_dinero_total, [Decimal("1") for _ in socios])

        return BienComunResponse(
            total_multas_recaudadas=total_multas_pagadas,
            total_intereses_obtenidos=total_intereses_obtenidos,
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
        ).where(Prestamo.estado != EstadoPrestamo.PAGADO.value)
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
        anio = anio or hoy_colombia().year
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
        total_bien_comun_general = total_multas_cobradas + suma(
            AbonoPrestamo.monto_interes, AbonoPrestamo.numero_cuota >= 4, *en_anio_abono
        )

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

        # Intereses de las tres primeras cuotas cobrados en el año: van al ahorro personal.
        intereses_personales = dict(db.execute(
            select(Prestamo.socio_id, func.sum(AbonoPrestamo.monto_interes))
            .join(AbonoPrestamo, AbonoPrestamo.prestamo_id == Prestamo.id)
            .where(AbonoPrestamo.numero_cuota <= 3, *en_anio_abono)
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

        socios_liquidados: list[LiquidacionSocioItem] = []
        total_deuda_descontada = cero
        total_multas_descontadas = cero
        gran_total_a_entregar = cero

        for item, utilidad, bien_comun_por_socio in zip(datos_socios, utilidades_por_socio, bien_comun_asignado):
            s = item["socio"]
            ahorrado, deuda, multas = item["ahorrado"], item["deuda"], item["multas_pendientes"]

            if s.is_active and ahorro_activos > cero and ahorrado > cero:
                participacion = ((ahorrado / ahorro_activos) * Decimal("100.00")).quantize(Decimal("0.01"))
            else:
                participacion = cero

            neto_entregar = ahorrado + utilidad + bien_comun_por_socio - deuda - multas
            total_deuda_descontada += deuda
            total_multas_descontadas += multas
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
            gran_total_a_entregar=gran_total_a_entregar,
            socios_liquidados=socios_liquidados,
        )

    @staticmethod
    def anios_con_movimientos(db: Session) -> list[int]:
        """Años desde el primer registro hasta el actual, del más reciente al más antiguo."""
        actual = hoy_colombia().year
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
