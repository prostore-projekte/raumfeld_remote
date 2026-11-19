# -*- coding: utf-8 -*-
"""
start.pyw - Doppelklick-Starter ohne Konsolenfenster (Windows: oeffnet mit pythonw).

Da pythonw keine Konsole hat, wuerden Fehler beim Start unsichtbar verschwinden.
Deshalb wird jeder Absturz in eine Protokolldatei geschrieben und - wenn
moeglich - als Meldungsfenster angezeigt:
    %APPDATA%/RaumfeldRemote/fehler.log
"""

import os
import traceback
from pathlib import Path


def _fehler_melden(text: str) -> Path:
    """Schreibt den Fehlertext ins Protokoll und zeigt ihn an. Rueckgabe: Protokollpfad."""
    basis = os.environ.get("APPDATA") or str(Path.home())
    datei = Path(basis) / "RaumfeldRemote" / "fehler.log"
    try:
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_text(text, encoding="utf-8")
    except OSError:
        pass  # Protokoll nicht schreibbar -> nur Meldungsfenster
    if os.environ.get("CI"):
        return datei  # automatischer Test (GitHub Actions): kein blockierendes Fenster
    try:
        import tkinter.messagebox
        tkinter.messagebox.showerror("Raumfeld Remote – Startfehler",
                                     f"{text[-1500:]}\n\nProtokoll: {datei}")
    except Exception:
        pass  # auch tkinter nicht nutzbar -> nur Protokoll
    return datei


if __name__ == "__main__":
    try:
        from raumfeld_remote.gui import starten
        starten()
    except Exception:
        _fehler_melden(traceback.format_exc())
        raise
