# Phase 1: real Chrome, read-only E2E

Run from `frontend`:

```powershell
npm.cmd run test:e2e:readonly
```

Requires the user's existing Vite (`http://localhost:5173`), FastAPI
(`http://127.0.0.1:8000`) and installed Google Chrome. The runner checks both
servers and exact VID-000003 metadata/SHA256 before launching Chrome. It never
starts, stops or restarts either server. No browser download is required.
Chrome uses Playwright's separate temporary profile, one worker, retries=0 and
GPU disabled; only the browser created by this run is closed by Playwright.

Exactly five tests use real UI and real allowed GET responses; no fixtures are
injected into the application and no server response is replaced. Stream requests
for VID-000001/2 are blocked, including the initial default video request before
the real selector is switched to VID-000003. Playback interactions only start
after the selected ID, stream URL and decoded dimensions/duration are verified.

All non-GET/HEAD requests, external resource requests, live analysis endpoints,
Capture/RIG access and WebSockets are blocked at browser-context level. This
includes the app's automatic POST `/capture-sessions`, not just inspection/AI
buttons. Unexpected attempted writes fail the test even though they are blocked;
the known automatic session bootstrap is reported separately. Requests are logged
as method/path only: no cookie/header/body logs, raw HAR or Playwright traces.
Local page screenshots contain the inspection UI and must be treated as local
evidence, not uploaded automatically.

## Stored data and ownership

The default reference is the real stored INSP-001694. Missing reference data is
reported, never created. Its public inspection metadata may be read; its private
Crop/Heatmap/Judge results require the rightful existing owner session. Default
Chrome has no such session. These protected GETs are deliberately not forwarded:
CaptureStore.authorize() performs TTL cleanup even on reads. TC-04/05 therefore
SKIP rather than copy cookies, change ownership, expose a local PNG through a
mock URL, create a Capture or start an inspection.

TC-03 may use a different real, public, non-Grab stored inspection with an existing
map; the actual ID is annotated in the report. This is not a validation of
INSP-001694's protected Crop. TC-02 checks stored-ID selection and tab state, not
a successful private Judge fetch when the session is unavailable.

An existing **user-supplied, legitimately authorized** Playwright storage state
can be supplied later via `VISION_E2E_STORAGE_STATE`. It must be inside
`frontend/playwright/.auth/` (Git ignored). The runner never creates, extracts or
prints this state. If any Capture PNG currently exists, this mode is refused
before browser launch to prevent the read-time TTL cleanup from deleting it.
An old/expired session is not restored or bypassed. Use only after reviewing the
active server/session and data protection requirements with the user.

### Edge/GV eligibility check only (no Capture creation)

```powershell
npm.cmd run test:e2e:readonly -- --grep 'TC-0[45]'
```

TC-04/05 now also load the real public stored image when no approved owner
session is available and verify the production Edge button is disabled for a
static image. This is an eligibility diagnostic, **not** a successful Edge/GV
test; both remain SKIP. Per-test `edge-gv-eligibility.json` and
`public-image-edge-unavailable.png` preserve the evidence. Do not relabel the
static image as LIVEVIEW_GRAB or inject a private saved PNG through a mock URL.

If no legitimate saved Grab session can be supplied, the minimum future run
requires separate explicit user approval: **one new Capture, zero inspections**.
Use one normal Playwright browser context/page for both Edge and GV checks.
Select VID-000003, pause/seek, click ROI selection (this may itself create the
single Capture), adjust ROI, then apply it with Grab on the same frozen frame
(the existing App branch crops locally without another Grab POST). Do not click
"Grab 이미지 검사" or either Gemini action. The Edge/GV input already exists
in `cropData.imageData`; a PatchCore result/inspection ID is not required.

The approved runner would need a separate write policy capped at exactly one
POST `/videos/VID-000003/grab`, allow only normal session/CSRF bootstrap and
read-back of that newly issued Capture, and share the page between both checks.
It must not reuse the read-only guard by disabling it globally. Expect one
server-managed 1920×480 temporary Capture PNG plus in-memory owner/CSRF state;
the ROI Crop is a browser Blob/ImageData, not a persistent inspection input.
No Inspection JSONL/event records, maps, RIGs or AI reviews should be created.
Compare ROI GV to the decoded source Crop directly because no stored inspection
mean exists for this new Capture. Do not delete the resulting Capture as test
cleanup; it remains under the normal TTL policy.

Normal session creation/read-back also invokes TTL cleanup. Before that future
run, recheck existing Capture PNG preservation with the user; do not assume an
old backup covers them. **The Capture-creation runner is separate and is never
executed by this read-only command.** Approval is required before enabling it.

### Approved one-Capture run

```powershell
npm.cmd run test:e2e:edge-gv:capture -- --approve-one-capture
```

Without the flag this command stops before contacting either server. Even with
the flag, **any existing file other than the Capture marker blocks the run before
session creation**. No file is deleted, renamed, restored or moved to satisfy
that gate. Current live expiry is memory-only: a PNG's age/default TTL is not
proof of the running server's actual expiration setting. Normal bootstrap can
delete expired registered Captures, and initial directory setup can remove
orphaned managed files. This test does not change either policy.

After the gate passes, `playwright.capture.config.mjs` runs only
`capture-edge-gv.spec.mjs`, sequentially in one fresh browser context/page.
The existing pixel detector is used on the actual paused VID-000003 frame to
find a fully observed candidate and derive ROI bounds; no frame/ROI/result is
hardcoded. If none is observed, no Grab is attempted. UI ROI selection performs
the sole server Grab; applying the ROI on that frozen frame crops locally.
Session POSTs are capped at four to allow the application's normal bootstrap;
the Grab budget is claimed before forwarding and cannot be reset after failure.
A create-exclusive `grab-attempt.json` also prevents a replacement worker from
issuing another Grab within that run. All inspection, manual-review and AI POSTs
remain blocked; only the newly issued Capture may be read back.

TC-04 checks actual newly rendered green/yellow pixels when observed segments
exist, state/details, toggle and zoom/pan. TC-05 compares displayed region values
to the same decoded source Crop; whole-ROI mean/median/std are independently
calculated from its original pixels. Anatomical correctness remains a visual
review item. No user Chrome is attached and no source state/cookie is exported.
One run is one approval: do not rerun the command after a Grab attempt, even if
the test fails. Existing PNGs left by a prior run will block the next run.

## Evidence and interpretation

Each run creates a unique `data/outputs/playwright-readonly/<timestamp>-<id>/`
containing preflight, JSON/HTML reports, per-test safety logs and screenshots
(including failed and skipped cases). `protection.json` compares the inspection
and event JSONL, target Crop if present, VID-000003 and initial Capture PNG hashes.
This is a scoped check, not a full-project asset audit.

Failures remain failures; no retries or application fixes are applied. Missing
authorized data is SKIP, not PASS. TC-03 checks visible render changes and raw
Pixel Inspector values; TC-04 checks Edge controls/status persistence. Exact
spatial alignment and anatomical contour correctness still require human visual
review of the screenshots. No model accuracy or real Gemini success is inferred.

Playwright references: [configuration](https://playwright.dev/docs/test-configuration),
[installed Chrome](https://playwright.dev/docs/browsers#google-chrome--microsoft-edge),
[request blocking](https://playwright.dev/docs/network#block-requests).
