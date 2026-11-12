"""Saldo, estado y mora de un préstamo derivados de sus abonos persistidos.

Regla de mora: se espera una cuota mensual a partir de la fecha del préstamo.
La cuota N vence N meses después del desembolso; desde el día siguiente a ese
vencimiento (más DIAS_GRACIA_MORA, hoy 0) la cuota está atrasada y el préstamo
queda EN_MORA. También entra en mora si supera la fecha de vencimiento con
deuda pendiente. El estado se recalcula siempre: al ponerse al día vuelve a
PENDIENTE.

Regla de intereses MORA_7_10: cada mes causa
monto_prestado x tasa. Si se paga a más tardar en la fecha límite corresponde la
tasa normal (7 %); desde el día siguiente, la tasa de mora (10 %). El
administrador ve la tasa sugerida y puede elegir la otra al registrar el abono;
la elegida queda guardada en el abono. Los préstamos con regla FIJA no cambian.

Regla de intereses REPARTO_7_3 (préstamos nuevos desde la actualización):
cada mes causa el 10 % del capital pendiente al iniciar el mes.
Mientras quede capital por pagar se siguen causando meses, aunque se haya
superado el número de cuotas pactado o el socio ya haya hecho abonos; cuando el
capital llega a $0 dejan de causarse. Cada peso de interés cobrado se reparte:
7/10 para el ahorro personal del socio y 3/10 para el bien común (se guarda en
el abono). El pago de intereses y el de capital siempre van separados.
"""
import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.prestamo import Prestamo, AbonoPrestamo, EstadoPrestamo, ESTADOS_CERRADOS, ReglaInteres

# Desde el día siguiente a la fecha límite ya hay atraso (igual que el 10 %).
DIAS_GRACIA_MORA = 0
TASA_NORMAL = Decimal("7.00")
TASA_MORA = Decimal("10.00")
# Regla 7 % / 3 %: 10 % mensual = 7 % para el socio + 3 % para el bien común.
TASA_REPARTO = Decimal("10.00")
TASA_SOCIO = Decimal("7.00")
TASA_BIEN_COMUN = Decimal("3.00")
DESTINO_REPARTO = "REPARTO_7_3"
# Tope de seguridad de meses causados por préstamo (50 años).
MAX_MESES_INTERES = 600
# Desde esta cuota los intereses van al bien común.
CUOTA_BIEN_COMUN = 4
CERO = Decimal("0.00")
ZONA_COLOMBIA = timezone(timedelta(hours=-5))


def hoy_colombia() -> date:
    """Fecha actual en Colombia (los servidores serverless corren en UTC)."""
    return datetime.now(ZONA_COLOMBIA).date()


def fecha_a_datetime(fecha: date) -> datetime:
    """Fecha elegida por el usuario -> mediodía de Colombia en UTC.

    El mediodía evita que el registro cambie de día (o de año) por la zona horaria.
    """
    return datetime(fecha.year, fecha.month, fecha.day, 12, tzinfo=ZONA_COLOMBIA).astimezone(timezone.utc)


def validar_fecha_registro(fecha: Optional[date]) -> None:
    """Solo impide fechas futuras: las cuentas se pasan del cuaderno con su fecha real."""
    from fastapi import HTTPException  # evitar dependencia web al importar modelos

    if fecha is None:
        return
    if fecha > hoy_colombia():
        raise HTTPException(status_code=422, detail="La fecha no puede ser futura")


def validar_fecha_abono(fecha: Optional[date]) -> None:
    """Abonos de préstamos: se permite cualquier fecha (pasada, actual o futura).

    Solo se rechazan fechas absurdas para evitar errores de digitación.
    """
    from fastapi import HTTPException  # evitar dependencia web al importar modelos

    if fecha is None:
        return
    if not (date(2000, 1, 1) <= fecha <= date(2100, 12, 31)):
        raise HTTPException(status_code=422, detail="La fecha del abono debe estar entre los años 2000 y 2100")


def sumar_meses(fecha: date, meses: int) -> date:
    """Suma meses calendario conservando el día o usando el último del mes."""
    total = fecha.month - 1 + meses
    anio, mes = fecha.year + total // 12, total % 12 + 1
    return date(anio, mes, min(fecha.day, calendar.monthrange(anio, mes)[1]))


