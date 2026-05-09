-- Migración para notificaciones a estilistas
-- Ejecutar en Supabase SQL Editor

-- 1. Agregar columna phone_number a la tabla stylists
ALTER TABLE stylists 
ADD COLUMN IF NOT EXISTS phone_number VARCHAR(50);

-- 2. Agregar columna reminder_stylist_30min_sent a la tabla appointments
ALTER TABLE appointments 
ADD COLUMN IF NOT EXISTS reminder_stylist_30min_sent BOOLEAN DEFAULT FALSE;

-- 3. Crear índice para mejorar el rendimiento del scheduler
CREATE INDEX IF NOT EXISTS idx_appointments_stylist_reminder 
ON appointments(reminder_stylist_30min_sent) 
WHERE status = 'scheduled';

COMMENT ON COLUMN stylists.phone_number IS 'Número de WhatsApp del estilista para notificaciones';
COMMENT ON COLUMN appointments.reminder_stylist_30min_sent IS 'Flag para evitar duplicidad en el recordatorio de 30 min al estilista';
