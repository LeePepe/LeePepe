# LeePepe — an engineering notebook

Approved direction · Production migration · 2026-10-20

## Principle

Make the person and the work easy to understand, then make activity explorable. The visual language is a quiet engineering notebook: warm neutral paper, precise rules, editorial type, restrained green, and honest labels.

## Diagnosis from actual rendered pixels

Baseline source: https://github.com/LeePepe, HTTP 200, captured by Chromium at 1440 and 390px on 2026-10-20. The accepted baseline and rendered review are retained in the delivery evidence outside the product repository.

| Visible fault | Concrete change |
|---|---|
| External typing graphic is blank in the captured README; the person's introduction is a small centered line | A real text H1 and one short, factual introduction; no external hero dependency |
| Eight differently colored stack badges compete before any selected work | One concise text stack line after the introduction |
| Two large calendar cards repeat structure and push projects down | One compact summary in README; a unified interactive activity notebook on the companion page |
| The project table contains about 40 rows, many with an em dash for the description | Three real selected apps, three short foundation links, and an ordinary all-repositories link |
| The bottom opaque stats widgets use dark panels even in the light profile and one is loading in the screenshot | First-party generated snapshot assets with light/dark colors and ordinary fallback text |
| Per-day detail is unavailable because the SVG is an embedded image | A clearly linked companion page with hover/focus tooltip and persistent click/touch details |

Public references: [GitHub Primer](https://primer.style/) for README compatibility and focus; [Vercel](https://vercel.com/design) for restrained rules and numeric hierarchy; [Stripe Press](https://press.stripe.com/) for editorial serif/sans contrast. These are references for the principles, not copies of their page layouts.

## Two surfaces, one hierarchy

- README uses only GitHub-supported Markdown/HTML, GitHub-rendered via the public Markdown API. No scripts, inline styles, custom layout CSS, iframe, or fake interactive SVG. The preview wrapper uses GitHub Markdown CSS and does not style individual README sections.
- README sequence: factual role → clear headline → concise stack → three selected apps → shared foundations → recent activity image + text fallback → expandable longer totals/counting rules → links.
- The companion HTML page repeats the same voice, project curation and colors, adding actual controls and daily inspection. No runtime framework or remote widget.
- Production activity comes from one complete public snapshot. The actual scan timestamp, generation and delayed-snapshot status prevent live-data claims. Public project copy is sourced from public metadata and READMEs; VitalStride capabilities remain explicitly exploratory/planned.

## Layout and spacing

- Companion content max-width 1200px; centered; desktop horizontal padding 40px, mobile 20px.
- Header height 88px desktop / 72px mobile. Hero padding 72px top and 72px bottom desktop / 40px each mobile.
- Section gaps 72px desktop / 48px mobile. Heading-to-content 24px.
- Spacing scale: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 72px.
- Work: three equal columns at >=900px, stacked below. Project card padding 24px; no large illustration or decorative hero panels.
- Activity: four independent KPI tiles, 16px gap; calendar and selected-day detail split at >=1100px, stacked below. Calendar scrolls internally on narrow screens with a visible hint; no page-level horizontal overflow.
- README max-width 900px within a GitHub-like neutral page wrapper, 32px article padding desktop / 20px mobile. Native GitHub section spacing remains intact.

## Typography

| Role | Web target |
|---|---|
| Hero | Georgia / system serif, 72px desktop / 44px mobile, weight 400, line-height 1.02, tracking -2px / -1px |
| Section title | Georgia, 36px desktop / 30px mobile, weight 400, line-height 1.15 |
| Card/project heading | System sans, 20px, weight 600 |
| KPI | System sans, 36px, weight 600, tabular numerals |
| Body | System sans, 15–17px, line-height 1.6 |
| Eyebrow/meta | System mono, 11–12px, line-height 1.5, letter spacing .6–1px |

Use real text for key profile copy. README uses GitHub's native system type and H1/H2 hierarchy rather than pretending arbitrary web CSS works there.

## Semantic colors and elevation

All web colors are CSS semantic tokens in `../site/styles.css`; palette values are centralized and have light/dark equivalents. Web adaptation uses concrete tokens because browser semantic colors do not supply all required surfaces.

- Light: paper `#f5f5f0`, surface `#ffffff`, inset `#eeefea`, text `#242822`, secondary `#62685e`, hairline `#dcded6`.
- Dark: paper `#171b18`, surface `#202620`, inset `#292f29`, text `#edf1e9`, secondary `#abb4a5`, hairline `#3d463b`.
- Accent / Human: light `#31694b`, dark `#a2cbae`. Agent: light `#795e78`, dark `#c8acc6`. Actor labels always carry words as well as color.
- Flat luminance tiers, 1px borders, 12px radius for metrics/project cards and 16px for the main calendar. No hero gradients, heavy shadows, glass effects, or decoration-only charts.
- Focus ring: 2px accent with 3px offset, never removed. Links stay distinguishable. Body secondary text is intended to meet WCAG AA at 12px or larger.

## Activity visualization and interaction

- A real 365-day calendar, Sunday-first weeks, UTC dates, blank alignment padding. Green intensity scale common to both actors; legend says counts, not GitHub “contributions.”
- Recent 7/30-day views show larger daily tiles with visible dates/counts. Range, actor, repository and metric jointly filter the calendar, selected-period KPI, recent summaries, actor mix, and persistent details.
- KPIs each include a small trend visualization or actor proportion bar. Four cards show selected period, last 7 days, last 30 days, and actor mix. Recent summaries are clamped to the selected range; labels explain this.
- Hover and focus show a visible date/count tooltip. Click/tap selects a persistent day. Arrow keys move through dates, Home/End move to first/last displayed day, Enter/Space selects. List items link to their actual public GitHub commit or PR.
- PRs use UTC creation dates. Merged/open/closed-unmerged are the current states of the creation-date cohort, explicitly labelled. Never describe them as merge events within the selected period.
- No data is a clear zero with an explanatory empty state; selected-day details update after filters and never show stale excluded entries.
- System/manual theme, reduced-motion support, form labels, keyboard focus, touch targets >=36px (compact calendar cells offer arrow-key navigation and the larger recent-day views for touch).

## Acceptance for independent design review

Actual screenshots of both surfaces at 1440/390px, light/dark. The accepted design review scored 32/35 with no P0 faults. Do not penalize the README for honoring native GitHub layout restrictions. Browser evidence covers actual interactions, zero page overflow, errors and theme behavior. Writer self-check is not independent design acceptance. Owner approved this direction before production migration.


## Production acceptance

The approved prototype uses representative data. Production reads only `site/data.json`, collected from eligible public repositories. Loading/failure/empty states, actual record links, snapshot age and generation identity are part of the final page. README images, text, daily table and site data are one generated bundle.
