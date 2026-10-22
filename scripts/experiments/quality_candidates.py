"""A-2 exploratory measurements only; no quality classification or runtime dependency."""

import cv2
import numpy as np

from scripts.experiments.analyze_quality_baseline import partitions


def checked_image(image):
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8:
        raise ValueError("UINT8_IMAGE_REQUIRED")
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.size else image
    if image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) < 3:
        raise ValueError("BGR_OR_GRAY_IMAGE_AT_LEAST_3X3_REQUIRED")
    return image


def sample_statistics(gray, mask):
    sample = gray[mask]
    if not sample.size:
        return None
    return {"pixels": int(sample.size), "area_fraction": float(mask.mean()),
            "mean_gv": float(sample.mean()), "median_gv": float(np.median(sample)),
            "std_gv": float(sample.std())}


def normalized_sharpness(gray, mask=None):
    selection = np.ones(gray.shape, bool) if mask is None else mask
    if not selection.any():
        return {"status": "NO_PIXELS", "laplacian_variance": None, "tenengrad": None,
                "laplacian_over_gray_variance": None, "tenengrad_over_gray_variance": None}
    laplacian = cv2.Laplacian(gray, cv2.CV_64F, ksize=3)
    gradient_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    variance = float(gray[selection].var())
    laplacian_variance = float(laplacian[selection].var())
    tenengrad = float((gradient_x ** 2 + gradient_y ** 2)[selection].mean())
    return {"status": "AVAILABLE_UNCALIBRATED" if variance > 1e-12 else "UNAVAILABLE_ZERO_CONTRAST",
            "laplacian_variance": laplacian_variance, "tenengrad": tenengrad,
            "laplacian_over_gray_variance": laplacian_variance / variance if variance > 1e-12 else None,
            "tenengrad_over_gray_variance": tenengrad / variance if variance > 1e-12 else None}


