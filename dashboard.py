"""
dashboard.py — Terminal-Dashboard mit 3 Tabs

Tab 1: JETZT       — Nächste Bewässerung pro Zone, Wetterstatus
Tab 2: GESUNDHEIT  — Health-Score (0–100) + Status pro Node
Tab 3: IMPACT      — Wasser gespart, CO₂, Energie

Alle 10 Sekunden automatisch aktualisiert.
"""

import os
from datetime import datetime
from zone_manager import ZoneManager, ZoneState, NodeState
from database import Database

# ── ANSI Farben ────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
GREY   = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

_tab = 0   # aktiver Tab (rotiert automatisch)


def color_moisture(v: float) -> str:
    pct = f"{v:.0%}"
    if v < 0.3:   return f"{RED}{pct}{RESET}"
    if v < 0.6:   return f"{YELLOW}{pct}{RESET}"
    return f"{GREEN}{pct}{RESET}"


def color_health(score: int) -> str:
    if score is None: return f"{GREY}—{RESET}"
    if score >= 80:   return f"{GREEN}{score}/100{RESET}"
    if score >= 50:   return f"{YELLOW}{score}/100{RESET}"
    return f"{RED}{score}/100{RESET}"


def status_icon(s: str) -> str:
    return {
        "OK":       f"{GREEN}✅ OK       {RESET}",
        "DRY":      f"{RED}🔴 TROCKEN  {RESET}",
        "WATERING": f"{BLUE}💧 GIESST   {RESET}",
        "OFFLINE":  f"{GREY}⚫ OFFLINE  {RESET}",
    }.get(s, s)


def moisture_bar(v: float, w: int = 12) -> str:
    f = int(v * w)
    bar = "█" * f + "░" * (w - f)
    if v < 0.3:   return f"{RED}[{bar}]{RESET}"
    if v < 0.6:   return f"{YELLOW}[{bar}]{RESET}"
    return f"{GREEN}[{bar}]{RESET}"


class Dashboard:
    def __init__(self, zone_manager: ZoneManager, db: Database):
        self.zm = zone_manager
        self.db = db
        self._tick = 0

    def render(self):
        os.system("cls" if os.name == "nt" else "clear")
        self._tick += 1

        # Tab wechselt alle 3 Zyklen automatisch (alle 30s)
        tab = (self._tick // 3) % 3

        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        tabs = [
            f"{'[1: JETZT]' if tab==0 else ' 1: JETZT '}",
            f"{'[2: GESUNDHEIT]' if tab==1 else ' 2: GESUNDHEIT '}",
            f"{'[3: IMPACT]' if tab==2 else ' 3: IMPACT '}",
        ]
        print(f"{BOLD}{'═'*66}{RESET}")
        print(f"{BOLD}   🌱 HappyPlant 3.0 Enterprise{RESET}   {GREY}{now}{RESET}")
        print(f"   {CYAN}{tabs[0]}{RESET}  {tabs[1]}  {tabs[2]}")
        print(f"{BOLD}{'═'*66}{RESET}")

        if tab == 0:
            self._render_now()
        elif tab == 1:
            self._render_health()
        else:
            self._render_impact()

        print(f"\n{GREY}  Auto-Tab-Wechsel alle 30s  |  [Strg+C] Beenden{RESET}")

    # ── Tab 1: JETZT ─────────────────────────────────────────

    def _render_now(self):
        """Nächste Bewässerung, Wetter, aktueller Status."""
        print(f"\n  {BOLD}Nächste Bewässerung & aktueller Zonenstatus{RESET}\n")

        for zone in self.zm.zones.values():
            bar = moisture_bar(zone.avg_moisture)
            print(f"  {BOLD}{zone.name}{RESET}")
            print(f"  Ø Feuchte: {bar} {color_moisture(zone.avg_moisture)}"
                  f"   Status: {status_icon(zone.status)}")
            print(f"  Wetter:    {GREY}{zone.weather_summary}{RESET}")
            print(f"  Bewässerung: {CYAN}{zone.next_watering_reason}{RESET}")
            if zone.last_watered:
                print(f"  Zuletzt gegossen: {BLUE}{zone.last_watered.strftime('%d.%m. %H:%M')}{RESET}"
                      f"  ({zone.total_waterings}x heute)")
            print(f"  {'─'*60}")

    # ── Tab 2: GESUNDHEIT ─────────────────────────────────────

    def _render_health(self):
        """Health-Score 0–100 pro Node mit Mini-Balken."""
        print(f"\n  {BOLD}Pflanzengesundheit — Health-Score pro Node{RESET}\n")

        for zone in self.zm.zones.values():
            print(f"  {BOLD}{zone.name}{RESET}")
            print(f"  {'Node':<20} {'Score':>8}  {'Status':<12}  {'Feuchte':>8}  {'Pflanze'}")
            print(f"  {'─'*60}")

            for node in zone.nodes.values():
                h = node.health
                score_str  = color_health(h.score if h else None)
                status_str = f"{h.icon} {h.status.value}" if h else "—"
                print(
                    f"  {GREY}{node.node_id:<20}{RESET}"
                    f" {score_str:>8}  "
                    f"{status_str:<12}  "
                    f"{color_moisture(node.soil_moisture):>8}  "
                    f"{GREY}{node.plant_name[:22]}{RESET}"
                )
            print()

    # ── Tab 3: IMPACT ─────────────────────────────────────────

    def _render_impact(self):
        """Wasser gespart, CO₂ absorbiert, Energie eingespart."""
        print(f"\n  {BOLD}Wasser-Impact & Klimabeitrag{RESET}\n")

        impact = self.zm.impact.calculate_impact()

        lines = impact.summary_lines()
        for line in lines:
            print(f"  {line}")

        # Gesamt-Einsparung hervorheben
        total_saved = impact.total_saved_l()
        print(f"\n  {'─'*40}")
        print(f"  {GREEN}{BOLD}Gesamt eingespart: {total_saved:.1f} L Wasser{RESET}")
        print(f"  {GREEN}Das entspricht ~{total_saved/1.5:.0f} Wasserflaschen (1.5L){RESET}")

        if impact.co2_absorbed_kg > 0:
            trees_equiv = impact.co2_absorbed_kg / 0.022  # ~22g CO₂/Tag pro Baum
            print(f"  {GREEN}CO₂-Äquivalent: {trees_equiv:.1f} Baum-Tage Urban Greening{RESET}")
