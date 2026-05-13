"""CSS strings for the dark cyber SaaS theme + the pixel-art office scene."""

DARK_THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@300;400;500;600;700;800;900&display=swap');

:root {
  --bg-deep: #04060f;
  --bg-base: #070b1a;
  --bg-card: rgba(15, 24, 48, 0.55);
  --bg-card-solid: #0f1830;
  --bg-card-hover: rgba(20, 33, 70, 0.75);
  --border: rgba(0, 217, 255, 0.18);
  --border-strong: rgba(0, 217, 255, 0.42);
  --cyan: #00d9ff;
  --cyan-bright: #4eecff;
  --cyan-glow: rgba(0, 217, 255, 0.55);
  --orange: #ff8c42;
  --orange-bright: #ffb380;
  --orange-glow: rgba(255, 140, 66, 0.55);
  --green: #00e676;
  --yellow: #ffd93d;
  --red: #ff4757;
  --purple: #9b59ff;
  --text-primary: #e8eef7;
  --text-secondary: #8b95a8;
  --text-muted: #4a5266;
}

/* Hide default Streamlit chrome */
#MainMenu        { visibility: hidden; }
footer           { visibility: hidden; }

/* Header: transparent dark bar, keep Deploy button */
header[data-testid="stHeader"] {
  background: rgba(4, 6, 15, 0.92) !important;
  border-bottom: 1px solid rgba(0, 217, 255, 0.10);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

/* Hide the screencast / record button, keep only Deploy */
[data-testid="stScreenCastRecordButton"],
button[aria-label="Record a screencast"],
button[aria-label="Stop recording"],
[data-testid="stToolbarActions"] > div:not(:last-child) { display: none !important; }

/* Background — deep blue-black with two distant nebulae */
.stApp {
  background:
    radial-gradient(ellipse 1200px 600px at 15% -10%, rgba(0, 217, 255, 0.10), transparent 60%),
    radial-gradient(ellipse 900px 700px at 95% 100%, rgba(255, 140, 66, 0.08), transparent 60%),
    radial-gradient(ellipse 1400px 800px at 50% 50%, rgba(20, 30, 80, 0.25), transparent 70%),
    linear-gradient(180deg, var(--bg-deep) 0%, var(--bg-base) 100%);
  color: var(--text-primary);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Subtle grid overlay */
.stApp::before {
  content: '';
  position: fixed; inset: 0;
  background-image:
    linear-gradient(rgba(0, 217, 255, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 217, 255, 0.025) 1px, transparent 1px);
  background-size: 60px 60px;
  pointer-events: none;
  z-index: 0;
}

/* Make sidebar feel like a console */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #060c1c 0%, #030712 100%);
  border-right: 1px solid var(--border);
  box-shadow: 4px 0 30px rgba(0, 0, 0, 0.5);
}
[data-testid="stSidebar"] * { color: var(--text-primary); }

/* Main block padding */
.block-container {
  padding-top: 1.5rem !important;
  padding-bottom: 6rem !important;
  max-width: 100% !important;
}

/* ==================== Typography ==================== */

h1, h2, h3, h4 {
  font-family: 'Inter', sans-serif;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}

.eyebrow {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.22em;
  color: var(--cyan);
  text-transform: uppercase;
  margin-bottom: 0.5rem;
  display: inline-block;
  padding: 0.2rem 0.7rem;
  background: rgba(0, 217, 255, 0.08);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
}

.section-title {
  font-size: 2.4rem;
  font-weight: 800;
  background: linear-gradient(120deg, #ffffff 0%, var(--cyan) 60%, var(--orange) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin: 0.25rem 0 0.4rem 0;
  letter-spacing: -0.03em;
  line-height: 1.1;
}

.section-sub {
  color: var(--text-secondary);
  font-size: 1rem;
  margin-bottom: 1.6rem;
  max-width: 780px;
  line-height: 1.55;
}

.mono { font-family: 'JetBrains Mono', monospace; }

/* ==================== Cards ==================== */

.glass-card {
  background: var(--bg-card);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 1.4rem 1.5rem;
  box-shadow: 0 6px 32px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255,255,255,0.03);
  position: relative;
  overflow: hidden;
}
.glass-card::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 1px;
  background: linear-gradient(90deg, transparent, var(--cyan), transparent);
  opacity: 0.5;
}
.glass-card-hover:hover {
  background: var(--bg-card-hover);
  border-color: var(--border-strong);
  transition: all .25s;
}

.kpi-card {
  background: linear-gradient(135deg, rgba(20, 33, 70, 0.7), rgba(15, 24, 48, 0.5));
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 1.1rem 1.3rem;
  position: relative;
}
.kpi-label {
  color: var(--text-secondary);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  margin-bottom: 0.4rem;
}
.kpi-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 2rem;
  font-weight: 700;
  color: var(--cyan);
  text-shadow: 0 0 18px var(--cyan-glow);
  line-height: 1;
}
.kpi-value.orange { color: var(--orange); text-shadow: 0 0 18px var(--orange-glow); }
.kpi-value.green  { color: var(--green);  text-shadow: 0 0 18px rgba(0, 230, 118, 0.4); }
.kpi-value.red    { color: var(--red);    text-shadow: 0 0 18px rgba(255, 71, 87, 0.4); }
.kpi-sub  { color: var(--text-secondary); font-size: 0.78rem; margin-top: 0.35rem; }

/* ==================== Buttons ==================== */

