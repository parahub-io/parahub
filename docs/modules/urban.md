# Urban Analysis (Pilot)

Draw a plot on the map and get its urban-planning picture: how the land is
qualified, what legal constraints sit over it, and what the municipal plan lets
you build there — with every statement traced back to its source.

> **Pilot feature.** Coverage is currently limited to one município (Caminha) and
> the result is a planning **copilot, not a legal opinion**. Every answer is
> labelled *não constitui parecer* — the binding decision and signature always
> belong to a licensed technician or the câmara municipal.

## What It Answers

From a plot polygon and an intended use, the analysis returns three layers:

1. **Territorial framing** — how the municipal plan (PDM) qualifies the land:
   urban or rural, the land-use category and sub-category, and the share of the
   plot each one covers when a plot straddles a boundary.
2. **Constraints** — the public-interest servitudes and restrictions that touch
   the plot: ecological reserve (REN), agricultural reserve (RAN), water domain,
   Natura 2000, heritage, infrastructure, and similar.
3. **Buildability** — the parameters the plan's regulation fixes for that
   category: utilization index, maximum buildable area, maximum sealed
   (impermeable) area, number of floors, and building height — computed for the
   actual plot.

On top of these it gives a **viability verdict** — *Yes / Conditional / No* — with
a confidence level and the reasons behind it, weighing the intended use against
the plan's table of permitted uses and the constraints that apply.

## Design Stance: The Data Answers, the AI Coordinates

Facts and numbers come only from the official planning data and a curated,
article-cited rules table — never from a language model's imagination. If a
natural-language layer is added later, it only turns the question and the answer
into plain words and explains them with citations; it never produces a number on
its own.

Two rules make this trustworthy:

- **Never invent.** Ask about a plot outside the covered area and the system says
  so plainly and lists which municípios *are* covered — it never guesses a
  qualification. Where the plan fixes no index for a category, the answer shows
  "not applicable" with the governing rule, not a fabricated figure.
- **Every statement traces to a source.** Each row carries its provenance — which
  plan layer and version for the map data, which article of which diploma for a
  rule — so an answer can always be checked against the original.

Because the data and rules are version-stamped, re-running the same query against
the same plan edition always gives the same answer, and every result is marked
*"in force as of"* its plan edition so a superseded answer labels itself.

## Levels

| Level | What it does | Status |
|-------|--------------|--------|
| L1 — Territorial framing | Land qualification + constraints over the plot | Built |
| L2 — Buildability | Indices, max buildable/sealed area, floors, height | Built (urban land) |
| L3 — Viability | Justified Yes/Conditional/No verdict for an intended use | Built (urban land) |
| L4 — Project assistant | Live check of a drawn building against setbacks/indices | Planned |
| L5 — Document generation | Descriptive memos and framing reports from the data | Planned |

Rural-land building rules and automatic parish attribution are not yet included —
where they are missing the answer stays at territorial framing rather than
guessing.

## Validation

The buildability numbers are hand-curated from the consolidated plan regulation
and transcribed with the article each one comes from — this is the human-auditable
artifact. Before any production reliance, a **licensed urbanista** signs off each
rule against its quoted source text through a dedicated validation dossier, and
each sign-off is recorded (who, when) and flagged stale if the rule later changes.
Until that validation is complete, output stays labelled *não constitui parecer*.

## Why the Data Is Public

Municipal plans in force are, by Portuguese and EU law, public and
machine-readable spatial data — deposited in vector form and served through
national planning-data services and municipal portals. The analysis reads that
public data; production use in a município is arranged formally with the câmara.

## How to Use It

On the map, open **Tools → Urban Analysis**, then either draw the plot vertex by
vertex or upload a plot outline as a GeoJSON file (WGS84 coordinates). Pick the
intended use and submit. The result appears in the map side panel: the viability
banner first, then the land qualification, buildability parameters with the
computed areas, the constraint badges, and the source and plan edition behind
them. Any signed-in profile can run an analysis for a covered município.

## Scope Beyond the Pilot

The engine is built município-agnostic. Scaling to more of Portugal follows a
"national spine plus municipal detail" path: national services already publish the
harmonized land-use geometry and the typed servitude layers for every plan in
force, while each município's own portal and regulation add the finer local
detail. The slow, careful part is never the software — it is curating and
validating each município's buildability rules from its regulation.
