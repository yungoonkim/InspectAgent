"""
VisionInsight - Day 3.5 Prompt 7
CPU 리소스 및 지연시간 실측 스크립트

측정 항목:
1. 모델 최초 로딩 시간 (ms)
2. 모델 로딩 전후 프로세스 메모리 사용량 (MB)
3. FastAPI lifespan 기반 서버 프로세스 메모리 사용량 (MB)
4. 단일 이미지 추론 시간 (ms)
5. 반복 추론 평균 시간 (ms, n=20)
6. 정상(T01) 및 불량(T06) 이미지 간 추론 시간 비교 (ms)
7. 첫 번째 API 검사 요청 응답 시간 (ms)
8. 모델 재사용 이후 API 검사 요청 평균 응답 시간 (ms, n=10)
9. CPU 사용량 및 메모리 피크
"""

import os
import sys
import time
import statistics
import cv2
import numpy as np
import ctypes
from ctypes import wintypes

# Windows API for memory measurement without external psutil dependency
class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]

def get_memory_usage_mb():
    try:
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        fn = ctypes.windll.kernel32.K32GetProcessMemoryInfo
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
        fn.restype = wintypes.BOOL
        if fn(handle, ctypes.byref(counters), ctypes.sizeof(counters)):
            return counters.WorkingSetSize / (1024 * 1024)
    except Exception:
        pass
    return 0.0

# 프로젝트 루트를 sys.path에 추가
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.ml.patchcore_inferencer import get_patchcore_inferencer
from fastapi.testclient import TestClient
from backend.main import app

