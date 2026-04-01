# scripts/incident/simulations/mocks/batch_processor.py
"""Dummy Batch Processor Lambda — simulates processing 10 transactions.
   Has a chaos flag to trigger partial failure (timeout at index 5)."""

import json
import logging
import time

from shared.middleware.observability import observe

logger = logging.getLogger()
logger.setLevel(logging.INFO)

@observe(operation="process_batch", metric_prefix="batch_processor")
def lambda_handler(event, context):
    """Main handler using @observe for all cross-cutting concerns."""
    logger.info("Batch processing started: %s", event)
    
    txn_ids = event.get("txn_ids", [f"txn-{i}" for i in range(1, 11)])
    force_partial_failure = event.get("force_partial_failure", False)
    
    processed = []
    
    for i, txn_id in enumerate(txn_ids):
        # Trigger partial failure/timeout before 6th item
        if force_partial_failure and i == 5:
            logger.error("[ERROR] Batch processing timed out at index 5. %d transactions pending.", len(txn_ids) - i)
            # Decorator will catch this, record the error, and re-raise
            raise Exception("LambdaTimeoutError: Task timed out after 30.00 seconds")
            
        logger.info("Processed transaction: %s", txn_id)
        processed.append(txn_id)
        # Mock some processing time
        time.sleep(0.1)

    return {
        "statusCode": 200,
        "body": json.dumps({"status": "success", "processed_count": len(processed)})
    }
