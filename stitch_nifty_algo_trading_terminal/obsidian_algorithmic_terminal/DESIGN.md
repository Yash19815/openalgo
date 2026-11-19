---
name: Obsidian Algorithmic Terminal
colors:
  surface: '#0c141c'
  surface-dim: '#0c141c'
  surface-bright: '#323a43'
  surface-container-lowest: '#070f17'
  surface-container-low: '#141c24'
  surface-container: '#182029'
  surface-container-high: '#232b33'
  surface-container-highest: '#2e363e'
  on-surface: '#dbe3ef'
  on-surface-variant: '#bbcac1'
  inverse-surface: '#dbe3ef'
  inverse-on-surface: '#29313a'
  outline: '#85948c'
  outline-variant: '#3c4a43'
  surface-tint: '#3adfab'
  primary: '#42e5b0'
  on-primary: '#003828'
  primary-container: '#00c896'
  on-primary-container: '#004d38'
  inverse-primary: '#006c4f'
  secondary: '#ffb3b2'
  on-secondary: '#680013'
  secondary-container: '#8b1825'
  on-secondary-container: '#ff9999'
  tertiary: '#b2ccff'
  on-tertiary: '#003064'
  tertiary-container: '#83b1ff'
  on-tertiary-container: '#004286'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#60fcc6'
  primary-fixed-dim: '#3adfab'
  on-primary-fixed: '#002116'
  on-primary-fixed-variant: '#00513b'
  secondary-fixed: '#ffdad9'
  secondary-fixed-dim: '#ffb3b2'
  on-secondary-fixed: '#410008'
  on-secondary-fixed-variant: '#8b1825'
  tertiary-fixed: '#d6e3ff'
  tertiary-fixed-dim: '#a9c7ff'
  on-tertiary-fixed: '#001b3e'
  on-tertiary-fixed-variant: '#00468c'
  background: '#0c141c'
  on-background: '#dbe3ef'
  surface-variant: '#2e363e'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '500'
    lineHeight: 28px
    letterSpacing: -0.01em
  data-metric-lg:
    fontFamily: JetBrains Mono
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.02em
  data-metric-md:
    fontFamily: JetBrains Mono
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  data-tabular:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0em
  data-tabular-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.02em
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
    letterSpacing: -0.005em
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0em
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.08em
  label-ui:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.01em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1.25rem
  margin: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.25rem
  space-xl: 1.5rem
---

## Brand & Style

This design system establishes a high-performance, institutional trading environment focused on execution velocity, data clarity, and sustained visual comfort. It deliberately rejects the hyper-dense, visually noisy paradigms typical of legacy financial terminals. Instead, it pairs institutional rigor with an airy, modern minimalist dark architecture.

### Aesthetics & Principles
- **Minimalist Dark Architecture:** Deep matte slate substrates eliminate screen glare over extended multi-monitor trading sessions.
- **Cognitive Hygiene:** Clutter is stripped away. Generous padding, intentional whitespace, and strictly organized metrics prioritize instant spatial recognition of high-value signals.
- **Instrumental Typographic Hierarchy:** UI interface text is quiet and systematic, while numerical data, execution metrics, prices, and timestamps are rendered in high-legibility tabular monospace typography.
- **Immediate Chromatic Parsing:** Color is strictly semantic. Green and red are reserved exclusively for execution states, P&L dynamics, and buy/sell signals to ensure rapid, error-free interpretation under volatile market conditions.

## Colors

