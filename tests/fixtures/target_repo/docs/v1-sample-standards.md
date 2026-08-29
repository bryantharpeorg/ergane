# Standards

The document `manifests/v1-sample.yaml` declares as its `standards:` path.

Spec 121 moved the parser regression fixture onto that sample, and the identity
comparison asserts the declared `standards` field, so the declared path has to
resolve — a sample whose declared document is absent would be a manifest whose
validity the suite itself disproves. This file is that resolution: non-empty, at
the path the sample names, and belonging to the fixture repo rather than to the
operator's live tree.

Every other fixture manifest declares no standards document, so nothing that
reads the corpus follows the path except the tests written for this sample. The
sibling `notes.md` is a precedent: a fixture file exists because the condition
its manifest demonstrates needs somewhere to point.