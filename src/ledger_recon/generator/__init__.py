"""Synthetic source generator.

Produces three sources that are supposed to agree and don't:
processor webhook events, bank statement lines and daily merchant master
snapshots, plus daily FX rates. Every disagreement is planted on purpose and
written to ``_truth/defects.jsonl`` so the pipeline can be scored on what it
catches.
"""

from ledger_recon.generator.config import GeneratorConfig
from ledger_recon.generator.run import generate

__all__ = ["GeneratorConfig", "generate"]