.stButton > button, .stDownloadButton > button {
  background: linear-gradient(135deg, rgba(0, 217, 255, 0.16), rgba(255, 140, 66, 0.10));
  border: 1px solid var(--border-strong);
  color: var(--text-primary);
  border-radius: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  transition: all 0.22s ease;
  padding: 0.5rem 1.1rem;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  background: linear-gradient(135deg, rgba(0, 217, 255, 0.32), rgba(255, 140, 66, 0.22));
  border-color: var(--cyan);
  box-shadow: 0 0 28px var(--cyan-glow);
  transform: translateY(-1px);
}
.stButton > button:focus { box-shadow: 0 0 0 2px var(--cyan); }

/* Primary CTA — pipeline run */
button[kind="primary"] {
  background: linear-gradient(135deg, var(--cyan) 0%, #6ad7ff 50%, var(--orange) 100%) !important;
  color: #04060f !important;
  border: none !important;
  font-weight: 800 !important;
  box-shadow: 0 0 26px var(--cyan-glow), 0 0 38px var(--orange-glow) !important;
}

/* ==================== Inputs ==================== */

.stTextInput input, .stTextArea textarea, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
  background: rgba(5, 10, 24, 0.7) !important;
  border: 1px solid var(--border) !important;
  color: var(--text-primary) !important;
  border-radius: 10px !important;
}
.stTextInput input:focus { border-color: var(--cyan) !important; box-shadow: 0 0 0 2px var(--cyan-glow) !important; }

/* Secret-input masking via st.container(key="masked_*") wrapper.
   Why: type="password" triggers Chrome's "save password?" popup + later autofill.
   We use type="default" (so Chrome ignores it) + CSS to visually mask the chars. */
.st-key-masked_llm_key input,
.st-key-masked_epa_key input,
.st-key-masked_discord_url input {
  -webkit-text-security: disc !important;
  -moz-text-security: disc !important;
  text-security: disc !important;
  font-family: "JetBrains Mono", monospace !important;
  letter-spacing: 0.12em !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] { background: transparent; gap: 0.4rem; border-bottom: 1px solid var(--border); }
.stTabs [data-baseweb="tab"] {
  background: rgba(15, 24, 48, 0.4);
  border: 1px solid var(--border);
  border-radius: 8px 8px 0 0;
  padding: 0.55rem 1.1rem;
  color: var(--text-secondary);
}
.stTabs [aria-selected="true"] {
  background: linear-gradient(180deg, rgba(0, 217, 255, 0.18), transparent);
  color: var(--cyan) !important;
  border-color: var(--border-strong);
  box-shadow: 0 -2px 12px var(--cyan-glow);
}

/* Radio / segmented controls */
.stRadio > div { gap: 0.4rem; }
.stRadio label { color: var(--text-primary) !important; }

/* Slider */
.stSlider [role="slider"] { background: var(--cyan) !important; box-shadow: 0 0 12px var(--cyan-glow) !important; }

/* Toggle */
.stCheckbox label, .stToggle label { color: var(--text-primary) !important; }

/* Metric */
[data-testid="stMetric"] {
  background: rgba(15, 24, 48, 0.5);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.85rem 1.1rem;
}
[data-testid="stMetricValue"] { color: var(--cyan) !important; }

/* Divider */
hr { border-color: var(--border) !important; opacity: 0.4; }

/* ==================== Status pill ==================== */

.pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.65rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.pill .dot {
  width: 6px; height: 6px; border-radius: 50%;
  box-shadow: 0 0 8px currentColor;
  animation: pulse 1.4s ease-in-out infinite;
}
@keyframes pulse {
  0%,100% { opacity: 1; transform: scale(1); }
  50%     { opacity: 0.4; transform: scale(0.75); }
}
.pill.cyan   { color: var(--cyan);   background: rgba(0, 217, 255, 0.10); border: 1px solid var(--border-strong); }
.pill.orange { color: var(--orange); background: rgba(255, 140, 66, 0.10); border: 1px solid rgba(255, 140, 66, 0.4); }
.pill.green  { color: var(--green);  background: rgba(0, 230, 118, 0.10);  border: 1px solid rgba(0, 230, 118, 0.4); }
.pill.red    { color: var(--red);    background: rgba(255, 71, 87, 0.10);  border: 1px solid rgba(255, 71, 87, 0.4); }
.pill.gray   { color: var(--text-secondary); background: rgba(139, 149, 168, 0.10); border: 1px solid rgba(139, 149, 168, 0.3); }
.pill.gray .dot { animation: none; opacity: 0.6; }

/* ==================== AQI badge ==================== */

.aqi-badge {
  display: inline-flex; align-items: center; gap: 0.5rem;
  padding: 0.35rem 0.8rem; border-radius: 8px;
  font-weight: 700;
  background: rgba(0,0,0,0.4);
  font-family: 'JetBrains Mono', monospace;
}

/* ==================== Hero ==================== */

.hero-wrap {
  background:
    radial-gradient(ellipse 600px 300px at 80% 50%, rgba(255, 140, 66, 0.15), transparent 60%),
    radial-gradient(ellipse 600px 300px at 20% 50%, rgba(0, 217, 255, 0.15), transparent 60%),
    linear-gradient(135deg, rgba(15, 24, 48, 0.7), rgba(5, 10, 24, 0.7));
  border: 1px solid var(--border-strong);
  border-radius: 22px;
  padding: 2rem 2.4rem;
  margin-bottom: 1.5rem;
  position: relative;
  overflow: hidden;
}
.hero-wrap::after {
  content: '';
  position: absolute; bottom: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, transparent, var(--cyan), var(--orange), transparent);
}
.hero-title {
  font-size: 2.8rem;
  font-weight: 900;
  letter-spacing: -0.04em;
  margin: 0.3rem 0 0.6rem 0;
  line-height: 1.05;
}
.hero-title .accent { color: var(--cyan); text-shadow: 0 0 28px var(--cyan-glow); }
.hero-title .accent2{ color: var(--orange); text-shadow: 0 0 28px var(--orange-glow); }
.hero-sub {
  color: var(--text-secondary);
  font-size: 1.05rem;
  max-width: 720px;
  line-height: 1.6;
}