def fecha_cuota(prestamo: Prestamo, numero: int) -> date:
    return sumar_meses(prestamo.fecha_prestamo, numero)


def cuotas_vencidas(prestamo: Prestamo, hoy: Optional[date] = None) -> int:
    """Cuotas cuyo vencimiento más los días de gracia ya pasó."""
    hoy = hoy or hoy_colombia()
    limite = hoy - timedelta(days=DIAS_GRACIA_MORA)
    vencidas = 0
    while vencidas < prestamo.numero_cuotas and fecha_cuota(prestamo, vencidas + 1) < limite:
        vencidas += 1
    return vencidas


def cuotas_atrasadas(prestamo: Prestamo, hoy: Optional[date] = None) -> int:
    if prestamo.estado in ESTADOS_CERRADOS:
        return 0
    if es_regla_mora(prestamo):
        return sum(1 for p in periodos_interes(prestamo, hoy) if p.vencido and p.pendiente > 0)
    return max(0, cuotas_vencidas(prestamo, hoy) - prestamo.cuotas_pagadas)


def fecha_proxima_cuota(prestamo: Prestamo) -> Optional[date]:
    if prestamo.estado in ESTADOS_CERRADOS:
        return None
    if es_regla_mora(prestamo):
        pendiente = next((p for p in periodos_interes(prestamo) if p.pendiente > 0), None)
        return pendiente.fecha_limite if pendiente else prestamo.fecha_vencimiento
    if prestamo.cuotas_pagadas < prestamo.numero_cuotas:
        return fecha_cuota(prestamo, prestamo.cuotas_pagadas + 1)
    return prestamo.fecha_vencimiento


def esta_en_mora(prestamo: Prestamo, hoy: Optional[date] = None) -> bool:
    hoy = hoy or hoy_colombia()
    if cuotas_atrasadas(prestamo, hoy) > 0:
        return True
    gracia = timedelta(days=DIAS_GRACIA_MORA)
    return bool(prestamo.fecha_vencimiento and hoy - gracia > prestamo.fecha_vencimiento)


def _estado_sin_pago(prestamo: Prestamo, hoy: Optional[date] = None) -> str:
    return EstadoPrestamo.EN_MORA.value if esta_en_mora(prestamo, hoy) else EstadoPrestamo.PENDIENTE.value


def recalcular_prestamo(db: Session, prestamo: Prestamo) -> None:
    # autoflush está deshabilitado: incluir altas, ediciones y bajas pendientes.
    db.flush()
    db.refresh(prestamo, attribute_names=["abonos"])
    capital, intereses, cuotas = db.execute(select(
        func.coalesce(func.sum(AbonoPrestamo.monto_capital), Decimal("0.00")),
        func.coalesce(func.sum(AbonoPrestamo.monto_interes), Decimal("0.00")),
        func.count(AbonoPrestamo.id),
    ).where(AbonoPrestamo.prestamo_id == prestamo.id)).one()
    prestamo.saldo_pendiente = max(CERO, prestamo.monto_prestado - capital)
    if es_regla_reparto(prestamo):
        for abono in prestamo.abonos:
            abono.interes_bien_comun = parte_bien_comun(prestamo, abono.monto_interes)
    if es_regla_mora(prestamo):
        periodos = periodos_interes(prestamo)
        prestamo.total_intereses = sum((p.valor for p in periodos), CERO)
        prestamo.cuotas_pagadas = sum(1 for p in periodos if p.pagado > 0 and p.pendiente == 0)
    else:
        prestamo.cuotas_pagadas = cuotas
    if prestamo.saldo_pendiente == 0 and intereses >= prestamo.total_intereses:
        prestamo.estado = EstadoPrestamo.PAGADO.value
    else:
        # Primero se deja como no pagado para que el cálculo de atraso aplique.
        prestamo.estado = EstadoPrestamo.PENDIENTE.value
        prestamo.estado = _estado_sin_pago(prestamo)


