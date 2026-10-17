"""Isolated, bounded diagnostic; never a calibration or product evaluation."""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import socket
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_SHA256 = "4b239d28e72c63bf782cd1d31981d7f4362c591e7c23164e4c0ac8b5e99b52a3"
THRESHOLD = 34.1442
FORWARD_LIMIT = 12
SCORE_RTOL = 1e-7
SCORE_ATOL = 1e-7


def synthetic_inputs():
    import numpy as np

    horizontal = np.broadcast_to(np.arange(256, dtype=np.uint8), (256, 256))
    vertical = horizontal.T
    checker = (((horizontal // 32 + vertical // 32) % 2) * 255).astype(np.uint8)
    return {
        "SYN-001": np.full((256, 256, 3), 128, dtype=np.uint8),
        "SYN-002": np.repeat(horizontal[:, :, None], 3, axis=2),
        "SYN-003": np.stack((horizontal, vertical, checker), axis=2),
    }


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def threshold_side(score):
    require(math.isfinite(score), "NONFINITE_SCORE")
    return "ABOVE" if score > THRESHOLD else "AT_OR_BELOW"


def compare_scores(input_id, baseline, candidate):
    difference = abs(candidate - baseline)
    return {
        "input_id": input_id,
        "a_score": baseline,
        "b_score": candidate,
        "absolute_difference": difference,
        "relative_difference_abs_over_abs_a": difference / abs(baseline) if baseline else None,
        "a_threshold_side": threshold_side(baseline),
        "b_threshold_side": threshold_side(candidate),
        "threshold_crossing": threshold_side(baseline) != threshold_side(candidate),
    }


def install_guards(output):
    forbidden = (ROOT / "dataset", ROOT / "test_data", ROOT.parent / "evaluation_private")
    attempts = {"network": 0, "forbidden_filesystem": 0}

    def within(path, parent):
        return path == parent or parent in path.parents

    def checked_path(value):
        if isinstance(value, (str, bytes, os.PathLike)):
            return Path(os.fsdecode(value)).resolve()
        return None

    def audit(event, arguments):
        if event in ("open", "os.listdir", "os.scandir") and arguments:
            path = checked_path(arguments[0])
            if path and (any(within(path, parent) for parent in forbidden) or "ground_truth" in path.parts):
                attempts["forbidden_filesystem"] += 1
                raise RuntimeError("DATASET_ACCESS_FORBIDDEN")
            if event == "open" and path:
                mode, flags = arguments[1:3]
                writing = isinstance(mode, str) and any(character in mode for character in "wax+")
                writing |= isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
                if writing and not within(path, output):
                    attempts["forbidden_filesystem"] += 1
                    raise RuntimeError("WRITE_OUTSIDE_EXPERIMENT_FORBIDDEN")
        if event in ("os.remove", "os.rmdir", "os.mkdir", "os.rename", "os.replace"):
            for value in arguments[:2] if event in ("os.rename", "os.replace") else arguments[:1]:
                path = checked_path(value)
                if path and not within(path, output):
                    attempts["forbidden_filesystem"] += 1
                    raise RuntimeError("MUTATION_OUTSIDE_EXPERIMENT_FORBIDDEN")
        if event == "subprocess.Popen":
            raise RuntimeError("SUBPROCESS_FORBIDDEN")

    def no_network(*arguments, **keywords):
        attempts["network"] += 1
        raise RuntimeError("NETWORK_FORBIDDEN")

    sys.addaudithook(audit)
    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    socket.socket.bind = no_network
    return attempts


def tensor_statistics(tensor):
    import torch

    values = tensor.detach().to(dtype=torch.float64, device="cpu")
    require(bool(torch.isfinite(values).all()), "NONFINITE_TENSOR")
    return {
        "shape": list(tensor.shape), "dtype": str(tensor.dtype), "device": str(tensor.device),
        "min": values.min().item(), "max": values.max().item(),
        "mean": values.mean().item(), "std_population": values.std(unbiased=False).item(),
    }


def model_fingerprint(model):
    digest = hashlib.sha256()
    for name, tensor in model.state_dict().items():
        require(tensor.device.type == "cpu", "NON_CPU_STATE")
        digest.update(name.encode())
        digest.update(str((tuple(tensor.shape), tensor.dtype)).encode())
        digest.update(tensor.detach().contiguous().numpy().tobytes())
    return digest.hexdigest()


def run_experiment(output, metadata):
    import numpy as np
    import torch
    import torchvision.transforms.v2 as transforms
    from anomalib.models import Patchcore
    from anomalib.models.components.feature_extractors import TimmFeatureExtractor
    from anomalib.models.image.patchcore.torch_model import PatchcoreModel
    from backend.ml.patchcore_inferencer import PatchCoreInferencer

    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    counters = metadata["forward_counts"]
    phase = {"loading": True}
    original_lightning = Patchcore.forward
    original_core = PatchcoreModel.forward
    original_features = TimmFeatureExtractor.forward

    def counted_lightning(model, *arguments, **keywords):
        require(not phase["loading"], "UNEXPECTED_LOADING_FORWARD")
        require(counters["lightning"] < FORWARD_LIMIT, "FORWARD_LIMIT_REACHED")
        counters["lightning"] += 1
        save_json(output / "experiment_metadata.json", metadata)
        require(not model.training and torch.is_inference_mode_enabled(), "UNSAFE_MODEL_MODE")
        return original_lightning(model, *arguments, **keywords)

    def counted_core(model, *arguments, **keywords):
        require(not phase["loading"], "UNEXPECTED_LOADING_CORE_FORWARD")
        require(counters["core"] < FORWARD_LIMIT, "CORE_FORWARD_LIMIT_REACHED")
        counters["core"] += 1
        require(not model.training, "CORE_TRAINING_FORBIDDEN")
        return original_core(model, *arguments, **keywords)

    def counted_features(model, *arguments, **keywords):
        require(not phase["loading"], "UNEXPECTED_LOADING_FEATURE_FORWARD")
        require(counters["features"] < FORWARD_LIMIT, "FEATURE_FORWARD_LIMIT_REACHED")
        counters["features"] += 1
        return original_features(model, *arguments, **keywords)

    Patchcore.forward = counted_lightning
    PatchcoreModel.forward = counted_core
    TimmFeatureExtractor.forward = counted_features
    try:
        wrapper = PatchCoreInferencer(
            ROOT / "models/patchcore/patchcore_bottle.ckpt",
            ROOT / "models/patchcore/model_metadata.json", device="cpu",
        )
        metadata["model_loads"] = 1
        phase["loading"] = False
        require(wrapper.memory_bank_shape == (9216, 384), "WRONG_MEMORY_BANK")
        require(not any(module.training for module in wrapper.model.modules()), "NOT_ALL_EVAL")
        require(not wrapper.model.model.embedding_store, "UNEXPECTED_EMBEDDINGS")
        original_transform = wrapper.transform
        external_steps = list(original_transform.transforms)
        require([type(step) for step in external_steps] == [
            transforms.Resize, transforms.ToImage, transforms.ToDtype, transforms.Normalize,
        ], "UNEXPECTED_EXTERNAL_PIPELINE")
        internal = wrapper.model.pre_processor.export_transform
        internal_steps = list(internal.transforms)
        require([type(step) for step in internal_steps] == [transforms.Resize, transforms.Normalize],
                "UNEXPECTED_INTERNAL_PIPELINE")
        candidate = copy.copy(wrapper)
        candidate.transform = transforms.Compose(external_steps[:-1])
        require(candidate.model is wrapper.model, "DIFFERENT_MODEL")
        require(all(left is right for left, right in zip(candidate.transform.transforms, external_steps[:-1])),
                "CHANGED_SHARED_TRANSFORMS")
        metadata["transforms"] = {
            "external_a": repr(original_transform), "external_b": repr(candidate.transform),
            "internal_transform": repr(wrapper.model.pre_processor.transform),
            "internal_export_transform": repr(internal),
        }
        metadata["package_versions"] = {name: version(name) for name in ("torch", "torchvision", "anomalib", "lightning", "timm")}
        postprocessor = wrapper.model.post_processor
        metadata["postprocessor"] = {"enabled": postprocessor is not None}
        if postprocessor is not None:
            metadata["postprocessor"]["enable_normalization"] = postprocessor.enable_normalization
            for name in ("image_min", "image_max", "_image_threshold"):
                value = float(getattr(postprocessor, name).detach().cpu().item())
                metadata["postprocessor"][name] = value if math.isfinite(value) else str(value)
        state_before = model_fingerprint(wrapper.model)
        metadata["model_state_before"] = state_before
        inputs = synthetic_inputs()
        repeated = synthetic_inputs()
        require(list(inputs) == ["SYN-001", "SYN-002", "SYN-003"], "INPUT_ALLOWLIST")
        for input_id, image in inputs.items():
            require(image.shape == (256, 256, 3) and image.dtype == np.uint8, "BAD_SYNTHETIC_INPUT")
            require(np.array_equal(image, repeated[input_id]), "NONDETERMINISTIC_INPUT")
        metadata["input_sha256"] = {name: hashlib.sha256(image.tobytes()).hexdigest() for name, image in inputs.items()}

        baseline_capture = {}

        def capture_baseline(model, arguments):
            baseline_capture["input"] = arguments[0].detach().clone()

        baseline_handle = wrapper.model.register_forward_pre_hook(capture_baseline)
        try:
            with torch.inference_mode():
                baseline = wrapper.predict(inputs["SYN-001"])
            threshold_side(baseline["anomaly_score"])
        finally:
            baseline_handle.remove()

        measurements = []
        comparisons = []
        for input_id, image in inputs.items():
            paired = {}
            tensors = {}
            for path_name, selected in (("A", wrapper), ("B", candidate)):
                observed = {"input_id": input_id, "path": path_name, "normalizations": []}
                captured = {}
                handles = []

                def capture_output(name):
                    def callback(module, arguments, returned):
                        captured[name] = returned.detach().clone()
                    return callback

                def capture_input(module, arguments):
                    captured["backbone_input"] = arguments[0].detach().clone()

                def capture_model_input(module, arguments):
                    captured["model_input"] = arguments[0].detach().clone()

                def capture_core_score(module, arguments, returned):
                    observed["core_score"] = float(returned.pred_score.detach().cpu().item())

                def count_normalize(location):
                    def callback(module, arguments, returned):
                        observed["normalizations"].append(location)
                    return callback

                handles.append(external_steps[2].register_forward_hook(capture_output("scaled_rgb")))
                handles.append(external_steps[0].register_forward_hook(
                    lambda module, arguments, returned: observed.update({"resize_size": list(returned.size)})
                ))
                handles.append(external_steps[-1].register_forward_hook(count_normalize("external")))
                handles.append(internal_steps[-1].register_forward_hook(count_normalize("internal_export")))
                handles.append(wrapper.model.register_forward_pre_hook(capture_model_input))
                handles.append(wrapper.model.pre_processor.register_forward_hook(capture_output("internal_output")))
                handles.append(wrapper.model.model.feature_extractor.register_forward_pre_hook(capture_input))
                handles.append(wrapper.model.model.register_forward_hook(capture_core_score))
                try:
                    with torch.inference_mode():
                        result = selected.predict(image)
                    score = float(result["anomaly_score"])
                    threshold_side(score)
                    require(math.isfinite(observed["core_score"]), "NONFINITE_CORE_SCORE")
                    for name, tensor in captured.items():
                        expected_shape = (3, 256, 256) if name == "scaled_rgb" else (1, 3, 256, 256)
                        require(tuple(tensor.shape) == expected_shape, "BAD_TENSOR_SHAPE")
                        require(tensor.dtype == torch.float32 and tensor.device.type == "cpu", "BAD_TENSOR_TYPE")
                    expected_order = ["external", "internal_export"] if path_name == "A" else ["internal_export"]
                    require(observed["normalizations"] == expected_order, "WRONG_NORMALIZE_CALLS")
                    rgb_reference = torch.from_numpy(image[:, :, ::-1].copy()).permute(2, 0, 1).float().div(255).unsqueeze(0)
                    torch.testing.assert_close(captured["scaled_rgb"].unsqueeze(0), rgb_reference, rtol=0, atol=1e-7)
                finally:
                    for handle in handles:
                        handle.remove()
                if input_id == "SYN-001" and path_name == "A":
                    require(torch.equal(captured["model_input"], baseline_capture["input"]), "BASELINE_TENSOR_MISMATCH")
                    require(math.isclose(score, baseline["anomaly_score"], rel_tol=SCORE_RTOL, abs_tol=SCORE_ATOL),
                            "BASELINE_SCORE_MISMATCH")
                    require(np.array_equal(result["anomaly_map"], baseline["anomaly_map"]), "INSTRUMENTATION_MAP_MISMATCH")
                    metadata["wrapper_equivalence"] = {
                        "input_id": input_id, "tensor_exact": True, "map_exact": True,
                        "wrapper_score": baseline["anomaly_score"], "a_score": score,
                        "absolute_score_difference": abs(score - baseline["anomaly_score"]),
                        "rtol": SCORE_RTOL, "atol": SCORE_ATOL,
                    }
                require(torch.equal(captured["internal_output"], captured["backbone_input"]), "BACKBONE_BOUNDARY_MISMATCH")
                observed["boundaries"] = {name: tensor_statistics(tensor) for name, tensor in captured.items()}
                observed["loader"] = {"shape": list(image.shape), "dtype": str(image.dtype), "channel_order": "BGR"}
                observed["score"] = score
                observed["normalize_count"] = len(observed["normalizations"])
                paired[path_name] = score
                tensors[path_name] = captured
                measurements.append(observed)
            require(torch.equal(tensors["A"]["scaled_rgb"], tensors["B"]["scaled_rgb"]), "DIFFERENT_SCALED_INPUT")
            require(torch.equal(tensors["B"]["model_input"], tensors["B"]["scaled_rgb"].unsqueeze(0)), "CANDIDATE_SCALE_MISMATCH")
            mean = torch.tensor([0.485, 0.456, 0.406]).reshape(1, 3, 1, 1)
            std = torch.tensor([0.229, 0.224, 0.225]).reshape(1, 3, 1, 1)
            require(torch.equal(tensors["A"]["model_input"], (tensors["B"]["model_input"] - mean) / std),
                    "MORE_THAN_EXTERNAL_NORMALIZE_CHANGED")
            comparisons.append(compare_scores(input_id, paired["A"], paired["B"]))
            save_json(output / "tensor_statistics.json", measurements)
            save_json(output / "score_comparison.json", comparisons)
        state_after = model_fingerprint(wrapper.model)
        require(state_before == state_after, "MODEL_STATE_CHANGED")
        require(not wrapper.model.model.embedding_store, "EMBEDDING_STORE_CHANGED")
        require(counters == {"lightning": 7, "core": 7, "features": 7}, "UNEXPECTED_FORWARD_COUNTS")
        metadata["model_state_after"] = state_after
        metadata["validations"] = {
            "synthetic_reproducibility": True, "same_scaled_rgb": True,
            "color_order_reference": True, "only_external_normalize_removed": True,
            "float32_cpu_bchw": True, "normalize_calls_observed": True,
            "internal_output_equals_backbone_input": True, "model_state_unchanged": True,
        }
        return comparisons
    finally:
        Patchcore.forward = original_lightning
        PatchcoreModel.forward = original_core
        TimmFeatureExtractor.forward = original_features


def save_json(path, value):
    serialized = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    json.loads(serialized)
    path.write_text(serialized + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name", required=True)
    arguments = parser.parse_args()
    require(arguments.run_name.replace("-", "").replace("_", "").isalnum(), "INVALID_RUN_NAME")
    output = (ROOT / "data/outputs/experiments/patchcore_synthetic_ab" / arguments.run_name).resolve()
    output.mkdir(parents=True, exist_ok=False)
    temporary = output / "temporary"
    temporary.mkdir()
    for key in ("TEMP", "TMP", "TMPDIR"):
        os.environ[key] = str(temporary)
    tempfile.tempdir = str(temporary)
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "CUDA_VISIBLE_DEVICES": "",
                       "PYTHONDONTWRITEBYTECODE": "1", "MPLCONFIGDIR": str(output / "matplotlib")})
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    platform.uname()
    protected = {name: file_hash(ROOT / name) for name in (
        "models/patchcore/patchcore_bottle.ckpt", "models/patchcore/model_metadata.json",
        "backend/ml/patchcore_inferencer.py", "backend/config.py",
        "data/inspections.jsonl", "data/inspection_logs.jsonl",
    )}
    require(protected["models/patchcore/patchcore_bottle.ckpt"] == CHECKPOINT_SHA256, "CHECKPOINT_HASH_MISMATCH")
    metadata = {
        "status": "RUNNING", "created_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint_sha256": CHECKPOINT_SHA256, "threshold": THRESHOLD,
        "forward_limit": FORWARD_LIMIT, "forward_counts": {"lightning": 0, "core": 0, "features": 0},
        "model_loads": 0, "purpose": "synthetic preprocessing diagnostic, not calibration or product evaluation",
        "script_sha256": file_hash(Path(__file__)),
        "tolerance_basis": "float32 CPU repeat, approximately one relative epsilon; exact Tensor/map required",
    }
    metadata["guard_attempts"] = install_guards(output)
    try:
        comparisons = run_experiment(output, metadata)
        require(all(file_hash(ROOT / name) == digest for name, digest in protected.items()), "PROTECTED_FILE_CHANGED")
        require(metadata["guard_attempts"] == {"network": 0, "forbidden_filesystem": 0}, "UNEXPECTED_GUARD_ATTEMPT")
        metadata["protected_files_unchanged"] = True
        metadata["status"] = "COMPLETE"
        summary = ["# Synthetic preprocessing diagnostic", "", "Not a product evaluation or calibration.", "",
                   "| Input | A score | B score | Absolute difference | Crossing |", "|---|---:|---:|---:|---|"]
        for row in comparisons:
            summary.append(f"| {row['input_id']} | {row['a_score']:.8f} | {row['b_score']:.8f} | {row['absolute_difference']:.8f} | {row['threshold_crossing']} |")
        (output / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
        print(json.dumps({"status": metadata["status"], "forward_counts": metadata["forward_counts"], "scores": comparisons}))
    except Exception as error:
        metadata["status"] = "STOPPED"
        metadata["error_type"] = type(error).__name__
        metadata["error_code"] = str(error) if isinstance(error, RuntimeError) and str(error).replace("_", "").isalnum() else "EXPERIMENT_ERROR"
        print(json.dumps({"status": "STOPPED", "error_type": metadata["error_type"], "error_code": metadata["error_code"],
                          "forward_counts": metadata["forward_counts"]}))
        raise SystemExit(1) from None
    finally:
        save_json(output / "experiment_metadata.json", metadata)


if __name__ == "__main__":
    main()
