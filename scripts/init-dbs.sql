-- Creates additional databases on the shared Postgres instance.
-- Runs automatically on first docker compose up via /docker-entrypoint-initdb.d/
CREATE DATABASE hatchet;
CREATE DATABASE plausible;
