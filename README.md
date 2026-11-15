# Мой Чиангмай: catalog

A searchable catalog of places, services, events and tips from the Telegram channel [«Мой Чиангмай»](https://t.me/my_chiangmai).

Site: https://skirpichenko.github.io/my-chiang-mai/ (GitHub Pages, served from `docs/`).

- `docs/` is the site. `docs/catalog.json` is generated, so never edit it by hand.
- `tools/` is the pipeline that turns the channel's Telegram export into the catalog.
- `work/` holds the export and the extraction results. It stays on the owner's computer and is never pushed, because the export includes contacts.

## Updating the catalog
1. In **Telegram Desktop**, open the channel → ⋮ → Export chat history.
   - Untick all media.
   - Format: Machine-readable JSON.
   - Period: all time.
2. Copy the exported `result.json` into `work/result.json` in this folder.
3. Open Claude Code in this folder and paste:

```
Update the channel catalog from the new Telegram export in work/result.json.
Follow CLAUDE.md, section "Updating the catalog after a new export", step by step.
If more than 3 part files need extraction, you may run tools/extract_workflow.js as a workflow.
Show me the build report (items before/after, names added and gone), then commit docs/catalog.json and push,
and check that the live site serves the new catalog.
```
