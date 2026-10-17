#!/bin/bash
TASKS="docs/superpowers/plans/2026-10-17-faze-3-tauri.md.tasks.json"
while [ ! -f STOP ] && grep -q '"status": "pending"' "$TASKS"; do
  claude -p "Podle CLAUDE.md a docs/STATE.md udělej první nedokončený task, celý postup včetně recenzí, přepiš docs/STATE.md a commitni. Pak skonči."
  read -p "Pokračovat dalším taskem? [Enter / Ctrl+C] "
done
