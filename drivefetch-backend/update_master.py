import os
import re

# ==========================================
# STEP 1: scapers/runner.py (URL sanitization)
# ==========================================
runner_file = "scrapers/runner.py"
with open(runner_file, "r", encoding="utf-8") as f:
    runner_content = f.read()

# Add GENERIC_POWERTRAIN_TAGS stripping
strip_logic = """
    # --- Strip generic powertrain tags from trim for URL building ---
    GENERIC_POWERTRAIN_TAGS = {
        "ev", "electric", "hev", "phev", "hybrid", 
        "petrol", "diesel", "cng", "awd", "fwd", "4x4", "4wd"
    }
    safe_trim = "" if (trim and trim.lower() in GENERIC_POWERTRAIN_TAGS) else (trim or "")
"""
if "GENERIC_POWERTRAIN_TAGS =" not in runner_content:
    runner_content = runner_content.replace('safe_trim   = trim or ""', strip_logic.strip())

with open(runner_file, "w", encoding="utf-8") as f:
    f.write(runner_content)


# ==========================================
# STEP 2: agents/recommender.py & orchestrator.py
# ==========================================
rec_file = "agents/recommender.py"
with open(rec_file, "r", encoding="utf-8") as f:
    rec_content = f.read()

# Native powertrain and spacing rules for recommender
native_rules = """
  Q4. TRIM flag & Native Powertrain Rule:
      - trim = "AWD"    → only when user wants AWD and the model has both FWD and AWD in Pakistan
      - trim = "EV"     → ONLY for models sold in Pakistan with *both* ICE and EV variants (e.g., MG ZS → trim="EV").
      - For natively EV-only models (BYD Atto 3, BYD Seal, BYD Dolphin, Changan Deepal S07/L07, GWM Ora 03, Seres 3), set trim="" (empty string).
      - trim = "Manual" → only when user explicitly requests manual on a dual-transmission model
      - trim = ""       → ALL other cases.

  Q4.5 Canonical Model Spacing:
      - Output properly spaced model names (e.g., "ZS EV" instead of "ZSEV", "Deepal S07" instead of "DeepalS07").
"""
if "Canonical Model Spacing:" not in rec_content:
    rec_content = re.sub(r'  Q4\. TRIM flag:.*?trim = ""       → ALL other cases.*?as standard\.', native_rules.strip(), rec_content, flags=re.DOTALL)

with open(rec_file, "w", encoding="utf-8") as f:
    f.write(rec_content)

orch_file = "agents/orchestrator.py"
with open(orch_file, "r", encoding="utf-8") as f:
    orch_content = f.read()

orch_rules = """
3. Native Powertrain Rule:
   - If a user requests an EV and the model has BOTH ICE and EV variants (like MG ZS), extract trim="EV".
   - If the model is natively EV-only (BYD Atto 3, BYD Seal, Changan Deepal S07/L07, GWM Ora 03, Seres 3), leave trim=None. DO NOT set trim="EV".
   
4. Canonical Model Spacing:
   - Output properly spaced model names (e.g., "ZS EV" instead of "ZSEV", "Deepal S07" instead of "DeepalS07").
"""
if "Canonical Model Spacing:" not in orch_content:
    orch_content = orch_content.replace('2. Do not hallucinate variants.', '2. Do not hallucinate variants.\n' + orch_rules.strip())

with open(orch_file, "w", encoding="utf-8") as f:
    f.write(orch_content)

# ==========================================
# STEP 3: scrapers/normalizer.py
# ==========================================
norm_file = "scrapers/normalizer.py"
with open(norm_file, "r", encoding="utf-8") as f:
    norm_content = f.read()

# Make sure MAKE_VETO_ALIASES is updated
veto_aliases = """MAKE_VETO_ALIASES: dict[str, list[str]] = {
    "daihatsu":  ["toyota", "daihatsu"],
    "toyota":    ["toyota", "daihatsu"],
    "mazda":     ["mazda", "suzuki"],                 # Scrum ↔ Every
    "subaru":    ["subaru", "daihatsu", "toyota"],      # Sambar/Justy ↔ Hijet/Thor
    "nissan":    ["nissan", "suzuki", "mitsubishi"],   # Clipper ↔ Every/Minicab
    "mitsubishi":["mitsubishi", "nissan", "suzuki"],
}"""
norm_content = re.sub(r'MAKE_VETO_ALIASES: dict\[str, list\[str\]\] = \{.*?\}', veto_aliases, norm_content, flags=re.DOTALL)

# Add missing aliases to MODEL_ALIAS_MAP
missing_aliases = """    "zsev":      ["zs ev", "zsev", "mg zs ev", "zs-ev", "zs electric"],
    "deepals07": ["deepal s07", "deepal s7", "s07", "s7", "deepal-s07"],
    "deepall07": ["deepal l07", "deepal l7", "l07", "l7", "deepal-l07"],
    "atto3":     ["atto 3", "atto3", "atto-3", "byd atto 3"],
    "ora03":     ["ora 03", "ora 3", "ora03", "ora good cat", "gwm ora 03"],
    "seres3":    ["seres 3", "seres3", "seres-3"],
    "atrai":     ["atrai", "atrai wagon", "hijet atrai"],
    "scrum":     ["scrum", "scrum wagon", "mazda scrum"],
    "clipper":   ["clipper", "nv100", "nv100 clipper"],
    "nbox":      ["n box", "nbox", "n-box"],
    "nvan":      ["n van", "nvan", "n-van"],
    "canbus":    ["canbus", "move canbus"],
    "spacia":    ["spacia", "speshia"],"""

# Inject if not present
if "zsev" not in norm_content:
    norm_content = norm_content.replace('MODEL_ALIAS_MAP: dict[str, list[str]] = {', 'MODEL_ALIAS_MAP: dict[str, list[str]] = {\n' + missing_aliases)

with open(norm_file, "w", encoding="utf-8") as f:
    f.write(norm_content)


# ==========================================
# STEP 4: scrapers/recommend_normalizer.py
# ==========================================
rec_norm_file = "scrapers/recommend_normalizer.py"
with open(rec_norm_file, "r", encoding="utf-8") as f:
    rec_norm_content = f.read()

# Fix title_clean scope
title_clean_fix = """    # ── 6. Smart trim — lazy seller fix ───────────────────────────────────
    trim_score = 0.0
    title_clean = title_lower.replace("-", "")"""

rec_norm_content = re.sub(
    r'    # ── 6\. Smart trim — lazy seller fix ───────────────────────────────────\n.*?trim_score = 0\.0',
    title_clean_fix,
    rec_norm_content,
    flags=re.DOTALL
)

# Remove the duplicated title_clean inside `if requested_trim:`
rec_norm_content = rec_norm_content.replace('        title_clean    = title_lower.replace("-", "")\n', '')

with open(rec_norm_file, "w", encoding="utf-8") as f:
    f.write(rec_norm_content)

print("All files updated successfully.")
