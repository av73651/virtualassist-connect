# scripts/incident/simulations/mocks/batch_recovery.py
"""Dummy Batch Recovery Step Function Handler — simulates reprocessing.
   Used for verifying that the Incident Manager correctly triggered the recovery
   workflow after a partial failure."""

import json
import logging
import time

from shared.middleware.observability import observe

logger = logging.getLogger()
logger.setLevel(logging.INFO)

@observe(operation="reprocess_batch", metric_prefix="batch_recovery")
def lambda_handler(event, context):
    """Main handler using @observe for all cross-cutting concerns."""
    logger.info("Batch recovery triggered: %s", event)
    
    incident_key = event.get("incident_key", "unknown")
    pending_txns = event.get("pending_txns", [f"txn-6", "txn-7", "txn-8", "txn-9", "txn-10"])
    
    reprocessed = []
    
    # Process the items that the initial batch missed
    for i, txn_id in enumerate(pending_txns):
        logger.info("[REPROCESSING] %s", txn_id)
        reprocessed.append(txn_id)
        # Mock some processing time
        time.sleep(1)

    logger.info("Batch recovery complete. Reprocessed %d items.", len(reprocessed))
    return {
        "status": "success",
        "incident_key": incident_key,
        "reprocessed_count": len(reprocessed)
    }