def sincronizar_moras(db: Session, hoy: Optional[date] = None) -> int:
    """Actualiza PENDIENTE/EN_MORA de los préstamos abiertos según la fecha.

    La mora depende del paso del tiempo, no solo de los abonos, por eso se
    sincroniza antes de leer préstamos. En la regla 7 % / 10 % un mes vencido
    sin pagar pasa a la tasa de mora, así que también se actualiza el total de
    intereses. Devuelve cuántos préstamos cambiaron.
    """
    prestamos = db.execute(
        select(Prestamo).where(Prestamo.estado.notin_(ESTADOS_CERRADOS))
    ).scalars().all()
    cambios = 0
    for prestamo in prestamos:
        cambio = False
        if es_regla_mora(prestamo):
            total = sum((p.valor for p in periodos_interes(prestamo, hoy)), CERO)
            if prestamo.total_intereses != total:
                prestamo.total_intereses = total
                cambio = True
        nuevo = _estado_sin_pago(prestamo, hoy)
        if prestamo.estado != nuevo:
            prestamo.estado = nuevo
            cambio = True
        cambios += cambio
    if cambios:
        db.commit()
    return cambios


# ---------------------------------------------------------------------------
# Regla de intereses 7 % / 10 %
# ---------------------------------------------------------------------------

REGLAS_PERIODICAS = (ReglaInteres.MORA_7_10.value, ReglaInteres.REPARTO_7_3.value)


def es_regla_mora(prestamo: Prestamo) -> bool:
    """Reglas con intereses mes a mes (7 % / 10 % y 7 % socio / 3 % bien común)."""
    return getattr(prestamo, "regla_interes", None) in REGLAS_PERIODICAS


def es_regla_reparto(prestamo: Prestamo) -> bool:
    return getattr(prestamo, "regla_interes", None) == ReglaInteres.REPARTO_7_3.value


def tasa_mora_de(prestamo: Prestamo) -> Decimal:
    if es_regla_reparto(prestamo):
        # En la regla 7 % / 3 % no hay tasa de mora: siempre es el 10 %.
        return prestamo.tasa_interes
    return prestamo.tasa_mora if prestamo.tasa_mora is not None else TASA_MORA


def interes_mensual(prestamo: Prestamo, tasa: Decimal, base: Optional[Decimal] = None) -> Decimal:
    """Interés de un mes; `base` es el capital del mes (por defecto el monto prestado)."""
    capital = prestamo.monto_prestado if base is None else base
    return (capital * tasa / Decimal("100")).quantize(Decimal("0.01"))


def parte_bien_comun(prestamo: Prestamo, monto_interes: Decimal) -> Optional[Decimal]:
    """Porción del interés cobrado que va al bien común (3 de cada 10 pesos).

    Devuelve None en reglas anteriores, que conservan la clasificación por cuota.
    """
    if not es_regla_reparto(prestamo):
        return None
    tasa = prestamo.tasa_interes or TASA_REPARTO
    monto = monto_interes or CERO
    if tasa <= 0:
        return CERO
    return min(monto, (monto * TASA_BIEN_COMUN / tasa).quantize(Decimal("0.01")))


def fecha_local(valor) -> date:
    """Fecha de Colombia de un abono (los datetime se guardan en UTC)."""
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(ZONA_COLOMBIA).date()
    return valor


def destino_interes(numero_cuota: int) -> str:
    return "BIEN_COMUN" if numero_cuota >= CUOTA_BIEN_COMUN else "AHORRO_PERSONAL"


def tasa_sugerida(prestamo: Prestamo, fecha_limite: date, fecha_pago: date) -> tuple[Decimal, int, str]:
    """Tasa que corresponde según la fecha: (tasa, días de retraso, motivo)."""
    dias = (fecha_pago - fecha_limite).days
    if es_regla_reparto(prestamo):
        if dias <= 0:
            return prestamo.tasa_interes, 0, "Pago dentro del plazo (a más tardar en la fecha límite)"
        texto = "día" if dias == 1 else "días"
        return prestamo.tasa_interes, dias, f"Pago con {dias} {texto} de retraso; la tasa sigue siendo {prestamo.tasa_interes.normalize():f} %"
    if dias <= 0:
        return prestamo.tasa_interes, 0, "Pago dentro del plazo (a más tardar en la fecha límite)"
    texto = "día" if dias == 1 else "días"
    return tasa_mora_de(prestamo), dias, f"Pago con {dias} {texto} de retraso respecto a la fecha límite"


