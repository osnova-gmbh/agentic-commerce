# Commerce flow film

A replacement for the character-led Alice/Bob cartoon. The visual is an animated
sequence diagram: fixed system lanes, moving request arrows, message details,
deal state and continuously visible money balances. There are no human characters.

The 62-second film follows the current EUR 500 report example: discovery, service
request and quote, mutual acceptance, funding confirmation, artifact delivery,
three independent checks, EUR 495 payout, EUR 5 operator fee and signed receipts.
Catalog calls and bank transfers are distinguished from signed finance messages.
It illustrates the protocol; it is not a screen recording or a live transaction.

## MP4 downloads

- [Full film with sound](out/commerce-flow-final.mp4) — 1920 × 1080, 24 fps, 62 seconds.
- [Silent film](out/commerce-flow.mp4) — the same protocol flow without audio.

Both finished MP4 exports are versioned in this repository. Use **Download raw file**
on the GitHub file page to save or play the export.

## Sources

- flow-data.js: the requests, payload summaries, timing and accounting.
- film.js: vector drawing and animation, independent of wall-clock time.
- commerce-flow.html: editable local animation with playback and scrubbing.
- index.html, server.mjs: exported-video player and chapter navigation.
- out/: the two finished MP4 exports are tracked; intermediate frames, previews
  and verification evidence remain ignored.

## Build with local Vidder

From the agentic-commerce root:

    node ../vidder/packages/canvas/src/cli.mjs render films/commerce-flow/commerce-flow.html --grid 24 --out films/commerce-flow/out
    node ../vidder/packages/canvas/src/cli.mjs render films/commerce-flow/commerce-flow.html --out films/commerce-flow/out
    node films/commerce-flow/server.mjs

Open http://127.0.0.1:4175/. The full export includes commerce-flow-final.mp4
with restrained confirmation sounds. The film is understandable without audio.

If a local headless Chrome export cannot start, use the same Vidder frame hooks
in the working browser:

    node films/commerce-flow/render-server.mjs

Open http://127.0.0.1:4176/ and click Render MP4. The page exports the same 1,488
deterministic Canvas frames and soundtrack; the local server packages them with
the Vidder FFmpeg dependency. No browser security flags or external services
are needed. The renderer also writes a contact sheet, poster and format metadata.
Arrow numbers restart in each chapter; they are not deal-event sequence numbers.

## Attribution

Protocol and amounts: repository SPEC.md, contracts/, and the demo code.
Drawing and timing: original for this film. Vidder Canvas 0.1.0 renders the film;
engine/core.js is an unmodified local runtime from the pinned upstream
90e966201add3ff41dc4ebd1348165c0cb2d5eab, copyright Alexey Fateev (MIT).
The upstream licence is retained in engine/LICENSE.
Manrope is reused from the existing project under the SIL Open Font License,
retained in assets/OFL-Manrope.txt. No external imagery or stock music.