/* ==================== Misc helpers ==================== */

.scroll-hint {
  text-align: center;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  letter-spacing: 0.2em;
  margin: 1rem 0 0.4rem 0;
}

.tag {
  display: inline-block;
  padding: 0.15rem 0.55rem;
  border-radius: 6px;
  font-size: 0.72rem;
  font-weight: 600;
  margin-right: 0.35rem;
  background: rgba(0, 217, 255, 0.10);
  color: var(--cyan);
  border: 1px solid var(--border);
  font-family: 'JetBrains Mono', monospace;
}
.tag.orange { background: rgba(255, 140, 66, 0.10); color: var(--orange); border-color: rgba(255, 140, 66, 0.3); }
.tag.purple { background: rgba(155, 89, 255, 0.10); color: var(--purple); border-color: rgba(155, 89, 255, 0.3); }
.tag.green  { background: rgba(0, 230, 118, 0.10);  color: var(--green);  border-color: rgba(0, 230, 118, 0.3); }

.muted { color: var(--text-secondary); }
.tiny  { font-size: 0.78rem; }

/* Plotly tooltip styling */
.js-plotly-plot .plotly .modebar { display: none !important; }

/* Streamlit chat */
[data-testid="stChatMessage"] { background: rgba(15, 24, 48, 0.6); border: 1px solid var(--border); border-radius: 14px; }

/* Expander */
.stExpander {
  background: rgba(15, 24, 48, 0.4);
  border: 1px solid var(--border) !important;
  border-radius: 12px !important;
}
.streamlit-expanderHeader { color: var(--text-primary) !important; font-weight: 600 !important; }