@dataclass
class PeriodoInteres:
    indice: int
    numero_cuota: int
    fecha_limite: date
    tasa: Decimal
    tasa_elegida: Optional[Decimal]
    valor: Decimal
    pagado: Decimal
    pendiente: Decimal
    vencido: bool
    destino: str
    # Capital sobre el que se calcula el interés del mes y fecha en que inicia.
    base: Decimal = CERO
    inicio: Optional[date] = None
    # Cuota agregada por la fecha del abono (posterior a la última cuota).
    nueva: bool = False

    @property
    def interes_bien_comun(self) -> Decimal:
        """Parte del interés del mes que va al bien común."""
        if self.destino == DESTINO_REPARTO:
            if self.tasa <= 0:
                return CERO
            return (self.valor * TASA_BIEN_COMUN / self.tasa).quantize(Decimal("0.01"))
        return self.valor if self.destino == "BIEN_COMUN" else CERO

    @property
    def interes_socio(self) -> Decimal:
        return self.valor - self.interes_bien_comun

    @property
    def estado(self) -> str:
        if self.pendiente == 0 and self.pagado > 0:
            return "PAGADO"
        return "EN_MORA" if self.vencido else "PENDIENTE"


def _requiere_cuota_nueva(periodos: list[PeriodoInteres], hasta: date) -> bool:
    """Un abono crea la cuota siguiente si su fecha pasa la última cuota o si todas
    las cuotas ya están pagadas (así el interés se sigue cobrando completo cada mes
    mientras se deba capital, en vez de cobrar diferencias sobre una cuota pagada)."""
    if hasta > periodos[-1].fecha_limite:
        return True
    return all(p.pagado > 0 and p.pendiente == 0 for p in periodos)


def periodos_interes(
    prestamo: Prestamo, hoy: Optional[date] = None, excluir_abono_id: Optional[int] = None,
    hasta: Optional[date] = None,
) -> list[PeriodoInteres]:
    """Intereses mes a mes de un préstamo con regla 7 % / 10 %.

    - Si el mes ya se cubrió con la tasa elegida en sus abonos, queda con esa tasa.
    - Si no está cubierto y ya pasó la fecha límite, se causa a la tasa de mora.
    - Si no está cubierto y aún está en plazo, se proyecta a la tasa normal
      (o a la elegida, si ya hubo un abono parcial).
    - Se incluyen las cuotas pactadas y las cuotas extra que ya tienen abonos.
    - Cuota nueva: si `hasta` (la fecha de un abono) es posterior a la fecha
      límite de la última cuota, o todas las cuotas ya están pagadas, y aún se
      debe capital, se agrega la cuota siguiente (última + 1) con su fecha
      límite, marcada como `nueva`.
    """
    if es_regla_reparto(prestamo):
        return _periodos_reparto(prestamo, hoy, excluir_abono_id, hasta)
    hoy = hoy or hoy_colombia()
    abonos = [a for a in (prestamo.abonos or []) if excluir_abono_id is None or a.id != excluir_abono_id]
    meses = max(prestamo.numero_cuotas, max((a.numero_cuota for a in abonos), default=0))

    pagos_capital = [(fecha_local(a.fecha_pago), a.monto_capital or CERO) for a in abonos]

    def periodo(indice: int) -> PeriodoInteres:
        inicio = sumar_meses(prestamo.fecha_prestamo, indice - 1)
        # El interés del mes se calcula sobre el capital que se debe al iniciar el mes:
        # el primer mes sobre el monto prestado; los siguientes descuentan los abonos a
        # capital hechos hasta ese día (inclusive). Así 10 % de $300.000 son $30.000.
        if indice == 1:
            base = prestamo.monto_prestado
        else:
            base = max(CERO, prestamo.monto_prestado - sum((c for f, c in pagos_capital if f <= inicio), CERO))
        limite = fecha_cuota(prestamo, indice)
        del_mes = [a for a in abonos if a.numero_cuota == indice]
        pagado = sum((a.monto_interes for a in del_mes), CERO)
        elegidas = [a.tasa_aplicada for a in del_mes if a.tasa_aplicada is not None and a.monto_interes > 0]
        elegida = max(elegidas) if elegidas else None
        vencido = limite < hoy
        if elegida is not None and pagado >= interes_mensual(prestamo, elegida, base):
            tasa = elegida
        elif vencido:
            tasa = max(elegida or CERO, tasa_mora_de(prestamo))
        else:
            tasa = elegida or prestamo.tasa_interes
        valor = interes_mensual(prestamo, tasa, base)
        return PeriodoInteres(
            indice=indice, numero_cuota=indice, fecha_limite=limite, tasa=tasa,
            tasa_elegida=elegida, valor=valor, pagado=pagado,
            pendiente=max(CERO, valor - pagado), vencido=vencido,
            destino=destino_interes(indice), base=base, inicio=inicio,
        )

    periodos = [periodo(indice) for indice in range(1, meses + 1)]
    capital_pagado = sum((a.monto_capital or CERO for a in abonos), CERO)
    if (
        hasta is not None and periodos and _requiere_cuota_nueva(periodos, hasta)
        and capital_pagado < prestamo.monto_prestado and meses < MAX_MESES_INTERES
    ):
        extra = periodo(meses + 1)
        extra.nueva = True
        periodos.append(extra)
    return periodos


