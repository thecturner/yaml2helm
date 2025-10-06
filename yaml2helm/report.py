"""Report tracking for yaml2helm conversion process."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class Report:
    """Track conversion statistics and results."""

    files_discovered: int = 0
    valid_objects: int = 0
    skipped: int = 0
    bad_yaml: int = 0
    templated: int = 0
    chart_path: Path | None = None
    conflicts: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def conflicts_count(self) -> int:
        """Get count of conflicts."""
        return len(self.conflicts)

    @property
    def errors_count(self) -> int:
        """Get count of errors."""
        return len(self.errors)

    def add_conflict(self, message: str) -> None:
        """Add a conflict message."""
        self.conflicts.append(message)

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)

    def summary(self) -> dict:
        """Get summary dictionary."""
        return {
            "files_discovered": self.files_discovered,
            "valid_objects": self.valid_objects,
            "skipped": self.skipped,
            "bad_yaml": self.bad_yaml,
            "templated": self.templated,
            "chart_path": str(self.chart_path) if self.chart_path else None,
            "conflicts_count": self.conflicts_count,
            "errors_count": self.errors_count,
        }
