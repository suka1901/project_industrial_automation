"""The layering is enforced here, not left to discipline.

An architecture described only in a document drifts. These tests read the
imports and fail if a dependency ever points outward, so the claim in
README.md stays true by construction.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

import ast
import sys
import unittest
from pathlib import Path

PI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PI))

# What each layer is allowed to import from inside the project. Dependencies
# point inward only: the domain knows nothing of the machinery around it.
ALLOWED = {
    "domain": {"domain"},
    "ports": {"domain", "ports"},
    "application": {"domain", "ports", "application"},
    "adapters": {"domain", "ports", "adapters"},
    "infrastructure": {"domain", "ports", "application", "adapters", "infrastructure"},
}
PROJECT_PACKAGES = set(ALLOWED)

# Libraries that would drag I/O or a framework into the pure layers.
FORBIDDEN_IN_CORE = {"cv2", "numpy", "ultralytics", "tkinter", "socket",
                     "pypylon", "yaml", "serial"}


def source_files(package: str):
    return [p for p in (PI / package).rglob("*.py") if "__pycache__" not in str(p)]


def imports_of(path: Path):
    """Top-level module names this file imports."""
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            names.extend(a.name.split(".")[0] for a in node.names)
    return names


class TestDependenciesPointInward(unittest.TestCase):
    def test_no_layer_imports_outward(self):
        for package, allowed in ALLOWED.items():
            for path in source_files(package):
                for name in imports_of(path):
                    if name in PROJECT_PACKAGES:
                        self.assertIn(
                            name, allowed,
                            f"{path.relative_to(PI)} imports '{name}', which is "
                            f"outside {package}. Dependencies point inward only.")

    def test_domain_and_ports_carry_no_io(self):
        """The core must stay testable with nothing installed."""
        for package in ("domain", "ports"):
            for path in source_files(package):
                for name in imports_of(path):
                    self.assertNotIn(
                        name, FORBIDDEN_IN_CORE,
                        f"{path.relative_to(PI)} imports '{name}'. The core must "
                        "not depend on I/O or a framework.")


class TestPortsArePolymorphic(unittest.TestCase):
    """Every port is an abstraction with at least one adapter behind it."""

    def _classes(self):
        found = {}
        for package in ALLOWED:
            for path in source_files(package):
                for node in ast.parse(path.read_text(encoding="utf-8")).body:
                    if isinstance(node, ast.ClassDef):
                        found[node.name] = [ast.unparse(b) for b in node.bases]
        return found

    def test_every_port_is_abstract_and_implemented(self):
        classes = self._classes()
        ports = [name for name, bases in classes.items() if "ABC" in bases]
        self.assertGreaterEqual(len(ports), 9, "ports have gone missing")
        for port in ports:
            implementations = [n for n, bases in classes.items() if port in bases]
            self.assertTrue(implementations, f"{port} has no implementation")

    def test_nothing_inherits_from_a_concrete_adapter(self):
        """Reuse is by composition; inheritance is only for implementing a port."""
        classes = self._classes()
        abstract = {n for n, bases in classes.items() if "ABC" in bases}
        abstract |= {"Worker"}          # the one deliberate template-method base
        for name, bases in classes.items():
            for base in bases:
                if base in classes and base not in abstract:
                    self.fail(f"{name} inherits from the concrete class {base}")


if __name__ == "__main__":
    unittest.main()
