# Hyperframes Composition Brief: FIFA Shadow Coach

## Objective
Create a short launch-style brag video for FIFA Shadow Coach.

## Output
- Composition directory: `brag-output-2026-09-30-141255/composition/`
- Rendered video: `brag-output-2026-09-30-141255/brag.mp4`
- Format: landscape — 1920x1080, 30fps
- Duration: 21s

## Source Material
- Project root: repo root (`world_cup_app.py`, `orchestrator.py`, `pipeline/live_fitness_calculator.py`, `CLAUDE.md`)
- Primary files read: world_cup_app.py (UI + copy), orchestrator.py (recommendation logic), pipeline/live_fitness_calculator.py (status buckets), CLAUDE.md (project name/description)
- Product name: FIFA Shadow Coach
- Tagline / strongest claim: "Real-time match tracking, player fitness, and substitution recommendations" (dashboard caption)
- Key UI to show: real Streamlit screenshots in `assets/ui/`: `title.png`, `score.png`, `fit12.png`, `fit34.png`, `rec.png` (captured at 2x from the running app; element offsets in the capture metadata)
- Copy that must appear verbatim (on-screen, from the UI screenshots or as text):
  - FIFA World Cup 2026 Live Analytics
  - Argentina 1-0 (34') Mexico 🟢 LIVE
  - #1 (81% Confidence) · Off: Striker #9 (33% fitness) · On: Forward #19 (89% fitness)
  - PEAK / FAIR / CRITICAL (fitness status buckets)
  - streamlit run world_cup_app.py

## Creative Direction
- Tone preset: default
- Creative direction: Saturday-night TV football broadcast package
- Interpretation: punchy, clean dips, broadcast graphics, holds long enough to read
- Angle: An armchair manager with a spreadsheet brain: the dashboard spots the tired striker and names the sub before the manager does.
- Hook: The score bug clock rolls 12'→34' while Striker #9's fitness ring drains 60%→33%, landing on "Running on empty."
- Outro / punchline: FIFA SHADOW COACH lockup + typed `streamlit run world_cup_app.py` + repo URL
- Avoid:
  - Generic SaaS language
  - Abstract filler visuals
  - Unrelated visual redesign
  - Real player names (sample data uses numbered positions)

## Visual Identity
- Background: #07110c with radial #0f2a1b, faint chalk pitch markings
- Text: #f3f7f2
- Accent: #7ed957 (🟢), status #fdd835 (🟡), #ff4b4b (🔴 / Streamlit red)
- Display font: Anton (local woff2)
- Body font: Source Sans 3 (local woff2; Streamlit's UI font); mono: JetBrains Mono
- Visual references: emoji traffic-light fitness list, recommendation card, score row

## Storyboard
Use the storyboard in `brag-plan.md` as the creative contract.

1. Hook — 0–3.0s — score bug, draining ring, 60%→33%, "Running on empty."
2. Reveal — 3.0–6.0s — wordmark + "Live World Cup 2026 fitness + sub calls" + status pills
3. Live scores — 6.0–10.0s — "Live scores, straight from ESPN." + real title/match row
4. Fitness — 10.0–14.0s — "Every player's fitness, minute by minute." + 12'→34' wipe
5. Sub call — 14.0–18.0s — "The sub call. Before the manager makes it." + highlights + 81% chip
6. Outro — 18.0–21.0s — lockup, typed command, repo

## Audio
- Audio role: warm punchy bed + moderate motion-matched accents
- Audio arc: fast fade-in → steady groove → lift at 16s → bell on lockup → fade out
- Music: `assets/music/happy-beats-business-moves-vol-1-by-ende-dot-app.mp3`
- Music treatment: volume ~0.35, fade in 0.3s, fade out last 0.8s
- Music cue guidance: preset `.claude/skills/brag/assets/music/cues/happy-beats-business-moves-vol-1-by-ende-dot-app.music-cues.json`; 120 BPM grid from 3.02s; strong cues 16.02 / 17.02 / 18.02
- Audio-reactive treatment: subtle — bass drives pitch glow + center-circle line opacity/scale
- Audio-coupled moments:
  - Hook — counter ticks (sparse) + soft thud on "Running on empty."
  - Reveal — soft impact at wordmark, drops per pill
  - Windows landing — card slide
  - Highlights — clicks; chip — success accent
  - Outro — bell + keypresses
- SFX selection guidance: prefer low/medium HF risk (sfx-analysis.md)
- Exact SFX choice: chosen against the implemented animation
- Audio files: copied into `composition/assets/`

## Hyperframes Instructions
Load hyperframes-core / animation / creative / keyframes / cli. Standalone composition, single paused GSAP timeline, local GSAP, local fonts with @font-face, `hyperframes check` as the gate, local render only.
