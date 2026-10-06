# Mac Guardian media kit

Your Mac has a doctor now.

English campaign for the Mac Guardian Agent Index listing. The physician and laptop mascot represents quiet, automatic macOS maintenance. Graphite, ivory and luminous mint connect the logo, campaign images and film.

## Deliverables

| Asset | File | Format |
| --- | --- | --- |
| Primary mascot logo | [mac-guardian-logo.png](images/mac-guardian-logo.png) | 1254 × 1254 PNG with transparent alpha |
| Brand hero | [Your Mac has a doctor now](images/01-your-mac-has-a-doctor.png) | 1672 × 941 PNG |
| Automatic maintenance | [Care that runs quietly](images/02-care-that-runs-quietly.png) | 1672 × 941 PNG |
| Personal file wiki | [A home for every file](images/03-a-home-for-every-file.png) | 1672 × 941 PNG |
| Conversation and control | [Just ask](images/04-just-ask.png) | 1672 × 941 PNG |
| Cinematic launch film | [mac-guardian-cinematic.mp4](videos/mac-guardian/renders/mac-guardian-cinematic.mp4) | 40 seconds, 1920 × 1080, 24 fps, H.264 + AAC stereo |
| Film contact sheet | [film-contact-sheet.png](film-contact-sheet.png) | Frames extracted from the finished MP4 |
| Gallery | [gallery.html](gallery.html) | Offline HTML gallery and video player |
| Image prompt set | [PROMPTS.md](PROMPTS.md) | Built-in image generation prompts and constraints |

## Film direction

The film opens with monumental typography and a heartbeat. The doctor arrives, then a storage lattice clears, a note receives a contextual filename, and files move into their wiki folders. Idle app updates, health checks and private backups lead into conversational control. The doctor returns for the final identity card.

An original 144 BPM instrumental score uses a heartbeat opening, electronic percussion, warm minor chords, short rises and a resolved closing. No voiceover is required; the English typography explains the product when played muted.

Scene IDs: 01-hook, 02-doctor, 03-space, 04-wiki, 05-care, 06-talk, 07-close.

## Edit and render

The editable HyperFrames project is in `videos/mac-guardian/`. Its scripts pin HyperFrames 0.8.138. Local fonts and the mascot are included.

```sh
cd videos/mac-guardian
npm run dev
npm run check
npm run render -- --quality delivery --fps 24 --output renders/mac-guardian-cinematic.mp4
```

Use the HyperFrames timeline to edit text, timing and layout. The [HyperFrames desktop app](https://hyperframes.dev/studio/download) adds editing through conversation with Framey.

To rebuild the original scene HTML, run `python3 build_film.py`. To regenerate the original soundtrack, run `uv run --with numpy create_score.py`. Keep the shipped `index.html` as the assembled master unless reassembling the scenes.

## Verification and provenance

The full HyperFrames browser check passed with zero lint, runtime, layout or contrast findings. The finished MP4 was checked for resolution, duration and audio; its contact sheet was inspected against the intended scenes. Text and product capabilities were reviewed in all four campaign images.

The logo and campaign images were created with the built-in image generation tool. The soundtrack is original local synthesis. File examples and conversations are illustrative and contain no personal documents or real diagnostics. The campaign describes the shipped v0.2.0 capabilities; security checks do not imply complete malware detection, and private backups apply to configured approved folders.

Campaign source and original soundtrack code are MIT. Barlow Condensed and JetBrains Mono retain their included SIL Open Font Licenses. No third-party music is included in the deliverable.
