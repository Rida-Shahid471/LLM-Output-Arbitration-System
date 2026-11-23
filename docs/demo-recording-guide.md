# Demo Recording Guide

**Capture date:** 2026-11-13
**Application:** local Docker dashboard at `http://127.0.0.1:8501/`
**API documentation:** `http://127.0.0.1:8000/docs`
**Provider shown:** local Ollama, `qwen2.5:1.5b`

## Public screenshot set

The approved public capture set is stored directly under `docs/screenshots/`. These are genuine viewport captures from the running local application/browser. The captures do not show Chrome tab titles, credentials, desktop clutter, or personal data. Some captures include the mouse pointer highlight; the application content remains readable. Historical originals and duplicate captures are preserved in an ignored private temporary directory and are not part of the public set.

| File | Verified view |
|---|---|
| [`01-dashboard.jpg`](screenshots/01-dashboard.jpg) | Application title, provider notice, navigation, and input form. |
| [`02-input-and-verdict.jpg`](screenshots/02-input-and-verdict.jpg) | Prompt “What is the capital of France?”, candidate “Lyon is the capital of France.”, and the actual `REJECT` result, score 2/10, confidence 80%. |
| [`03-critic-reports.jpg`](screenshots/03-critic-reports.jpg) | Three visible critic cards and their differing issue reports. |
| [`04-disagreement-evidence.jpg`](screenshots/04-disagreement-evidence.jpg) | Pairwise disagreement topics and quoted evidence. |
| [`05-disagreement-evidence-details.jpg`](screenshots/05-disagreement-evidence-details.jpg) | Continuation of the actual disagreement detail view. |
| [`06-history.jpg`](screenshots/06-history.jpg) | Refreshed history showing eight stored records, including the France demo arbitration. |
| [`07-analytics.jpg`](screenshots/07-analytics.jpg) | Analytics over eight stored records: pair agreement 14.3%, disagreement 85.7%; latency text is clipped by the narrow browser viewport. |
| [`08-api-documentation.jpg`](screenshots/08-api-documentation.jpg) | Live Swagger route list for health, arbitration, batch, history, retrieval, and analytics. |

The France example shown in the screenshots is a real local Ollama arbitration stored with ID `e3bcaf25-587b-4e0c-a259-4781346cc915`. It returned `REJECT`, 2/10, 80% confidence, provider/model `ollama/qwen2.5:1.5b`; all three critic cards and disagreement evidence are shown. The Australia example in the recorded video is a separate real local run. Neither demonstration is a label-quality evaluation, and model judgments can be wrong. These operational records were not used in or written to the evaluation artifacts.

The Analytics page displays operational aggregates over the app's stored records, not benchmark metrics. Its average-latency value is visibly clipped at the viewport width in the screenshot; do not quote a latency from that capture.

## Recorded walkthrough

**Video:** [`docs/demo/llm-output-arbitration-demo.mp4`](demo/llm-output-arbitration-demo.mp4) (compressed, full-length public copy; 17,315,100 bytes / 16.51 MiB). The original user recording is preserved separately at `docs/demo/LLM_arbitration_system_demo.mp4` and is 130,438,415 bytes / 124.4 MiB. The public copy remains below GitHub's 100 MiB ordinary Git-file limit; the original is excluded from normal Git tracking and was not overwritten.

The video shows a real local Ollama session with the Australia prompt and incorrect Sydney answer, the `REJECT` result (1/10, 90% confidence), the red evidence marker, all three critic reports, disagreement details, History, and Analytics. It does not show API documentation; use the genuine Swagger screenshot for that view. I opened the recording in VLC, verified its 2:04 duration, and extracted one review frame every four seconds. The inspected frames show the application throughout without unrelated tabs, credentials, or personal desktop content. The analytics page displays local operational-record metrics, including a measured latency value; it is not an evaluation benchmark.

## Repeatable narration outline (about two minutes)

1. **0:00–0:25 — Input:** Show the local Ollama dashboard and enter the Australia question with the incorrect Sydney answer.
2. **0:25–0:55 — Arbitration:** Submit the request and let the actual local model run; keep any wait visible or explain it without implying an instant response.
3. **0:55–1:20 — Verdict and evidence:** Show the actual `REJECT` result, score 1/10, 90% confidence, red confirmed-evidence marker, and three critic reports.
4. **1:20–1:40 — Disagreement:** Show the structured disagreement records and explain that the model's judgment is fallible.
5. **1:40–1:55 — History:** Show the persisted arbitration in the local history.
6. **1:55–2:05 — Analytics:** Show operational aggregates and state that they are not evaluation metrics.
7. **Optional separate view — API:** Show `http://127.0.0.1:8000/docs`; this is represented by the screenshot rather than the current video.

## Privacy and recording checklist

- Keep both services on loopback; do not expose them publicly.
- Use only the non-sensitive example shown above.
- Do not show `.env`, credentials, private data, unrelated tabs, or other apps.
- Do not conceal or narrate away a failure/fallback if one appears during a new run. The current saved result is the actual `REJECT` result described above.
- Do not present mock output as semantic evaluation or analytics as benchmark metrics.
- Capture only the browser content area and review the saved video before sharing.

## Recording and privacy status

The user-created MP4 was opened in VLC and reviewed at regular frame intervals before compression. The full-length transcoding completed successfully: VLC/x264 reported 3,735 encoded frames at 30.01 fps (about 2:04.5), and Windows media properties report 1,424 × 772 pixels. A separate VLC playback/decode check successfully opened the compressed MP4, identified the H.264 video track (3,734 samples, about 124 seconds), initialized its decoder, and read through the stream. The compressed video was produced from the original without trimming or changing the workflow. The frame review showed the application throughout and no visible credentials, browser tab titles, private desktop details, or personal information. The original is preserved unchanged. The demo records one application example; four-case pipeline checks are separately covered by the offline regression test. The API documentation view is in the screenshot set, not the recording.

**Media status:** genuine original reviewed; full-length H.264/MP4 copy decoded in VLC; duration, resolution, and size verified; original preserved and Git-ignored. No new recording software or model was installed for this work.
