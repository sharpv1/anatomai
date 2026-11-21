"""Read-only content schema and quarantined legacy snapshot.

DDL below is frozen at creation; this revision never imports mutable app models.
"""

# ruff: noqa: E501 -- frozen generated PostgreSQL DDL and seed statements
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0003_content"
down_revision = "0002_identity"
branch_labels = None
depends_on = None

SCHEMA_SQL = (
    """
CREATE TABLE disciplines (
	id UUID NOT NULL, 
	slug VARCHAR(128) NOT NULL, 
	title VARCHAR(512) NOT NULL, 
	normalized_search_text TEXT DEFAULT '' NOT NULL, 
	icon_key VARCHAR(64) NOT NULL, 
	color_token VARCHAR(16) NOT NULL, 
	position INTEGER DEFAULT '0' NOT NULL, 
	status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
	CONSTRAINT pk_disciplines PRIMARY KEY (id), 
	CONSTRAINT ck_disciplines_status CHECK (status IN ('draft', 'published', 'withdrawn')), 
	CONSTRAINT ck_disciplines_position CHECK (position >= 0), 
	CONSTRAINT ck_disciplines_color CHECK (color_token IN ('blue','mint','violet','orange')), 
	CONSTRAINT uq_disciplines_slug UNIQUE (slug)
)

""",
    """CREATE INDEX ix_disciplines_status_position_id ON disciplines (status, position, id)""",
    """
CREATE TABLE access_policies (
	id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	requirement VARCHAR(32) NOT NULL, 
	status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
	CONSTRAINT pk_access_policies PRIMARY KEY (id), 
	CONSTRAINT ck_access_policies_status CHECK (status IN ('draft', 'published', 'withdrawn')), 
	CONSTRAINT ck_access_policies_requirement CHECK (requirement IN ('authenticated','unavailable')), 
	CONSTRAINT uq_access_policies_code UNIQUE (code)
)

""",
    """
CREATE TABLE assets (
	id UUID NOT NULL, 
	storage_key VARCHAR(256) NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	media_type VARCHAR(128) NOT NULL, 
	byte_size BIGINT NOT NULL, 
	status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
	created_by UUID, 
	CONSTRAINT pk_assets PRIMARY KEY (id), 
	CONSTRAINT ck_assets_status CHECK (status IN ('draft', 'published', 'withdrawn')), 
	CONSTRAINT ck_assets_size CHECK (byte_size > 0), 
	CONSTRAINT ck_assets_hash CHECK (sha256 ~ '^[0-9a-f]{64}$'), 
	CONSTRAINT uq_assets_storage_key UNIQUE (storage_key), 
	CONSTRAINT fk_assets_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT
)

""",
    """
CREATE TABLE questions (
	id UUID NOT NULL, 
	external_source VARCHAR(128) NOT NULL, 
	external_id VARCHAR(128), 
	current_revision_id UUID, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_questions PRIMARY KEY (id), 
	CONSTRAINT uq_questions_external_source UNIQUE (external_source, external_id)
)

""",
    """
CREATE TABLE catalog_state (
	id SERIAL NOT NULL, 
	version BIGINT DEFAULT '1' NOT NULL, 
	changed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_catalog_state PRIMARY KEY (id), 
	CONSTRAINT ck_catalog_state_singleton CHECK (id = 1 AND version > 0)
)

""",
    """
CREATE TABLE categories (
	id UUID NOT NULL, 
	discipline_id UUID NOT NULL, 
	slug VARCHAR(128) NOT NULL, 
	title VARCHAR(512) NOT NULL, 
	normalized_search_text TEXT DEFAULT '' NOT NULL, 
	position INTEGER DEFAULT '0' NOT NULL, 
	status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
	CONSTRAINT pk_categories PRIMARY KEY (id), 
	CONSTRAINT ck_categories_status CHECK (status IN ('draft', 'published', 'withdrawn')), 
	CONSTRAINT ck_categories_position CHECK (position >= 0), 
	CONSTRAINT uq_categories_discipline_slug UNIQUE (discipline_id, slug), 
	CONSTRAINT uq_categories_discipline_id UNIQUE (discipline_id, id), 
	CONSTRAINT fk_categories_discipline_id_disciplines FOREIGN KEY(discipline_id) REFERENCES disciplines (id) ON DELETE RESTRICT
)

""",
    """CREATE INDEX ix_categories_discipline_id_status_position_id ON categories (discipline_id, status, position, id)""",
    """
CREATE TABLE content_sources (
	id UUID NOT NULL, 
	slug VARCHAR(128) NOT NULL, 
	title VARCHAR(512) NOT NULL, 
	attribution TEXT NOT NULL, 
	license_reference TEXT, 
	evidence_asset_id UUID, 
	reviewed_by UUID, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
	CONSTRAINT pk_content_sources PRIMARY KEY (id), 
	CONSTRAINT ck_content_sources_status CHECK (status IN ('draft', 'published', 'withdrawn')), 
	CONSTRAINT uq_content_sources_slug UNIQUE (slug), 
	CONSTRAINT fk_content_sources_evidence_asset_id_assets FOREIGN KEY(evidence_asset_id) REFERENCES assets (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_content_sources_reviewed_by_users FOREIGN KEY(reviewed_by) REFERENCES users (id) ON DELETE RESTRICT
)

""",
    """
CREATE TABLE topics (
	id UUID NOT NULL, 
	discipline_id UUID NOT NULL, 
	category_id UUID, 
	access_policy_id UUID, 
	slug VARCHAR(128) NOT NULL, 
	title VARCHAR(512) NOT NULL, 
	normalized_search_text TEXT DEFAULT '' NOT NULL, 
	position INTEGER DEFAULT '0' NOT NULL, 
	status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
	CONSTRAINT pk_topics PRIMARY KEY (id), 
	CONSTRAINT ck_topics_status CHECK (status IN ('draft', 'published', 'withdrawn')), 
	CONSTRAINT ck_topics_position CHECK (position >= 0), 
	CONSTRAINT uq_topics_discipline_slug UNIQUE (discipline_id, slug), 
	CONSTRAINT uq_topics_discipline_id UNIQUE (discipline_id, id), 
	CONSTRAINT fk_topics_category_owner FOREIGN KEY(discipline_id, category_id) REFERENCES categories (discipline_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_topics_discipline_id_disciplines FOREIGN KEY(discipline_id) REFERENCES disciplines (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_topics_access_policy_id_access_policies FOREIGN KEY(access_policy_id) REFERENCES access_policies (id) ON DELETE RESTRICT
)

""",
    """CREATE INDEX ix_topics_category_id ON topics (category_id)""",
    """CREATE INDEX ix_topics_discipline_id_status_position_id ON topics (discipline_id, status, position, id)""",
    """
CREATE TABLE question_revisions (
	id UUID NOT NULL, 
	question_id UUID NOT NULL, 
	revision_number INTEGER NOT NULL, 
	kind VARCHAR(32) DEFAULT 'single_choice' NOT NULL, 
	text TEXT NOT NULL, 
	explanation TEXT, 
	source_id UUID, 
	source_reference TEXT DEFAULT '' NOT NULL, 
	source_page VARCHAR(128), 
	created_by UUID, 
	medical_review_by UUID, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
	normalized_search_text TEXT DEFAULT '' NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	CONSTRAINT pk_question_revisions PRIMARY KEY (id), 
	CONSTRAINT ck_question_revisions_status CHECK (status IN ('draft', 'published', 'withdrawn')), 
	CONSTRAINT uq_question_revisions_owner_number UNIQUE (question_id, revision_number), 
	CONSTRAINT uq_question_revisions_owner_id UNIQUE (question_id, id), 
	CONSTRAINT ck_question_revisions_kind_version CHECK (revision_number > 0 AND kind IN ('single_choice','multiple_choice')), 
	CONSTRAINT ck_question_revisions_text_size CHECK (octet_length(text) BETWEEN 1 AND 8000), 
	CONSTRAINT ck_question_revisions_fingerprint CHECK (fingerprint ~ '^[0-9a-f]{64}$'), 
	CONSTRAINT fk_question_revisions_question_id_questions FOREIGN KEY(question_id) REFERENCES questions (id) ON DELETE CASCADE, 
	CONSTRAINT fk_question_revisions_source_id_content_sources FOREIGN KEY(source_id) REFERENCES content_sources (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_question_revisions_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_question_revisions_medical_review_by_users FOREIGN KEY(medical_review_by) REFERENCES users (id) ON DELETE RESTRICT
)

""",
    """CREATE INDEX ix_question_revisions_question_id_status ON question_revisions (question_id, status)""",
    """
CREATE TABLE test_definitions (
	id UUID NOT NULL, 
	topic_id UUID NOT NULL, 
	slug VARCHAR(128) NOT NULL, 
	title VARCHAR(512) NOT NULL, 
	normalized_search_text TEXT DEFAULT '' NOT NULL, 
	exam_duration_seconds INTEGER NOT NULL, 
	question_limit INTEGER, 
	selection_policy VARCHAR(32) DEFAULT 'ordered_all' NOT NULL, 
	policy_version INTEGER DEFAULT '1' NOT NULL, 
	internal_difficulty VARCHAR(32), 
	status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
	CONSTRAINT pk_test_definitions PRIMARY KEY (id), 
	CONSTRAINT ck_test_definitions_status CHECK (status IN ('draft', 'published', 'withdrawn')), 
	CONSTRAINT uq_test_definitions_topic_id UNIQUE (topic_id, slug), 
	CONSTRAINT ck_test_definitions_limits CHECK (exam_duration_seconds > 0 AND (question_limit IS NULL OR question_limit > 0)), 
	CONSTRAINT ck_test_definitions_policy CHECK (selection_policy = 'ordered_all' AND policy_version > 0), 
	CONSTRAINT fk_test_definitions_topic_id_topics FOREIGN KEY(topic_id) REFERENCES topics (id) ON DELETE RESTRICT
)

""",
    """CREATE INDEX ix_test_definitions_topic_id_status_id ON test_definitions (topic_id, status, id)""",
    """
CREATE TABLE question_options (
	id UUID NOT NULL, 
	revision_id UUID NOT NULL, 
	position INTEGER NOT NULL, 
	code VARCHAR(16) NOT NULL, 
	text TEXT NOT NULL, 
	is_correct BOOLEAN DEFAULT false NOT NULL, 
	CONSTRAINT pk_question_options PRIMARY KEY (id), 
	CONSTRAINT uq_question_options_revision_id UNIQUE (revision_id, id), 
	CONSTRAINT uq_question_options_revision_position UNIQUE (revision_id, position), 
	CONSTRAINT uq_question_options_revision_code UNIQUE (revision_id, code), 
	CONSTRAINT ck_question_options_size_position CHECK (position >= 0 AND octet_length(text) BETWEEN 1 AND 2000), 
	CONSTRAINT fk_question_options_revision_id_question_revisions FOREIGN KEY(revision_id) REFERENCES question_revisions (id) ON DELETE CASCADE
)

""",
    """
CREATE TABLE topic_questions (
	topic_id UUID NOT NULL, 
	question_id UUID NOT NULL, 
	position INTEGER NOT NULL, 
	CONSTRAINT pk_topic_questions PRIMARY KEY (topic_id, question_id), 
	CONSTRAINT uq_topic_questions_topic_id UNIQUE (topic_id, position), 
	CONSTRAINT ck_topic_questions_position CHECK (position >= 0), 
	CONSTRAINT fk_topic_questions_topic_id_topics FOREIGN KEY(topic_id) REFERENCES topics (id) ON DELETE CASCADE, 
	CONSTRAINT fk_topic_questions_question_id_questions FOREIGN KEY(question_id) REFERENCES questions (id) ON DELETE RESTRICT
)

""",
    """CREATE INDEX ix_topic_questions_question_id ON topic_questions (question_id)""",
    """
CREATE TABLE notes (
	id UUID NOT NULL, 
	discipline_id UUID NOT NULL, 
	topic_id UUID, 
	current_revision_id UUID, 
	access_policy_id UUID, 
	slug VARCHAR(128) NOT NULL, 
	position INTEGER DEFAULT '0' NOT NULL, 
	status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
	CONSTRAINT pk_notes PRIMARY KEY (id), 
	CONSTRAINT ck_notes_status CHECK (status IN ('draft', 'published', 'withdrawn')), 
	CONSTRAINT ck_notes_position CHECK (position >= 0), 
	CONSTRAINT uq_notes_discipline_id UNIQUE (discipline_id, slug), 
	CONSTRAINT fk_notes_topic_owner FOREIGN KEY(discipline_id, topic_id) REFERENCES topics (discipline_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_notes_discipline_id_disciplines FOREIGN KEY(discipline_id) REFERENCES disciplines (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_notes_access_policy_id_access_policies FOREIGN KEY(access_policy_id) REFERENCES access_policies (id) ON DELETE RESTRICT
)

""",
    """CREATE INDEX ix_notes_discipline_id_status_position_id ON notes (discipline_id, status, position, id)""",
    """CREATE INDEX ix_notes_topic_id ON notes (topic_id)""",
    """
CREATE TABLE note_revisions (
	id UUID NOT NULL, 
	note_id UUID NOT NULL, 
	revision_number INTEGER NOT NULL, 
	title VARCHAR(512) NOT NULL, 
	normalized_search_text TEXT DEFAULT '' NOT NULL, 
	sanitized_body TEXT, 
	asset_id UUID, 
	source_id UUID, 
	source_reference TEXT DEFAULT '' NOT NULL, 
	created_by UUID, 
	medical_review_by UUID, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
	CONSTRAINT pk_note_revisions PRIMARY KEY (id), 
	CONSTRAINT ck_note_revisions_status CHECK (status IN ('draft', 'published', 'withdrawn')), 
	CONSTRAINT uq_note_revisions_owner_number UNIQUE (note_id, revision_number), 
	CONSTRAINT uq_note_revisions_owner_id UNIQUE (note_id, id), 
	CONSTRAINT ck_note_revisions_content_version CHECK (revision_number > 0 AND (sanitized_body IS NOT NULL OR asset_id IS NOT NULL)), 
	CONSTRAINT ck_note_revisions_body_size CHECK (sanitized_body IS NULL OR octet_length(sanitized_body) BETWEEN 1 AND 256000), 
	CONSTRAINT fk_note_revisions_note_id_notes FOREIGN KEY(note_id) REFERENCES notes (id) ON DELETE CASCADE, 
	CONSTRAINT fk_note_revisions_asset_id_assets FOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_note_revisions_source_id_content_sources FOREIGN KEY(source_id) REFERENCES content_sources (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_note_revisions_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_note_revisions_medical_review_by_users FOREIGN KEY(medical_review_by) REFERENCES users (id) ON DELETE RESTRICT
)

""",
    """
CREATE TABLE legacy_mappings (
	entity_type VARCHAR(32) NOT NULL, 
	legacy_id VARCHAR(128) NOT NULL, 
	discipline_id UUID, 
	topic_id UUID, 
	test_definition_id UUID, 
	question_id UUID, 
	CONSTRAINT pk_legacy_mappings PRIMARY KEY (entity_type, legacy_id), 
	CONSTRAINT ck_legacy_mappings_typed_target CHECK ((entity_type = 'discipline' AND discipline_id IS NOT NULL AND topic_id IS NULL AND test_definition_id IS NULL AND question_id IS NULL) OR (entity_type = 'topic' AND topic_id IS NOT NULL AND discipline_id IS NULL AND test_definition_id IS NULL AND question_id IS NULL) OR (entity_type = 'test_definition' AND test_definition_id IS NOT NULL AND discipline_id IS NULL AND topic_id IS NULL AND question_id IS NULL) OR (entity_type = 'question' AND question_id IS NOT NULL AND discipline_id IS NULL AND topic_id IS NULL AND test_definition_id IS NULL)), 
	CONSTRAINT uq_legacy_mappings_discipline_id UNIQUE (discipline_id), 
	CONSTRAINT fk_legacy_mappings_discipline_id_disciplines FOREIGN KEY(discipline_id) REFERENCES disciplines (id) ON DELETE RESTRICT, 
	CONSTRAINT uq_legacy_mappings_topic_id UNIQUE (topic_id), 
	CONSTRAINT fk_legacy_mappings_topic_id_topics FOREIGN KEY(topic_id) REFERENCES topics (id) ON DELETE RESTRICT, 
	CONSTRAINT uq_legacy_mappings_test_definition_id UNIQUE (test_definition_id), 
	CONSTRAINT fk_legacy_mappings_test_definition_id_test_definitions FOREIGN KEY(test_definition_id) REFERENCES test_definitions (id) ON DELETE RESTRICT, 
	CONSTRAINT uq_legacy_mappings_question_id UNIQUE (question_id), 
	CONSTRAINT fk_legacy_mappings_question_id_questions FOREIGN KEY(question_id) REFERENCES questions (id) ON DELETE RESTRICT
)

""",
    """ALTER TABLE notes ADD CONSTRAINT fk_notes_current_revision_owner FOREIGN KEY(id, current_revision_id) REFERENCES note_revisions (note_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED""",
    """ALTER TABLE questions ADD CONSTRAINT fk_questions_current_revision_owner FOREIGN KEY(id, current_revision_id) REFERENCES question_revisions (question_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED""",
)

