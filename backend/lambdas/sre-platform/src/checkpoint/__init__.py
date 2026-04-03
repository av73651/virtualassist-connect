"""Checkpoint SDK — fire-and-forget progress tracking for batch workloads.

Usage:
    from src.checkpoint import CheckpointClient

    checkpoint = CheckpointClient(
        table_name="sre-checkpoints-dev",
        bucket_name="sre-checkpoint-manifests-dev",
    )
"""

from src.checkpoint.client import CheckpointClient

__all__ = ["CheckpointClient"]
