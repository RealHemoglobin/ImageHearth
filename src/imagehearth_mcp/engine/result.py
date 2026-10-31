from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImageResult:
    path: Path
    warnings: list[str] = field(default_factory=list)

    def __str__(self):
        lines = [str(self.path)]
        lines.extend(f"WARNING: {warning}" for warning in self.warnings)
        return "\n".join(lines)
