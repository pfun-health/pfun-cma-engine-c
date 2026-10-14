# Documentation Formatting Conventions

This document specifies the formatting conventions used throughout the repository documentation, as demonstrated in `README.md`.

## General Principles

All documentation should follow these formatting standards for consistency and readability.

---

## Markdown Elements

### Headings

Use standard Markdown heading levels with consistent spacing:

```markdown
# Level 1 Heading

## Level 2 Heading

### Level 3 Heading
```

- Use `#` for main title (typically repository/document name)
- Use `##` for primary sections
- Use `###` for subsections
- Always leave blank lines before and after headings

### Emphasis

- Use underscores for italics: `_text_` renders as _text_
- Use double asterisks for bold: `**text**` renders as **text**
- Use backticks for inline code: `` `code` `` renders as `code`

### Lists

- Use hyphens (`-`) for unordered lists
- Use proper indentation for nested items
- Use em-dashes (`—`) to separate list item labels from descriptions

Example:
```markdown
- `directory_name/` — Brief description of the directory
- `another_name/` — Another description here
```

### Links

- Link to files using inline code with Markdown links: `[`` `file.md` ``](file.md)`
- External links should include the full URL: `[Link Text](https://example.com)`

### Horizontal Rules

Use triple hyphens (`---`) for major section breaks:

```markdown
---
```

Keep spacing consistent around horizontal rules.

### Code Blocks

Code blocks should specify the language:

````markdown
```sh
$ command here
```
````

Common language identifiers:
- `sh` or `bash` for shell commands
- `c` for C code
- `python` for Python code

### GitHub Alerts

Use GitHub's alert syntax for important notes, warnings, and tips:

```markdown
> [!NOTE]
> This is a note

> [!WARNING]
> This is a warning

> [!TIP]
> This is a helpful tip
```

These render as styled alert boxes in GitHub.

---

## Punctuation & Spacing

- Use em-dashes (`—`) not hyphens (`-`) or en-dashes (`–`) for separating clauses
- Use proper spacing around em-dashes: `text — more text`
- Ensure consistent spacing around inline code and links

---

## Structure Template

Follow this basic structure for documentation:

1. **Title** (Level 1 heading)
2. **Introductory paragraph** with brief context
3. **Optional alert** if there's important context (using `> [!NOTE]` syntax)
4. **Horizontal rule** to introduce main content
5. **Primary sections** (Level 2 headings)
6. **Subsections** (Level 3 headings) as needed
7. **Code examples** with proper language specification
8. **References or related links** if applicable

---

## Examples from README.md

### Repository List Example

```markdown
## Repository layout

- `src/` — core C model implementation
- `include/pfun_cma_engine/` — public C headers
- `pfun_cma_engine/` — Python bindings and packaged shared library, with language-surface facade dirs (`py/`, `ts/`, `c/`)
- `demos/` — interactive C demo plus Python scenario demos and the `scenariogen` scenario-buffer package (`demos/py/scenariogen/`)
- `docs/` — build notes and tracked demo outputs
- `tests/` — pytest and LLVM validation fixtures
- `tools/` — developer utilities
```

### Alert Example

```markdown
> [!NOTE]
> "CMA" is a fundamental initialism, short for "Cortisol-Melatonin-Adiponectin."
```

### Section Break Example

```markdown
## Build and run

See [`docs/BUILD.md`](docs/BUILD.md) for build instructions.

## Validation
```

### Code Block Example

```markdown
```sh
$ uv run pytest \
    tests/test_activity.py \
    tests/test_demo_scenarios.py
$ make test
```
```

---

## File-Specific Notes

### README.md

The README serves as the entry point. It should:
- Start with a clear title and brief description in italics
- Include an alert explaining any critical terminology
- Provide a quick repository layout overview
- Link to detailed documentation files for complex topics

### docs/BUILD.md

Build documentation should:
- Clearly separate different build methods (Makefile, CMake, Docker)
- Use code blocks with `sh` language identifier
- Provide copy-paste ready commands
- Link to related documentation when referencing other files

### docs/SCENARIO_DB.md

Technical documentation should:
- Use clear section hierarchies
- Include tables for data schemas and specifications
- Use proper LaTeX notation for mathematical expressions
- Explain design decisions and tradeoffs

### PROPOSED.md

Roadmap documents should:
- Use horizontal rules to separate major sections
- Clearly indicate status (COMPLETE, PARTIAL, PLANNED)
- Use tables for status tracking
- Include detailed explanations with proper emphasis

---

## Validation Checklist

When updating documentation:

- [ ] Headings follow the three-level hierarchy consistently
- [ ] Em-dashes (`—`) are used for separations, not hyphens or en-dashes
- [ ] Inline code uses backticks (`` `code` ``)
- [ ] File links use the pattern `[`` `path/file.md` ``](path/file.md)`
- [ ] Code blocks specify the language (e.g., `sh`, `c`, `python`)
- [ ] GitHub alerts use the proper syntax: `> [!TYPE]`
- [ ] Horizontal rules are used for major section breaks
- [ ] Lists use hyphens (`-`) for items
- [ ] No trailing whitespace on any lines
- [ ] Consistent blank lines around structural elements
