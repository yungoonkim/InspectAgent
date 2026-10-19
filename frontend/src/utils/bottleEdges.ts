export type EdgePoint = { x: number; y: number };
export type EdgeSegment = [EdgePoint, EdgePoint];
export interface RegionBrightness {
  mean: number;
  median: number;
  std: number;
  pixels: number;
  areaRatio: number;
}
export interface EdgeAssessment {
  status: 'SUCCESS' | 'UNCERTAIN' | 'FAILED';
  reasons: string[];
  closed: boolean;
  components: number;
  perimeter: number;
  circularity: number | null;
  referenceRadius: number | null;
  radialRms: number | null;
  radialMax: number | null;
  coverage: number;
  largestGapDegrees: number | null;
}
export interface BottleEdges {
  status: 'SUCCESS' | 'UNCERTAIN' | 'FAILED';
  reasons: string[];
  width: number;
  height: number;
  outer: EdgeSegment[];
  rim: EdgeSegment[];
  assessment: { outer: EdgeAssessment; rim: EdgeAssessment };
  regions: { roi: RegionBrightness | null; body: RegionBrightness | null;
    rim: RegionBrightness | null; background: RegionBrightness | null };
  statistics: { threshold: number; area: number; roiMean: number; bodyMean: number | null;
    backgroundMean: number | null; rimSupport: number; contrastStd: number };
}

function emptyAssessment(): EdgeAssessment {
  return { status: 'FAILED', reasons: ['NO_OBSERVED_CONTOUR'], closed: false, components: 0,
    perimeter: 0, circularity: null, referenceRadius: null, radialRms: null, radialMax: null,
    coverage: 0, largestGapDegrees: null };
}

function brightness(gray: Uint8Array, mask?: Uint8Array, selected = 1): RegionBrightness | null {
  const histogram = new Uint32Array(256);
  let pixels = 0;
  let total = 0;
  let squares = 0;
  for (let index = 0; index < gray.length; index++) {
    if (mask && mask[index] !== selected) continue;
    const value = gray[index];
    histogram[value]++; pixels++; total += value; squares += value * value;
  }
  if (!pixels) return null;
  let cumulative = 0;
  let lower = -1;
  let upper = 0;
  for (let value = 0; value < 256; value++) {
    cumulative += histogram[value];
    if (lower < 0 && cumulative > Math.floor((pixels - 1) / 2)) lower = value;
    if (cumulative > Math.floor(pixels / 2)) { upper = value; break; }
  }
  const mean = total / pixels;
  return { mean, median: (lower + upper) / 2, std: Math.sqrt(Math.max(0, squares / pixels - mean ** 2)),
    pixels, areaRatio: pixels / gray.length };
}

function contourAssessment(segments: EdgeSegment[], area: number, center: EdgePoint): EdgeAssessment {
  const result = emptyAssessment();
  if (!segments.length) return result;
  const graph = new Map<string, string[]>();
  const key = (point: EdgePoint) => `${point.x},${point.y}`;
  const referenceRadius = Math.sqrt(area / Math.PI);
  let squaredDeviation = 0;
  let maximumDeviation = 0;
  for (const [first, second] of segments) {
    const firstKey = key(first);
    const secondKey = key(second);
    graph.set(firstKey, [...(graph.get(firstKey) ?? []), secondKey]);
    graph.set(secondKey, [...(graph.get(secondKey) ?? []), firstKey]);
    result.perimeter += Math.hypot(first.x - second.x, first.y - second.y);
    const deviation = Math.abs(Math.hypot((first.x + second.x) / 2 - center.x,
      (first.y + second.y) / 2 - center.y) - referenceRadius);
    squaredDeviation += deviation ** 2;
    maximumDeviation = Math.max(maximumDeviation, deviation);
  }
  const visited = new Set<string>();
  for (const start of graph.keys()) {
    if (visited.has(start)) continue;
    result.components++;
    const pending = [start];
    visited.add(start);
    while (pending.length) {
      for (const neighbor of graph.get(pending.pop()!) ?? []) {
        if (!visited.has(neighbor)) { visited.add(neighbor); pending.push(neighbor); }
      }
    }
  }
  result.closed = result.components === 1 && [...graph.values()].every(neighbors => neighbors.length === 2);
  result.reasons = result.closed ? [] : ['CONTOUR_OPEN_OR_AMBIGUOUS'];
  result.status = result.closed ? 'SUCCESS' : 'UNCERTAIN';
  result.coverage = result.closed ? 1 : 0;
  result.referenceRadius = referenceRadius;
  result.radialRms = Math.sqrt(squaredDeviation / segments.length);
  result.radialMax = maximumDeviation;
  result.circularity = result.closed ? 4 * Math.PI * area / result.perimeter ** 2 : null;
  return result;
}

