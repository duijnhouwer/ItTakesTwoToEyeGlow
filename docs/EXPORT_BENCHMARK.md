# Direct FFmpeg streaming benchmark

Measured on the same local Linux desktop/GPU on 2026-09-18, using the source
application with the Qt event loop and visible viewport. One run per version;
these results are indicative, not a repeated statistical benchmark.

Baseline commit: `10587c6` (PNG staging). Comparison: working tree with direct
RGB streaming into FFmpeg. Both runs used the synthetic recording's full 300
frames, a fixed reset camera with orbit disabled, a 1200 × 840 application
window, 1920 × 1080 export resolution, 30 fps, quality 90, and libx264 preset
`fast`. Timing starts immediately before export and ends at export completion,
including finalization and cleanup but excluding application startup and video
verification. Capture calls are timed separately inside that interval.

| Measurement | PNG staging | Direct streaming |
| --- | ---: | ---: |
| Total export time | 23.843 s | 17.769 s |
| Time inside viewport capture | 12.231 s | 12.382 s |
| Frames / video duration | 300 / 10 s | 300 / 10 s |
| Output bytes | 1,937,483 | 1,937,483 |

Elapsed time decreased by 6.075 seconds (25.5%); throughput increased by about
1.34×. The MP4 files are byte-for-byte identical, with SHA-256
`dcca7652124c1c5fa1d69c37f62fd06cd27d23860b98279f651962703895289a`.

Local results and videos are in `.runtime/export-benchmark/before.*` and
`.runtime/export-benchmark/after.*`. The benchmark driver used for both runs is
`/tmp/eyeglow_export_benchmark.py`. No offscreen rendering or rendering changes
were included. Results do not establish performance at 4K or on other machines.

Video now streams RGB frames into FFmpeg from the single background worker,
with at most one frame write pending. Rendering remains on the Qt thread.
Screenshots still use PNG. Cancellation kills the encoder to unblock pending
pipe writes, and final output is published only after the encoder succeeds.
