"""The roadmap: spec frontmatter intent, computed readiness, and the render.

This package is the factory's second workflow surface's data layer (US1): a
pure reader turns a `specs/` corpus into a graph of `SpecEntry`s — each with a
declared intent state and `depends_on_landed` edges — and readiness computation
distinguishes attested from observed satisfaction. The workflow and CLI live
in sibling modules; the grammar and the graph are here.
"""