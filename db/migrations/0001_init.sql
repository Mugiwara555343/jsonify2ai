CREATE TABLE documents (
  id UUID PRIMARY KEY,
  filename TEXT NOT NULL,
  kind TEXT CHECK (kind IN ('text','image','pdf','audio')) NOT NULL,
  size_bytes BIGINT,
  mime TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE chunks (
  id UUID PRIMARY KEY,
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  idx INT NOT NULL,
  text TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE images (
  id UUID PRIMARY KEY,
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  caption TEXT,
  tags TEXT[],
  created_at TIMESTAMPTZ DEFAULT now()
);
