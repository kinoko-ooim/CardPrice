# Pokopia Guide Pokédex

## 1. Visual Theme & Atmosphere

Pokopia Guide's Pokédex page uses a friendly game-wiki visual language: soft, rounded, collectible, and information-dense without feeling technical. The page should feel like a polished companion guide for a cozy monster-collection game rather than a generic database dashboard.

The overall mood is:

- playful and approachable
- softly tactile, with pill shapes and rounded panels
- bright and cheerful, but not neon-heavy
- optimized for browsing lots of small filter controls and compact cards

The aesthetic should balance three ideas:

- guidebook clarity
- toy-like rounded UI
- lightweight fantasy-game charm

Avoid sterile enterprise UI, sharp-cornered minimalism, or heavy dark-mode-first styling.

## 2. Color Palette & Roles

Use a light, botanical base palette with candy-accent highlights.

| Role | Color | Usage |
| --- | --- | --- |
| Background Base | `#edf0e8` | Main page background, large surfaces |
| Surface White | `#ffffff` | Cards, panels, filter groups, elevated content |
| Primary Text | `#00282a` | Headings, important labels, high-contrast icons |
| Secondary Text | `rgba(0, 40, 42, 0.72)` | Supporting copy, metadata, helper text |
| Border / Ring | `#0000001a` | Subtle outlines, separators, pills |
| Mint Accent | `#00bb7f` | Active filters, success-style states, positive tags |
| Mint Soft | `#00bb7f33` | Active chip background, selected pills, soft fills |
| Leaf Green | `#4cb86a` | Secondary positive accent, icon tint, category support |
| Bright Green | `#5dc879` | Hover glow, playful emphasis, friendly highlights |
| Golden Accent | `#f99c00` | Count highlights, featured filters, warm emphasis |
| Golden Soft | `#f99c001a` | Badge background, tab hover, soft emphasis blocks |
| Blue Utility | `#3080ff33` | Informational accents, optional secondary selection |
| Pink Rare Accent | `#ec4899` | Specialty highlight, rare/favorite states, glow accents |

Color behavior:

- Default UI should stay light and neutral.
- Accent colors should appear in compact bursts, mostly on chips, tags, icons, and hover/focus states.
- Use mint as the primary interactive accent.
- Use gold for totals, counts, and featured highlights.
- Keep large surfaces pale and restful.

## 3. Typography Rules

The page uses rounded, friendly typography that matches a game guide.

### Font Families

- Display / Major headings: `Fredoka`, fallback to rounded sans
- Body / UI / labels: `Nunito`
- Dense metadata / code-like utility text: `Nunito Sans` or a clean monospace fallback only when needed

### Hierarchy

| Element | Font | Size | Weight | Notes |
| --- | --- | --- | --- | --- |
| H1 | `Fredoka` | `clamp(2.2rem, 4vw, 3.2rem)` | `700` | Rounded, cheerful, compact line-height |
| H2 | `Fredoka` | `1.5rem - 2rem` | `600-700` | Section dividers for browse groups |
| H3 | `Fredoka` or bold `Nunito` | `1.1rem - 1.25rem` | `700` | Card titles / Pokémon names |
| Body | `Nunito` | `0.95rem - 1rem` | `500-600` | Comfortable, warm, readable |
| Small Meta | `Nunito` | `0.75rem - 0.875rem` | `600` | Tags, counts, labels |
| Tiny Chip Text | `Nunito` | `10px - 12px` | `600-700` | Filter chips and compact status pills |

Typography rules:

- Prefer short, compact line lengths in metadata areas.
- Use bold rounded headings to keep the page game-like and collectible.
- Keep body copy simple and clean rather than editorial.
- Use uppercase sparingly; most labels should stay title case or sentence case.

## 4. Component Stylings

### Navigation

- Top navigation should be compact and scannable.
- Primary nav items appear as clean links or soft pills.
- Secondary taxonomy groups can be grouped by topic with subtle spacing and lightweight headings.
- Theme and language controls should look like utility pills, not heavy buttons.

### Filter Chips

- This page's signature component is the rounded browse chip.
- Chips should be `9999px` pill shapes with centered icon + label layout.
- Default state: white or near-white background, subtle outline, dark text.
- Hover state: slight lift or color wash using mint or gold soft fills.
- Active state: mint fill or mint-tinted background with stronger text contrast.
- Type/category chips may borrow semantic color hints, but keep the system visually consistent.

### Cards / List Items

- Pokémon entries should feel like compact encyclopedia cards.
- Use rounded rectangles with large radii, soft borders, and light shadow.
- Keep content dense but grouped into clear attribute clusters.
- Names and numbers should be visually separated from metadata tags.
- Card layout should support quick scanning before deep reading.

