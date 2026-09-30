# Brag Plan: FIFA Shadow Coach

## What is this app?
A Streamlit dashboard that pulls live FIFA World Cup 2026 matches from ESPN, estimates every player's in-match fitness, and recommends who to substitute, complete with a confidence score.

## The angle
An armchair manager with a spreadsheet brain. On TV you just see the score. This app sees that the striker is running on fumes and names his replacement. We play it like a TV sports broadcast package: score bug, a draining fitness gauge, then the dashboard makes the call.

## Hook (first 2-3 seconds)
A score bug reads "ARG 1–0 MEX" with the clock rolling 12'→34'. At the same time a huge "Striker #9" fitness number drains 60% → 33% inside a ring gauge that turns yellow, then red. It lands on the line "Running on empty." Both numbers are real output of the app's `LiveFitnessCalculator` at 12' and 34'.

## Key moments (the middle)
- The real dashboard's title and match row: "FIFA World Cup 2026 Live Analytics", then "Argentina 1-0 (34') Mexico 🟢 LIVE", with the LIVE dot pulsing.
- The real "⚡ Player Fitness" panel at 12' (🟢/🟡) wiping to the same panel at 34' (🔴) while a minute chip counts up.
- The real "💡 Substitution Recommendations" card: "#1 (81% Confidence)", "Off: Striker #9 (33% fitness)", "On: Forward #19 (89% fitness)", highlighted one line at a time.

## Outro / punchline
"FIFA SHADOW COACH" lockup, then `$ streamlit run world_cup_app.py` typed out, then github.com/harshul27/fifalyst.

## User flow worth showing
Open the dashboard → see a live match row from ESPN → watch each player's fitness fall as the minutes pass → get the substitution call (off / on / confidence).

## Tone
- Preset: default
- Creative direction: Saturday-night TV football broadcast package
- Interpretation: punchy and playful but confident. Broadcast graphics (score bug, minute chip), big condensed type, clean dips between scenes, and no sarcasm about the product.

## Format: landscape — 1920x1080
## Duration: 21s

## Visual identity (from the project)
The Streamlit app uses the default Streamlit theme and emoji status markers. Brand colours are taken from those:
- Background: #07110c night-pitch green-black (radial to #0f2a1b), for the video frame around the real white Streamlit UI
- Accent: #7ed957 (the dashboard's 🟢), plus status #fdd835 (🟡) and #ff4b4b (🔴 / Streamlit primary red)
- Text: #f3f7f2
- Display font: Anton (broadcast condensed)
- Body font: Source Sans 3 (the font Streamlit itself renders in)
- Strongest visual element: the emoji traffic-light fitness list and the substitution recommendation card

## Data note
Real screenshots of `world_cup_app.py` running in Streamlit. There was no live World Cup match, so a sample Argentina v Mexico match with fictional numbered players ("Striker #9", "Forward #19") was fed through the app's real `LiveFitnessCalculator` and `_generate_recommendations`. All percentages and the 81% confidence are genuine outputs of that code. There are no real player names.

## Share copy (draft)
Your striker is at 33% fitness in the 34th minute. The manager hasn't noticed. FIFA Shadow Coach has.

## Audio direction
- Role: warm, punchy bed with a few motion-matched accents
- Music: happy-beats-business-moves-vol-1-by-ende-dot-app.mp3 (120 BPM)
- Music treatment: quick fade-in, bed at about 0.35, a lift into the outro, fade out over the last ~0.8s
- Music cue guidance: bundled preset read (120.19 BPM). The beat grid runs every ~0.5s from 3.02s. Strong cues: 16.02, 17.02, 18.02. Lock the outro lockup to 18.02 and the confidence chip near 16.02. Scene cuts sit on the grid at 3.02 / 6.02 / 10.02 / 14.02.
- Audio-reactive treatment: subtle. Music bass makes the pitch glow and the centre-circle lines breathe. No waveform or equalizer visuals.
- SFX posture: moderate (default tone), motion-matched, low HF-risk picks
- Audio-coupled moments: fitness counter drop, drop into the wordmark, windows landing, the fitness wipe, the two highlight boxes, the confidence chip, the typed command, the outro payoff
- Restraint rule: no stacked hits, no bright repeated ticks, and nothing louder than the bed on repeated events

## Storyboard

### Scene 1 — Hook: fading striker — 3.0s
Score bug "ARG 1–0 MEX" slides down top-left, with its clock counting 12'→34'. A centred ring gauge drains while a giant "60%" counts down to "33%", yellow turning red. Labels read "STRIKER #9" and "FITNESS". At ~1.9s, "Running on empty." rises in and holds to the cut (~1s settled).
Sequential/interaction: yes. The number counts down step by step, synced with the clock.
Audio intent: tension building under the bed
Audio-coupled idea: counter ticks (sparse and soft), a soft thud when "Running on empty." lands
Music: bed fades in fast
Transition mood: clean dip → Scene 2

### Scene 2 — Reveal — 3.0s
"FIFA SHADOW COACH" (COACH in green) scales in with overshoot on the 3.02 beat. Then "Live World Cup 2026 fitness + sub calls" appears, then the three status pills 🟢 PEAK · 🟡 FAIR · 🔴 CRITICAL one by one (the calculator's real status names).
Sequential/interaction: yes. The pills arrive one by one on every other beat, then hold.
Audio intent: arrival and confidence
Audio-coupled idea: major-reveal soft impact at the wordmark, light drops on the pills
Transition mood: clean dip → Scene 3

### Scene 3 — Live scores — 4.0s
Caption "Live scores, straight from ESPN." A browser window rises holding the real dashboard title and the Argentina 1-0 (34') Mexico 🟢 LIVE row. The LIVE dot pulses and the camera slowly pushes in.
Sequential/interaction: caption, then the window
Audio intent: product lands
Audio-coupled idea: card slide when the window lands
Transition mood: clean dip → Scene 4

### Scene 4 — Fitness, minute by minute — 4.0s
Caption "Every player's fitness, minute by minute." The window shows the real Player Fitness panel at 12'. A red scan-line wipes down to reveal the 34' panel (🟢/🟡 → 🔴) while a red minute chip counts 12'→34'.
Sequential/interaction: yes. A simulated time-lapse wipe.
Audio intent: time passing
Audio-coupled idea: soft sweep/slide under the wipe
Transition mood: clean dip → Scene 5

### Scene 5 — The sub call — 4.0s
Caption "The sub call. Before the manager makes it." The real recommendation card: a red box draws over "Off: Striker #9 (33% fitness)", then a green box over "On: Forward #19 (89% fitness)". The "81% confidence" chip pops near the 16.02 strong cue.
Sequential/interaction: yes. The highlights arrive one by one, a beat apart, then hold.
Audio intent: the payoff
Audio-coupled idea: click per highlight, success accent on the chip
Transition mood: clean dip → Scene 6

### Scene 6 — Outro — 3.0s
"FIFA SHADOW COACH" lockup lands on 18.02, `$ streamlit run world_cup_app.py` types out, then "github.com/harshul27/fifalyst" fades up and holds.
Sequential/interaction: yes. A typed command.
Audio intent: resolved and proud
Audio-coupled idea: bell payoff on the lockup, soft keypresses for typing
Music: fades out over the last 0.8s

**Music mood for this video:** upbeat
**Audio summary:** The upbeat 120 BPM bed carries the whole piece: soft ticks build tension in the hook, a warm impact lands the reveal, crisp UI accents mark each product moment, and a bell closes the lockup as the music fades.
