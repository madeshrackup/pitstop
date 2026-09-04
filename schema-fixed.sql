-- Pitstop / WiiLink WFC schema (adjusted for POSTGRES_USER=pitstop)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';
SET default_table_access_method = heap;

CREATE TABLE IF NOT EXISTS public.users (
    profile_id bigint NOT NULL,
    user_id bigint NOT NULL,
    gsbrcd character varying NOT NULL,
    password character varying NOT NULL,
    ng_device_id bigint,
    email character varying NOT NULL,
    unique_nick character varying NOT NULL,
    firstname character varying,
    lastname character varying DEFAULT ''::character varying
);

ALTER TABLE ONLY public.users
    ADD COLUMN IF NOT EXISTS last_ip_address character varying DEFAULT ''::character varying,
    ADD COLUMN IF NOT EXISTS last_ingamesn character varying DEFAULT ''::character varying,
    ADD COLUMN IF NOT EXISTS has_ban boolean DEFAULT false,
    ADD COLUMN IF NOT EXISTS ban_issued timestamp without time zone,
    ADD COLUMN IF NOT EXISTS ban_expires timestamp without time zone,
    ADD COLUMN IF NOT EXISTS ban_reason character varying,
    ADD COLUMN IF NOT EXISTS ban_reason_hidden character varying,
    ADD COLUMN IF NOT EXISTS ban_moderator character varying,
    ADD COLUMN IF NOT EXISTS ban_tos boolean,
    ADD COLUMN IF NOT EXISTS open_host boolean DEFAULT false;

DO $$
BEGIN
    IF (SELECT data_type FROM information_schema.columns WHERE table_name='users' AND column_name='ng_device_id') != 'ARRAY' THEN
        ALTER TABLE public.users
            ALTER COLUMN ng_device_id TYPE bigint[] using array[ng_device_id];
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.sake_records (
    game_id integer NOT NULL,
    table_id character varying NOT NULL,
    record_id integer NOT NULL DEFAULT (random() * 2147483647)::integer,
    owner_id integer NOT NULL,
    fields jsonb NOT NULL CHECK (jsonb_typeof(fields) = 'object' AND jsonb_array_length(jsonb_path_query_array(fields, '$.keyvalue().key')) <= 64),
    create_time timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    update_time timestamp without time zone DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT one_sake_record_constraint UNIQUE (game_id, table_id, record_id)
);

CREATE TABLE IF NOT EXISTS public.mario_kart_wii_sake (
    regionid smallint NOT NULL CHECK (regionid >= 1 AND regionid <= 7),
    courseid smallint NOT NULL CHECK (courseid >= 0 AND courseid <= 32767),
    score integer NOT NULL CHECK (score > 0 AND score < 360000),
    pid integer NOT NULL CHECK (pid > 0),
    playerinfo varchar(108) NOT NULL CHECK (LENGTH(playerinfo) = 108),
    ghost bytea CHECK (ghost IS NULL OR (OCTET_LENGTH(ghost) BETWEEN 148 AND 10240)),

    CONSTRAINT one_time_per_course_constraint UNIQUE (courseid, pid)
);

ALTER TABLE ONLY public.mario_kart_wii_sake
    ADD COLUMN IF NOT EXISTS id serial,
    ADD COLUMN IF NOT EXISTS upload_time timestamp without time zone;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'mario_kart_wii_sake_pkey'
    ) THEN
        ALTER TABLE ONLY public.mario_kart_wii_sake
            ADD CONSTRAINT mario_kart_wii_sake_pkey PRIMARY KEY (id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.gamestats_public_data (
    profile_id bigint NOT NULL,
    dindex character varying NOT NULL,
    ptype character varying NOT NULL,
    pdata character varying NOT NULL,
    modified_time timestamp without time zone NOT NULL,

    CONSTRAINT one_pdata_constraint UNIQUE (profile_id, dindex, ptype)
);

CREATE SEQUENCE IF NOT EXISTS public.users_profile_id_seq
    AS integer
    START WITH 1000000000
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.users_profile_id_seq OWNED BY public.users.profile_id;

ALTER TABLE ONLY public.users ALTER COLUMN profile_id SET DEFAULT nextval('public.users_profile_id_seq'::regclass);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_pkey'
    ) THEN
        ALTER TABLE ONLY public.users
            ADD CONSTRAINT users_pkey PRIMARY KEY (profile_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.events (
    id serial PRIMARY KEY,
    event_type character varying NOT NULL,
    event_data jsonb NOT NULL,
    event_time timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);
