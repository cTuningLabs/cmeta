"""
CMeta common repo functions

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

###################################################################################################
def _extract_category_artifact(s: str) -> str:
    import re

    # Remove leading/trailing whitespace and parentheses from the entire string
    s = s.strip().strip('()')
    
    # 1) Specific case: ignore preceding words if a 16-hex token directly precedes ':'
    # Example: "(in fursin website) Logos   f7458783a87400f1:79541da5b57f6591"
    #          -> f7458783a87400f1::79541da5b57f6591
    # 2) Already normalized with '::'
    # 3) Single ':' -> normalize to '::'
    patterns = [
        (r'.*?\b([0-9a-fA-F]{16})\s*:\s*(.+)',  # trailing 16-hex before colon
         lambda g1, g2: f"{g1}::{g2.strip()}"),
        (r"([\w.,\-@'\s\"]+)::([\w.,\-@'\s\"]+)",  # Added ' to character class, already has ::
         lambda g1, g2: f"{g1.strip()}::{g2.strip()}"),
        (r"([\w.,\-@'\s\"]+):([\w.,\-@'\s\"]+)",  # Added ' to character class, single :
         lambda g1, g2: f"{g1.split()[-1]}::{g2.split()[0]}"),
    ]

    for regex, builder in patterns:
        match = re.search(regex, s)
        if match:
            g1 = match.group(1).strip()
            g2 = match.group(2).strip()
            return builder(g1, g2).replace('"', '')

    return None
