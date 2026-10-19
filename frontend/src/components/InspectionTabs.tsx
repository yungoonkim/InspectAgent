import { useRef, useState } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';

interface Props {
  grabPanel: ReactNode;
  judgePanel: ReactNode;
  staticImagePanel: ReactNode;
}

type InspectionTab = 'grab' | 'static';

export function InspectionTabs({ grabPanel, judgePanel, staticImagePanel }: Props) {
  const [activeTab, setActiveTab] = useState<InspectionTab>('grab');
  const [activeGrabTab, setActiveGrabTab] = useState<'patchcore' | 'judge'>('patchcore');
  const grabButton = useRef<HTMLButtonElement>(null);
  const staticButton = useRef<HTMLButtonElement>(null);
  const patchcoreButton = useRef<HTMLButtonElement>(null);
  const judgeButton = useRef<HTMLButtonElement>(null);

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, tab: InspectionTab) => {
    let nextTab: InspectionTab;
    if (event.key === 'Home') nextTab = 'grab';
    else if (event.key === 'End') nextTab = 'static';
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') nextTab = tab === 'grab' ? 'static' : 'grab';
    else return;
    event.preventDefault();
    setActiveTab(nextTab);
    (nextTab === 'grab' ? grabButton : staticButton).current?.focus();
  };

  const handleGrabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, tab: 'patchcore' | 'judge') => {
    let nextTab: 'patchcore' | 'judge';
    if (event.key === 'Home') nextTab = 'patchcore';
    else if (event.key === 'End') nextTab = 'judge';
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') nextTab = tab === 'patchcore' ? 'judge' : 'patchcore';
    else return;
    event.preventDefault();
    setActiveGrabTab(nextTab);
    (nextTab === 'patchcore' ? patchcoreButton : judgeButton).current?.focus();
  };

  return <section className="inspection-tabs" aria-label="검사 방식 선택">
    <div className="view-mode-tabs" role="tablist" aria-label="검사 패널">
      <button ref={grabButton} id="grab-inspection-tab" type="button" role="tab"
        aria-controls="grab-inspection-panel" aria-selected={activeTab === 'grab'}
        tabIndex={activeTab === 'grab' ? 0 : -1} className={`tab-btn ${activeTab === 'grab' ? 'active' : ''}`}
        onClick={() => setActiveTab('grab')} onKeyDown={event => handleKeyDown(event, 'grab')}>
        Grab 이미지 검사
      </button>
      <button ref={staticButton} id="static-inspection-tab" type="button" role="tab"
        aria-controls="static-inspection-panel" aria-selected={activeTab === 'static'}
        tabIndex={activeTab === 'static' ? 0 : -1} className={`tab-btn ${activeTab === 'static' ? 'active' : ''}`}
        onClick={() => setActiveTab('static')} onKeyDown={event => handleKeyDown(event, 'static')}>
        정적 이미지 검사
      </button>
    </div>
    <div id="grab-inspection-panel" role="tabpanel" aria-labelledby="grab-inspection-tab"
      className="inspection-tab-panel" hidden={activeTab !== 'grab'}>
      <div className="inspection-grab-stages">
        <div className="view-mode-tabs" role="tablist" aria-label="Grab 검사 단계">
          <button ref={patchcoreButton} id="patchcore-inspection-tab" type="button" role="tab"
            aria-controls="patchcore-inspection-panel" aria-selected={activeGrabTab === 'patchcore'}
            tabIndex={activeGrabTab === 'patchcore' ? 0 : -1} className={`tab-btn ${activeGrabTab === 'patchcore' ? 'active' : ''}`}
            onClick={() => setActiveGrabTab('patchcore')} onKeyDown={event => handleGrabKeyDown(event, 'patchcore')}>
            1차 · PatchCore 검사
          </button>
          <button ref={judgeButton} id="judge-inspection-tab" type="button" role="tab"
            aria-controls="judge-inspection-panel" aria-selected={activeGrabTab === 'judge'}
            tabIndex={activeGrabTab === 'judge' ? 0 : -1} className={`tab-btn ${activeGrabTab === 'judge' ? 'active' : ''}`}
            onClick={() => setActiveGrabTab('judge')} onKeyDown={event => handleGrabKeyDown(event, 'judge')}>
            2차 · Gemini Judge
          </button>
        </div>
        <div id="patchcore-inspection-panel" role="tabpanel" aria-labelledby="patchcore-inspection-tab"
          className="inspection-tab-panel" hidden={activeGrabTab !== 'patchcore'}>{grabPanel}</div>
        <div id="judge-inspection-panel" role="tabpanel" aria-labelledby="judge-inspection-tab"
          className="inspection-tab-panel" hidden={activeGrabTab !== 'judge'}>{judgePanel}</div>
      </div>
    </div>
    <div id="static-inspection-panel" role="tabpanel" aria-labelledby="static-inspection-tab"
      className="inspection-tab-panel" hidden={activeTab !== 'static'}>
      {staticImagePanel}
    </div>
  </section>;
}
