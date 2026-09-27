"""
pipeline/coicop_hierarchy.py
────────────────────────────
Dynamic COICOP Hierarchy Data Model & Multi-Tier Aggregator.

Implements the official UN COICOP 2018 / ILO 2020 CPI standard:
- Elementary Aggregate (EA) is dynamically defined as the lowest level
  with reliable expenditure weights:
    * CASE A: Class has detailed weighted subclasses -> Subclasses are EAs.
    * CASE B: Class has NO detailed weighted subclasses -> Class itself is the EA.
- Strictly prevents parent-child double counting.
- Provides 1:1 mapping: Product -> EA -> Class -> Group -> Division -> Headline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

log = logging.getLogger(__name__)

DEFAULT_CSV_PATH = (
    Path(__file__).resolve().parent.parent
    / "dbt"
    / "seeds"
    / "cambodia_cpi_coicop_weights_breakdown.csv"
)


@dataclass
class COICOPNode:
    node_code: str
    node_level: str  # "Division", "Group", "Class", "Subclass"
    name: str
    weight: float
    name_kh: str = ""
    parent_code: Optional[str] = None
    has_weighted_children: bool = False
    is_elementary_aggregate: bool = False
    children_codes: List[str] = field(default_factory=list)
    class_code: Optional[str] = None
    group_code: Optional[str] = None
    division_code: Optional[str] = None


class COICOPHierarchy:
    """
    In-memory representation of the complete COICOP expenditure hierarchy.
    Dynamically identifies Elementary Aggregates (EAs) and validates mathematical integrity.
    """

    def __init__(self, nodes: Dict[str, COICOPNode]):
        self.nodes = nodes
        self.divisions: Dict[str, COICOPNode] = {}
        self.groups: Dict[str, COICOPNode] = {}
        self.classes: Dict[str, COICOPNode] = {}
        self.subclasses: Dict[str, COICOPNode] = {}
        self.elementary_aggregates: Dict[str, COICOPNode] = {}

        self._organize_and_link()

    def _organize_and_link(self) -> None:
        """Categorizes nodes by level and establishes ancestor linkages."""
        for code, node in self.nodes.items():
            lvl = node.node_level
            if lvl == "Division":
                self.divisions[code] = node
            elif lvl == "Group":
                self.groups[code] = node
            elif lvl == "Class":
                self.classes[code] = node
            elif lvl == "Subclass":
                self.subclasses[code] = node

            if node.is_elementary_aggregate:
                self.elementary_aggregates[code] = node

        # Link Class, Group, Division ancestors for each node
        for code, node in self.nodes.items():
            curr = code
            while curr:
                curr_node = self.nodes.get(curr)
                if not curr_node:
                    break
                lvl = curr_node.node_level
                if lvl == "Class" and not node.class_code:
                    node.class_code = curr_node.node_code
                elif lvl == "Group" and not node.group_code:
                    node.group_code = curr_node.node_code
                elif lvl == "Division" and not node.division_code:
                    node.division_code = curr_node.node_code
                curr = curr_node.parent_code

    @classmethod
    def load_from_df(cls, df: pd.DataFrame) -> COICOPHierarchy:
        """Builds a COICOPHierarchy from a DataFrame containing breakdown weights."""
        nodes_raw: Dict[str, COICOPNode] = {}

        valid_levels = {"Division", "Group", "Class", "Subclass"}
        for _, row in df.iterrows():
            lvl = str(row.get("coicop_level", "")).strip()
            if lvl not in valid_levels:
                continue
            code = str(row.get("coicop_code", "")).strip()
            wt_val = row.get("weight_pct")
            try:
                wt = float(wt_val)
            except (ValueError, TypeError):
                continue

            name = str(row.get("coicop_name", "")).strip()
            name_kh = str(row.get("coicop_name_kh", "")).strip()

            nodes_raw[code] = COICOPNode(
                node_code=code,
                node_level=lvl,
                name=name,
                name_kh=name_kh,
                weight=wt,
            )

        # 1. Infer parent codes from dot notation
        for code, node in nodes_raw.items():
            if node.node_level == "Division":
                node.parent_code = None
            else:
                parts = code.split(".")
                node.parent_code = ".".join(parts[:-1])

        # 2. Populate direct children
        for code, node in nodes_raw.items():
            p = node.parent_code
            if p and p in nodes_raw:
                nodes_raw[p].children_codes.append(code)

        # 3. Determine has_weighted_children and is_elementary_aggregate
        for code, node in nodes_raw.items():
            has_wt_children = len(node.children_codes) > 0
            node.has_weighted_children = has_wt_children
            # Elementary aggregate: leaf node at Class or Subclass level with NO weighted children
            node.is_elementary_aggregate = (not has_wt_children) and (
                node.node_level in {"Class", "Subclass"}
            )

        hierarchy = cls(nodes_raw)
        hierarchy.validate_hierarchy()
        return hierarchy

    @classmethod
    def load_default(cls, csv_path: Optional[Path | str] = None) -> COICOPHierarchy:
        """Loads hierarchy from default dbt seed CSV file or path."""
        path = Path(csv_path) if csv_path else DEFAULT_CSV_PATH
        if not path.exists():
            raise FileNotFoundError(f"COICOP weights breakdown CSV not found at: {path}")
        df = pd.read_csv(path, dtype=str)
        return cls.load_from_df(df)

    def validate_hierarchy(self) -> None:
        """Runs the 8 mandatory quality control validation checks."""
        # 1. Child weights must not exceed parent weight
        for code, node in self.nodes.items():
            if node.has_weighted_children:
                for c_code in node.children_codes:
                    child = self.nodes[c_code]
                    if child.weight > node.weight + 1e-5:
                        raise ValueError(
                            f"Validation Fail: Child {c_code} weight ({child.weight}) exceeds parent {code} ({node.weight})"
                        )

        # 2. Child weights sum approximately to parent weight
        for code, node in self.nodes.items():
            if node.has_weighted_children:
                child_sum = sum(self.nodes[c].weight for c in node.children_codes)
                if abs(child_sum - node.weight) > 0.02:
                    raise ValueError(
                        f"Validation Fail: Parent {code} ({node.name}) weight={node.weight} != children sum={child_sum:.3f}"
                    )

        # 3. A parent with children must not also be marked as an EA
        for code, node in self.nodes.items():
            if node.has_weighted_children and node.is_elementary_aggregate:
                raise ValueError(
                    f"Validation Fail: Node {code} has children but is marked as EA!"
                )

        # Total EA weights must sum to exactly 100.000%
        total_ea_wt = sum(ea.weight for ea in self.elementary_aggregates.values())
        if abs(total_ea_wt - 100.0) > 0.01:
            raise ValueError(
                f"Validation Fail: Sum of Elementary Aggregate weights={total_ea_wt:.4f}% != 100.000%"
            )

        # 6, 7, 8. Check invariant paths: EA -> Class -> Group -> Division
        for code, ea in self.elementary_aggregates.items():
            if not ea.class_code or ea.class_code not in self.classes:
                raise ValueError(f"Validation Fail: EA {code} does not map to a valid Class")
            cls_node = self.classes[ea.class_code]
            if not cls_node.group_code or cls_node.group_code not in self.groups:
                raise ValueError(f"Validation Fail: Class {cls_node.node_code} does not map to a valid Group")
            grp_node = self.groups[cls_node.group_code]
            if not grp_node.division_code or grp_node.division_code not in self.divisions:
                raise ValueError(f"Validation Fail: Group {grp_node.node_code} does not map to a valid Division")

        log.debug("COICOPHierarchy passed all 8 validation checks successfully.")

    def get_elementary_aggregates_for_class(self, class_code: str) -> List[COICOPNode]:
        """
        Returns all Elementary Aggregates belonging to a Class:
        - Case A: Returns list of child leaf Subclasses.
        - Case B: Returns [class_node] itself.
        """
        cls_node = self.classes.get(class_code)
        if not cls_node:
            return []

        if not cls_node.has_weighted_children:
            # Case B: Class has no subclasses -> Class is the EA
            return [cls_node]

        # Case A: Find all descendant leaf EAs under this class
        eas: List[COICOPNode] = []

        def _collect_leaf_eas(n: COICOPNode):
            if n.is_elementary_aggregate:
                eas.append(n)
            else:
                for child_c in n.children_codes:
                    child = self.nodes.get(child_c)
                    if child:
                        _collect_leaf_eas(child)

        _collect_leaf_eas(cls_node)
        return eas

    def aggregate_multi_tier(
        self, ea_indices: Dict[str, float]
    ) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
        """
        Executes hierarchical aggregation according to UN COICOP / ILO 2020:
        EA indices -> Class indices -> Group indices -> Division indices.

        Case A: Class has detailed weighted subclasses:
            I_Class = sum(w_e * I_e) / sum(w_e) over active leaf EAs under that Class.
        Case B: Class has NO detailed weighted subclasses:
            I_Class = I_EA (Class itself is the EA).

        Group:
            I_Group = sum(w_c * I_c) / sum(w_c) over active Classes under that Group.
        Division:
            I_Division = sum(w_g * I_g) / sum(w_g) over active Groups under that Division.

        Returns:
            (class_indices, group_indices, division_indices)
        """
        import numpy as np

        class_indices: Dict[str, float] = {}
        group_indices: Dict[str, float] = {}
        division_indices: Dict[str, float] = {}

        # 1. EA -> Class
        for cls_code, cls_node in self.classes.items():
            if not cls_node.has_weighted_children:
                # Case B: Class is itself an Elementary Aggregate
                if cls_code in ea_indices and not pd.isna(ea_indices[cls_code]):
                    class_indices[cls_code] = float(ea_indices[cls_code])
                else:
                    class_indices[cls_code] = np.nan
            else:
                # Case A: Class has detailed weighted subclasses
                child_eas = self.get_elementary_aggregates_for_class(cls_code)
                active_eas = [
                    ea for ea in child_eas 
                    if ea.node_code in ea_indices and not pd.isna(ea_indices[ea.node_code])
                ]
                if active_eas:
                    sum_w = sum(ea.weight for ea in active_eas)
                    sum_w_idx = sum(ea.weight * ea_indices[ea.node_code] for ea in active_eas)
                    class_indices[cls_code] = float(sum_w_idx / sum_w) if sum_w > 0 else np.nan
                else:
                    class_indices[cls_code] = np.nan

        # 2. Class -> Group
        for grp_code, grp_node in self.groups.items():
            child_classes = [self.classes[c] for c in grp_node.children_codes if c in self.classes]
            active_classes = [
                c for c in child_classes
                if c.node_code in class_indices and not pd.isna(class_indices[c.node_code])
            ]
            if active_classes:
                sum_w = sum(c.weight for c in active_classes)
                sum_w_idx = sum(c.weight * class_indices[c.node_code] for c in active_classes)
                group_indices[grp_code] = float(sum_w_idx / sum_w) if sum_w > 0 else np.nan
            else:
                group_indices[grp_code] = np.nan

        # 3. Group -> Division
        for div_code, div_node in self.divisions.items():
            child_groups = [self.groups[g] for g in div_node.children_codes if g in self.groups]
            active_groups = [
                g for g in child_groups
                if g.node_code in group_indices and not pd.isna(group_indices[g.node_code])
            ]
            if active_groups:
                sum_w = sum(g.weight for g in active_groups)
                sum_w_idx = sum(g.weight * group_indices[g.node_code] for g in active_groups)
                division_indices[div_code] = float(sum_w_idx / sum_w) if sum_w > 0 else np.nan
            else:
                division_indices[div_code] = np.nan

        return class_indices, group_indices, division_indices

    def map_product_to_ea(
        self, raw_code: Optional[str], product_name: Optional[str] = None
    ) -> str:
        """
        Maps a product's raw classification code and name to EXACTLY ONE Elementary Aggregate (EA).
        Enforces strict uniqueness (Rules 4 & 5):
        1. Exact match with an EA.
        2. Downward roll-up (if code is more granular than an EA).
        3. Disambiguation of coarse parent codes (e.g. 01.1.1 or 01.1.1.1) to official leaf EAs.
        """
        if raw_code is None or pd.isna(raw_code):
            raw_code = "01"
        code = str(raw_code).strip()
        if not code or code.upper() == "UNCLASSIFIED":
            code = "01"

        # 1. Exact match with an Elementary Aggregate
        if code in self.elementary_aggregates:
            return code

        # 2. Downward roll-up (strip sub-digits if code is more granular than EA, e.g. 01.1.5.1 -> 01.1.5)
        parts = code.split(".")
        for i in range(len(parts) - 1, 0, -1):
            parent_code = ".".join(parts[:i])
            if parent_code in self.elementary_aggregates:
                return parent_code

        # 3. Disambiguation if product was coded to a parent node that has children
        # (e.g., product has '01.1.1' or '01.1.1.1' or '01.1.2')
        name_lower = (str(product_name) if product_name and pd.notna(product_name) else "").lower()

        # Division 01: Food parent classes
        if code.startswith("01.1.1.1"):  # Rice parent
            if any(k in name_lower for k in ["jasmine", "rumduol", "phka", "ផ្ការំដួល", "ម្លិះ"]):
                return "01.1.1.1.1"  # Jasmine / Quality 1
            if any(k in name_lower for k in ["sticky", "glutinous", "damnoeb", "ដំណើប"]):
                return "01.1.1.1.3"  # Sticky Rice
            return "01.1.1.1.2"  # Mixed White Rice (Quality 2 - standard default)

        if code.startswith("01.1.1"):  # Bread & Cereals parent
            if any(k in name_lower for k in ["rice", "អង្ករ"]):
                if any(k in name_lower for k in ["jasmine", "rumduol", "phka"]):
                    return "01.1.1.1.1"
                if any(k in name_lower for k in ["sticky", "glutinous"]):
                    return "01.1.1.1.3"
                return "01.1.1.1.2"
            if any(k in name_lower for k in ["bread", "baguette", "sandwich", "នំប៉័ង"]):
                return "01.1.1.2"
            if any(k in name_lower for k in ["noodle", "pasta", "spaghetti", "macaroni", "ramen", "មី", "គុយទាវ"]):
                return "01.1.1.3"
            if any(k in name_lower for k in ["biscuit", "cracker", "cookie", "wafer", "នំស្រួយ"]):
                return "01.1.1.4"
            if any(k in name_lower for k in ["cake", "pastry", "donut", "pie", "tart", "នំ"]):
                return "01.1.1.5"
            return "01.1.1.9"  # Other cereals and flour (residual default)

        if code.startswith("01.1.2"):  # Meat parent
            if any(k in name_lower for k in ["beef", "cow", "steak", "គោ"]):
                return "01.1.2.2"
            if any(k in name_lower for k in ["chicken", "poultry", "មាន់"]):
                return "01.1.2.3"
            if any(k in name_lower for k in ["duck", "ទា"]):
                return "01.1.2.4"
            if any(k in name_lower for k in ["sausage", "paté", "pate", "hotdog", "ham", "bacon", "ក្រក", "ប៉ាតេ"]):
                return "01.1.2.5"
            return "01.1.2.1"  # Fresh pork (standard default, highest weight 5.618%)

        if code.startswith("01.1.3"):  # Fish & Seafood parent
            if any(k in name_lower for k in ["shrimp", "prawn", "crab", "squid", "lobster", "clam", "oyster", "បង្គា", "ក្តាម", "មឹក"]):
                return "01.1.3.2"
            if any(k in name_lower for k in ["dried", "prahok", "canned", "ngiet", "ប្រហុក", "ត្រីងៀត", "ត្រីខ"]):
                return "01.1.3.3"
            return "01.1.3.1"  # Fresh fish (standard default, highest weight 7.435%)

        if code.startswith("01.1.4"):  # Dairy & Eggs parent
            if any(k in name_lower for k in ["egg", "eggs", "ពង", "ស៊ុត"]):
                if any(k in name_lower for k in ["salted", "century", "fermented", "ប្រៃ"]):
                    return "01.1.4.2"
                return "01.1.4.1"  # Fresh eggs
            return "01.1.4.3"  # Dairy products (milk, cheese, yogurt)

        if code.startswith("01.1.6"):  # Fruit parent
            if any(k in name_lower for k in ["nut", "seed", "almond", "cashew", "peanut", "walnut", "គ្រាប់"]):
                return "01.1.6.2"
            if any(k in name_lower for k in ["dried", "preserve", "raisin", "prune", "ដំណាប់"]):
                return "01.1.6.3"
            return "01.1.6.1"  # Fresh fruit

        if code.startswith("01.1.7"):  # Vegetables parent
            if any(k in name_lower for k in ["pickle", "fermented", "preserve", "ជ្រក់"]):
                return "01.1.7.6"
            if any(k in name_lower for k in ["potato", "cassava", "mushroom", "tuber", "ដំឡូង", "ផ្សិត"]):
                return "01.1.7.4"
            if any(k in name_lower for k in ["bean", "soy", "pea", "lentil", "pulse", "សណ្ដែក"]):
                return "01.1.7.5"
            if any(k in name_lower for k in ["carrot", "onion", "garlic", "root", "ការ៉ុត", "ខ្ទឹម"]):
                return "01.1.7.3"
            if any(k in name_lower for k in ["tomato", "cucumber", "eggplant", "chili", "pepper", "pumpkin", "ប៉េងប៉ោះ", "ត្រសក់", "ម្ទេស"]):
                return "01.1.7.2"
            return "01.1.7.1"  # Leaf and stalk vegetables

        # Division 03: Garments parent
        if code.startswith("03.1.2"):
            if any(k in name_lower for k in ["infant", "baby", "newborn", "toddler", "ទារក"]):
                return "03.1.2.3"
            if any(k in name_lower for k in ["men", "boy", "male", "gentleman", "បុរស", "កុមារា"]):
                return "03.1.2.2"
            if any(k in name_lower for k in ["women", "girl", "female", "lady", "dress", "skirt", "ស្ត្រី", "កុមារី"]):
                return "03.1.2.1"
            return "03.1.2.9"  # Other garments

        # Division 07: Fuel parent
        if code.startswith("07.2.2"):
            if any(k in name_lower for k in ["diesel", "gasoil", "ម៉ាស៊ូត"]):
                return "07.2.2.2"
            if any(k in name_lower for k in ["oil", "lubricant", "brake", "motor oil", "ប្រេងម៉ាស៊ីន", "ប្រេងរំអិល"]):
                return "07.2.2.3"
            return "07.2.2.1"  # Gasoline (standard default, highest weight 4.969%)

        # Fallback: Find first available EA in this division/group
        div = code[:2]
        div_eas = [ea for c, ea in self.elementary_aggregates.items() if c.startswith(div)]
        if div_eas:
            # Pick highest weighted EA in the division
            div_eas.sort(key=lambda n: n.weight, reverse=True)
            return div_eas[0].node_code

        # Global fallback: Rice Grade 2
        return "01.1.1.1.2"