function polygonMask(points: EdgePoint[], width: number, height: number): Uint8Array {
  const mask = new Uint8Array(width * height);
  for (let row = 0; row < height; row++) {
    const intersections: number[] = [];
    for (let index = 0; index < points.length; index++) {
      const first = points[index];
      const second = points[(index + 1) % points.length];
      if ((first.y > row + 0.5) !== (second.y > row + 0.5)) {
        intersections.push(first.x + (row + 0.5 - first.y) * (second.x - first.x) / (second.y - first.y));
      }
    }
    intersections.sort((first, second) => first - second);
    for (let index = 0; index + 1 < intersections.length; index += 2) {
      for (let column = Math.max(0, Math.ceil(intersections[index] - 0.5));
        column < width && column + 0.5 < intersections[index + 1]; column++) mask[row * width + column] = 1;
    }
  }
  return mask;
}

export function detectBottleEdges(image: Pick<ImageData, 'width' | 'height' | 'data'>): BottleEdges {
  const { width, height, data } = image;
  const size = width * height;
  const result: BottleEdges = { status: 'FAILED', reasons: [], width, height, outer: [], rim: [],
    assessment: { outer: emptyAssessment(), rim: emptyAssessment() },
    regions: { roi: null, body: null, rim: null, background: null },
    statistics: { threshold: 0, area: 0, roiMean: 0, bodyMean: null, backgroundMean: null, rimSupport: 0, contrastStd: 0 } };
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 24 || height < 24 || size > 4_000_000
    || data.length !== size * 4) return { ...result, reasons: ['INVALID_IMAGE_SIZE'] };
  const gray = new Uint8Array(size);
  const measurementGray = new Uint8Array(size);
  const histogram = new Uint32Array(256);
  let total = 0;
  let squares = 0;
  for (let index = 0; index < size; index++) {
    const value = Math.round(data[index * 4] * 0.299 + data[index * 4 + 1] * 0.587 + data[index * 4 + 2] * 0.114);
    gray[index] = value; histogram[value]++; total += value; squares += value * value;
    measurementGray[index] = (data[index * 4] * 9798 + data[index * 4 + 1] * 19235
      + data[index * 4 + 2] * 3735 + 16384) >> 15;
  }
  result.regions.roi = brightness(measurementGray);
  result.statistics.roiMean = result.regions.roi!.mean;
  result.statistics.contrastStd = Math.sqrt(Math.max(0, squares / size - (total / size) ** 2));
  if (result.statistics.contrastStd < 3) return { ...result, reasons: ['NO_IMAGE_CONTRAST'] };
  let belowCount = 0;
  let belowSum = 0;
  let maximumVariance = -1;
  let threshold = 0;
  for (let level = 0; level < 255; level++) {
    belowCount += histogram[level]; belowSum += histogram[level] * level;
    if (!belowCount || belowCount === size) continue;
    const difference = belowSum / belowCount - (total - belowSum) / (size - belowCount);
    const variance = belowCount * (size - belowCount) * difference * difference;
    if (variance > maximumVariance) { maximumVariance = variance; threshold = level; }
  }
  result.statistics.threshold = threshold;
  const labels = new Int32Array(size);
  const queue = new Int32Array(size);
  let component = 0;
  let largestId = 0;
  let largestArea = 0;
  let secondArea = 0;
  const neighbors = (index: number) => {
    const column = index % width;
    return [column ? index - 1 : -1, column + 1 < width ? index + 1 : -1,
      index >= width ? index - width : -1, index + width < size ? index + width : -1];
  };
  for (let start = 0; start < size; start++) {
    if (labels[start] || gray[start] > threshold) continue;
    component++;
    let head = 0;
    let tail = 1;
    queue[0] = start; labels[start] = component;
    while (head < tail) {
      for (const neighbor of neighbors(queue[head++])) {
        if (neighbor >= 0 && !labels[neighbor] && gray[neighbor] <= threshold) {
          labels[neighbor] = component; queue[tail++] = neighbor;
        }
      }
    }
    if (tail > largestArea) { secondArea = largestArea; largestArea = tail; largestId = component; }
    else secondArea = Math.max(secondArea, tail);
  }
  if (largestArea < size * 0.08 || largestArea > size * 0.93) return { ...result, reasons: ['NO_ISOLATED_BODY'] };
  const outside = new Uint8Array(size);
  let head = 0;
  let tail = 0;
  const seed = (index: number) => {
    if (!outside[index] && labels[index] !== largestId) { outside[index] = 1; queue[tail++] = index; }
  };
  for (let column = 0; column < width; column++) { seed(column); seed(size - width + column); }
  for (let row = 0; row < height; row++) { seed(row * width); seed(row * width + width - 1); }
  while (head < tail) for (const neighbor of neighbors(queue[head++])) if (neighbor >= 0) seed(neighbor);
  let area = 0;
  let sumX = 0;
  let sumY = 0;
  let bodySum = 0;
  let minimumX = width;
  let minimumY = height;
  let maximumX = 0;
  let maximumY = 0;
  for (let index = 0; index < size; index++) {
    if (outside[index]) continue;
    const column = index % width;
    const row = Math.floor(index / width);
    area++; sumX += column; sumY += row; bodySum += gray[index];
    minimumX = Math.min(minimumX, column); maximumX = Math.max(maximumX, column);
    minimumY = Math.min(minimumY, row); maximumY = Math.max(maximumY, row);
    if (column > 0 && outside[index - 1]) result.outer.push([{ x: column, y: row }, { x: column, y: row + 1 }]);
    if (column + 1 < width && outside[index + 1]) result.outer.push([{ x: column + 1, y: row }, { x: column + 1, y: row + 1 }]);
    if (row > 0 && outside[index - width]) result.outer.push([{ x: column, y: row }, { x: column + 1, y: row }]);
    if (row + 1 < height && outside[index + width]) result.outer.push([{ x: column, y: row + 1 }, { x: column + 1, y: row + 1 }]);
  }
  result.statistics.area = area;
  result.statistics.bodyMean = area ? bodySum / area : null;
  result.statistics.backgroundMean = area < size ? (total - bodySum) / (size - area) : null;
  if (!area || !result.outer.length) return { ...result, outer: [], reasons: ['NO_OBSERVED_OUTER_EDGE'],
    statistics: { ...result.statistics, bodyMean: null, backgroundMean: null } };
  if (minimumX === 0 || minimumY === 0 || maximumX === width - 1 || maximumY === height - 1) result.reasons.push('BODY_CLIPPED');
  if (secondArea > largestArea * 0.3) result.reasons.push('MULTIPLE_BODY_CANDIDATES');
  if (result.statistics.contrastStd < 12) result.reasons.push('LOW_CONTRAST');
  const aspect = (maximumX - minimumX + 1) / (maximumY - minimumY + 1);
  if (aspect < 0.65 || aspect > 1.55) result.reasons.push('IRREGULAR_BODY_SHAPE');
  const centerX = sumX / area;
  const centerY = sumY / area;
  const radius = Math.min(maximumX - minimumX + 1, maximumY - minimumY + 1) / 2;
  const sample = (column: number, row: number): number | null => {
    const pixelX = Math.round(column);
    const pixelY = Math.round(row);
    if (pixelX < 1 || pixelY < 1 || pixelX >= width - 1 || pixelY >= height - 1) return null;
    let sum = 0;
    for (let offsetY = -1; offsetY <= 1; offsetY++) for (let offsetX = -1; offsetX <= 1; offsetX++) {
      sum += gray[(pixelY + offsetY) * width + pixelX + offsetX];
    }
    return sum / 9;
  };
  const candidates: ({ point: EdgePoint; radius: number } | null)[] = [];
  for (let angleIndex = 0; angleIndex < 72; angleIndex++) {
    const angle = angleIndex / 72 * Math.PI * 2;
    const cosine = Math.cos(angle);
    const sine = Math.sin(angle);
    let bestGradient = Math.max(6, result.statistics.contrastStd * 0.1);
    let candidate = null;
    for (let distance = Math.max(4, Math.floor(radius * 0.3)); distance <= radius * 0.82; distance++) {
      const before = sample(centerX + cosine * (distance - 2), centerY + sine * (distance - 2));
      const after = sample(centerX + cosine * (distance + 2), centerY + sine * (distance + 2));
      if (before === null || after === null || after - before <= bestGradient) continue;
      const point = { x: centerX + cosine * distance + 0.5, y: centerY + sine * distance + 0.5 };
      const index = Math.floor(point.y) * width + Math.floor(point.x);
      if (outside[index]) continue;
      bestGradient = after - before;
      candidate = { point, radius: distance };
    }
    candidates.push(candidate);
  }
  const distances = candidates.filter(candidate => candidate !== null).map(candidate => candidate.radius).sort((first, second) => first - second);
  const median = distances[Math.floor(distances.length / 2)] ?? 0;
  const supported = candidates.map(candidate => candidate && Math.abs(candidate.radius - median) <= Math.max(3, radius * 0.14) ? candidate : null);
  result.statistics.rimSupport = supported.filter(Boolean).length / 72;
  for (let index = 0; index < supported.length; index++) {
    const first = supported[index];
    const second = supported[(index + 1) % supported.length];
    if (first && second && Math.hypot(first.point.x - second.point.x, first.point.y - second.point.y) <= Math.max(6, radius * 0.16)) {
      result.rim.push([first.point, second.point]);
    }
  }
  if (result.statistics.rimSupport < 0.8 || result.rim.length < 54) result.reasons.push('RIM_SUPPORT_INSUFFICIENT');
  result.status = result.reasons.length ? 'UNCERTAIN' : 'SUCCESS';
  result.assessment.outer = contourAssessment(result.outer, area, { x: centerX + 0.5, y: centerY + 0.5 });
  const bodyReasons = result.reasons.filter(reason => reason !== 'RIM_SUPPORT_INSUFFICIENT');
  result.assessment.outer.reasons.push(...bodyReasons);
  if (bodyReasons.length) result.assessment.outer.status = 'UNCERTAIN';
  const completeRim = result.rim.length === 72;
  const points = supported.filter(candidate => candidate !== null).map(candidate => candidate.point);
  let polygonArea = 0;
  if (completeRim) for (let index = 0; index < points.length; index++) {
    const first = points[index];
    const second = points[(index + 1) % points.length];
    polygonArea += first.x * second.y - second.x * first.y;
  }
  result.assessment.rim = contourAssessment(result.rim, Math.abs(polygonArea) / 2,
    { x: centerX + 0.5, y: centerY + 0.5 });
  result.assessment.rim.coverage = result.rim.length / 72;
  let longestGap = 0;
  let currentGap = 0;
  for (let index = 0; index < 144; index++) {
    currentGap = supported[index % 72] ? 0 : Math.min(72, currentGap + 1);
    longestGap = Math.max(longestGap, currentGap);
  }
  result.assessment.rim.largestGapDegrees = longestGap * 5;
  if (!completeRim) {
    result.assessment.rim.referenceRadius = null;
    result.assessment.rim.radialRms = null;
    result.assessment.rim.radialMax = null;
    result.assessment.rim.reasons.push('RIM_NOT_CLOSED_NO_INTERIOR_MASK');
  }
  if (result.assessment.outer.status === 'SUCCESS') {
    result.regions.body = brightness(measurementGray, outside, 0);
    result.regions.background = brightness(measurementGray, outside, 1);
    if (completeRim && result.assessment.rim.closed) {
      const mask = polygonMask(points, width, height);
      if (mask.every((included, index) => !included || !outside[index])) result.regions.rim = brightness(measurementGray, mask);
      else result.assessment.rim.reasons.push('RIM_OUTSIDE_BODY');
    }
  }
  if (result.assessment.outer.status !== 'SUCCESS' || !result.regions.rim) {
    if (result.assessment.rim.status === 'SUCCESS') result.assessment.rim.status = 'UNCERTAIN';
    if (result.assessment.outer.status !== 'SUCCESS') result.assessment.rim.reasons.push('OUTER_MASK_UNCERTAIN');
  }
  result.status = result.assessment.outer.status === 'SUCCESS' && result.assessment.rim.status === 'SUCCESS'
    ? 'SUCCESS' : 'UNCERTAIN';
  return result;
}

export function drawBottleEdges(context: CanvasRenderingContext2D, edges: BottleEdges, originX: number, originY: number, zoom: number): void {
  context.save();
  context.globalAlpha = 1;
  context.beginPath();
  context.rect(originX, originY, edges.width * zoom, edges.height * zoom);
  context.clip();
  context.lineWidth = 1.5;
  for (const [segments, color] of [[edges.outer, '#22c55e'], [edges.rim, '#facc15']] as const) {
    context.strokeStyle = color;
    context.beginPath();
    for (const [first, second] of segments) {
      context.moveTo(originX + first.x * zoom, originY + first.y * zoom);
      context.lineTo(originX + second.x * zoom, originY + second.y * zoom);
    }
    context.stroke();
  }
  context.restore();
}
