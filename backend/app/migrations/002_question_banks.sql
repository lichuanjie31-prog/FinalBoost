ALTER TABLE files ADD COLUMN sha256 TEXT;
ALTER TABLE files ADD COLUMN purpose TEXT NOT NULL DEFAULT 'general';

CREATE TABLE subjects (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 normalized_name TEXT NOT NULL,
 scope TEXT NOT NULL CHECK(scope IN ('system','private')),
 owner_user_id TEXT REFERENCES users(id),
 created_at REAL NOT NULL,
 CHECK(
   (scope='system' AND owner_user_id IS NULL) OR
   (scope='private' AND owner_user_id IS NOT NULL)
 )
);
CREATE UNIQUE INDEX subjects_system_name
 ON subjects(normalized_name) WHERE scope='system';
CREATE UNIQUE INDEX subjects_private_owner_name
 ON subjects(owner_user_id,normalized_name) WHERE scope='private';
CREATE INDEX subjects_owner_search
 ON subjects(owner_user_id,scope,normalized_name,id);

CREATE TABLE papers (
 id TEXT PRIMARY KEY,
 owner_user_id TEXT NOT NULL REFERENCES users(id),
 subject_id TEXT NOT NULL REFERENCES subjects(id),
 name TEXT NOT NULL,
 college TEXT NOT NULL,
 year INTEGER NOT NULL CHECK(year BETWEEN 1900 AND 2100),
 semester TEXT NOT NULL,
 visibility TEXT NOT NULL CHECK(visibility IN ('private','public')),
 publication_status TEXT CHECK(publication_status IN ('draft','published','unpublished')),
 file_id TEXT NOT NULL UNIQUE REFERENCES files(id),
 source_public_paper_id TEXT REFERENCES papers(id),
 created_at REAL NOT NULL,
 published_at REAL,
 updated_at REAL NOT NULL,
 CHECK(
   (visibility='private' AND publication_status IS NULL) OR
   (visibility='public' AND publication_status IS NOT NULL)
 ),
 CHECK(source_public_paper_id IS NULL OR visibility='private')
);
CREATE UNIQUE INDEX papers_owner_public_source
 ON papers(owner_user_id,source_public_paper_id)
 WHERE source_public_paper_id IS NOT NULL;
CREATE INDEX papers_private_list
 ON papers(owner_user_id,visibility,created_at DESC,id DESC);
CREATE INDEX papers_admin_list
 ON papers(owner_user_id,visibility,publication_status,created_at DESC,id DESC);
CREATE INDEX papers_public_list
 ON papers(visibility,publication_status,published_at DESC,id DESC);
CREATE INDEX papers_subject_filter
 ON papers(subject_id,visibility,created_at DESC,id DESC);
