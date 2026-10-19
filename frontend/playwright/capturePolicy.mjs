import { existsSync, readdirSync } from 'node:fs';

export function requireCaptureApproval(argumentsList) {
  if (argumentsList.length !== 1 || argumentsList[0] !== '--approve-one-capture') {
    throw new Error('EXPLICIT_ONE_CAPTURE_APPROVAL_REQUIRED');
  }
}

export function existingCaptureFiles(directory) {
  if (!existsSync(directory)) return [];
  return readdirSync(directory).filter(name => name !== '.visioninsight-captures');
}

export function requireEmptyCaptureDirectory(directory) {
  if (existingCaptureFiles(directory).length) throw new Error('EXISTING_CAPTURE_TTL_DELETION_RISK');
}

export function createGrabBudget(sourceRevision) {
  let attempts = 0;
  let selectedFrame = null;
  return {
    select(frame) {
      if (attempts || !Number.isInteger(frame) || frame < 0 || frame >= 480) throw new Error('INVALID_CAPTURE_SELECTION');
      selectedFrame = frame;
    },
    claim(body) {
      if (attempts) throw new Error('GRAB_BUDGET_EXHAUSTED');
      if (selectedFrame === null || body.frame_index !== selectedFrame || body.source_revision !== sourceRevision
        || Object.keys(body).some(key => !['frame_index', 'source_revision'].includes(key))) {
        throw new Error('GRAB_SOURCE_MISMATCH');
      }
      attempts++;
    },
    get attempts() { return attempts; },
  };
}
