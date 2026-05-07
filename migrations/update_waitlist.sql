-- Migración para actualizar la tabla waitlist según ideas.md
-- Ejecutar este script en Supabase SQL Editor

-- Paso 1: Crear los ENUMs necesarios
DO $$ BEGIN
    CREATE TYPE waitlist_request_type AS ENUM ('flexible', 'specific');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE waitlist_status AS ENUM ('waiting', 'offered', 'rejected', 'no_response');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Paso 2: Agregar nuevas columnas a la tabla waitlist
-- Nota: preferred_date ya existe, lo cambiamos a nullable
ALTER TABLE waitlist 
    ALTER COLUMN preferred_date DROP NOT NULL;

ALTER TABLE waitlist 
    ADD COLUMN IF NOT EXISTS request_type waitlist_request_type NOT NULL DEFAULT 'flexible';

ALTER TABLE waitlist 
    ADD COLUMN IF NOT EXISTS preferred_time VARCHAR(5);

ALTER TABLE waitlist 
    ADD COLUMN IF NOT EXISTS preferred_stylist_id UUID REFERENCES stylists(id);

ALTER TABLE waitlist 
    ADD COLUMN IF NOT EXISTS preferred_service_id UUID REFERENCES services(id);

ALTER TABLE waitlist 
    ADD COLUMN IF NOT EXISTS rejection_count INTEGER DEFAULT 0;

ALTER TABLE waitlist 
    ADD COLUMN IF NOT EXISTS status waitlist_status DEFAULT 'waiting';

ALTER TABLE waitlist 
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

-- Paso 3: Crear índices para mejor rendimiento
CREATE INDEX IF NOT EXISTS idx_waitlist_salon_status ON waitlist(salon_id, status);
CREATE INDEX IF NOT EXISTS idx_waitlist_request_type ON waitlist(request_type);
CREATE INDEX IF NOT EXISTS idx_waitlist_created_at ON waitlist(created_at);

-- Paso 4: Crear trigger para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION update_waitlist_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_waitlist_updated_at ON waitlist;
CREATE TRIGGER trigger_update_waitlist_updated_at
    BEFORE UPDATE ON waitlist
    FOR EACH ROW
    EXECUTE FUNCTION update_waitlist_updated_at();
