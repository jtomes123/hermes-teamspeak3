# PBI Workflow Instructions

## Directory Structure

```
pbis/
├── PBI_TEMPLATE.md          # Template for new PBIs
├── INSTRUCTIONS.md           # This file
├── planned/                  # PBIs not yet started
│   ├── PBI-001_example.md
│   └── ...
└── completed/                # PBIs that are done
    └── ...
```

## Creating a New PBI

1. Use the exact structure from `PBI_TEMPLATE.md`.
2. Determine the next PBI number: find the highest `PBI-XXX` in both `planned/` and `completed/`, then increment by 1.
3. Create the file as `pbis/planned/PBI-XXX_[lowercase-slug].md`.
4. Fill in all sections. Required fields: Title, Priority, Description, Acceptance Criteria.
5. Set `Created` to today's date. Leave `Completed` blank.

## Completing a PBI

1. Update acceptance criteria: mark completed items with `[x]`.
2. Add any final notes to Comments and Notes.
3. Set `Completed` to today's date.
4. Set `Status` to `Completed`.
5. Move the file from `pbis/planned/` to `pbis/completed/`.

## Rules

- Never delete a PBI — only move to `pbis/completed/`.
- Numbering is sequential across both folders (take max from both).
- Files must use the exact template format.
- Slugs are lowercase, hyphen-separated.
- Always ask the user before creating PBIs for fields they did not specify.
