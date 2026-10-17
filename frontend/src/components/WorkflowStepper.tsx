import React from 'react';
import { ChevronRight } from 'lucide-react';

interface WorkflowStepperProps {
  currentStep: number;
}

export const WorkflowStepper: React.FC<WorkflowStepperProps> = ({ currentStep }) => {
  const steps = [
    { num: 1, label: '1. 라이브 스트림', sub: 'H.264 비디오', active: currentStep >= 1 },
    { num: 2, label: '2. 프레임 캡처', sub: 'FastAPI Grab', active: currentStep >= 2 },
    { num: 3, label: '3. ROI 영역', sub: '제품 Crop (600×600)', active: currentStep >= 3, deferred: false },
    { num: 4, label: '4. PatchCore 검사', sub: '이상 탐지 (34.1442)', active: currentStep >= 4, deferred: false },
    { num: 5, label: '5. Gemini 진단', sub: '근거 기반 리포트', active: currentStep >= 4, deferred: false },
  ];

  return (
    <div className="workflow-stepper">
      <div className="stepper-left">
        <h1 className="stepper-title">실시간 비전 품질 검사 및 프레임 Grab 워크스페이스</h1>
        <p className="stepper-desc">
          MVTec AD Bottle 실시간 컨베이어 영상 모니터링 및 정밀 프레임 캡처 시스템
        </p>
      </div>

      <div className="stepper-steps hidden lg:flex">
        {steps.map((step, idx) => (
          <React.Fragment key={step.num}>
            <div
              className={`step-item ${
                step.active ? (step.num === currentStep ? 'active' : 'complete') : ''
              }`}
            >
              <div className="step-dot" />
              <span>{step.label}</span>
              {step.deferred && (
                <span className="text-[10px] text-slate-500 font-mono">(준비중)</span>
              )}
            </div>
            {idx < steps.length - 1 && (
              <ChevronRight size={12} className="step-arrow" />
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};
