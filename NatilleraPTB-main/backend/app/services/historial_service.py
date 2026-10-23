"""Servicio centralizado para el Registro y Reversión del Historial de Movimientos."""
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import inspect, select, Date, DateTime, Numeric, func

from app.models.historial import HistorialMovimiento
from app.models.usuario import Usuario
from app.models.socio import Socio
from app.models.prestamo import Prestamo, AbonoPrestamo
from app.models.actividad import Actividad
from app.models.rifa import Rifa
from app.models.reunion import Reunion
from app.models.nota import Nota
from app.models.finanzas import FinanzaSocio
from app.services.prestamos_service import recalcular_prestamo


def custom_json_serializer(obj: Any) -> Any:
    """Serializador personalizado para tipos de datos Decimal, date y datetime."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def model_to_dict(obj: Any, include_relationships: bool = True) -> Dict[str, Any]:
    """Convierte un objeto SQLAlchemy ORM a un diccionario serializable en JSON."""
    if obj is None:
        return {}
    
    result = {}
    mapper = inspect(obj.__class__)
    for column in mapper.columns:
        val = getattr(obj, column.key)
        if isinstance(val, Decimal):
            result[column.key] = str(val)
        elif isinstance(val, (datetime, date)):
            result[column.key] = val.isoformat()
        else:
            result[column.key] = val

    # Incluir relaciones hijo críticas al eliminar entidades padre
    if include_relationships:
        if isinstance(obj, Prestamo) and hasattr(obj, "abonos") and obj.abonos:
            result["abonos"] = [model_to_dict(a, include_relationships=False) for a in obj.abonos]
        elif isinstance(obj, Socio):
            result["finanzas"] = [model_to_dict(f, include_relationships=False) for f in obj.finanzas]
            result["prestamos"] = [model_to_dict(p) for p in obj.prestamos]

    return result


def _restaurar_registro(db: Session, model: Any, datos: Dict[str, Any]) -> Any:
    """Inserta una instantánea con sus fechas, sin sobrescribir IDs reutilizados."""
    if datos.get("id") is not None and db.get(model, datos["id"]) is not None:
        raise HTTPException(status_code=409, detail="El ID a restaurar ya está ocupado")
    valores = {}
    for column in inspect(model).columns:
        if column.key not in datos:
            continue
        value = datos[column.key]
        if value is not None:
            if isinstance(column.type, DateTime):
                value = datetime.fromisoformat(value)
            elif isinstance(column.type, Date):
                value = date.fromisoformat(value)
            elif isinstance(column.type, Numeric):
                value = Decimal(str(value))
        valores[column.key] = value
    obj = model(**valores)
    db.add(obj)
    # Garantizar el orden padre -> hijos incluso con autoflush=False.
    db.flush()
    return obj


def _restaurar_prestamo(db: Session, datos: Dict[str, Any]) -> Prestamo:
    prestamo = _restaurar_registro(db, Prestamo, datos)
    for abono in datos.get("abonos", []):
        _restaurar_registro(db, AbonoPrestamo, {**abono, "prestamo_id": prestamo.id})
    return prestamo


def registrar_movimiento(
    db: Session,
    modulo: str,
    tipo_accion: str,
    descripcion: str,
    entidad_tipo: str,
    entidad_id: Optional[int] = None,
    datos_previos: Optional[Any] = None,
    datos_nuevos: Optional[Any] = None,
    usuario: Optional[Usuario] = None,
    commit_now: bool = False
) -> HistorialMovimiento:
    """
    Registra un evento en la bitácora de auditoría / historial de movimientos.
    """
    prev_json = None
    if datos_previos is not None:
        if isinstance(datos_previos, (dict, list)):
            prev_json = json.dumps(datos_previos, default=custom_json_serializer, ensure_ascii=False)
        elif hasattr(datos_previos, "__tablename__"):
            prev_json = json.dumps(model_to_dict(datos_previos), default=custom_json_serializer, ensure_ascii=False)
        else:
            prev_json = str(datos_previos)

    new_json = None
    if datos_nuevos is not None:
        if isinstance(datos_nuevos, (dict, list)):
            new_json = json.dumps(datos_nuevos, default=custom_json_serializer, ensure_ascii=False)
        elif hasattr(datos_nuevos, "__tablename__"):
            new_json = json.dumps(model_to_dict(datos_nuevos), default=custom_json_serializer, ensure_ascii=False)
        else:
            new_json = str(datos_nuevos)

    usuario_id = usuario.id if usuario else None
    usuario_nombre = (usuario.nombre_completo or usuario.username) if usuario else "Sistema"

    historial = HistorialMovimiento(
        modulo=modulo,
        tipo_accion=tipo_accion,
        descripcion=descripcion,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        datos_previos=prev_json,
        datos_nuevos=new_json,
        usuario_id=usuario_id,
        usuario_nombre=usuario_nombre,
        revertido=False
    )
    db.add(historial)
    if commit_now:
        db.commit()
        db.refresh(historial)
    return historial


def revertir_movimiento(db: Session, historial_id: int, current_user: Usuario) -> Dict[str, Any]:
    """
    Ejecuta la reversión (Undo) de una acción registrada en el historial.
    Soporta la restauración completa de items borrados, revertir creaciones o restaurar estados editados.
    """
    stmt = select(HistorialMovimiento).where(HistorialMovimiento.id == historial_id).with_for_update()
    historial = db.execute(stmt).scalar_one_or_none()

    if not historial:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Movimiento con ID {historial_id} no encontrado en el historial",
        )

    if historial.revertido:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este movimiento ya fue revertido previamente",
        )

    entidad_tipo = historial.entidad_tipo
    tipo_accion = historial.tipo_accion

    models = {model.__name__: model for model in (
        Socio, Prestamo, AbonoPrestamo, FinanzaSocio, Actividad, Rifa, Reunion, Nota
    )}
    if entidad_tipo not in models or tipo_accion not in {"CREAR", "EDITAR", "ELIMINAR"}:
        raise HTTPException(status_code=409, detail="Este tipo de movimiento no admite reversión")
    target = db.execute(select(models[entidad_tipo]).where(
        models[entidad_tipo].id == historial.entidad_id
    ).with_for_update()).scalar_one_or_none()
    if tipo_accion == "ELIMINAR" and target is not None:
        raise HTTPException(status_code=409, detail="El ID a restaurar ya está ocupado")
    if tipo_accion in {"CREAR", "EDITAR"}:
        if target is None:
            raise HTTPException(status_code=409, detail="La entidad ya no existe")
        # Abonos editados tienen verificación numérica específica más abajo.
        if not (entidad_tipo == "AbonoPrestamo" and tipo_accion == "EDITAR"):
            expected = json.loads(historial.datos_nuevos or "{}")
            actual = model_to_dict(target)
            numeric_fields = {c.key for c in inspect(target.__class__).columns if isinstance(c.type, Numeric)}
            def same_value(key, value):
                if key in numeric_fields and value is not None and actual.get(key) is not None:
                    return Decimal(str(actual[key])) == Decimal(str(value))
                return actual.get(key) == value
            if not expected or any(not same_value(k, v) for k, v in expected.items() if k not in {"updated_at"}):
                raise HTTPException(status_code=409, detail="Hay cambios posteriores; revierte primero el movimiento más reciente")
            if tipo_accion == "CREAR" and isinstance(target, (Socio, Prestamo)):
                if (isinstance(target, Socio) and (target.finanzas or target.prestamos)) or (isinstance(target, Prestamo) and target.abonos):
                    raise HTTPException(status_code=409, detail="La entidad tiene movimientos dependientes")
    if entidad_tipo == "FinanzaSocio":
        data = model_to_dict(target) if target else json.loads(historial.datos_previos or "{}")
        socio = db.execute(select(Socio).where(Socio.id == data.get("socio_id")).with_for_update()).scalar_one_or_none()
        if socio is None:
            raise HTTPException(status_code=409, detail="El socio ya no existe")
        movements = db.execute(select(FinanzaSocio).where(FinanzaSocio.socio_id == socio.id)).scalars().all()
        balance = sum((m.monto if m.tipo_movimiento == "APORTE" else -m.monto if m.tipo_movimiento == "RETIRO_AHORRO" else Decimal("0") for m in movements), Decimal("0"))
        effect = Decimal(data["monto"]) * (1 if data["tipo_movimiento"] == "APORTE" else -1 if data["tipo_movimiento"] == "RETIRO_AHORRO" else 0)
        if balance + (effect if tipo_accion == "ELIMINAR" else -effect) < 0:
            raise HTTPException(status_code=409, detail="La reversión dejaría el ahorro negativo")

    # 1. REVERTIR ELIMINACIÓN (Restaurar registro exacto con sus mismos valores e ID)
    if tipo_accion == "ELIMINAR":
        if not historial.datos_previos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No hay datos previos guardados para revertir esta eliminación",
            )
        datos = json.loads(historial.datos_previos)

        if entidad_tipo == "Prestamo":
            _restaurar_prestamo(db, datos)

        elif entidad_tipo == "Socio":
            socio = _restaurar_registro(db, Socio, datos)
            for finanza in datos.get("finanzas", []):
                _restaurar_registro(db, FinanzaSocio, {**finanza, "socio_id": socio.id})
            for prestamo in datos.get("prestamos", []):
                _restaurar_prestamo(db, {**prestamo, "socio_id": socio.id})

        elif entidad_tipo == "AbonoPrestamo":
            prestamo = db.execute(select(Prestamo).where(
                Prestamo.id == datos["prestamo_id"]
            ).with_for_update()).scalar_one_or_none()
            if prestamo is None:
                raise HTTPException(status_code=409, detail="El préstamo ya no existe")
            _restaurar_registro(db, AbonoPrestamo, datos)
            recalcular_prestamo(db, prestamo)

        else:
            _restaurar_registro(db, models[entidad_tipo], datos)

    # 2. REVERTIR CREACIÓN (Eliminar la entidad recién creada)
    elif tipo_accion == "CREAR":
        entidad_id = historial.entidad_id
        if not entidad_id and historial.datos_nuevos:
            datos = json.loads(historial.datos_nuevos)
            entidad_id = datos.get("id")

        if entidad_id:
            if entidad_tipo == "Prestamo":
                obj = db.get(Prestamo, entidad_id)
                if obj: db.delete(obj)
            elif entidad_tipo == "Socio":
                obj = db.get(Socio, entidad_id)
                if obj: db.delete(obj)
            elif entidad_tipo == "AbonoPrestamo":
                obj = db.get(AbonoPrestamo, entidad_id)
                if obj:
                    prestamo = db.execute(select(Prestamo).where(
                        Prestamo.id == obj.prestamo_id
                    ).with_for_update()).scalar_one()
                    db.delete(obj)
                    recalcular_prestamo(db, prestamo)
            elif entidad_tipo == "Actividad":
                obj = db.get(Actividad, entidad_id)
                if obj: db.delete(obj)
            elif entidad_tipo == "Rifa":
                obj = db.get(Rifa, entidad_id)
                if obj: db.delete(obj)
            elif entidad_tipo == "Reunion":
                obj = db.get(Reunion, entidad_id)
                if obj: db.delete(obj)
            elif entidad_tipo == "Nota":
                obj = db.get(Nota, entidad_id)
                if obj: db.delete(obj)
            elif entidad_tipo == "FinanzaSocio":
                obj = db.get(FinanzaSocio, entidad_id)
                if obj: db.delete(obj)

    # 3. REVERTIR EDICIÓN (Restaurar campos a datos_previos)
    elif tipo_accion == "EDITAR":
        if not historial.datos_previos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No hay datos previos guardados para restaurar la edición",
            )
        datos = json.loads(historial.datos_previos)
        entidad_id = historial.entidad_id or datos.get("id")

        if entidad_id:
            if entidad_tipo == "Prestamo":
                obj = db.get(Prestamo, entidad_id)
                if obj:
                    for k, v in datos.items():
                        if k in ["monto_prestado", "tasa_interes", "total_intereses", "saldo_pendiente"]:
                            setattr(obj, k, Decimal(str(v)))
                        elif k in ["fecha_prestamo", "fecha_vencimiento"] and v:
                            setattr(obj, k, date.fromisoformat(v))
                        elif k not in ["id", "created_at", "abonos"]:
                            setattr(obj, k, v)
            elif entidad_tipo == "AbonoPrestamo":
                prestamo = db.execute(select(Prestamo).where(
                    Prestamo.id == datos["prestamo_id"]
                ).with_for_update()).scalar_one_or_none()
                obj = db.get(AbonoPrestamo, entidad_id)
                if obj is None or prestamo is None:
                    raise HTTPException(status_code=409, detail="El abono o préstamo ya no existe")
                nuevos = json.loads(historial.datos_nuevos) if historial.datos_nuevos else {}
                campos = ("monto_abonado", "monto_capital", "monto_interes", "numero_cuota")
                actual = model_to_dict(obj)
                if any(campo not in nuevos or Decimal(str(actual[campo])) != Decimal(str(nuevos[campo])) for campo in campos):
                    raise HTTPException(status_code=409, detail="El abono tiene cambios posteriores; revierte primero la edición más reciente")
                otros_capitales = db.execute(select(func.coalesce(
                    func.sum(AbonoPrestamo.monto_capital), Decimal("0.00")
                )).where(AbonoPrestamo.prestamo_id == prestamo.id,
                         AbonoPrestamo.id != obj.id)).scalar_one()
                if otros_capitales + Decimal(datos["monto_capital"]) > prestamo.monto_prestado:
                    raise HTTPException(status_code=409, detail="La reversión excedería el capital del préstamo")
                for campo in campos:
                    setattr(obj, campo, int(datos[campo]) if campo == "numero_cuota" else Decimal(datos[campo]))
                recalcular_prestamo(db, prestamo)
            elif entidad_tipo == "Socio":
                obj = db.get(Socio, entidad_id)
                if obj:
                    for k, v in datos.items():
                        if k == "aporte_mensual":
                            setattr(obj, k, Decimal(str(v)))
                        elif k not in ["id", "created_at", "finanzas", "prestamos"]:
                            setattr(obj, k, v)
            elif entidad_tipo == "Actividad":
                obj = db.get(Actividad, entidad_id)
                if obj:
                    for k, v in datos.items():
                        if k in ["inversion", "ingresos_brutos", "ganancia_neta"]:
                            setattr(obj, k, Decimal(str(v)))
                        elif k == "fecha" and v:
                            setattr(obj, k, date.fromisoformat(v))
                        elif k not in ["id", "created_at"]:
                            setattr(obj, k, v)
            elif entidad_tipo == "Rifa":
                obj = db.get(Rifa, entidad_id)
                if obj:
                    for k, v in datos.items():
                        if k in ["inversion_premios", "valor_boleta", "ganancia_por_boleta", "ganancias_totales"]:
                            setattr(obj, k, Decimal(str(v)))
                        elif k == "fecha" and v:
                            setattr(obj, k, date.fromisoformat(v))
                        elif k not in ["id", "created_at"]:
                            setattr(obj, k, v)
            elif entidad_tipo == "Reunion":
                obj = db.get(Reunion, entidad_id)
                if obj:
                    for k, v in datos.items():
                        if k == "ganancias_reunion":
                            setattr(obj, k, Decimal(str(v)))
                        elif k == "fecha" and v:
                            setattr(obj, k, date.fromisoformat(v))
                        elif k not in ["id", "created_at"]:
                            setattr(obj, k, v)
            elif entidad_tipo == "Nota":
                obj = db.get(Nota, entidad_id)
                if obj:
                    for k, v in datos.items():
                        if k == "fecha_programada":
                            setattr(obj, k, date.fromisoformat(v) if v else None)
                        elif k not in ["id", "created_at", "updated_at"]:
                            setattr(obj, k, v)

    # Marcar log original como revertido
    historial.revertido = True

    # Registrar el nuevo evento de auditoría para la Reversión
    desc_reversión = f"Reversión de {tipo_accion.lower()} en {entidad_tipo} #{historial.entidad_id or ''}: {historial.descripcion}"
    registrar_movimiento(
        db=db,
        modulo=historial.modulo,
        tipo_accion="REVERTIR",
        descripcion=desc_reversión,
        entidad_tipo=entidad_tipo,
        entidad_id=historial.entidad_id,
        datos_previos=historial.datos_nuevos,
        datos_nuevos=historial.datos_previos,
        usuario=current_user,
        commit_now=False
    )

    db.commit()
    return {"message": "Movimiento revertido exitosamente", "historial_id": historial_id}
