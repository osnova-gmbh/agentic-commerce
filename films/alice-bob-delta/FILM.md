# Alice, Bob & Delta — a fair deal

## Brief
Reinterpret the agent-commerce / ProOrder idea as a short character-led cartoon. Alice buys a market-research report from Bob; Delta is the intermediary holding the money. Show the practical value, not the application UI. Graphics and acting carry the explanation. No disclaimer overlays, step counters, playback instructions, invented adoption claims, or protocol jargon.

## Direction
- 26 seconds; 1920 × 1080, 16:9; 24 fps export, whole character drawings mostly on twos.
- Warm cream paper, confident dark-green ink, coral Alice, blue Bob, sage-green Delta. Original full-body cartoon people and an expressive little escrow-vault character.
- A report with a bar chart is the recurring prop. Gold coins represent payment, not an exact accounting diagram.
- Original soft pizzicato-like synthesized music and short transaction/typing accents; no voiceover. Understandable muted.
- Local Manrope lettering, mostly names/roles and very short scene headings. No paragraphs.

## Story / beats
| Time | Action | Copy |
|---|---|---|
| 0–4 s | Alice imagines a research report; Bob shows he can make it. Delta arrives between them. | A report. A new supplier. / Alice · Buyer / Bob · Seller |
| 4–8 s | Alice visibly hands payment toward Delta. Coins enter Delta's chest, the lock closes; Bob can see the money is reserved. | Delta holds the money. / Delta · Escrow |
| 8–13 s | Bob works at a desk; charts build into the report. Alice waits, while the locked coins remain with Delta. | Bob gets to work. |
| 13–18 s | Bob sends the report to a separate checking station above Delta. Three checks tick off while the coins remain locked. | Independent checks. |
| 18–23 s | Checked report reaches Alice, then the lock opens and payment travels to Bob. Both react happily. | Work delivered. Bob paid. |
| 23–26 s | All three hold a satisfied closing pose: Alice with the report, Bob with payment, Delta between them. | Good work. Fair trade. |

## Performance and continuity
- Whole drawings for rest, thought, anticipation, reach, release, work, receive and delight. Bent-arm silhouettes are redrawn, not rotated capsule puppets. Compatible poses have explicitly spaced inbetweens; blinks are replacement drawings.
- Feet stay on the same floor. Hands and props share authored contact landmarks at release/catch. Separate one-frame prop travel from two-frame character exposures.
- One consistent stage and cast placement make each transfer legible. The independent checks are a distinct graphic station, not Delta judging its own transaction.
- No refund branch in this short first film; keep one causal story readable. No fee arithmetic is implied by symbolic coins.
- Screen-registered, seeded paper speckles; stable ink marks for every held cel. No per-frame random noise.

## Sources and licenses
- Story: repository `SPEC.md`, purpose and role separation. This is an explainer, not footage of an operational financial service.
- Characters, props, storyboard, choreography and score: original code-authored artwork for this film.
- Runtime: unmodified local `@vidder/canvas` scaffold from `C:/ai/_experiments/vidder`, package 0.1.0, upstream `90e966201add3ff41dc4ebd1348165c0cb2d5eab`. See `engine/` licenses and source notes.
- Manrope: reused local font from `apps/landing/assets`, SIL Open Font License retained in `assets/`.
- No external images, generated-media services, stock music, or runtime network dependencies.

## Files and commands
Editable source: `alice-bob-delta.html`, `drawings.js`, `film.js`. Viewer: `index.html` (final MP4).

From repository root:

```sh
npm --prefix ../vidder run canvas -- render films/alice-bob-delta/alice-bob-delta.html --grid 24 --out films/alice-bob-delta/out
npm --prefix ../vidder run canvas -- render films/alice-bob-delta/alice-bob-delta.html --strip 142,16 --out films/alice-bob-delta/out
npm --prefix ../vidder run canvas -- render films/alice-bob-delta/alice-bob-delta.html --out films/alice-bob-delta/out
node films/alice-bob-delta/server.mjs
# With the viewer running (requires the local Vidder checkout):
node films/alice-bob-delta/verify.mjs
```

Viewer: http://127.0.0.1:4174/ . `VIDDER_ROOT` and `CHROME` override the verification script's local checkout/browser paths. The Manrope WOFF2 is also embedded in `assets/font.css` so Chrome's file-URL font restrictions do not break offline exports.

## Review
Completed:
- Proved the payment handoff in an isolated four-second production shot. Corrected contour occlusion before building the rest of the story.
- Inspected the full 24-frame overview, the encoded contact sheet, full-size working/checking/closing drawings and consecutive transfer strips. No clipped characters or accidental blank scene frames observed.
- Verified 106 whole character drawings and their fixed foot landmarks; 12 exact PNG repeat-after-forward/backward/grid-seek comparisons passed with the same browser and embedded font.
- Delivered `out/alice-bob-delta-final.mp4`: 26 seconds, 1920 × 1080, H.264, 624 frames at 24 fps, AAC stereo at 48 kHz. Complete FFmpeg decode succeeded; no black-frame intervals reported.
- Audio measurement: peak −6.7 dBFS, mean −27.3 dBFS, no clipping. The earlier quieter mix is retained in `out/revisions/`.
- Chrome played the complete encoded film at normal speed without media errors or dropped frames. Forward/backward video seeking, HTTP byte ranges and the 390px mobile viewer passed.
- Evidence: `out/verification.json`, `out/decode.log`, `out/alice-bob-delta-contact.jpg`, `out/alice-bob-delta-strip-132.jpg`, `out/alice-bob-delta-strip-502.jpg`, `out/encoded-final.png` and viewer screenshots.

Limits: original code-authored flat cartoon, not frame-by-frame traditional production. Primary layout is landscape; mobile viewing preserves that composition. No narration or refund branch. Visual assessment used stills/contact sheets/consecutive strips; full-speed encoded playback was checked automatically, not visually watched or listened to in real time. Source and outputs stay local; nothing was published.
