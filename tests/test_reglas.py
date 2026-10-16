"""Pruebas de las reglas de negocio con casos válidos e inválidos.
Ejecutar:  python -m unittest discover -s tests -v"""
import copy
import unittest
from datetime import datetime, timedelta

from campus import config, reglas

CFG = config.cargar()
LUNES = datetime(2026, 10, 19, 8, 0)
SPUTNIK = {"id": "E02", "nombre": "Sputnik", "aforo": 38, "estado": "disponible", "inhabilitacion": None}
AZUL = {"id": "E08", "nombre": "Azul", "aforo": 10, "estado": "disponible", "inhabilitacion": None}


def reserva(ini, fin, estado="confirmada"):
    return {"id": "X", "inicio": ini.isoformat(), "fin": fin.isoformat(), "estado": estado}


class TestEspacios(unittest.TestCase):
    def test_r1_solapamiento(self):
        existente = [reserva(LUNES, LUNES + timedelta(hours=2))]
        self.assertTrue(reglas.r1_solapamiento(LUNES + timedelta(hours=1), LUNES + timedelta(hours=3), existente, CFG))
        # Intervalos semiabiertos: 8–10 y 10–12 no chocan
        self.assertEqual(reglas.r1_solapamiento(LUNES + timedelta(hours=2), LUNES + timedelta(hours=4), existente, CFG), [])

    def test_r2_aforo(self):
        self.assertEqual(reglas.r2_aforo(38, SPUTNIK, CFG), [])
        self.assertTrue(reglas.r2_aforo(39, SPUTNIK, CFG))
        self.assertTrue(reglas.r2_aforo(0, SPUTNIK, CFG))

    def test_r3_inhabilitado(self):
        self.assertTrue(reglas.r3_espacio_habilitado({**SPUTNIK, "estado": "inhabilitado", "inhabilitacion": "directa"}))

    def test_r0_horario(self):
        ahora = LUNES - timedelta(days=1)
        self.assertEqual(reglas.r0_intervalo(LUNES, LUNES + timedelta(hours=2), CFG, ahora), [])
        self.assertTrue(reglas.r0_intervalo(LUNES.replace(hour=21), LUNES.replace(hour=23), CFG, ahora))
        self.assertTrue(reglas.r0_intervalo(LUNES, LUNES + timedelta(minutes=45), CFG, ahora))

    def test_r8_ocupacion_minima_solo_salas_grandes(self):
        self.assertTrue(reglas.r8_ocupacion_minima(5, SPUTNIK, CFG))       # mínimo 12
        self.assertEqual(reglas.r8_ocupacion_minima(12, SPUTNIK, CFG), [])
        self.assertEqual(reglas.r8_ocupacion_minima(1, AZUL, CFG), [])     # sala pequeña

    def test_umbral_pcs(self):
        self.assertEqual(reglas.umbral_pcs(38, CFG), 20)
        self.assertEqual(reglas.umbral_pcs(32, CFG), 17)
        self.assertEqual(reglas.umbral_pcs(20, CFG), 11)


class TestRecursos(unittest.TestCase):
    def test_r4_limite_global(self):
        activos = [{"recurso_id": "R1", "pool": "audio", "fin_esperado": (LUNES + timedelta(hours=1)).isoformat()}] * 2
        self.assertTrue(reglas.r4_limite_prestamos(activos, "audio", CFG, LUNES))
        self.assertEqual(reglas.r4_limite_prestamos(activos[:1], "audio", CFG, LUNES), [])

    def test_r4_interruptor_por_pool(self):
        cfg = copy.deepcopy(CFG)
        cfg["limites"]["por_pool"] = True
        uno = [{"recurso_id": "R1", "pool": "computo_portatil", "fin_esperado": (LUNES + timedelta(hours=1)).isoformat()}]
        self.assertIn("pool", reglas.r4_limite_prestamos(uno, "computo_portatil", cfg, LUNES)[0])
        self.assertEqual(reglas.r4_limite_prestamos(uno, "audio", cfg, LUNES), [])

    def test_r4_vencido_bloquea(self):
        vencido = [{"recurso_id": "R1", "pool": "audio", "fin_esperado": (LUNES - timedelta(hours=1)).isoformat()}]
        self.assertIn("vencido", reglas.r4_limite_prestamos(vencido, "audio", CFG, LUNES)[0])

    def test_r5_transiciones(self):
        self.assertEqual(reglas.r5_transicion("prestado", "danado", CFG), [])
        self.assertTrue(reglas.r5_transicion("danado", "disponible", CFG))


class TestIncidencias(unittest.TestCase):
    def test_r6_efecto_segun_prioridad(self):
        self.assertEqual(reglas.r6_efecto("invalida", "critica", CFG), "inhabilitar")
        self.assertEqual(reglas.r6_efecto("invalida", "media", CFG), "aviso")
        self.assertEqual(reglas.r6_efecto("invalida", "baja", CFG), "ninguno")
        self.assertEqual(reglas.r6_efecto("no_afecta", "critica", CFG), "ninguno")

    def test_r7_automatica(self):
        self.assertTrue(reglas.r7_automatica("critica", 0.9, True, CFG)[0])
        self.assertFalse(reglas.r7_automatica("critica", 0.5, True, CFG)[0])
        self.assertFalse(reglas.r7_automatica("critica", 0.9, False, CFG)[0])
        self.assertFalse(reglas.r7_automatica("alta", 0.9, True, CFG)[0])

    def test_r7_ventana_de_vinculo(self):
        r = reserva(LUNES, LUNES + timedelta(hours=2))
        self.assertTrue(reglas.vinculo_reserva(r, CFG, LUNES + timedelta(hours=1)))       # durante
        self.assertTrue(reglas.vinculo_reserva(r, CFG, LUNES + timedelta(hours=2, minutes=59)))  # POST
        self.assertFalse(reglas.vinculo_reserva(r, CFG, LUNES + timedelta(hours=3, minutes=1)))
        self.assertFalse(reglas.vinculo_reserva(r, CFG, LUNES - timedelta(minutes=10)))   # sin ventana previa
        self.assertFalse(reglas.vinculo_reserva(reserva(LUNES, LUNES + timedelta(hours=2), "cancelada"), CFG, LUNES))


class TestConfiguracion(unittest.TestCase):
    def test_config_incoherente_se_detecta(self):
        cfg = copy.deepcopy(CFG)
        cfg["reservas"]["duracion_min"] = 45
        cfg["incidencias"]["prioridad_que_inhabilita"] = "urgente"
        errores = config.validar(cfg)
        self.assertTrue(any("múltiplo" in e for e in errores))
        self.assertTrue(any("prioridad_que_inhabilita" in e for e in errores))


if __name__ == "__main__":
    unittest.main()
