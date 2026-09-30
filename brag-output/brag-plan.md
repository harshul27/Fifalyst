# /brag plan — FIFA Shadow Coach

**What it is:** A Streamlit dashboard that tracks live FIFA World Cup 2026 matches from ESPN, estimates every player's in-match fitness, and suggests who to sub.
**For:** Football nerds, armchair managers, analysts watching the World Cup.
**Sets it apart:** It doesn't just show the score. It says "take off #9, bring on #19" with a confidence number.
**Best claim:** The dashboard's own copy: "Real-time match tracking, player fitness, and substitution recommendations."
**Visual hook:** A striker's fitness draining live: 60% at 12' → 33% at 34'. Both numbers come from the app's own `LiveFitnessCalculator` math.
**Real UI shown:** Screenshots of the actual `world_cup_app.py` running in Streamlit. A sample Argentina v Mexico match (fictional numbered players) is fed through the real fitness calculator and the real `_generate_recommendations`.
**Tone:** `default` pushed toward a TV sports broadcast: dark pitch, score bug, confident cuts.
**Share caption:** Built an armchair-manager AI for World Cup 2026: live fitness for every player and the sub call before the manager makes it.

## Visual identity
- Night-pitch background #07110c → #0f2a1b, faint chalk pitch lines.
- Status colours taken from the dashboard's own 🟢🟡🔴: #7ed957 / #fdd835 / #ff4b4b (Streamlit red).
- Type: Anton (broadcast headlines), Source Sans 3 (Streamlit's UI font), JetBrains Mono (command).
- Real UI sits in a floating browser window over the pitch.

## Storyboard (21.0s, 30fps, 1920×1080, 120 BPM; every cut lands on a beat)
| # | Time | Scene | On-screen text | Motion / SFX |
|---|---|---|---|---|
| 1 | 0.0–3.0 | **Hook.** Score bug "ARG 1–0 MEX" with the clock rolling 12'→34'. A huge "Striker #9" fitness number drains 60%→33% while a ring gauge empties, yellow → red. | "STRIKER #9" · "60% → 33%" · "Running on empty." | Whistle at 0.1s, soft ticks as the number drops |
| 2 | 3.0–6.0 | **Reveal.** Wordmark. | "FIFA SHADOW COACH" / "Live World Cup 2026 fitness + sub calls" | Whoosh in, bass drop |
| 3 | 6.0–10.0 | **Live scores.** Browser window with the real title + the Argentina 1-0 Mexico (34') 🟢 LIVE row; the LIVE dot pulses. | "Live scores, straight from ESPN." | Window slides up |
| 4 | 10.0–14.0 | **Fitness.** Real Player Fitness panel at 12', then a wipe to the same panel at 34' (🟢🟡 → 🔴). A clock chip counts 12'→34'. | "Every player's fitness, minute by minute." | Wipe whoosh |
| 5 | 14.0–18.0 | **The sub call.** Real Substitution Recommendation #1, zoomed. A highlight sweeps "Off: Striker #9", then "On: Forward #19". | "The sub call. Before the manager makes it." + "81% confidence" chip | Soft click per highlight |
| 6 | 18.0–21.0 | **Outro.** Wordmark + typed `streamlit run world_cup_app.py` + repo. | "FIFA SHADOW COACH" / "github.com/harshul27/fifalyst" | Final hit, crowd swell fades |

Transitions dip through the background (old content out, then new in), with no muddy crossfades.

## Music cue guidance
Original synth track, 120 BPM in A minor, generated in numpy. Four bars of intro pulse under the hook, a drop at 3.0s, and a steady groove through the highlights. A final chord at 18.0s rings out. The SFX are tuned to A and placed on beat grid points.
