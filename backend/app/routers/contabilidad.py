"""Router de Contabilidad (/contabilidad): arqueo del dinero de la natillera.

El dinero esperado siempre se calcula desde los registros del sistema:
    liquidez en caja (capital total - cartera prestada, igual que el Dashboard)
    - gastos generales registrados
    - liquidaciones ya pagadas a los socios
Las cuentas son las líneas editables; "GUARDAR REGISTRO" copia todo en tablas
propias, por lo que el historial no cambia al editar o borrar cuentas.
"""
from decimal import Decimal
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_active_admin, get_current_user
from app.models.contabilidad import (
    ContabilidadCuenta, ContabilidadRegistro, ContabilidadRegistroCuenta, ResultadoContabilidad,
)
from app.models.gastos import GastoGeneral
from app.models.liquidacion import LiquidacionPago
from app.models.usuario import Usuario
from app.schemas.contabilidad import (
    ContabilidadActual, CuentaCreate, CuentaResponse, DesgloseEsperado, RegistroCreate, RegistroResponse,
)
from app.services.finanzas_service import FinanzasService
from app.services.historial_service import model_to_dict, registrar_movimiento

router = APIRouter(prefix="/contabilidad", tags=["Contabilidad"])
CERO = Decimal("0.00")


def calcular_dinero_esperado(db: Session) -> DesgloseEsperado:
    capital = FinanzasService.calcular_capital_total(db)
    gastos = db.execute(select(func.coalesce(func.sum(GastoGeneral.monto), CERO))).scalar_one()
    liquidaciones = db.execute(select(func.coalesce(func.sum(LiquidacionPago.monto), CERO))).scalar_one()
    return DesgloseEsperado(
        capital_total=capital.capital_total,
        cartera_prestada=capital.total_dinero_prestado_activo,
        liquidez_sistema=capital.liquidez_disponible_caja,
        gastos_generales=gastos,
        liquidaciones_pagadas=liquidaciones,
        dinero_esperado=capital.liquidez_disponible_caja - gastos - liquidaciones,
    )


def resultado_de(diferencia: Decimal) -> str:
    if diferencia == 0:
        return ResultadoContabilidad.CUADRADA
    return ResultadoContabilidad.FALTANTE if diferencia < 0 else ResultadoContabilidad.SOBRANTE


def _cuentas(db: Session) -> List[ContabilidadCuenta]:
    return db.execute(select(ContabilidadCuenta).order_by(ContabilidadCuenta.id.asc())).scalars().all()


def _cuenta(db: Session, cuenta_id: int) -> ContabilidadCuenta:
    cuenta = db.get(ContabilidadCuenta, cuenta_id)
    if cuenta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Cuenta con ID {cuenta_id} no encontrada")
    return cuenta


@router.get("", response_model=ContabilidadActual, summary="Dinero esperado vs. dinero registrado en cuentas")
def contabilidad_actual(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ContabilidadActual:
    desglose = calcular_dinero_esperado(db)
    cuentas = _cuentas(db)
    total = sum((c.valor for c in cuentas), CERO)
    diferencia = total - desglose.dinero_esperado
    return ContabilidadActual(
        dinero_esperado=desglose.dinero_esperado,
        desglose=desglose,
        cuentas=cuentas,
        total_cuentas=total,
        diferencia=diferencia,
        resultado=resultado_de(diferencia),
    )


@router.post("/cuentas", response_model=CuentaResponse, status_code=status.HTTP_201_CREATED, summary="Agregar una cuenta")
def crear_cuenta(
    cuenta_in: CuentaCreate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db),
) -> ContabilidadCuenta:
    cuenta = ContabilidadCuenta(nombre=cuenta_in.nombre, valor=cuenta_in.valor)
    db.add(cuenta)
    db.flush()
    registrar_movimiento(
        db=db, modulo="Contabilidad", tipo_accion="CREAR",
        descripcion=f"Cuenta '{cuenta.nombre}' agregada con ${cuenta.valor:,.2f}",
        entidad_tipo="ContabilidadCuenta", entidad_id=cuenta.id, datos_nuevos=cuenta, usuario=current_user,
    )
    db.commit()
    db.refresh(cuenta)
    return cuenta


