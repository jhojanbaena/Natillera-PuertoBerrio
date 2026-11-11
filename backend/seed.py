"""Script de Semillero de Datos (Seed) para el Sistema de Gestión de Natillera.
Crea usuarios, socios, movimientos de ahorro, préstamos, abonos, actividades, rifas, reuniones y notas.
"""
from script_support import require_schema, run_command


def run_seed():
    from datetime import date, timedelta
    from decimal import Decimal
    from sqlalchemy.engine import make_url
    from app.core.config import settings
    from app.core.database import SessionLocal, Base
    from app.core.security import get_password_hash
    from app.models import (
        Usuario,
        Socio,
        FinanzaSocio,
        TipoMovimientoFinanciero,
        Prestamo,
        AbonoPrestamo,
        EstadoPrestamo,
        Actividad,
        Rifa,
        TipoRifa,
        Reunion,
        Nota,
    )

    if settings.ENVIRONMENT == "production" or make_url(settings.DATABASE_URL).host not in {"localhost", "127.0.0.1"}:
        raise SystemExit("El semillero con credenciales de demostración solo se permite en PostgreSQL local")
    with SessionLocal.begin() as db:
        print("Iniciando semillero de datos...")

        # La migración de esquema es explícita y debe ejecutarse antes.
        require_schema(db.connection(), Base.metadata)

        # 2. Usuario Administrador por defecto
        admin = db.query(Usuario).filter(Usuario.username == "admin").first()
        if not admin:
            admin = Usuario(
                username="admin",
                password_hash=get_password_hash("12345678"),
                nombre_completo="Administrador General",
                is_admin=True,
                is_active=True,
            )
            db.add(admin)
            print(" -> Usuario creado: admin / 12345678")

        # 3. Socios representativos
        socios_data = [
            {"cedula": "10010001", "nombre": "Carlos Alberto Restrepo", "telefono": "3014567890", "residencia": "Cra 45 # 12-30", "aporte": "150000.00"},
            {"cedula": "10010002", "nombre": "Diana Marcela Osorio", "telefono": "3127894561", "residencia": "Calle 67 # 89-10", "aporte": "200000.00"},
            {"cedula": "10010003", "nombre": "Fernando Jose Mejia", "telefono": "3156781234", "residencia": "Av. Los Alamos # 23-45", "aporte": "100000.00"},
            {"cedula": "10010004", "nombre": "Gloria Patricia Ramirez", "telefono": "3209876543", "residencia": "Transversal 5 # 18-90", "aporte": "250000.00"},
            {"cedula": "10010005", "nombre": "Hernan Dario Betancur", "telefono": "3112345678", "residencia": "Diagonal 40 # 10-05", "aporte": "120000.00"},
        ]

        socios_creados = []
        for s in socios_data:
            socio_existente = db.query(Socio).filter(Socio.cedula == s["cedula"]).first()
            if not socio_existente:
                socio = Socio(
                    cedula=s["cedula"],
                    nombre=s["nombre"],
                    telefono=s["telefono"],
                    residencia=s["residencia"],
                    aporte_mensual=Decimal(s["aporte"]),
                    is_active=True,
                )
                db.add(socio)
                socios_creados.append(socio)
            else:
                socios_creados.append(socio_existente)

        db.flush()
        for sc in socios_creados:
            db.refresh(sc)
        print(f" -> {len(socios_creados)} socios verificados/registrados.")

        # 4. Transacciones financieras de Ahorros y Multas
        if db.query(FinanzaSocio).count() < 10:
            for socio in socios_creados:
                # 2 aportes por cada socio
                db.add(FinanzaSocio(
                    socio_id=socio.id,
                    tipo_movimiento=TipoMovimientoFinanciero.APORTE.value,
                    monto=socio.aporte_mensual,
                    descripcion="Aporte ordinario mensual ciclo 1"
                ))
                db.add(FinanzaSocio(
                    socio_id=socio.id,
                    tipo_movimiento=TipoMovimientoFinanciero.APORTE.value,
                    monto=socio.aporte_mensual,
                    descripcion="Aporte ordinario mensual ciclo 2"
                ))
            # Registrar una multa y un pago de multa
            db.add(FinanzaSocio(
                socio_id=socios_creados[0].id,
                tipo_movimiento=TipoMovimientoFinanciero.MULTA.value,
                monto=Decimal("15000.00"),
                descripcion="Inasistencia a reunión del comité de festejos"
            ))
            db.add(FinanzaSocio(
                socio_id=socios_creados[1].id,
                tipo_movimiento=TipoMovimientoFinanciero.PAGO_MULTA.value,
                monto=Decimal("10000.00"),
                descripcion="Pago de multa por retraso en entrega de boletas"
            ))
            db.flush()
            print(" -> Transacciones financieras iniciales generadas.")

        # 5. Préstamos y abonos de cuota
        if db.query(Prestamo).count() < 2:
            # Préstamo 1: En curso para socio 1
            p1 = Prestamo(
                socio_id=socios_creados[0].id,
                monto_prestado=Decimal("600000.00"),
                tasa_interes=Decimal("5.0"),
                total_intereses=Decimal("30000.00"),
                saldo_pendiente=Decimal("450000.00"),
                numero_cuotas=4,
                cuotas_pagadas=1,
                estado=EstadoPrestamo.PENDIENTE.value,
                fecha_prestamo=date.today() - timedelta(days=30),
                fecha_vencimiento=date.today() + timedelta(days=90),
            )
            db.add(p1)
            db.flush()
            db.refresh(p1)

            db.add(AbonoPrestamo(
                prestamo_id=p1.id,
                monto_abonado=Decimal("180000.00"),
                monto_capital=Decimal("150000.00"),
                monto_interes=Decimal("30000.00"),
                numero_cuota=1,
            ))

            # Préstamo 2: Para socio 2
            p2 = Prestamo(
                socio_id=socios_creados[1].id,
                monto_prestado=Decimal("400000.00"),
                tasa_interes=Decimal("4.0"),
                total_intereses=Decimal("16000.00"),
                saldo_pendiente=Decimal("400000.00"),
                numero_cuotas=2,
                cuotas_pagadas=0,
                estado=EstadoPrestamo.PENDIENTE.value,
                fecha_prestamo=date.today() - timedelta(days=5),
                fecha_vencimiento=date.today() + timedelta(days=55),
            )
            db.add(p2)
            db.flush()
            print(" -> Préstamos y abonos iniciales generados.")

        # 6. Actividades comunitarias
        if db.query(Actividad).count() < 2:
            db.add(Actividad(
                nombre="Almuerzo Comunitario Pro-Aguinaldos",
                grupo_encargado="Comité Social",
                fecha=date.today() + timedelta(days=12),
                inversion=Decimal("120000.00"),
                ingresos_brutos=Decimal("380000.00"),
                ganancia_neta=Decimal("260000.00"),
                descripcion="Venta de sancocho y postres en el salón comunal"
            ))
            db.add(Actividad(
                nombre="Bingo Navideño de Integración",
                grupo_encargado="Comité Deportivo",
                fecha=date.today() + timedelta(days=25),
                inversion=Decimal("80000.00"),
                ingresos_brutos=Decimal("290000.00"),
                ganancia_neta=Decimal("210000.00"),
                descripcion="Bingo familiar con premios donados por el comercio local"
            ))
            db.flush()
            print(" -> Actividades comunitarias generadas.")

        # 7. Rifas
        if db.query(Rifa).count() < 2:
            db.add(Rifa(
                nombre="Rifa Nevera No Frost 300L",
                tipo=TipoRifa.GRANDE.value,
                fecha=date.today() + timedelta(days=20),
                inversion_premios=Decimal("800000.00"),
                valor_boleta=Decimal("20000.00"),
                total_boletas=100,
                boletas_vendidas=95,
                ganancia_por_boleta=Decimal("11578.95"),
                ganancias_totales=Decimal("1100000.00"),
                descripcion="Sorteo oficial con el premio mayor de la Lotería de Medellín"
            ))
            db.add(Rifa(
                nombre="Rifa Interna Canasta de Licores",
                tipo=TipoRifa.INTERNA.value,
                fecha=date.today() + timedelta(days=8),
                inversion_premios=Decimal("150000.00"),
                valor_boleta=Decimal("10000.00"),
                total_boletas=50,
                boletas_vendidas=50,
                ganancia_por_boleta=Decimal("7000.00"),
                ganancias_totales=Decimal("350000.00"),
                descripcion="Rifa rápida entre socios durante la asamblea ordinaria"
            ))
            db.flush()
            print(" -> Rifas comunitarias generadas.")

        # 8. Reuniones
        if db.query(Reunion).count() < 2:
            db.add(Reunion(
                fecha=date.today() + timedelta(days=7),
                hora="19:00",
                lugar="Salón Comunal Los Sauces",
                tema="Asamblea Mensual de Seguimiento y Entrega de Talonarios",
                compromisos="Llevar registro de firmas y recoger aportes",
                asistentes_requeridos="Todos los socios activos",
                ganancias_reunion=Decimal("45000.00")
            ))
            db.add(Reunion(
                fecha=date.today() - timedelta(days=21),
                hora="18:30",
                lugar="Casa de doña Gloria",
                tema="Revisión de solicitudes de crédito de emergencia",
                compromisos="Aprobar préstamo para socio Carlos Restrepo",
                asistentes_requeridos="Junta directiva",
                ganancias_reunion=Decimal("0.00")
            ))
            db.flush()
            print(" -> Reuniones agendadas.")

        # 9. Notas
        if db.query(Nota).count() < 2:
            db.add(Nota(
                titulo="Cuenta Bancaria para Transferencias",
                contenido="Se recuerda que los pagos por transferencia deben hacerse a la cuenta de ahorros del fondo e incluir el número de cédula en el comprobante."
            ))
            db.add(Nota(
                titulo="Fecha límite de entrega de rifas",
                contenido="Todos los talonarios de la rifa de la nevera deben entregarse liquidados a más tardar 3 días antes de la fecha del sorteo."
            ))
            db.flush()
            print(" -> Notas de bitácora creadas.")

    print("Semillero completado con éxito! Base de datos lista.")


if __name__ == "__main__":
    raise SystemExit(run_command(run_seed))
