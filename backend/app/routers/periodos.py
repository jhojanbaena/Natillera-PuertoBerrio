"""Router de Años (/periodos): historial de años de la natillera y creación de años nuevos."""
from typing import Annotated
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_active_admin, get_current_user
from app.core.periodos import crear_nuevo_periodo, leer_periodos, resumen_periodo
from app.models.usuario import Usuario
from app.schemas.periodo import PeriodoActual, PeriodoCreate, PeriodoCreado, PeriodoResponse, PeriodosResponse

router = APIRouter(prefix="/periodos", tags=["Años"])


def _actual(db: Session) -> PeriodoActual:
    activo = db.info["periodo_activo_anio"]
    return PeriodoActual(
        anio_activo=activo,
        anio_consultado=db.info["periodo_anio"],
        solo_lectura=db.info["solo_lectura"],
    )


@router.get("/actual", response_model=PeriodoActual, summary="Año activo y año que se está consultando")
def periodo_actual(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> PeriodoActual:
    return _actual(db)


@router.get("", response_model=PeriodosResponse, summary="Todos los años de la natillera con su resumen")
def listar_periodos(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> PeriodosResponse:
    base = db.info["motor_base"]
    periodos = leer_periodos(base)
    actual = _actual(db)
    return PeriodosResponse(
        **actual.model_dump(),
        proximo_anio=max(p["anio"] for p in periodos) + 1,
        periodos=[
            PeriodoResponse(
                anio=p["anio"], activo=p["activo"], copiado_de_anio=p["copiado_de_anio"],
                socios_copiados=p["socios_copiados"], usuario_nombre=p["usuario_nombre"],
                created_at=p["created_at"], **resumen_periodo(base, p),
            )
            for p in sorted(periodos, key=lambda p: p["anio"], reverse=True)
        ],
    )


@router.post("", response_model=PeriodoCreado, status_code=status.HTTP_201_CREATED,
             summary="Crear el año siguiente (copia los socios del último año; lo demás inicia en cero)")
def crear_periodo(
    periodo_in: PeriodoCreate,
    current_user: Annotated[Usuario, Depends(get_current_active_admin)],
    db: Session = Depends(get_db),
) -> PeriodoCreado:
    usuario = current_user.nombre_completo or current_user.username
    base = db.info["motor_base"]
    # La sesión no escribe: la creación va en su propia transacción y conexión.
    db.close()
    return PeriodoCreado(**crear_nuevo_periodo(base, periodo_in.anio, usuario))