TRIGGERS_SQL = (
    """CREATE FUNCTION medexa_content_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN UPDATE catalog_state SET version=version+1, changed_at=clock_timestamp() WHERE id=1; RETURN NULL; END; $$""",
    """CREATE FUNCTION medexa_content_state_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF TG_OP='DELETE' OR NEW.id<>1 OR NEW.version<=OLD.version THEN RAISE EXCEPTION 'Invalid catalog state change'; END IF; RETURN NEW; END; $$""",
    """CREATE FUNCTION medexa_content_no_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Content tables cannot be truncated'; END; $$""",
    """CREATE FUNCTION medexa_content_search() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
IF TG_TABLE_NAME='question_revisions' THEN NEW.normalized_search_text=replace(lower(normalize(NEW.text,NFC)),'ё','е');
ELSE NEW.normalized_search_text=replace(lower(normalize(NEW.title,NFC)),'ё','е'); END IF;
RETURN NEW; END; $$""",
    """CREATE FUNCTION medexa_content_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
IF TG_OP='INSERT' THEN RETURN NEW; END IF;
IF OLD.status IN ('published','withdrawn') THEN
 IF TG_OP='UPDATE' AND to_jsonb(NEW)=to_jsonb(OLD) THEN RETURN NEW; END IF;
 IF TG_OP='UPDATE' AND OLD.status='published' AND NEW.status='withdrawn' AND (to_jsonb(NEW)-'status')=(to_jsonb(OLD)-'status') THEN RETURN NEW; END IF;
 RAISE EXCEPTION 'Published content is immutable; create another revision';
END IF;
IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END; $$""",
    """CREATE FUNCTION medexa_content_metadata_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF OLD.status<>'draft' THEN RAISE EXCEPTION 'Archive published metadata instead of deleting'; END IF; RETURN OLD; END; $$""",
    """CREATE FUNCTION medexa_content_option_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s text;
BEGIN
IF TG_OP<>'INSERT' THEN
 SELECT status INTO s FROM question_revisions WHERE id=OLD.revision_id FOR UPDATE;
 IF s IN ('published','withdrawn') THEN RAISE EXCEPTION 'Published options are immutable'; END IF;
END IF;
IF TG_OP<>'DELETE' THEN
 SELECT status INTO s FROM question_revisions WHERE id=NEW.revision_id FOR UPDATE;
 IF s IN ('published','withdrawn') THEN RAISE EXCEPTION 'Published options are immutable'; END IF;
 RETURN NEW;
END IF; RETURN OLD; END; $$""",
    """CREATE FUNCTION medexa_content_source_check() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
IF NEW.status='published' AND (
 NEW.license_reference IS NULL OR length(trim(NEW.license_reference))=0 OR NEW.reviewed_at IS NULL OR NEW.reviewed_at>clock_timestamp() OR NOT EXISTS (
 SELECT 1 FROM user_roles ur JOIN users u ON u.id=ur.user_id WHERE ur.user_id=NEW.reviewed_by AND ur.role_code='content_reviewer' AND u.status='active'))
THEN RAISE EXCEPTION 'Verified content rights are required'; END IF;
RETURN NEW; END; $$""",
    """CREATE FUNCTION medexa_content_question_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE q question_revisions%ROWTYPE; n int; c int;
BEGIN
IF TG_TABLE_NAME='question_options' THEN
 SELECT * INTO q FROM question_revisions WHERE id=COALESCE(NEW.revision_id,OLD.revision_id);
ELSE SELECT * INTO q FROM question_revisions WHERE id=NEW.id; END IF;
IF NOT FOUND OR q.status<>'published' THEN RETURN NULL; END IF;
SELECT count(*),count(*) FILTER(WHERE is_correct) INTO n,c FROM question_options WHERE revision_id=q.id;
IF n<2 OR n>8 OR q.kind<>'single_choice' OR c<>1 THEN RAISE EXCEPTION 'Unsupported published question or invalid answer key'; END IF;
IF q.created_by IS NULL OR q.medical_review_by IS NULL OR q.created_by=q.medical_review_by OR q.reviewed_at IS NULL OR q.reviewed_at>clock_timestamp() OR NOT EXISTS (
 SELECT 1 FROM user_roles ur JOIN users u ON u.id=ur.user_id WHERE ur.user_id=q.medical_review_by AND ur.role_code='content_reviewer' AND u.status='active') OR NOT EXISTS (
 SELECT 1 FROM content_sources s WHERE s.id=q.source_id AND s.status='published')
THEN RAISE EXCEPTION 'Medical review and verified source are required'; END IF;
RETURN NULL; END; $$""",
    """CREATE FUNCTION medexa_content_note_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r note_revisions%ROWTYPE;
BEGIN
SELECT * INTO r FROM note_revisions WHERE id=NEW.id;
IF NOT FOUND OR r.status<>'published' THEN RETURN NULL; END IF;
IF r.created_by IS NULL OR r.medical_review_by IS NULL OR r.created_by=r.medical_review_by OR r.reviewed_at IS NULL OR r.reviewed_at>clock_timestamp() OR NOT EXISTS (
 SELECT 1 FROM user_roles ur JOIN users u ON u.id=ur.user_id WHERE ur.user_id=r.medical_review_by AND ur.role_code='content_reviewer' AND u.status='active') OR NOT EXISTS (
 SELECT 1 FROM content_sources s WHERE s.id=r.source_id AND s.status='published') OR (r.asset_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM assets a WHERE a.id=r.asset_id AND a.status='published'))
THEN RAISE EXCEPTION 'Reviewed note, verified source and approved asset are required'; END IF;
RETURN NULL; END; $$""",
    """CREATE FUNCTION medexa_content_pointer_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p uuid;
BEGIN
IF TG_TABLE_NAME='questions' THEN
 SELECT current_revision_id INTO p FROM questions WHERE id=NEW.id;
 IF p IS NOT NULL AND NOT EXISTS(SELECT 1 FROM question_revisions WHERE id=p AND question_id=NEW.id AND status='published') THEN RAISE EXCEPTION 'Invalid published question pointer'; END IF;
ELSE
 SELECT current_revision_id INTO p FROM notes WHERE id=NEW.id;
 IF p IS NOT NULL AND NOT EXISTS(SELECT 1 FROM note_revisions WHERE id=p AND note_id=NEW.id AND status='published') THEN RAISE EXCEPTION 'Invalid published note pointer'; END IF;
END IF; RETURN NULL; END; $$""",
    """CREATE FUNCTION medexa_content_withdraw() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
IF OLD.status='published' AND NEW.status='withdrawn' THEN
 IF TG_TABLE_NAME='question_revisions' THEN UPDATE questions SET current_revision_id=NULL WHERE id=NEW.question_id AND current_revision_id=NEW.id;
 ELSE UPDATE notes SET current_revision_id=NULL WHERE id=NEW.note_id AND current_revision_id=NEW.id; END IF;
END IF; RETURN NULL; END; $$""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON disciplines FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON disciplines FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON categories FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON categories FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON access_policies FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON access_policies FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON topics FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON topics FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON test_definitions FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON test_definitions FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON assets FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON assets FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON content_sources FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON content_sources FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON questions FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON questions FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON question_revisions FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON question_revisions FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON question_options FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON question_options FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON topic_questions FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON topic_questions FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON notes FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON notes FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON note_revisions FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON note_revisions FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_version AFTER INSERT OR UPDATE OR DELETE ON legacy_mappings FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_version()""",
    """CREATE TRIGGER content_no_truncate BEFORE TRUNCATE ON legacy_mappings FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER b_normalize BEFORE INSERT OR UPDATE ON disciplines FOR EACH ROW EXECUTE FUNCTION medexa_content_search()""",
    """CREATE TRIGGER b_normalize BEFORE INSERT OR UPDATE ON categories FOR EACH ROW EXECUTE FUNCTION medexa_content_search()""",
    """CREATE TRIGGER b_normalize BEFORE INSERT OR UPDATE ON topics FOR EACH ROW EXECUTE FUNCTION medexa_content_search()""",
    """CREATE TRIGGER b_normalize BEFORE INSERT OR UPDATE ON test_definitions FOR EACH ROW EXECUTE FUNCTION medexa_content_search()""",
    """CREATE TRIGGER b_normalize BEFORE INSERT OR UPDATE ON question_revisions FOR EACH ROW EXECUTE FUNCTION medexa_content_search()""",
    """CREATE TRIGGER b_normalize BEFORE INSERT OR UPDATE ON note_revisions FOR EACH ROW EXECUTE FUNCTION medexa_content_search()""",
    """CREATE TRIGGER a_immutable BEFORE UPDATE OR DELETE ON question_revisions FOR EACH ROW EXECUTE FUNCTION medexa_content_immutable()""",
    """CREATE TRIGGER a_immutable BEFORE UPDATE OR DELETE ON note_revisions FOR EACH ROW EXECUTE FUNCTION medexa_content_immutable()""",
    """CREATE TRIGGER a_immutable BEFORE UPDATE OR DELETE ON content_sources FOR EACH ROW EXECUTE FUNCTION medexa_content_immutable()""",
    """CREATE TRIGGER content_metadata_delete BEFORE DELETE ON disciplines FOR EACH ROW EXECUTE FUNCTION medexa_content_metadata_delete()""",
    """CREATE TRIGGER content_metadata_delete BEFORE DELETE ON categories FOR EACH ROW EXECUTE FUNCTION medexa_content_metadata_delete()""",
    """CREATE TRIGGER content_metadata_delete BEFORE DELETE ON topics FOR EACH ROW EXECUTE FUNCTION medexa_content_metadata_delete()""",
    """CREATE TRIGGER content_metadata_delete BEFORE DELETE ON test_definitions FOR EACH ROW EXECUTE FUNCTION medexa_content_metadata_delete()""",
    """CREATE TRIGGER content_metadata_delete BEFORE DELETE ON notes FOR EACH ROW EXECUTE FUNCTION medexa_content_metadata_delete()""",
    """CREATE TRIGGER content_metadata_delete BEFORE DELETE ON assets FOR EACH ROW EXECUTE FUNCTION medexa_content_metadata_delete()""",
    """CREATE TRIGGER content_metadata_delete BEFORE DELETE ON access_policies FOR EACH ROW EXECUTE FUNCTION medexa_content_metadata_delete()""",
    """CREATE TRIGGER content_state_guard BEFORE UPDATE OR DELETE ON catalog_state FOR EACH ROW EXECUTE FUNCTION medexa_content_state_guard()""",
    """CREATE TRIGGER content_state_no_truncate BEFORE TRUNCATE ON catalog_state FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()""",
    """CREATE TRIGGER content_option_guard BEFORE INSERT OR UPDATE OR DELETE ON question_options FOR EACH ROW EXECUTE FUNCTION medexa_content_option_guard()""",
    """CREATE TRIGGER content_source_check BEFORE INSERT OR UPDATE ON content_sources FOR EACH ROW EXECUTE FUNCTION medexa_content_source_check()""",
    """CREATE CONSTRAINT TRIGGER content_question_check AFTER INSERT OR UPDATE ON question_revisions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION medexa_content_question_check()""",
    """CREATE CONSTRAINT TRIGGER content_option_check AFTER INSERT OR UPDATE OR DELETE ON question_options DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION medexa_content_question_check()""",
    """CREATE CONSTRAINT TRIGGER content_note_check AFTER INSERT OR UPDATE ON note_revisions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION medexa_content_note_check()""",
    """CREATE CONSTRAINT TRIGGER content_pointer_check AFTER INSERT OR UPDATE ON questions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION medexa_content_pointer_check()""",
    """CREATE CONSTRAINT TRIGGER content_pointer_check AFTER INSERT OR UPDATE ON notes DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION medexa_content_pointer_check()""",
    """CREATE TRIGGER content_withdraw AFTER UPDATE ON question_revisions FOR EACH ROW EXECUTE FUNCTION medexa_content_withdraw()""",
    """CREATE TRIGGER content_withdraw AFTER UPDATE ON note_revisions FOR EACH ROW EXECUTE FUNCTION medexa_content_withdraw()""",
    """CREATE TRIGGER a_immutable BEFORE UPDATE OR DELETE ON assets FOR EACH ROW EXECUTE FUNCTION medexa_content_immutable()""",
)

