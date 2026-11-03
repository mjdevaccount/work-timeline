"""work-timeline: the contract for a shared work timeline, and a remote writer that never raises.

A unit of work (a CI job, a build, a deploy, a batch run) is recorded as one row on a timeline
receiver: opened as `running` when it starts, closed as `ok`, `failed` or `cancelled` when it
ends. This package is the contract both sides share and the client a remote writer uses.

Modules:
    vocab: The closed kinds, layers and statuses, and the outcome mapping.
    contract: The request models the receiver validates with and the client builds through.
    client: `TimelineClient`: `open`, `close`, `record`, and `recorded()` around a block.
    cli: `python -m work_timeline`, the same writer for shell callers.
"""

from work_timeline.client import TimelineClient, Unit
from work_timeline.contract import WorkClose, WorkOpen, WorkRecord
from work_timeline.vocab import KINDS, LAYERS, STATUSES, TERMINAL, status_for

__version__ = "0.3.0"

__all__ = [
    "KINDS",
    "LAYERS",
    "STATUSES",
    "TERMINAL",
    "TimelineClient",
    "Unit",
    "WorkClose",
    "WorkOpen",
    "WorkRecord",
    "__version__",
    "status_for",
]
