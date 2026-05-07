# Suite de Tests - Beauty Assistant

## Estructura

```
tests/
├── __init__.py
├── conftest.py           # Fixtures y configuración compartida
├── test_appointments.py  # Tests unitarios de appointments/
├── test_flows.py         # Tests de integración de flujos completos
├── test_edge_cases.py    # Tests de casos edge y robustez
├── test_llm_logic.py     # Tests de lógica del LLM con API real
└── manual_test.py        # Tests manuales con DeepSeek API real
```

## Instalación

```bash
pip install -r requirements-test.txt
```

## Ejecutar Tests

### Todos los tests (unitarios e integración)
```bash
pytest tests/ -v
```

### Solo tests unitarios
```bash
pytest tests/test_appointments.py -v
```

### Solo tests de integración
```bash
pytest tests/test_flows.py -v
```

### Solo casos edge
```bash
pytest tests/test_edge_cases.py -v
```

### Test manual con DeepSeek real
```bash
python tests/manual_test.py
```

O con pytest:
```bash
pytest tests/manual_test.py -v -s
```
Tests de lógica del LLM (recomendado)
```bash
python tests/test_llm_logic.py
```

O con pytest:
```bash
pytest tests/test_llm_y `test_llm_logic.py` logic.py -v -s
```

Estos tests prueban:
- Detección de intenciones del LLM
- Extracción de entidades
- Generación de respuestas
- Integración con Orchestrator
- Conciencia del contexto
- Manejo de errores
- Multi-lenguaje

### 
### Con coverage
```bash
pytest tests/ --cov=. --cov-report=html
```

## Configuración Requerida

Para `manual_test.py` necesitas:
- `DEEPSEEK_API_KEY` en tu archivo `.env`

## Notas Importantes

1. **Tests independientes**: Cada test crea su propio estado en BD en memoria
2. **SQLite in-memory**: Los tests usan SQLite en lugar de PostgreSQL para velocidad
3. **Modelos simplificados**: `conftest.py` tiene modelos simplificados para testing
4. **Tests determinísticos**: Los tests unitarios no dependen del LLM real
5. **Manual test**: `manual_test.py` usa la API real de DeepSeek y requiere configuración

## Troubleshooting

### Error: ModuleNotFoundError
Asegúrate de estar en el directorio raíz del proyecto:
```bash
cd /home/experience/Documents/GitHub/beauty-assistant
pytest tests/ -v
```

### Error: DEEPSEEK_API_KEY not found
Para `manual_test.py`, agrega a tu `.env`:
```
DEEPSEEK_API_KEY=tu_clave_aqui
```

### Tests fallan por timezone
Los tests usan `America/New_York` como timezone por defecto. Ajusta en `conftest.py` si necesitas otro.
