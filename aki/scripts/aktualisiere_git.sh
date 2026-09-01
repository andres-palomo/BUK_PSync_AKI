#!/bin/bash

echo "🚀 Starte Git-Update..."

# 1. Änderungen hinzufügen
git add .

# 2. Commit mit einer Nachricht (wird beim Aufruf übergeben oder nutzt Standard)
COMMIT_MSG=${1:-"Auto-Update: Daten und Code aktualisiert"}
git commit -m "$COMMIT_MSG"

# 3. Zum GitLab Server pushen
git push origin main

echo "✅ Erfolgreich zu GitLab hochgeladen!"