### Tags / Metadata Pills

- Small rounded tags should be heavily used for type, specialty, environment, and habitat signals.
- Tags should have low-contrast colored fills rather than saturated solid blocks.
- Mix semantic tinting with a common rounded shape so the UI stays unified.

### Buttons

- Buttons should feel lightweight and guide-like, not app-dashboard heavy.
- Primary actions: rounded, warm accent or mint accent, medium weight.
- Secondary actions: white or soft-tinted background with border.
- Avoid aggressive gradients except for occasional collectible or featured states.

### Search / Input Controls

- Inputs should use rounded borders, soft interior padding, and minimal chrome.
- Focus states should use a mint ring or warm gold ring, never harsh blue by default.
- Placeholder text should stay muted and friendly.

## 5. Layout Principles

This is a browsing-first reference page. Layout should prioritize discoverability over dramatic hero composition.

Principles:

- Use stacked content sections with comfortable vertical rhythm.
- Place filters early and keep them visually chunked by category.
- Treat each browse mode as a distinct module: type, specialty, favorite, environment.
- Favor multi-column card grids or dense vertical lists depending on viewport width.
- Make counts and category switches easy to spot at a glance.

Spacing scale:

- Tight: `4px`, `6px`, `8px`
- UI default: `12px`, `16px`
- Section spacing: `24px`, `32px`
- Major section separation: `40px - 56px`

Border radius scale:

- Small tags: `0.25rem - 0.75rem`
- Chips / pills: `2rem` or fully rounded
- Panels / cards: `1.25rem - 1.5rem`
- Featured blocks: `calc(base radius + 16px)` style oversized softness

## 6. Depth & Elevation

Depth is soft and glow-based rather than dramatic.

Shadow system:

- Base surfaces: minimal or no visible shadow
- Cards and floating pills: subtle `shadow-sm` style shadow
- Featured or selected states: diffuse color glow, especially gold or pink
- Rare highlight states can use soft aura effects like:
  - `0 0 20px 2px rgba(251, 191, 36, 0.3)`
  - `0 0 20px 2px rgba(236, 72, 153, 0.3)`

Elevation rules:

- Most components should rely on border + radius first, shadow second.
- Use glows sparingly for collectible emphasis.
- Never let shadows make the page feel enterprise, glassmorphic, or overly premium.

## 7. Do's and Don'ts

### Do

- Use rounded shapes generously.
- Keep the page light, airy, and approachable.
- Let category chips and metadata do most of the visual work.
- Use mint and gold as the main emotional accents.
- Keep dense information easy to scan through consistent tag structures.
- Use friendly display typography for section titles and names.

### Don't

- Don't switch to severe black-and-white minimalism.
- Don't use sharp corners on primary UI components.
- Don't make cards too large or editorial; this is a browsing database.
- Don't overuse gradients across entire backgrounds.
- Don't let accent colors dominate large surfaces.
- Don't use heavy enterprise table styling.
- Don't make dark mode the default visual reference for this design.

## 8. Responsive Behavior

The design should adapt from dense desktop browsing to compact mobile filtering.

Desktop:

- Show filters in grouped rows or wrapped chip clusters.
- Use multi-column card layouts where appropriate.
- Keep taxonomy navigation visible and easy to skim.

Tablet:

- Collapse large filter areas into tighter wrapped groups.
- Reduce card density slightly for readability.
- Preserve chip-based interaction rather than switching to dropdown-only UI too early.

Mobile:

- Stack sections vertically with strong grouping.
- Convert wide metadata rows into wrapped pill groups.
- Keep touch targets large and rounded.
- Let filter chips wrap naturally across lines.
- Avoid horizontal overflow in data-rich cards.

Touch targets:

- Minimum touch height: `40px`
- Preferred chip/button height: `44px+`

## 9. Agent Prompt Guide

### Quick style summary

- Cozy game guide
- Rounded taxonomy chips
- `Fredoka` headings + `Nunito` body
- Pale sage background
- White cards
- Mint and gold accents
- Soft glow highlights for featured states

### Prompt starter

Use a playful, rounded, cozy guidebook style inspired by a creature-collection database. Keep the page light with a pale sage background, white cards, soft outlines, and fully rounded filter pills. Use `Fredoka` for major headings and `Nunito` for body text. Lean on mint green and warm gold for active states, counts, and highlighted chips. Make the layout browsing-first, compact, and highly scannable rather than editorial or corporate.

### If adapting this style to another product

- Keep the friendly rounded system.
- Preserve the chip-heavy taxonomy model.
- Translate category colors into that product's domain.
- Keep information density high, but visually soft.
- Prefer collectible-database energy over SaaS dashboard energy.
