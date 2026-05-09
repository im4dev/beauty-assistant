-- Migración para añadir flexibilidad a las citas
-- Ejecutar en Supabase SQL Editor

-- 1. Agregar columna is_flexible a la tabla appointments
ALTER TABLE appointments 
ADD COLUMN IF NOT EXISTS is_flexible BOOLEAN DEFAULT FALSE;

-- 2. Actualizar citas existentes (opcional)
-- Por defecto todas son FALSE, lo cual es correcto para citas ya creadas.

COMMENT ON COLUMN appointments.is_flexible IS 'Indica si el cliente aceptó un horario automático (ANY) y está abierto a adelantos';