/* ==================== Cover / landing page ==================== */
.cover-wrap {
  min-height: 78vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 3rem 1.5rem 2rem 1.5rem;
  position: relative;
}
.cover-wrap::before {
  content: '';
  position: absolute; inset: 0;
  background:
    radial-gradient(ellipse 700px 400px at 50% 30%, rgba(0, 217, 255, 0.15), transparent 60%),
    radial-gradient(ellipse 500px 400px at 50% 80%, rgba(255, 140, 66, 0.10), transparent 60%);
  pointer-events: none;
  z-index: -1;
}
.cover-logo {
  font-size: 7.5rem;
  line-height: 1;
  filter:
    drop-shadow(0 0 30px var(--cyan-glow))
    drop-shadow(0 0 50px var(--orange-glow));
  animation: coverFloat 3.6s ease-in-out infinite;
  margin-bottom: 1rem;
}
@keyframes coverFloat {
  0%,100% { transform: translateY(0) rotate(-3deg); }
  50%     { transform: translateY(-12px) rotate(3deg); }
}
.cover-eyebrow {
  font-family: 'JetBrains Mono', monospace;
  color: var(--cyan);
  letter-spacing: 0.32em;
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  margin-bottom: 1rem;
  padding: 0.3rem 0.9rem;
  border: 1px solid var(--border-strong);
  border-radius: 999px;
  background: rgba(0, 217, 255, 0.08);
  display: inline-block;
}
.cover-title {
  font-size: 5rem;
  font-weight: 900;
  background: linear-gradient(120deg, #ffffff 0%, var(--cyan) 45%, var(--orange) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin: 0.4rem 0 0.8rem 0;
  letter-spacing: -0.045em;
  line-height: 1.05;
}
.cover-subtitle {
  color: var(--text-secondary);
  font-size: 1.15rem;
  max-width: 680px;
  line-height: 1.7;
  margin: 0 auto 2rem auto;
}
.cover-features {
  display: flex;
  gap: 0.7rem;
  flex-wrap: wrap;
  justify-content: center;
  margin-bottom: 2.4rem;
  max-width: 760px;
}
.cover-feature {
  background: rgba(15, 24, 48, 0.5);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.75rem 1.1rem;
  font-size: 0.85rem;
  color: var(--text-primary);
  font-weight: 600;
  display: flex; align-items: center; gap: 0.5rem;
}
.cover-feature .ico { font-size: 1.05rem; }
.cover-status {
  display: flex; gap: 0.6rem; flex-wrap: wrap; justify-content: center;
  margin-bottom: 2.5rem;
}
.cover-hint {
  color: var(--text-muted);
  font-size: 0.82rem;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.15em;
  margin-top: 1rem;
  text-transform: uppercase;
  opacity: 0.7;
  animation: hintPulse 2s ease-in-out infinite;
}
@keyframes hintPulse { 0%,100% { opacity: 0.5; } 50% { opacity: 1; } }

@keyframes ctaGlow {
  0%,100% { box-shadow: 0 0 40px var(--cyan-glow), 0 0 60px var(--orange-glow), 0 8px 24px rgba(0,0,0,0.4); }
  50%     { box-shadow: 0 0 60px var(--cyan-glow), 0 0 90px var(--orange-glow), 0 12px 32px rgba(0,0,0,0.5); }
}
</style>
"""


# ---------------------------------------------------------------------------
# Pixel-art office HTML
# ---------------------------------------------------------------------------

AGENT_STAGE_CSS = """
<style>
.office {
  background:
    repeating-linear-gradient(0deg, transparent 0, transparent 19px, rgba(0,217,255,0.06) 19px, rgba(0,217,255,0.06) 20px),
    repeating-linear-gradient(90deg, transparent 0, transparent 19px, rgba(0,217,255,0.06) 19px, rgba(0,217,255,0.06) 20px),
    linear-gradient(180deg, #0a1228 0%, #050a18 100%);
  border: 1px solid rgba(0, 217, 255, 0.25);
  border-radius: 18px;
  padding: 1.8rem 1.0rem 1.2rem 1.0rem;
  display: grid;
  /* Force 3 in a row so the three lobsters line up neatly across the
     full office width. Fall back to 1×3 on very narrow screens. */
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.9rem;
  image-rendering: pixelated;
  position: relative;
  min-height: 320px;
}
@media (max-width: 720px) {
  .office { grid-template-columns: 1fr; }
}
.office::before {
  content: 'PIXEL OFFICE · LOBSTER AGENTS';
  position: absolute; top: 8px; left: 14px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  letter-spacing: 0.25em;
  color: rgba(0, 217, 255, 0.5);
  text-transform: uppercase;
}

.desk {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;          /* anchor lobster + base to the bottom */
  padding-top: 1rem;
  min-height: 260px;                  /* keep all 4 desks the same height */
}

.bubble {
  background: rgba(15, 24, 48, 0.95);
  border: 1px solid var(--bubble-color, #00d9ff);
  border-radius: 10px;
  padding: 0.45rem 0.6rem;
  font-size: 0.7rem;
  color: #e8eef7;
  /* Tight gap below so the speech-tail visually meets the lobster's head
     without an awkward floating distance. */
  margin-bottom: 0.15rem;
  position: relative;
  width: 100%;
  max-width: 200px;
  min-height: 3rem;
  box-sizing: border-box;
  text-align: center;
  box-shadow: 0 0 14px var(--bubble-glow, rgba(0, 217, 255, 0.4));
  animation: bubbleIn 0.4s ease-out;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-height: 1.25;
  word-break: break-word;
}
.bubble::after {
  content: '';
  position: absolute;
  /* Tail extends slightly past the bubble so it sits between bubble and
     the lobster's head — not the desk monitor box below. */
  bottom: -7px; left: 50%;
  transform: translateX(-50%);
  border: 7px solid transparent;
  border-top-color: var(--bubble-color, #00d9ff);
}
/* Empty state — fully hidden, takes no visual space (no faint outline,
   no margin). The desk's flex layout keeps the lobster anchored at the
   bottom regardless. */
.bubble.empty {
  opacity: 0;
  border: 1px dashed transparent;
  box-shadow: none;
  visibility: hidden;
}
.bubble.empty::after { border-top-color: transparent; }
@keyframes bubbleIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

.lobster {
  font-size: 3.2rem;
  filter: grayscale(0.6) brightness(0.7);
  transition: filter 0.4s, transform 0.3s, text-shadow 0.4s;
  line-height: 1;
  /* Lift the emoji a hair so the speech-bubble tail visually lands on the
     lobster's head, not on empty space above it. */
  margin-top: -0.25rem;
}
.lobster.active {
  filter: none;
  text-shadow: 0 0 18px var(--agent-glow, #00d9ff);
  animation: bob 1.2s ease-in-out infinite;
}
@keyframes bob {
  0%,100% { transform: translateY(0) rotate(-2deg); }
  50%     { transform: translateY(-4px) rotate(2deg); }
}

.monitor {
  width: 84px; height: 62px;
  background: #0a1228;
  border: 2px solid var(--agent-color, #00d9ff);
  border-radius: 4px;
  margin-top: 0.3rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--agent-color, #00d9ff);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.62rem;
  text-shadow: 0 0 6px var(--agent-color, #00d9ff);
  position: relative;
  box-shadow: inset 0 0 12px rgba(0, 217, 255, 0.2);
}
.monitor.active::after {
  content: '';
  position: absolute; top: 4px; right: 6px;
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--agent-color, #00d9ff);
  box-shadow: 0 0 8px var(--agent-color, #00d9ff);
  animation: pulse 1s ease-in-out infinite;
}

.desk-base {
  width: 110px; height: 8px;
  background: linear-gradient(180deg, #1a2545 0%, #0f1830 100%);
  border-top: 1px solid rgba(0, 217, 255, 0.3);
  margin-top: 4px;
}

.agent-label {
  margin-top: 0.4rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--agent-color, #00d9ff);
  letter-spacing: 0.08em;
}
.agent-role {
  font-size: 0.7rem;
  color: #8b95a8;
  margin-top: 2px;
}
.agent-desc {
  font-size: 0.66rem;
  color: #6a7080;
  margin-top: 4px;
  text-align: center;
  max-width: 170px;
  line-height: 1.35;
  /* Reserve 2 lines of description height so desks whose desc happens to
     fit on 1 line (e.g. 預警員's short blurb) still match the height of
     the 2-line desks (採集者 / 分析師). Without this, `justify-content:
     flex-end` on .desk pushes the shorter desk's lobster downward. */
  min-height: calc(0.66rem * 1.35 * 2);
}

/* Browser screenshot viewport */
.browser-window {
  background: #0a1228;
  border: 1px solid rgba(0, 217, 255, 0.3);
  border-radius: 10px;
  overflow: hidden;
  font-family: 'JetBrains Mono', monospace;
}
.browser-bar {
  background: linear-gradient(180deg, #1a2545, #0f1830);
  padding: 0.4rem 0.6rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  border-bottom: 1px solid rgba(0, 217, 255, 0.2);
}
.browser-dot { width: 9px; height: 9px; border-radius: 50%; }
.browser-url {
  flex: 1; font-size: 0.65rem; color: #8b95a8;
  background: rgba(0,0,0,0.3); padding: 0.18rem 0.5rem; border-radius: 4px;
  margin-left: 0.4rem;
}
.browser-body {
  padding: 0.8rem; font-size: 0.7rem;
  background:
    repeating-linear-gradient(0deg, transparent 0 24px, rgba(255,255,255,0.02) 24px 25px);
  color: #c0c8d8;
  min-height: 120px;
  position: relative;
}
.scan-row {
  display: flex; justify-content: space-between; padding: 0.18rem 0;
  border-bottom: 1px dashed rgba(255,255,255,0.06);
}
.scan-row.highlight {
  background: rgba(255, 140, 66, 0.08);
  border: 1px solid var(--orange);
  border-radius: 4px;
  box-shadow: 0 0 12px rgba(255, 140, 66, 0.5);
  padding: 0.18rem 0.5rem;
  animation: scanPulse 1.4s ease-in-out infinite;
  color: var(--orange);
}
@keyframes scanPulse {
  0%,100% { box-shadow: 0 0 12px rgba(255, 140, 66, 0.4); }
  50%     { box-shadow: 0 0 22px rgba(255, 140, 66, 0.8); }
}
.scan-cursor {
  position: absolute;
  width: 8px; height: 12px;
  background: var(--orange);
  animation: blink 0.7s steps(1) infinite;
}
@keyframes blink {
  0%,50%   { opacity: 1; }
  51%,100% { opacity: 0; }
}

/* Communication log (legacy, still used for RAG docs list) */
.comm-log {
  background: #050a18;
  border: 1px solid rgba(0, 217, 255, 0.2);
  border-radius: 10px;
  padding: 0.6rem 0.8rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  max-height: 360px;
  overflow-y: auto;
}
.comm-row { padding: 0.32rem 0; border-bottom: 1px dashed rgba(255,255,255,0.04); }
.comm-row:last-child { border-bottom: none; }
.comm-time { color: #4a5266; margin-right: 0.5rem; }
.comm-agent {
  display: inline-block; padding: 0.05rem 0.4rem; border-radius: 4px;
  font-weight: 700; margin-right: 0.5rem; font-size: 0.65rem;
}

/* ==================== Multi-agent group chat room ==================== */
.chat-room {
  background:
    linear-gradient(180deg, rgba(5, 10, 24, 0.6) 0%, rgba(5, 10, 24, 0.95) 100%);
  border: 1px solid rgba(0, 217, 255, 0.22);
  border-radius: 14px;
  padding: 0.6rem 0.4rem 0.6rem 0.6rem;
  max-height: 380px;
  overflow-y: auto;
  scroll-behavior: smooth;
}
.chat-room::-webkit-scrollbar { width: 6px; }
.chat-room::-webkit-scrollbar-thumb { background: rgba(0,217,255,0.2); border-radius: 3px; }
.chat-room::-webkit-scrollbar-track { background: transparent; }

.chat-msg-row {
  display: flex;
  gap: 0.6rem;
  padding: 0.55rem 0.3rem;
  border-bottom: 1px dashed rgba(255, 255, 255, 0.04);
  animation: chatBubbleIn 0.25s ease-out;
}
.chat-msg-row:last-child { border-bottom: none; }
@keyframes chatBubbleIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}

.chat-avatar {
  width: 30px; height: 30px;
  min-width: 30px;
  border-radius: 50%;
  color: #04060f;
  font-weight: 900;
  font-size: 0.78rem;
  font-family: 'JetBrains Mono', monospace;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  border: 1px solid rgba(255, 255, 255, 0.18);
}

.chat-body { flex: 1; min-width: 0; }

.chat-meta {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.68rem;
  font-family: 'JetBrains Mono', monospace;
  margin-bottom: 0.25rem;
  flex-wrap: wrap;
}
.chat-from {
  font-weight: 800;
  letter-spacing: 0.02em;
}
.chat-arrow {
  color: #4a5266;
  font-weight: 700;
  margin: 0 1px;
  font-size: 0.85rem;
  line-height: 1;
}
.chat-to {
  font-weight: 700;
  letter-spacing: 0.02em;
  padding: 0.05rem 0.35rem;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.04);
}
.chat-meta-sep { color: #4a5266; }
.chat-sys-tag {
  color: #8b95a8;
  background: rgba(139, 149, 168, 0.10);
  padding: 0.05rem 0.35rem;
  border-radius: 4px;
  font-size: 0.62rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.chat-time {
  color: #4a5266;
  margin-left: auto;
  font-size: 0.65rem;
}
.chat-text {
  color: #d4dae8;
  font-size: 0.82rem;
  line-height: 1.5;
  word-break: break-word;
}

/* Cleaning report card */
.clean-card {
  background: linear-gradient(135deg, rgba(20, 33, 70, 0.7), rgba(15, 24, 48, 0.5));
  border: 1px solid rgba(255, 140, 66, 0.4);
  border-radius: 14px;
  padding: 1rem 1.2rem;
  box-shadow: 0 0 24px rgba(255, 140, 66, 0.15);
}
.clean-card .head {
  font-family: 'JetBrains Mono', monospace;
  color: var(--orange);
  font-size: 0.72rem;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  margin-bottom: 0.6rem;
}

/* Compact 2×2 grid of agent reports under the lobster theater.
   Each card is a <details> element — collapsed shows role + 1-sentence
   preview; click expands to the full LLM reply. This keeps the dashboard
   sections below from getting pushed down by long Gemini responses. */
.agent-report-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  /* align-items: start prevents one card's expansion from stretching the
     other card in the same grid row — each <details> grows independently. */
  align-items: start;
  gap: 0.6rem;
  margin-top: 0.35rem;
}
.agent-report {
  background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 10%, rgba(15, 24, 48, 0.5)), rgba(15, 24, 48, 0.55));
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
  border-left: 3px solid var(--accent);
  border-radius: 10px;
  padding: 0.55rem 0.8rem;
  transition: border-color 0.15s ease, box-shadow 0.2s ease;
}
.agent-report:hover {
  border-color: color-mix(in srgb, var(--accent) 60%, transparent);
}
.agent-report[open] {
  /* Subtle highlight when expanded so the user can see which one's open */
  box-shadow: 0 0 22px color-mix(in srgb, var(--accent) 18%, transparent);
  border-color: color-mix(in srgb, var(--accent) 55%, transparent);
}
.agent-report summary {
  cursor: pointer;
  list-style: none;
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-areas: "head toggle" "preview toggle";
  column-gap: 0.6rem;
  row-gap: 0.2rem;
  align-items: start;
}
.agent-report summary::-webkit-details-marker,
.agent-report summary::marker { display: none; content: ''; }

.agent-report-head {
  grid-area: head;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 0.72rem;
  letter-spacing: 0.08em;
}
.agent-report-label {
  color: #8b95a8;
  font-weight: 500;
  letter-spacing: 0;
}
.agent-report-preview {
  grid-area: preview;
  font-size: 0.78rem;
  line-height: 1.5;
  color: #c0c8d8;
  /* Clamp to 2 lines max in the collapsed preview so all 4 cards stay
     the same compact height regardless of how chatty Gemini is. */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.agent-report-toggle {
  grid-area: toggle;
  align-self: end;
  font-size: 0.65rem;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
  opacity: 0.75;
  padding-left: 0.5rem;
  border-left: 1px solid rgba(255, 255, 255, 0.08);
  user-select: none;
}
.agent-report:not([open]) .agent-report-toggle::before { content: '▶ 看詳細'; }
.agent-report[open] .agent-report-toggle::before { content: '▼ 收合'; }

.agent-report-body {
  margin-top: 0.55rem;
  padding-top: 0.55rem;
  border-top: 1px dashed rgba(255, 255, 255, 0.10);
  font-size: 0.8rem;
  line-height: 1.6;
  color: #c0c8d8;
  white-space: pre-wrap;
  word-break: break-word;
}
@media (max-width: 1100px) {
  .agent-report-grid { grid-template-columns: 1fr; }
}

/* Health alert card */
.alert-card {
  background: linear-gradient(135deg, rgba(20, 33, 70, 0.6), rgba(15, 24, 48, 0.4));
  border: 1px solid rgba(0, 217, 255, 0.2);
  border-left: 4px solid var(--accent, #00d9ff);
  border-radius: 12px;
  padding: 1rem 1.2rem;
  margin-bottom: 0.8rem;
  position: relative;
}
.alert-city { font-weight: 800; font-size: 1.05rem; letter-spacing: -0.01em; }
.alert-aqi {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.8rem; font-weight: 800;
  color: var(--accent, #00d9ff);
  text-shadow: 0 0 14px var(--accent-glow, rgba(0,217,255,0.4));
  line-height: 1;
}

/* Expanded floating chat panel — bottom-right, replaces FAB when chat_expanded */
.st-key-floating_chat {
  position: fixed !important;
  bottom: 24px !important;
  right: 24px !important;
  z-index: 99999 !important;
  width: 440px !important;
  /* Pinned at full height from the moment the panel opens — using `height`
     (not max-height) so it never collapses to content. The calc clamp keeps
     it inside the viewport on smaller laptop screens. */
  height: 640px !important;
  max-height: calc(100vh - 60px) !important;
  background: rgba(10, 18, 40, 0.97) !important;
  -webkit-backdrop-filter: blur(16px);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(0, 217, 255, 0.35) !important;
  border-radius: 18px !important;
  padding: 14px 16px 18px !important;
  box-shadow:
    0 20px 50px rgba(0, 0, 0, 0.7),
    0 0 40px rgba(0, 217, 255, 0.18) !important;
  /* The panel itself doesn't scroll — only the inner history container does.
     This pins the chat-input to the bottom and the contact bar to the top. */
  overflow: hidden !important;
  display: flex !important;
  flex-direction: column !important;
  gap: 0.3rem;
}
/* LINE-style contact bar at top of expanded chat panel */
.line-contact-bar {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  padding: 0.45rem 0.5rem 0.7rem 0.2rem;
  margin: -4px -6px 0.45rem -6px;     /* extend to panel edges */
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding-right: 44px;                /* leave room for the absolute close btn */
}
.line-contact-avatar {
  width: 40px; height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #ff6b35, #ff8c42);
  box-shadow: 0 0 12px rgba(255, 107, 53, 0.55);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; line-height: 1;
  flex-shrink: 0;
  border: 2px solid rgba(255, 255, 255, 0.08);
}
.line-contact-info { flex: 1; min-width: 0; }
.line-contact-name {
  font-weight: 800;
  font-size: 0.95rem;
  color: #e8eef7;
  letter-spacing: -0.01em;
  line-height: 1.15;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.line-contact-status {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  color: #8b95a8;
  font-size: 0.72rem;
  margin-top: 2px;
}
.line-status-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #00e676;
  box-shadow: 0 0 6px rgba(0, 230, 118, 0.7);
  animation: linePulse 1.6s ease-in-out infinite;
}
@keyframes linePulse {
  0%,100% { opacity: 1; transform: scale(1); }
  50%     { opacity: 0.55; transform: scale(0.85); }
}

/* Close button inside the panel: target by widget key for precision.
   Streamlit (>=1.40) adds class `.st-key-<key>` on the wrapper div of any
   widget that has a key argument — so .st-key-chat_close hits our ✕ button
   wrapper exactly, without leaking to chat-input or expander toggle buttons. */
.st-key-floating_chat .st-key-chat_close {
  position: absolute !important;
  top: 10px !important;
  right: 10px !important;
  width: 32px !important;
  height: 32px !important;
  margin: 0 !important;
  padding: 0 !important;
  z-index: 1000 !important;
}
.st-key-floating_chat .st-key-chat_close > div,
.st-key-floating_chat .st-key-chat_close button {
  width: 32px !important;
  height: 32px !important;
  min-width: 32px !important;
  min-height: 32px !important;
  padding: 0 !important;
  margin: 0 !important;
  border-radius: 50% !important;
  background: rgba(255, 255, 255, 0.08) !important;
  color: #c0c8d8 !important;
  border: 1px solid rgba(255, 255, 255, 0.18) !important;
  font-size: 0.92rem !important;
  font-weight: 700 !important;
  line-height: 1 !important;
  box-shadow: none !important;
  animation: none !important;
  /* Snap hover/active states immediately — no inherited 0.22s transition.
     Long transitions made the close look "twitchy" because the panel got
     unmounted mid-animation when Streamlit re-ran after the click. */
  transition: background-color 80ms ease, color 80ms ease, border-color 80ms ease !important;
  transform: none !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}
.st-key-floating_chat .st-key-chat_close button:hover {
  background: rgba(255, 71, 87, 0.20) !important;
  color: #ff4757 !important;
  border-color: rgba(255, 71, 87, 0.5) !important;
  transform: none !important;
  box-shadow: none !important;
}
.st-key-floating_chat .st-key-chat_close button:active,
.st-key-floating_chat .st-key-chat_close button:focus {
  /* Kill the focus ring and the active-state translateY that .stButton's
     base style would otherwise apply on press — keeps the click visually
     stable through the Streamlit rerun. */
  transform: none !important;
  box-shadow: 0 0 0 2px rgba(255, 71, 87, 0.35) !important;
  outline: none !important;
}
/* Chat input inside the floating panel.
   `margin-top: auto` + `flex-shrink: 0` + `order: 99` guarantee the input
   is always pinned to the very bottom of the flex column, regardless of
   how short the conversation history is or how Streamlit re-orders the
   DOM after a rerun. */
.st-key-floating_chat [data-testid="stChatInput"] {
  margin-top: auto !important;
  flex-shrink: 0 !important;
  order: 99 !important;
}
.st-key-floating_chat [data-testid="stChatInput"] textarea {
  min-height: 44px !important;
  padding: 11px 14px !important;
  font-size: 0.88rem !important;
  line-height: 1.4 !important;
  border-radius: 14px !important;
}
.st-key-floating_chat [data-testid="stChatInput"] > div {
  border-radius: 14px !important;
}
/* Slightly larger submit button (↑) to match the taller input */
.st-key-floating_chat [data-testid="stChatInput"] button {
  width: 34px !important;
  height: 34px !important;
}
/* Inner scroll container: only the history scrolls, the contact bar above
   and the chat input below stay pinned. `flex: 1` claims all remaining
   vertical space; `min-height: 0` lets overflow-y actually engage inside
   a flex parent. Inner flex with `justify-content: flex-end` anchors the
   welcome message (and short conversations) to the bottom, right above
   the input — matching LINE's UX. */
.st-key-chat_history {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  overflow-y: auto !important;
  padding-right: 4px;
  display: flex !important;
  flex-direction: column !important;
  justify-content: flex-end !important;
  order: 1 !important;
}
.st-key-chat_history::-webkit-scrollbar { width: 6px; }
.st-key-chat_history::-webkit-scrollbar-thumb { background: rgba(0, 217, 255, 0.25); border-radius: 3px; }
.st-key-chat_history::-webkit-scrollbar-track { background: transparent; }

/* Per-message references row — under each bot reply, indented to align with
   the bubble (avatar 32 + gap 8 ≈ 42px). Collapsed by default via <details>. */
.line-refs-row {
  display: flex;
  padding-left: 42px;
  margin-top: -2px;
  margin-bottom: 0.2rem;
  max-width: 100%;
}
.line-bubble-refs {
  background: transparent;
  border-radius: 8px;
  max-width: 78%;
  min-width: 0;
}
.line-bubble-refs summary {
  font-size: 0.7rem;
  color: #9b59ff;
  cursor: pointer;
  list-style: none;
  padding: 3px 9px;
  background: rgba(155, 89, 255, 0.10);
  border: 1px solid rgba(155, 89, 255, 0.25);
  border-radius: 8px;
  user-select: none;
  display: inline-block;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.line-bubble-refs summary::-webkit-details-marker { display: none; }
.line-bubble-refs summary::marker { content: ''; }
.line-bubble-refs[open] summary::before { content: '▼ '; opacity: 0.7; }
.line-bubble-refs:not([open]) summary::before { content: '▶ '; opacity: 0.7; }
.line-bubble-refs .ref-list {
  margin-top: 4px;
  padding: 8px 10px;
  background: rgba(155, 89, 255, 0.06);
  border-left: 2px solid #9b59ff;
  border-radius: 0 8px 8px 0;
}
.line-bubble-refs .ref-item {
  font-size: 0.72rem;
  line-height: 1.5;
  padding: 3px 0;
}
.line-bubble-refs .ref-item + .ref-item {
  border-top: 1px dashed rgba(155, 89, 255, 0.15);
  margin-top: 4px;
  padding-top: 6px;
}
.line-bubble-refs .ref-source {
  color: #9b59ff;
  font-weight: 700;
  font-size: 0.7rem;
}
.line-bubble-refs .ref-quote {
  color: #c0c8d8;
  margin-top: 2px;
}
@media (max-width: 768px) {
  .st-key-floating_chat { width: calc(100vw - 32px) !important; right: 16px !important; }
}

/* LINE-style chat bubbles inside the floating panel */
.line-chat-stream {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;                /* LINE has tight inter-message spacing */
  padding: 0.4rem 0.1rem 0.6rem;
}

/* Date separator at top of conversation (LINE-style centered pill) */
.line-date-separator {
  display: flex;
  justify-content: center;
  margin: 0.3rem 0 0.5rem 0;
}
.line-date-separator span {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #8b95a8;
  font-size: 0.65rem;
  letter-spacing: 0.08em;
  padding: 3px 12px;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
}

/* A row: bot side = avatar + bubble + time | user side = time + bubble.
   align-items: flex-end so the timestamp lines up with the bottom of the
   bubble (LINE convention). */
.line-row {
  display: flex;
  align-items: flex-end;
  gap: 0.45rem;
  max-width: 100%;
}
.line-row-bot { justify-content: flex-start; }
.line-row-me  { justify-content: flex-end; }

.line-avatar {
  flex: 0 0 32px;
  width: 32px; height: 32px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 17px;
  line-height: 1;
  align-self: flex-end;
}
.line-avatar-bot {
  background: linear-gradient(135deg, #ff6b35, #ff8c42);
  box-shadow: 0 0 8px rgba(255, 107, 53, 0.55);
}
/* .line-avatar-me kept defined but unused — LINE doesn't show your own
   avatar in your own chat. Leaving the class to avoid breakage if anyone
   re-introduces it. */
.line-avatar-me {
  background: linear-gradient(135deg, #00d9ff, #0fa8d0);
  box-shadow: 0 0 8px rgba(0, 217, 255, 0.55);
}

/* Bubble = the message body. Max-width is set here directly because
   .line-bubble is now a flex child of .line-row (no longer wrapped in a
   group). The cap at 70% leaves room for the timestamp + avatar on the
   400px-wide panel. */
.line-bubble {
  padding: 0.5rem 0.7rem;
  border-radius: 14px;
  font-size: 0.84rem;
  line-height: 1.5;
  color: #e6ebf2;
  word-wrap: break-word;
  white-space: pre-wrap;
  position: relative;
  max-width: 70%;
}
.line-bubble-bot {
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-bottom-left-radius: 4px;
}
.line-bubble-me {
  background: linear-gradient(135deg, #06c755, #04a449);
  border: 1px solid rgba(6, 199, 85, 0.55);
  border-bottom-right-radius: 4px;
  color: #ffffff;
}

/* Timestamp beside each bubble (LINE convention: time is to the right of
   bot bubbles and to the left of user bubbles). align-items: flex-end on
   .line-row keeps it level with the bubble's bottom edge. */
.line-bubble-time {
  font-size: 0.6rem;
  color: #6a7080;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.02em;
  white-space: nowrap;
  flex-shrink: 0;
  margin-bottom: 3px;
  user-select: none;
}

/* Typing-indicator bubble: same styling as a bot bubble, but the content
   is three dots that bounce in sequence to mimic "the assistant is thinking" */
.line-bubble-typing {
  padding: 0.65rem 0.95rem !important;
  min-height: 1.25rem;
}
.line-typing-dots {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.line-typing-dots span {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #8b95a8;
  opacity: 0.4;
  animation: typingDot 1.4s ease-in-out infinite;
}
.line-typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.line-typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes typingDot {
  0%, 100% { opacity: 0.35; transform: translateY(0); }
  30%      { opacity: 1;   transform: translateY(-3px); }
}

/* Floating AI assistant FAB — Streamlit-native button, fixed bottom-right */
.st-key-fab_container {
  position: fixed !important;
  bottom: 24px !important;
  right: 24px !important;
  z-index: 99999 !important;
  width: auto !important;
  max-width: 200px;
  margin: 0 !important;
  padding: 0 !important;
}
.st-key-fab_container .stButton,
.st-key-fab_container [data-testid="stButton"] {
  width: auto !important;
}
.st-key-fab_container .stButton > button,
.st-key-fab_container [data-testid="stBaseButton-secondary"] {
  background: linear-gradient(135deg, #00d9ff 0%, #6ad7ff 45%, #ff8c42 100%) !important;
  color: #04060f !important;
  border: 2px solid rgba(255, 255, 255, 0.18) !important;
  border-radius: 999px !important;
  padding: 13px 24px !important;
  font-weight: 900 !important;
  font-size: 0.95rem !important;
  letter-spacing: 0.02em !important;
  box-shadow:
    0 0 30px rgba(0, 217, 255, 0.55),
    0 0 50px rgba(255, 140, 66, 0.45),
    0 6px 18px rgba(0, 0, 0, 0.45) !important;
  animation: fabFloat 3.2s ease-in-out infinite;
  transition: transform 0.2s, box-shadow 0.2s !important;
  cursor: pointer !important;
  width: auto !important;
  min-width: 0 !important;
}
.st-key-fab_container .stButton > button:hover,
.st-key-fab_container [data-testid="stBaseButton-secondary"]:hover {
  transform: translateY(-3px) scale(1.04) !important;
  box-shadow:
    0 0 40px rgba(0, 217, 255, 0.85),
    0 0 70px rgba(255, 140, 66, 0.65),
    0 10px 26px rgba(0, 0, 0, 0.55) !important;
  color: #04060f !important;
  border-color: rgba(255, 255, 255, 0.3) !important;
}
@keyframes fabFloat {
  0%,100% { transform: translateY(0); }
  50%     { transform: translateY(-5px); }
}
@media (max-width: 768px) {
  .st-key-fab_container .stButton > button { padding: 10px 18px !important; font-size: 0.85rem !important; }
}
</style>
"""