def _periodos_reparto(
    prestamo: Prestamo, hoy: Optional[date] = None, excluir_abono_id: Optional[int] = None,
    hasta: Optional[date] = None,
) -> list[PeriodoInteres]:
    """Intereses mes a mes de la regla 7 % / 3 % (10 % del capital pendiente).

    - El mes N inicia N-1 meses después del desembolso y vence N meses después.
    - Su interés es el 10 % del capital pendiente al iniciar el mes: el primer
      mes sobre el monto prestado; los siguientes descuentan los abonos a capital
      hechos hasta el día en que inicia el mes (inclusive).
    - Se proyectan los meses pactados y, si queda capital, se siguen causando los
      meses que ya iniciaron aunque se haya superado el plazo, y los que ya
      tienen abonos.
    - Cuota nueva: si `hasta` (la fecha de un abono) es posterior a la fecha
      límite de la última cuota, o todas las cuotas ya están pagadas, se agrega
      la cuota siguiente (última + 1).
    - Cuando el capital llega a $0 no se causan más meses.
    """
    hoy = hoy or hoy_colombia()
    abonos = [a for a in (prestamo.abonos or []) if excluir_abono_id is None or a.id != excluir_abono_id]
    pagos_capital = [(fecha_local(a.fecha_pago), a.monto_capital or CERO) for a in abonos]
    ultima_cuota_abonada = max((a.numero_cuota for a in abonos), default=0)
    tasa = prestamo.tasa_interes

    def periodo(indice: int) -> Optional[PeriodoInteres]:
        inicio = sumar_meses(prestamo.fecha_prestamo, indice - 1)
        if indice == 1:
            base = prestamo.monto_prestado
        else:
            base = prestamo.monto_prestado - sum((c for f, c in pagos_capital if f <= inicio), CERO)
        if base <= 0:
            return None
        limite = fecha_cuota(prestamo, indice)
        pagado = sum((a.monto_interes for a in abonos if a.numero_cuota == indice), CERO)
        valor = interes_mensual(prestamo, tasa, base)
        return PeriodoInteres(
            indice=indice, numero_cuota=indice, fecha_limite=limite, tasa=tasa,
            tasa_elegida=tasa if pagado > 0 else None, valor=valor, pagado=pagado,
            pendiente=max(CERO, valor - pagado), vencido=limite < hoy,
            destino=DESTINO_REPARTO, base=base, inicio=inicio,
        )

    periodos = []
    for indice in range(1, MAX_MESES_INTERES + 1):
        inicio = sumar_meses(prestamo.fecha_prestamo, indice - 1)
        if indice > max(prestamo.numero_cuotas, ultima_cuota_abonada) and inicio > hoy:
            break
        actual = periodo(indice)
        if actual is None:
            return periodos
        periodos.append(actual)
    if hasta is not None and periodos and _requiere_cuota_nueva(periodos, hasta) and len(periodos) < MAX_MESES_INTERES:
        extra = periodo(len(periodos) + 1)
        if extra is not None:
            extra.nueva = True
            periodos.append(extra)
    return periodos


def intereses_pendientes_vencidos(prestamo: Prestamo, hoy: Optional[date] = None) -> Decimal:
    """Intereses de meses ya vencidos que siguen sin pagar."""
    if prestamo.estado in ESTADOS_CERRADOS:
        return CERO
    if es_regla_mora(prestamo):
        return sum((p.pendiente for p in periodos_interes(prestamo, hoy) if p.vencido), CERO)
    pagado = sum((a.monto_interes for a in (prestamo.abonos or [])), CERO)
    vencidas = min(cuotas_vencidas(prestamo, hoy), prestamo.numero_cuotas)
    return max(CERO, interes_mensual(prestamo, prestamo.tasa_interes) * vencidas - pagado)


