"""__init__.py for mwgym.run"""
from .spec import WorkerRun, WorkerVersion, ComputePolicy, Evaluation
from .verifier import verify, list_verifiers, register_verifier
from .receipt import record_receipt, get_receipt, get_campaign_receipts, receipt_summary
from .executor import execute, ExecuteResult