SNAPSHOT_SHA256 = "df4c92e12de77e68c3cde7aa14521cf6f77e1a6cad9a35f0e7040d99c786df5e"

NAMESPACE = UUID("b5d4c800-4b61-4784-8c02-aad5732d40a3")


def legacy_id(kind, key):
    return uuid5(NAMESPACE, kind + ":" + key)


def insert(table, **values):
    columns = ", ".join(values)
    binds = ", ".join(":" + name for name in values)
    op.execute(sa.text(f"INSERT INTO {table} ({columns}) VALUES ({binds})").bindparams(**values))


def seed_legacy():
    raw = (Path(__file__).resolve().parents[1] / "data" / "0003_legacy_questions.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SNAPSHOT_SHA256:
        raise RuntimeError("Immutable legacy snapshot checksum mismatch")
    snapshot = json.loads(raw)
    if len(snapshot["questions"]) != 10 or snapshot["review_status"] != "unverified":
        raise RuntimeError("Invalid legacy quarantine snapshot")
    source = legacy_id("source", "legacy")
    insert(
        "content_sources",
        id=source,
        slug="anatomai-legacy-5450646",
        title="Unverified legacy repository snapshot",
        attribution=snapshot["source_path"]
        + " @ "
        + snapshot["source_commit"]
        + " sha256:"
        + snapshot["source_sha256"],
        status="draft",
    )
    definitions = [
        ("anatomy", "Анатомия", "Опорно-двигательная система", "blue", "anatomy", 12, "a"),
        ("physiology", "Физиология", "Нервная система", "mint", "physiology", 9, "p"),
        ("neuro", "Неврология", "Черепные нервы", "violet", "neuro", 18, "n"),
        ("histology", "Гистология", "Ткани организма", "orange", "histology", 7, "h"),
    ]
    for position, (key, title, theme, color, icon, minutes, prefix) in enumerate(definitions):
        discipline = legacy_id("discipline", key)
        topic = legacy_id("topic", key)
        test = legacy_id("test", key)
        insert(
            "disciplines",
            id=discipline,
            slug=key,
            title=title,
            icon_key=icon,
            color_token=color,
            position=position,
            status="draft",
        )
        insert(
            "topics",
            id=topic,
            discipline_id=discipline,
            slug=key + "-legacy",
            title=theme,
            position=0,
            status="draft",
        )
        insert(
            "test_definitions",
            id=test,
            topic_id=topic,
            slug=key + "-legacy",
            title=title + ": " + theme,
            exam_duration_seconds=minutes * 60,
            status="draft",
        )
        for kind, target, col in [
            ("discipline", discipline, "discipline_id"),
            ("topic", topic, "topic_id"),
            ("test_definition", test, "test_definition_id"),
        ]:
            insert("legacy_mappings", entity_type=kind, legacy_id=key, **{col: target})
        for order, q in enumerate(q for q in snapshot["questions"] if q["id"].startswith(prefix)):
            qid = legacy_id("question", q["id"])
            rid = legacy_id("revision", q["id"])
            insert(
                "questions", id=qid, external_source="anatomai-legacy-5450646", external_id=q["id"]
            )
            insert(
                "question_revisions",
                id=rid,
                question_id=qid,
                revision_number=1,
                kind="single_choice",
                text=q["text"],
                explanation=q["explanation"],
                source_id=source,
                source_reference="Medical correctness and rights NOT verified",
                fingerprint=hashlib.sha256(
                    json.dumps(q, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest(),
                status="draft",
            )
            for i, answer in enumerate(q["answers"]):
                insert(
                    "question_options",
                    id=legacy_id("option", q["id"] + ":" + str(i)),
                    revision_id=rid,
                    position=i,
                    code=chr(65 + i),
                    text=answer,
                    is_correct=i == q["correct_answer"],
                )
            insert("topic_questions", topic_id=topic, question_id=qid, position=order)
            insert("legacy_mappings", entity_type="question", legacy_id=q["id"], question_id=qid)


def upgrade():
    for sql in SCHEMA_SQL:
        op.execute(sa.text(sql))
    op.execute(sa.text("INSERT INTO catalog_state(id,version) VALUES (1,1)"))
    for sql in TRIGGERS_SQL:
        op.execute(sa.text(sql))
    seed_legacy()


def downgrade():
    op.drop_constraint("fk_questions_current_revision_owner", "questions", type_="foreignkey")
    op.drop_constraint("fk_notes_current_revision_owner", "notes", type_="foreignkey")
    op.drop_table("legacy_mappings")
    op.drop_table("note_revisions")
    op.drop_table("notes")
    op.drop_table("topic_questions")
    op.drop_table("question_options")
    op.drop_table("test_definitions")
    op.drop_table("question_revisions")
    op.drop_table("topics")
    op.drop_table("content_sources")
    op.drop_table("categories")
    op.drop_table("catalog_state")
    op.drop_table("questions")
    op.drop_table("assets")
    op.drop_table("access_policies")
    op.drop_table("disciplines")
    op.execute("DROP FUNCTION medexa_content_version()")
    op.execute("DROP FUNCTION medexa_content_state_guard()")
    op.execute("DROP FUNCTION medexa_content_no_truncate()")
    op.execute("DROP FUNCTION medexa_content_search()")
    op.execute("DROP FUNCTION medexa_content_immutable()")
    op.execute("DROP FUNCTION medexa_content_metadata_delete()")
    op.execute("DROP FUNCTION medexa_content_option_guard()")
    op.execute("DROP FUNCTION medexa_content_source_check()")
    op.execute("DROP FUNCTION medexa_content_question_check()")
    op.execute("DROP FUNCTION medexa_content_note_check()")
    op.execute("DROP FUNCTION medexa_content_pointer_check()")
    op.execute("DROP FUNCTION medexa_content_withdraw()")
