"""work-timeline: the `ops.work` contract and the one remote writer for it.

* `vocab`    -- the closed vocabulary (kinds, layers, statuses) and the outcome mapping.
* `contract` -- the request models the receiver validates with and the client builds through.
* `client`   -- `TimelineClient`: open/close/record and `recorded()` around a block; never raises.
"""

from work_timeline.client import TimelineClient, Unit
from work_timeline.contract import WorkClose, WorkOpen, WorkRecord
from work_timeline.vocab import KINDS, LAYERS, STATUSES, TERMINAL, status_for

__version__ = "0.2.0"

__all__ = ["KINDS", "LAYERS", "STATUSES", "TERMINAL", "TimelineClient", "Unit", "WorkClose", "WorkOpen",
           "WorkRecord", "status_for"]