def highlight_statistics(gray, foreground):
    high = (gray >= 245).astype(np.uint8)
    count, labels, statistics, _ = cv2.connectedComponentsWithStats(high, connectivity=8)
    largest = np.zeros_like(high, dtype=bool)
    if count > 1:
        selected = 1 + int(np.argmax(statistics[1:, cv2.CC_STAT_AREA]))
        largest = labels == selected
    ring = (cv2.dilate(largest.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & ~largest
    floating = gray.astype(np.float64)
    local_mean = cv2.boxFilter(floating, -1, (5, 5))
    local_variance = np.maximum(cv2.boxFilter(floating * floating, -1, (5, 5)) - local_mean ** 2, 0)
    gradient_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    edge_magnitude = np.sqrt(gradient_x ** 2 + gradient_y ** 2)
    return {
        "ge245_fraction": float(high.mean()), "ge250_fraction": float((gray >= 250).mean()),
        "ge254_fraction": float((gray >= 254).mean()), "component_count_ge245": count - 1,
        "largest_component_pixels": int(largest.sum()), "largest_component_fraction": float(largest.mean()),
        "largest_component_touches_border": bool(largest[0].any() or largest[-1].any() or largest[:, 0].any() or largest[:, -1].any()),
        "largest_component_std": float(gray[largest].std()) if largest.any() else None,
        "largest_component_local_std_median": float(np.median(np.sqrt(local_variance[largest]))) if largest.any() else None,
        "surrounding_edge_mean": float(edge_magnitude[ring].mean()) if ring.any() else None,
        "local_std_median_5x5": float(np.median(np.sqrt(local_variance))),
        "foreground_ge245_fraction": float((gray[foreground] >= 245).mean()) if foreground is not None else None,
        "background_ge245_fraction": float((gray[~foreground] >= 245).mean()) if foreground is not None and (~foreground).any() else None,
        "interpretation": "DIGITAL_HIGHLIGHT_MEASUREMENTS_NOT_OVEREXPOSURE_VERDICT",
    }


def measure(image):
    image = checked_image(image)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    quantiles = np.percentile(gray, [10, 25, 50, 75, 90])
    central = np.zeros_like(gray, dtype=bool)
    top, left = height // 4, width // 4
    central[top:height - top, left:width - left] = True
    side = min(96, height, width)
    fixed = np.zeros_like(gray, dtype=bool)
    fixed_top, fixed_left = (height - side) // 2, (width - side) // 2
    fixed[fixed_top:fixed_top + side, fixed_left:fixed_left + side] = True
    segments, masks = partitions(image)
    foreground = masks.get("closed_gray207_contour")
    failure = segments["closed_gray207_contour"]["status"]
    contours, _ = cv2.findContours((gray < 207).astype(np.uint8) * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if sum(cv2.contourArea(contour) >= gray.size * 0.1 for contour in contours) > 1:
        foreground = None
        failure = "UNAVAILABLE_MULTIPLE_LARGE_COMPONENTS"
    foreground_details = sample_statistics(gray, foreground) if foreground is not None else None
    background_details = sample_statistics(gray, ~foreground) if foreground is not None else None
    central_details, edge_details = sample_statistics(gray, central), sample_statistics(gray, ~central)
    return {
        "width": width, "height": height, "mean_gv": float(gray.mean()), "median_gv": float(quantiles[2]),
        "std_gv": float(gray.std()), "p10": float(quantiles[0]), "p25": float(quantiles[1]),
        "p75": float(quantiles[3]), "p90": float(quantiles[4]), "below125_fraction": float((gray < 125).mean()),
        "bright_ge200_fraction": float((gray >= 200).mean()), "contrast_p90_p10": float(quantiles[4] - quantiles[0]),
        "center_fraction50": central_details, "edge_fraction50": edge_details,
        "edge_minus_center_gv": edge_details["mean_gv"] - central_details["mean_gv"] if edge_details else None,
        "center_fixed96": sample_statistics(gray, fixed), "center_fixed_side": side,
        "center_fixed_sharpness": normalized_sharpness(gray, fixed), "sharpness": normalized_sharpness(gray),
        "segmentation": {"status": failure, "foreground": foreground_details, "background": background_details,
                         "confidence": "NOT_CALIBRATED_NOT_A_SEGMENTATION_GROUND_TRUTH",
                         "foreground_sharpness": normalized_sharpness(gray, foreground) if foreground is not None else None},
        "highlights": highlight_statistics(gray, foreground),
        "limitations": ["No exposure, focus or defect ground truth", "Center may miss rim or off-center bottle",
                        "Derivatives depend on scale, noise and ROI composition; normalization is not a blur classifier"],
    }


def crop_region(frame, roi):
    frame = checked_image(frame)
    if set(roi) != {"x", "y", "width", "height"} or any(type(value) is not int for value in roi.values()):
        raise ValueError("INTEGER_X_Y_WIDTH_HEIGHT_REQUIRED")
    left, top, width, height = (roi[key] for key in ("x", "y", "width", "height"))
    if min(left, top) < 0 or min(width, height) < 3 or left + width > frame.shape[1] or top + height > frame.shape[0]:
        raise ValueError("ROI_OUT_OF_BOUNDS_OR_TOO_SMALL")
    return frame[top:top + height, left:left + width].copy()


def variants(image):
    image = checked_image(image)
    floating = image.astype(np.float64)
    center = floating.mean(axis=(0, 1), keepdims=True)
    noise = np.random.default_rng(20261020).normal(0, 2, image.shape)
    success, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not success:
        raise ValueError("JPEG_SIMULATION_FAILED")
    result = {
        "original": image.copy(), "blur_sigma1": cv2.GaussianBlur(image, (0, 0), 1),
        "blur_sigma2": cv2.GaussianBlur(image, (0, 0), 2),
        "gain_half": (floating * 0.5).astype(np.uint8),
        "contrast_half": np.clip(center + (floating - center) * 0.5, 0, 255).astype(np.uint8),
        "blur2_gain_half": (cv2.GaussianBlur(image, (0, 0), 2).astype(float) * 0.5).astype(np.uint8),
        "clipping_gain1_8": np.clip(floating * 1.8, 0, 255).astype(np.uint8),
        "noise_sigma2": np.clip(floating + noise, 0, 255).astype(np.uint8),
        "jpeg_quality80": cv2.imdecode(encoded, cv2.IMREAD_COLOR),
    }
    if min(image.shape[:2]) >= 6:
        result["half_resolution"] = cv2.resize(image, (image.shape[1] // 2, image.shape[0] // 2), interpolation=cv2.INTER_AREA)
    return result
