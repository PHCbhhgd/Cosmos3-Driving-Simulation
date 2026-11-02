"""Evaluate the upstream hardware gate before installing the whole Auto runtime.

Only two upstream functions are compiled from AST; this avoids unrelated training
imports. Their bodies are used unchanged, and source location/commit are recorded.
"""

import ast
import importlib
import json
import subprocess
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "repos/cosmos-framework/cosmos_framework/model/generator/mot/maskless_attention.py"
tree = ast.parse(source.read_text())
names = {"_flash_attn_interface", "gapped_replay_unavailable_reason"}
nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
code = ast.Module(
    body=[
        ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
        *nodes,
    ],
    type_ignores=[],
)
ast.fix_missing_locations(code)
scope = {"torch": torch, "import_module": importlib.import_module}
exec(compile(code, str(source), "exec"), scope)
config = json.loads((ROOT / "storage/models/Cosmos3-Nano-Sim-Auto/config.json").read_text())
implementation = config["model"]["config"]["teacher_forcing_kv_implementation"]
reason = scope["gapped_replay_unavailable_reason"](torch.device("cuda:0"))
report = {
    "status": "unsupported_hardware" if reason else "hardware_gate_passed",
    "device": torch.cuda.get_device_name(0),
    "compute_capability": torch.cuda.get_device_capability(0),
    "checkpoint_implementation": implementation,
    "reason": reason,
    "method": "Unmodified upstream function bodies evaluated from AST; no full model loaded",
    "source": str(source.relative_to(ROOT)),
    "function_line": next(
        node.lineno for node in nodes if node.name == "gapped_replay_unavailable_reason"
    ),
    "framework_commit": subprocess.check_output(
        ["git", "-C", str(ROOT / "repos/cosmos-framework"), "rev-parse", "HEAD"], text=True
    ).strip(),
}
assert implementation == "multiview_maskless_kv"
out = ROOT / "artifacts/sim_hardware_check.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))

if reason:
    raise SystemExit(1)
