"""Isolated A-3-1 regression runner; no server or operational settings are loaded."""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from scripts.experiments.analyze_quality_baseline import snapshot, write_json


TESTS = [
    "tests/test_quality_shadow_metrics.py", "tests/test_quality_shadow_store.py",
    "tests/test_quality_shadow_worker.py", "tests/test_quality_shadow_integration.py",
    "tests/test_quality_baseline_analysis.py", "tests/test_quality_candidates.py",
    "tests/test_quality_shadow_design.py", "tests/test_grab_inspection.py",
    "tests/test_reinspection_workflow.py",
]
CHANGED_CODE = {
    "backend/config.py", "backend/main.py", "backend/grab_inspection.py",
    "backend/quality_shadow_metrics.py", "backend/quality_shadow_store.py", "backend/quality_shadow_worker.py",
}


def config_without_shadow():
    class RemoveShadow(ast.NodeTransformer):
        def visit_AnnAssign(self, node):
            if isinstance(node.target, ast.Name) and node.target.id == "QUALITY_SHADOW_ENABLED":
                return None
            return self.generic_visit(node)

        def visit_Assign(self, node):
            if any(isinstance(target, ast.Attribute) and target.attr == "QUALITY_SHADOW_ENABLED" for target in node.targets):
                return None
            return self.generic_visit(node)

    tree = RemoveShadow().visit(ast.parse((ROOT / "backend/config.py").read_text(encoding="utf-8")))
    return hashlib.sha256(ast.dump(tree).encode()).hexdigest()


def protected():
    result = snapshot([])
    result["sha256"] = {name.replace("\\", "/"): value for name, value in result["sha256"].items()}
    result["user_config_ast_without_shadow"] = config_without_shadow()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("snapshot", "test", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    if (ROOT / "data/outputs/quality-shadow-validation").resolve() not in output.parents:
        raise ValueError("ISOLATED_QUALITY_SHADOW_OUTPUT_REQUIRED")
    if arguments.mode in {"snapshot", "test"}:
        output.mkdir(parents=True, exist_ok=False)
    if arguments.mode == "test":
        os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        os.environ["QUALITY_SHADOW_ENABLED"] = "false"
        os.environ["VISION_REVIEW_LIVE_ENABLED"] = "false"
        from scripts.safe_regression_backend import run_tests

        return run_tests(output, TESTS)
    if arguments.mode == "snapshot":
        before = protected()
        write_json(output / "protection-before.json", before)
        print(json.dumps({"files": len(before["sha256"]), "unverified": len(before["unverified"])}))
        return 2 if before["unverified"] else 0
    before = json.loads((output / "protection-before.json").read_text(encoding="utf-8"))
    after = protected()
    changes = sorted(name for name in set(before["sha256"]) | set(after["sha256"]) if before["sha256"].get(name) != after["sha256"].get(name))
    unexpected = sorted(set(changes) - CHANGED_CODE)
    result = {"verified_before": len(before["sha256"]), "unexpected_changes": unexpected,
              "intentional_code_changes": sorted(set(changes) & CHANGED_CODE),
              "unverified_before": before["unverified"], "unverified_after": after["unverified"],
              "user_config_preserved": before["user_config_ast_without_shadow"] == after["user_config_ast_without_shadow"],
              "database": "NOT_CONNECTED_NOT_VERIFIED"}
    result["operational_assets_unchanged"] = not unexpected and not before["unverified"] and not after["unverified"] and result["user_config_preserved"]
    write_json(output / "protection-final.json", result)
    print(json.dumps(result))
    return 0 if result["operational_assets_unchanged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