@router.put("/cuentas/{cuenta_id}", response_model=CuentaResponse, summary="Editar una cuenta")
def editar_cuenta(
    cuenta_id: int,
    cuenta_in: CuentaCreate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db),
) -> ContabilidadCuenta:
    cuenta = _cuenta(db, cuenta_id)
    previos = model_to_dict(cuenta)
    cuenta.nombre = cuenta_in.nombre
    cuenta.valor = cuenta_in.valor
    db.flush()
    registrar_movimiento(
        db=db, modulo="Contabilidad", tipo_accion="EDITAR",
        descripcion=f"Cuenta '{cuenta.nombre}' actualizada a ${cuenta.valor:,.2f}",
        entidad_tipo="ContabilidadCuenta", entidad_id=cuenta.id, datos_previos=previos, datos_nuevos=cuenta,
        usuario=current_user,
    )
    db.commit()
    db.refresh(cuenta)
    return cuenta


@router.delete("/cuentas/{cuenta_id}", summary="Eliminar una cuenta (no afecta los registros guardados)")
def eliminar_cuenta(
    cuenta_id: int,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db),
):
    cuenta = _cuenta(db, cuenta_id)
    registrar_movimiento(
        db=db, modulo="Contabilidad", tipo_accion="ELIMINAR",
        descripcion=f"Cuenta '{cuenta.nombre}' (${cuenta.valor:,.2f}) eliminada",
        entidad_tipo="ContabilidadCuenta", entidad_id=cuenta.id, datos_previos=cuenta, usuario=current_user,
    )
    db.delete(cuenta)
    db.commit()
    return {"message": "Cuenta eliminada", "cuenta_id": cuenta_id}


@router.get("/registros", response_model=List[RegistroResponse], summary="Historial de registros contables")
def listar_registros(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> List[ContabilidadRegistro]:
    return db.execute(
        select(ContabilidadRegistro).order_by(ContabilidadRegistro.fecha_registro.desc(), ContabilidadRegistro.id.desc())
    ).scalars().all()


@router.get("/registros/{registro_id}", response_model=RegistroResponse, summary="Detalle de un registro contable")
def obtener_registro(
    registro_id: int,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ContabilidadRegistro:
    registro = db.get(ContabilidadRegistro, registro_id)
    if registro is None:
        raise HTTPException(status_code=404, detail=f"Registro con ID {registro_id} no encontrado")
    return registro


@router.post("/registros", response_model=RegistroResponse, status_code=status.HTTP_201_CREATED,
             summary="GUARDAR REGISTRO: copia el estado actual de la contabilidad")
def guardar_registro(
    registro_in: RegistroCreate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db),
) -> ContabilidadRegistro:
    """Toma las cuentas guardadas y el dinero esperado en este momento (calculado en el
    servidor) y los copia en un registro que ya no cambia."""
    desglose = calcular_dinero_esperado(db)
    cuentas = _cuentas(db)
    if not cuentas:
        raise HTTPException(status_code=422, detail="Agrega al menos una cuenta antes de guardar el registro")
    total = sum((c.valor for c in cuentas), CERO)
    diferencia = total - desglose.dinero_esperado
    registro = ContabilidadRegistro(
        dinero_esperado=desglose.dinero_esperado,
        total_cuentas=total,
        diferencia=diferencia,
        resultado=resultado_de(diferencia),
        desglose_esperado={k: str(v) for k, v in desglose.model_dump().items()},
        observacion=(registro_in.observacion or "").strip() or None,
        usuario_nombre=(current_user.nombre_completo or current_user.username),
        cuentas=[
            ContabilidadRegistroCuenta(orden=i, nombre=c.nombre, valor=c.valor)
            for i, c in enumerate(cuentas, start=1)
        ],
    )
    db.add(registro)
    db.flush()
    registrar_movimiento(
        db=db, modulo="Contabilidad", tipo_accion="REGISTRAR",
        descripcion=(
            f"Registro contable #{registro.id}: esperado ${registro.dinero_esperado:,.2f}, "
            f"en cuentas ${registro.total_cuentas:,.2f} ({registro.resultado.lower()})"
        ),
        entidad_tipo="ContabilidadRegistro", entidad_id=registro.id,
        datos_nuevos={
            **model_to_dict(registro, include_relationships=False),
            "cuentas": [{"nombre": c.nombre, "valor": str(c.valor)} for c in registro.cuentas],
        },
        usuario=current_user,
    )
    db.commit()
    db.refresh(registro)
    return registro
