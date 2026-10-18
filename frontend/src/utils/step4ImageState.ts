import type { AnomalyMapMetadata } from '../api/inspection';

export interface InspectionIdentity {
  inspection_id: string;
  image_id: string;
  provenance?: string;
}

export interface InspectionImageIdentity {
  inspectionId: string;
  imageId: string;
}

interface ImageDimensions {
  width: number;
  height: number;
}

export function isFixtureInspection(inspection: InspectionIdentity | null | undefined): boolean {
  return inspection?.inspection_id === 'INSP-001391' ||
    inspection?.provenance === 'RECORDED_TEST_FIXTURE';
}

export function isInspectionImageCurrent(
  inspection: InspectionIdentity | null | undefined,
  image: InspectionImageIdentity | null | undefined
): boolean {
  return !!inspection?.inspection_id && !!inspection.image_id && !!image &&
    image.inspectionId === inspection.inspection_id && image.imageId === inspection.image_id;
}

function isPositiveDimension(dimension: number): boolean {
  return Number.isSafeInteger(dimension) && dimension > 0;
}

export function isAnomalyMapCompatible(
  inspection: InspectionIdentity | null | undefined,
  metadata: AnomalyMapMetadata | null | undefined,
  source?: ImageDimensions | null,
  overlay?: ImageDimensions | null
): boolean {
  if (!inspection || isFixtureInspection(inspection) || !metadata ||
    !inspection.inspection_id || !inspection.image_id ||
    metadata.inspection_id !== inspection.inspection_id || metadata.image_id !== inspection.image_id ||
    metadata.localization_available !== true || metadata.available === false ||
    !isPositiveDimension(metadata.original_image_width) ||
    !isPositiveDimension(metadata.original_image_height) ||
    !isPositiveDimension(metadata.anomaly_map_width) ||
    !isPositiveDimension(metadata.anomaly_map_height)) {
    return false;
  }

  return (!source || (source.width === metadata.original_image_width &&
    source.height === metadata.original_image_height)) &&
    (!overlay || (overlay.width === metadata.original_image_width &&
    overlay.height === metadata.original_image_height));
}

export function startInspectionHeatmapLoad(
  inspection: InspectionIdentity,
  dependencies: {
    getMetadata: (inspectionId: string) => Promise<AnomalyMapMetadata>;
    getOverlayUrl: (inspectionId: string) => string;
    createImage: () => HTMLImageElement;
    onAvailable: (metadata: AnomalyMapMetadata, imageElement: HTMLImageElement) => void;
    onUnavailable: () => void;
  }
): () => void {
  let isCurrent = true;
  const cancel = () => { isCurrent = false; };

  if (isFixtureInspection(inspection)) {
    dependencies.onUnavailable();
    return cancel;
  }

  void dependencies.getMetadata(inspection.inspection_id).then((metadata) => {
    if (!isCurrent) return;
    if (!isAnomalyMapCompatible(inspection, metadata)) {
      dependencies.onUnavailable();
      return;
    }

    const overlay = dependencies.createImage();
    overlay.crossOrigin = inspection.image_id.startsWith('IMG-GRAB-') ? 'use-credentials' : 'anonymous';
    overlay.onload = () => {
      if (!isCurrent) return;
      if (!isAnomalyMapCompatible(inspection, metadata, null, {
        width: overlay.naturalWidth,
        height: overlay.naturalHeight,
      })) {
        dependencies.onUnavailable();
        return;
      }
      dependencies.onAvailable(metadata, overlay);
    };
    overlay.onerror = () => {
      if (isCurrent) dependencies.onUnavailable();
    };
    overlay.src = dependencies.getOverlayUrl(inspection.inspection_id);
  }).catch(() => {
    if (isCurrent) dependencies.onUnavailable();
  });

  return cancel;
}