The palette is engineered for high-contrast accessibility against low-reflectance, deep-spectrum dark backgrounds. Background surfaces use cool matte slate values rather than harsh pure blacks (#000000) to preserve dimensional softness and prevent ocular fatigue.

### Palette Architecture
- **Base Canvas (`#0B1117`):** The primary canvas substrate. A low-sheen, absorbing matte slate.
- **Panel Surface (`#121A22`):** Primary structural panels, modular columns, and navigation docks.
- **Elevated Card (`#18222C`):** Higher-tier structural entities: metric cards, floating modal palettes, execution sidebars.
- **Subtle Surface Border (`#22303E`):** Crisp, low-luminosity outlines used sparingly to demarcate functional regions without introducing visual gridlock.
- **Emerald Mint (`#00C896`):** Primary signal color. Represents bullish movements, net-positive delta, buy orders, filled profit targets, and operational system health.
- **Soft Crimson (`#F06469`):** Danger and loss indicator. Dictates stop-loss triggers, short execution orders, negative delta, and critical system anomalies.
- **Soft Amber (`#F5A623`):** Warning indicator. Alerts to slippage tolerances, margin warnings, queued routing states, or unconfirmed API webhooks.
- **Link/Auxiliary Blue (`#4D96FF`):** Informational accent for navigation anchors, selected tabs, interactive strike selectors, and active tooltips.
- **Text Layers:** Primary text (`#F0F4F8`), Secondary/Labels (`#8F9CA9`), Muted/Disabled (`#4E5D6C`).

## Typography

The typography strategy separates structural interface elements from financial calculations.

### Functional Roles
- **System Interface (`Inter`):** Drives section headers, narrative notifications, navigational cues, and modal configuration fields. Inter delivers neutral, high-legibility optical clarity that does not compete with volatile algorithmic feeds.
- **Tabular Monospace (`JetBrains Mono`):** Dedicated exclusively to indices, strike ladders, spot prices, lot sizes, tick timestamps, order books, and P&L metrics. Its fixed character metrics eliminate column shifting during high-frequency data recalculation.
- **Rules & Scannability:** Numeric data should always render with tabular lining numerals (`tnum`). Never scale font sizes down below 10px under any circumstance; critical risk alerts and strikes must remain readable across multiple viewing distances.

## Layout & Spacing

The terminal uses a modular, fluid grid structured to adapt across wide trading screens, laptop setups, and tablet monitoring interfaces.

### Grid & Density Rhythm
- **Modular Fluid Foundation:** Employs a 12-column responsive layout with `gutter: 1.25rem` (20px) and `margin: 1.5rem` (24px).
- **Breathing Room:** Rejects standard ultra-cramped terminal layouts in favor of generous, deliberate spacing (`space-lg`, `space-xl`). Metric cards and operational tables utilize internal component padding of `1.25rem` to `1.5rem` (`p-5` to `p-6`) with inter-card gaps of `1.25rem` to `1.5rem` (`gap-5` to `gap-6`).
- **Responsive Adaptations:**
  - **Desktop / Multi-Monitor (≥1440px):** 3-to-4 column modular panels (Order Ladder, NIFTY Central Chart, Open Algorithmic Strategies, Global Positions Matrix).
  - **Compact Laptop (1024px – 1439px):** 2-column stacked configuration; secondary analytics dock below active strategy view.
  - **Tablet / Mobile Audit (<1023px):** Single-column stacked overview; order execution shifts to an anchor drawer to maximize chart and telemetry viewport area.

## Elevation & Depth

Visual hierarchy is maintained through subtle, planar tonal layering combined with hair-thin separation borders, rather than heavy dropshadows or blurred skeuomorphic effects.

### Layering Model
- **Ground Floor (`#0B1117`):** The main background viewport layer.
- **Dock / Panel Layer (`#121A22`):** Primary workspaces resting directly on the canvas, outlined by a 1px solid border (`#22303E`).
- **Floating / Metric Layer (`#18222C`):** High-priority modules, key performance metrics, order entry modules, and dropdown drawers. These surfaces use an ambient shadow for subtle depth separation: `0 4px 20px -2px rgba(0, 0, 0, 0.45)`.
- **Top / Modal Layer (`#18222C`):** Emergency kill-switches, confirmation overlays, and algorithm parameter adjustments. Elevated with `0 12px 36px 0 rgba(0, 0, 0, 0.65)` and backed by an `#0B1117` backdrop tint with 75% opacity.
- **No Heavy Shadows:** Keep borders razor-sharp (`1px solid #22303E`) to ensure structural crispness across low-nit dark displays.

## Shapes

The design system employs a soft geometric language (`roundedness: 1`), striking a balance between modern visual polish and the rigorous structure of a financial terminal.

### Corner Radius System
- **Micro Elements (`0.25rem` / `rounded`):** Default for algorithmic parameter inputs, strike selector tags, dropdown selectors, order book row hover highlights, and execution buttons.
- **Cards & Containers (`0.5rem` / `rounded-lg`):** Metric panels, charting surfaces, tabular data wraps, strategy cards, and execution dialogs.
- **Modal Viewports (`0.75rem` / `rounded-xl`):** System overlay dialogs and critical confirmation drawers.
- **Strict Prohibition:** Full-pill shapes (`rounded-full`) are prohibited for actionable operational elements, but may be used at microscopic scale (max height 6px) for live connection heartbeat indicators.

## Components

### Buttons & Order Triggers
- **Primary Signal (Buy / Long):** Emerald Mint `#00C896` fill, text `#0B1117` (JetBrains Mono, bold). On hover: brightness increases to 110%. On active: scaled down to `0.98`.
- **Secondary Signal (Sell / Short):** Soft Crimson `#F06469` fill, text `#FFFFFF` (JetBrains Mono, bold). On hover: brightness increases to 110%.
- **Tertiary / Neutral Actions:** Surface `#18222C` with border `1px solid #22303E`, text `#F0F4F8`. On hover: border transitions to `#4D96FF`, text shifts to `#4D96FF`.
- **Emergency Kill Switch:** Outlined Soft Crimson `#F06469` with `background: rgba(240, 100, 105, 0.08)`. High-urgency styling with an unmistakable destructive accent.

### Chips & Strategy Status Badges
- **Active Algo Running:** Background `rgba(0, 200, 150, 0.12)`, border `1px solid rgba(0, 200, 150, 0.3)`, text `#00C896`, paired with a pulsing 6px live heartbeat dot.
- **Halted / Error:** Background `rgba(240, 100, 105, 0.12)`, border `1px solid rgba(240, 100, 105, 0.3)`, text `#F06469`.
- **Standby / Neutral Strike Tag:** Background `#18222C`, border `1px solid #22303E`, text `#8F9CA9`.

### Metric & Telemetry Cards
- **Structure:** Elevated surface (`#18222C`) with `p-5` or `p-6`, framed by a single `#22303E` boundary.
- **Content Flow:** Header displays `label-caps` in `#8F9CA9`, right-aligned delta indicator chip, followed by prominent `data-metric-lg` figures. 
- **Subtext:** Real-time variance in monospace tabular layout; positive P&L displays `#00C896`, negative displays `#F06469`.

### Data Tables & Execution Ladders
- **Headers:** Surface `#121A22`, uppercase label font (`label-caps`), text `#8F9CA9`, bottom border `1px solid #22303E`.
- **Rows:** Alternating rows avoid striped fills. Instead, rows sit transparent over `#121A22` and illuminate to `#18222C` strictly on cursor hover. Height is fixed to 40px to ensure click accuracy during rapid interaction.
- **Alignment:** Alphanumeric tickers left-align; strikes, quantities, prices, and timestamps strictly right-align.

### Inputs & Strike Selectors
- **Fields:** Dark surface background (`#0B1117`), border `1px solid #22303E`, text `#F0F4F8` in `data-tabular`. Focus state engages a `1px solid #4D96FF` halo without blurry multi-pixel rings.
- **Stepper Buttons:** Embedded within input groups, maintaining clean square geometry with zero spacing gaps.

### Simplified High-Legibility Charts
- **Canvas:** Matte panel `#121A22` with minimal grid lines (`#18222C`, dotted or dashed 1px).
- **Price Action:** High-contrast mint `#00C896` and crimson `#F06469` candle bodies without dense gradients.
- **Axes:** Labels rendered in `data-tabular-sm` using `#8F9CA9`, positioned cleanly along right and bottom edges with unobstructed margin clearance.