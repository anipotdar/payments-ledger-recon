-- Databricks notebook source
-- One-time setup. Free Edition gives you the `workspace` catalog; everything
-- for this project lives in its own schema so it can be dropped and rebuilt.

CREATE SCHEMA IF NOT EXISTS workspace.ledger_recon
COMMENT 'Payments ledger and reconciliation';

-- Landing zone. Upload generator output here (see README: Run it).
CREATE VOLUME IF NOT EXISTS workspace.ledger_recon.landing
COMMENT 'Raw files exactly as the sources deliver them';

-- Auto Loader keeps its schema and checkpoint state here.
CREATE VOLUME IF NOT EXISTS workspace.ledger_recon.checkpoints
COMMENT 'Auto Loader schema locations and stream checkpoints';
