# Third-party notices

Ergane itself is licensed under the Apache License, Version 2.0 — see `LICENSE`.

This repository also **redistributes** material written by other people. That
material is not Ergane's to relicense: it stays under its own terms, which is why
it is listed here rather than folded into the top-level license. Every item below
is MIT-licensed, and MIT's one obligation is that its copyright notice and
permission notice travel with the copy. This file is how they travel.

If you vendor further third-party material into this tree, add it here in the
same commit. A notice added later is a notice that was missing in between.

---

## Spec Kit — Copyright GitHub, Inc.

- **Upstream:** <https://github.com/github/spec-kit>
- **License:** MIT
- **Where it lives here:**
  - `.specify/` — templates, memory and shell scripts for spec-driven development

Ergane's spec workflow is built on Spec Kit's structure; `specs/<feature>/` and
the `.specify/` layout are its conventions, not Ergane's inventions.

Spec Kit's authoring *skills* are no longer vendored here. They are a tool an
operator installs, not material this repository redistributes, so they are named
as a prerequisite in `README.md` and left to the operator's own agent
configuration. The same went for the third-party skill collection this tree used
to carry under `.agents/skills/`: removed rather than relicensed, because a
development-time convenience is not something a repository should be shipping on
someone else's behalf.

---

## MIT License

Spec Kit is distributed under the following terms.

```
MIT License

Copyright (c) GitHub, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Runtime dependencies

Ergane's declared dependencies are installed from PyPI rather than vendored, so
their licenses are not reproduced here — they travel with the packages. For the
record, none of them is copyleft:

| Package | License |
| --- | --- |
| `temporalio` | MIT |
| `httpx` | BSD-3-Clause |
| `pyyaml` | MIT |
| `python-telegram-bot` | LGPL-3.0 (used unmodified, as a library) |

`python-telegram-bot` is the one worth naming explicitly: it is LGPL, which is
compatible with Apache-2.0 for a project that merely *uses* the library without
modifying it, as Ergane does. Modifying it in-tree would change that analysis.
