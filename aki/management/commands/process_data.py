import os
import sys
import pandas as pd
import re

""" merge_survey_data.py
Führt die Datensätze `oeffentlich.csv` und `verifiziert.csv` zusammen und:
- markiert die Herkunft in der Spalte `Umfrage`
- bereinigt die LimeSurvey-Variablennamen (z.B. `D3k1[SQ005]` -> `D3k1_5`)
- entfernt redundante Kommentar-Flag-Spalten
"""

def clean_and_transform(df):
    """
    Bereinigt Spaltennamen, z.B.:
    - 'D3k1[SQ005]'          -> 'D3k1_5'
    - 'C8[SQ001_SQ002]'      -> 'C8_1_2'         (Matrixfrage: Zeile+Spalte)
    - 'C5[SQ001comment]'     -> 'C5_1_comment'   (Freitext-Kommentar)
    - 'C5[SQ001]'            -> wird GELÖSCHT, wenn eine passende
                                 'C5[SQ001comment]'-Spalte existiert
                                 (reine Ja/Nein-Flag ohne Inhalt)
    """

    # --- 1. Redundante Kommentar-Flags identifizieren und löschen ---
    flag_pattern = re.compile(r"^(.*)\[SQ0*(\d+)\]$")
    comment_pattern = re.compile(r"^(.*)\[SQ0*(\d+)comment\]$")

    # Basen (Fragename + Nummer) sammeln, zu denen es eine echte Kommentar-Spalte gibt
    comment_bases = set()
    for col in df.columns:
        m = comment_pattern.match(col)
        if m:
            comment_bases.add((m.group(1), m.group(2)))

    # Passende Flag-Spalten (ohne "comment") finden und droppen
    cols_to_drop = []
    for col in df.columns:
        m = flag_pattern.match(col)
        if m and (m.group(1), m.group(2)) in comment_bases:
            cols_to_drop.append(col)

    if cols_to_drop:
        print(f"🗑️  Entferne {len(cols_to_drop)} redundante Kommentar-Flag-Spalte(n): {cols_to_drop}")
        df = df.drop(columns=cols_to_drop)

    # --- 2. Spaltennamen umbenennen ---
    def rename_col(col):
        # Matrixfragen mit zwei SQ-Codes: C8[SQ001_SQ002] -> C8_1_2
        col = re.sub(r"\[SQ0*(\d+)_SQ0*(\d+)\]", r"_\1_\2", col)
        # Kommentarfelder: C5[SQ001comment] -> C5_1_comment
        col = re.sub(r"\[SQ0*(\d+)comment\]", r"_\1_comment", col)
        # normale Einzel-SQ-Codes: D3k1[SQ005] -> D3k1_5
        col = re.sub(r"\[SQ0*(\d+)\]", r"_\1", col)
        return col

    df = df.rename(columns=rename_col)
    return df

def merge_survey_data():
    # 1. Pfade definieren
    base_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    raw_dir = os.path.join(base_dir, "data", "raw")
    processed_dir = os.path.join(base_dir, "data", "clean")

    # Pfade zu den beiden CSV-Dateien
    file_oeffentlich = os.path.join(raw_dir, "oeffentlich.csv")
    file_verifiziert = os.path.join(raw_dir, "verifiziert.csv")

    # Prüfen, ob die Quelldateien existieren
    if not os.path.exists(file_oeffentlich) or not os.path.exists(file_verifiziert):
        raise FileNotFoundError(
            f"❌ Fehler: Eine oder beide Dateien fehlen im Ordner '{raw_dir}'! "
            f"Bitte stelle sicher, dass 'oeffentlich.csv' und 'verifiziert.csv' dort liegen."
        )

    print("📖 Lese Tabellen ein...")
    df_oeffentlich = pd.read_csv(file_oeffentlich)
    df_verifiziert = pd.read_csv(file_verifiziert)

    # 2. Spaltenvergleich nur zur Info (keine Fehlermeldung mehr!)
    cols_oeffentlich = set(df_oeffentlich.columns)
    cols_verifiziert = set(df_verifiziert.columns)

    diff_oeffentlich = cols_oeffentlich - cols_verifiziert
    diff_verifiziert = cols_verifiziert - cols_oeffentlich

    if diff_oeffentlich or diff_verifiziert:
        print("ℹ️ Hinweis: Die Spalten der beiden Tabellen sind nicht exakt identisch.")
        if diff_oeffentlich:
            print(f"   Nur in 'oeffentlich' vorhanden: {diff_oeffentlich}")
        if diff_verifiziert:
            print(f"   Nur in 'verifiziert' vorhanden: {diff_verifiziert}")
        print("   ➜ Beide Spalten-Sets werden beibehalten, fehlende Werte werden mit NaN aufgefüllt.")
    else:
        print("✅ Spalten-Check: Alle Variablen sind exakt identisch.")

    # 3. Neue Variable 'Umfrage' hinzufügen
    df_oeffentlich["Umfrage"] = "oeffentlich"
    df_verifiziert["Umfrage"] = "verifiziert"

    # 4. Daten untereinanderfügen (Concat) - fehlende Spalten werden automatisch mit NaN aufgefüllt
    df_merged = pd.concat([df_oeffentlich, df_verifiziert], ignore_index=True)

    # 4b. 'Umfrage' an die erste Stelle verschieben
    cols = df_merged.columns.tolist()
    cols.insert(0, cols.pop(cols.index("Umfrage")))
    df_merged = df_merged[cols]

    # -------------------------------------------------------------------
    # Bereinigung & Transformation aufrufen
    # -------------------------------------------------------------------
    print("🧹 Bereinige und transformiere Daten...")
    df_clean = clean_and_transform(df_merged)

    # 5. Speichern im 'clean'-Ordner
    os.makedirs(processed_dir, exist_ok=True)
    output_path = os.path.join(processed_dir, "clean_data.csv")

    df_clean.to_csv(output_path, index=False, encoding="utf-8")

    print(
        f"🚀 Merge & Bereinigung erfolgreich! {len(df_clean)} Datensätze wurden gespeichert unter:"
    )
    print(f"👉 {output_path}")

    return df_clean


if __name__ == "__main__":
    try:
        merge_survey_data()
    except Exception as e:
        print(e)
        sys.exit(1)