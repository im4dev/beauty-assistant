-- Migración para agregar campos de recordatorios a la tabla appointments
-- Ejecutar este script en Supabase SQL Editor

-- Agregar campos de recordatorios
ALTER TABLE appointments 
    ADD COLUMN IF NOT EXISTS reminder_24h_sent BOOLEAN DEFAULT FALSE;

ALTER TABLE appointments 
    ADD COLUMN IF NOT EXISTS reminder_1h_sent BOOLEAN DEFAULT FALSE;

-- Crear índices para mejor rendimiento en consultas de scheduler
CREATE INDEX IF NOT EXISTS idx_appointments_status_start_time ON appointments(status, start_time);
CREATE INDEX IF NOT EXISTS idx_appointments_reminders ON appointments(reminder_24h_sent, reminder_1h_sent);
