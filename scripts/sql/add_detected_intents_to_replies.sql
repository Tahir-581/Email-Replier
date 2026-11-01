-- Run in pgAdmin (or psql): database = email_replier (see EMAIL_DB in .env).
-- On a fresh DB, create `replies` first; on existing DB, ALTER is enough.

CREATE TABLE IF NOT EXISTS replies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id VARCHAR(255) NOT NULL,
    thread_id VARCHAR(255),
    from_addr VARCHAR(255),
    to_addr VARCHAR(255),
    subject TEXT,
    body TEXT,
    intent_label VARCHAR(255),
    profile_type VARCHAR(100),
    sender_name VARCHAR(255),
    detected_intents JSONB,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_replies_email_id ON replies (email_id);
CREATE INDEX IF NOT EXISTS ix_replies_id ON replies (id);

ALTER TABLE replies ADD COLUMN IF NOT EXISTS detected_intents JSONB;

-- Optional: confirm column exists
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'replies' AND column_name = 'detected_intents';
