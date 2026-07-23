from __future__ import annotations

from typing import Union

from .log import NormalizedLog
from .metric import NormalizedMetric
from .span import NormalizedSpan

Normalized = Union[NormalizedLog, NormalizedSpan, NormalizedMetric]