@dataclass
class AbonoCalculado:
    numero_cuota: int
    monto_capital: Decimal
    monto_interes: Decimal
    tasa_aplicada: Decimal
    fecha_limite: date
    dias_retraso: int


def cuota_por_defecto(periodos: list[PeriodoInteres]) -> PeriodoInteres:
    """La cuota nueva creada por la fecha del abono; si no hay, la primera pendiente."""
    nueva = next((p for p in periodos if p.nueva), None)
    if nueva is not None:
        return nueva
    return next((p for p in periodos if p.pendiente > 0), periodos[-1])


def calcular_abono_mora(
    prestamo: Prestamo, abono_in, excluir_abono_id: Optional[int] = None, saldo_capital: Optional[Decimal] = None,
) -> AbonoCalculado:
    """Valida y completa un abono de un préstamo con regla 7 % / 10 %.

    El interés de un abono corresponde a un solo mes (numero_cuota); así
    la regla del bien común (cuota >= 4) clasifica cada peso correctamente.
    """
    from fastapi import HTTPException  # evitar dependencia web al importar modelos

    fecha_pago = abono_in.fecha_pago or hoy_colombia()
    periodos = periodos_interes(prestamo, excluir_abono_id=excluir_abono_id, hasta=fecha_pago)
    if not periodos:
        raise HTTPException(status_code=422, detail="El préstamo no tiene meses de interés")
    if es_regla_reparto(prestamo) and abono_in.tasa_aplicada is not None and abono_in.tasa_aplicada != prestamo.tasa_interes:
        raise HTTPException(status_code=422, detail=f"La tasa de este préstamo es {prestamo.tasa_interes.normalize():f} %")
    if abono_in.numero_cuota is not None:
        periodo = next((p for p in periodos if p.numero_cuota == abono_in.numero_cuota), None)
        if periodo is None:
            primero, ultimo = periodos[0].numero_cuota, periodos[-1].numero_cuota
            raise HTTPException(status_code=422, detail=f"La cuota debe estar entre #{primero} y #{ultimo}")
    else:
        periodo = cuota_por_defecto(periodos)

    sugerida, dias, _ = tasa_sugerida(prestamo, periodo.fecha_limite, fecha_pago)
    tasa = abono_in.tasa_aplicada if abono_in.tasa_aplicada is not None else sugerida
    if tasa not in (prestamo.tasa_interes, tasa_mora_de(prestamo)):
        raise HTTPException(
            status_code=422,
            detail=f"La tasa debe ser {prestamo.tasa_interes:g} % o {tasa_mora_de(prestamo):g} %",
        )
    # Tope del mes con la tasa más alta elegida (un abono previo al 10 % no baja al 7 %).
    tasa_mes = max(tasa, periodo.tasa_elegida or CERO)
    pendiente_mes = max(CERO, interes_mensual(prestamo, tasa_mes, periodo.base) - periodo.pagado)
    saldo = prestamo.saldo_pendiente if saldo_capital is None else saldo_capital

    if abono_in.monto_capital is not None:
        monto_capital = abono_in.monto_capital
        monto_interes = abono_in.monto_interes or CERO
    else:
        # Primero el interés del mes y luego el capital.
        monto_interes = min(pendiente_mes, abono_in.monto_abonado)
        monto_capital = abono_in.monto_abonado - monto_interes
    if monto_interes > pendiente_mes:
        raise HTTPException(
            status_code=422,
            detail=(
                f"El interés supera lo pendiente de la cuota #{periodo.numero_cuota} "
                f"al {tasa_mes:g} % (${pendiente_mes:,.2f}). Registra los demás meses en abonos separados."
            ),
        )
    if monto_capital > saldo:
        raise HTTPException(status_code=422, detail="El capital abonado no puede superar el saldo pendiente")
    return AbonoCalculado(
        numero_cuota=periodo.numero_cuota,
        monto_capital=monto_capital,
        monto_interes=monto_interes,
        tasa_aplicada=tasa,
        fecha_limite=periodo.fecha_limite,
        dias_retraso=dias,
    )