def run_cpu_benchmark():
    print("=" * 60)
    print("VisionInsight CPU Resource & Latency Benchmark (Prompt 7)")
    print("=" * 60)

    # 1. 모델 로딩 전 메모리
    mem_before_load = get_memory_usage_mb()
    print(f"[1] Memory before model load: {mem_before_load:.2f} MB")

    # 2. 모델 최초 로딩 시간 측정
    t0 = time.perf_counter()
    inferencer = get_patchcore_inferencer()
    t1 = time.perf_counter()
    model_load_time_ms = (t1 - t0) * 1000.0

    mem_after_load = get_memory_usage_mb()
    mem_diff_load = mem_after_load - mem_before_load
    print(f"[2] Model initial load time: {model_load_time_ms:.2f} ms")
    print(f"[3] Memory after model load: {mem_after_load:.2f} MB (Delta: +{mem_diff_load:.2f} MB)")

    # 3. 모델 버전 및 호환성 검증
    compat_res = inferencer.verify_compatibility(expected_threshold=34.1442)
    compat_ok = compat_res["verified"]
    compat_msg = "; ".join(compat_res["reasons"]) if compat_res["reasons"] else "OK (SHA256, memory bank, and threshold aligned)"
    print(f"[4] Model compatibility check: {compat_ok} ({compat_msg})")
    print(f"     Checkpoint SHA256: {compat_res.get('checkpoint_sha256')}")

    # 4. 이미지 준비 (정상 T01, 불량 T06)
    good_img_path = os.path.join(project_root, "dataset", "bottle", "test", "good", "000.png")
    defect_img_path = os.path.join(project_root, "dataset", "bottle", "test", "broken_large", "000.png")

    if not os.path.exists(good_img_path):
        # 만약 없으면 train/good 사용
        good_img_path = os.path.join(project_root, "dataset", "bottle", "train", "good", "000.png")

    good_img = cv2.imread(good_img_path)
    defect_img = cv2.imread(defect_img_path)

    # 5. 첫 번째 단일 이미지 추론 시간 (Warm-up)
    t0 = time.perf_counter()
    pred_first = inferencer.predict(good_img)
    t1 = time.perf_counter()
    first_infer_time_ms = (t1 - t0) * 1000.0
    print(f"[5] First inference latency (good image): {first_infer_time_ms:.2f} ms (Internal: {pred_first['inference_time_ms']:.2f} ms, Score: {pred_first['anomaly_score']:.4f})")

    # 6. 정상 이미지 반복 추론 (n=20)
    good_latencies = []
    for _ in range(20):
        t0 = time.perf_counter()
        pred = inferencer.predict(good_img)
        t1 = time.perf_counter()
        good_latencies.append(pred["inference_time_ms"])

    good_mean = statistics.mean(good_latencies)
    good_std = statistics.stdev(good_latencies)
    good_min = min(good_latencies)
    good_max = max(good_latencies)
    print(f"[6] Good image 20-run latency: Mean={good_mean:.2f} ms, Min={good_min:.2f} ms, Max={good_max:.2f} ms, Std={good_std:.2f} ms")

    # 7. 불량 이미지 반복 추론 (n=20)
    defect_latencies = []
    for _ in range(20):
        t0 = time.perf_counter()
        pred = inferencer.predict(defect_img)
        t1 = time.perf_counter()
        defect_latencies.append(pred["inference_time_ms"])

    defect_mean = statistics.mean(defect_latencies)
    defect_std = statistics.stdev(defect_latencies)
    defect_min = min(defect_latencies)
    defect_max = max(defect_latencies)
    print(f"[7] Defect image 20-run latency: Mean={defect_mean:.2f} ms, Min={defect_min:.2f} ms, Max={defect_max:.2f} ms, Std={defect_std:.2f} ms")

    diff_mean = abs(good_mean - defect_mean)
    print(f"[8] Difference between Normal and Defect latency: {diff_mean:.2f} ms")

    mem_after_infer = get_memory_usage_mb()
    print(f"[9] Memory after repeated inference: {mem_after_infer:.2f} MB")

    # 8. FastAPI TestClient 기반 End-to-End API 응답 시간 측정
    print("\n" + "-" * 40)
    print("FastAPI E2E API Request Latency Benchmark")
    print("-" * 40)

    with TestClient(app) as client:
        # GET /health
        resp_health = client.get("/health")
        print(f"[10] GET /health status: {resp_health.status_code}, data: {resp_health.json()}")

        # GET /inspections/images to find valid image IDs
        resp_imgs = client.get("/inspections/images")
        images_data = resp_imgs.json().get("images", [])
        good_img_id = images_data[0]["image_id"] if images_data else "IMG-BOTTLE-0001"
        defect_img_id = images_data[-1]["image_id"] if len(images_data) > 1 else good_img_id
        print(f"     Retrieved {len(images_data)} image mappings. Using Good={good_img_id}, Defect={defect_img_id}")

        # First POST /inspections (Warm-up)
        t0 = time.perf_counter()
        resp_first = client.post("/inspections", json={"product_id": "PROD-BENCH-001", "image_id": good_img_id})
        t1 = time.perf_counter()
        first_api_latency_ms = (t1 - t0) * 1000.0
        first_data = resp_first.json()
        print(f"[11] First POST /inspections ({good_img_id}) latency: {first_api_latency_ms:.2f} ms")
        print(f"     Status: {resp_first.status_code}, result: {first_data.get('result')}, final_result: {first_data.get('final_result')}, score: {first_data.get('anomaly_score')}")

        # Repeated POST /inspections (Good, n=10)
        api_latencies_good = []
        for _ in range(10):
            t0 = time.perf_counter()
            resp = client.post("/inspections", json={"product_id": "PROD-BENCH-001", "image_id": good_img_id})
            t1 = time.perf_counter()
            api_latencies_good.append((t1 - t0) * 1000.0)

        api_good_mean = statistics.mean(api_latencies_good)
        print(f"[12] Repeated POST /inspections ({good_img_id}, n=10): Mean={api_good_mean:.2f} ms, Min={min(api_latencies_good):.2f} ms, Max={max(api_latencies_good):.2f} ms")

        # Repeated POST /inspections (Defect, n=10)
        api_latencies_defect = []
        for _ in range(10):
            t0 = time.perf_counter()
            resp = client.post("/inspections", json={"product_id": "PROD-BENCH-001", "image_id": defect_img_id})
            t1 = time.perf_counter()
            api_latencies_defect.append((t1 - t0) * 1000.0)

        api_defect_mean = statistics.mean(api_latencies_defect)
        print(f"[13] Repeated POST /inspections ({defect_img_id}, n=10): Mean={api_defect_mean:.2f} ms, Min={min(api_latencies_defect):.2f} ms, Max={max(api_latencies_defect):.2f} ms")

    total_proc_mem = get_memory_usage_mb()
    print(f"\n[14] Final Process Total RSS Memory: {total_proc_mem:.2f} MB")
    print("=" * 60)

if __name__ == "__main__":
    run_cpu_benchmark()
