"""Every name one firmware module imports from another actually exists there.

`pico/` cannot be imported under CPython — utils pulls in `urequests`, display
pulls in `framebuf` — so the rest of the suite only reaches the leaf modules
that were deliberately kept import-free. That leaves the most ordinary mistake
in the package completely uncovered: moving a helper out of `utils.py` and
missing one of its callers is an ImportError on the device at boot, and a full
green test run here.

So this reads the modules with `ast` instead of importing them, and checks the
bare-name imports (`from utils import percentile`) against what the target
module actually defines. No execution, no MicroPython stubs.
"""

import ast
import pathlib

PICO = pathlib.Path(__file__).resolve().parents[1] / "pico"


def _modules():
    """Every firmware module, keyed by the bare name its siblings import it as."""
    found = {}
    for path in sorted(PICO.rglob("*.py")):
        found[path.stem] = path
    return found


def _defined(tree):
    """Top-level names a module binds, including re-exported imports."""
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names


def test_bare_name_imports_resolve():
    modules = _modules()
    trees = {
        name: ast.parse(path.read_text(encoding="utf-8"))
        for name, path in modules.items()
    }
    defined = {name: _defined(tree) for name, tree in trees.items()}

    missing = []
    for name, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level:
                continue
            # Only siblings under pico/; stdlib and MicroPython modules are
            # not ours to check.
            target = node.module.split(".")[-1] if node.module else ""
            if target not in defined or target == name:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                if alias.name not in defined[target]:
                    missing.append(
                        "pico/%s.py imports %r from %s, which does not define it"
                        % (name, alias.name, target)
                    )

    assert not missing, "\n".join(missing)
