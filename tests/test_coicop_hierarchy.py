"""
Tests for COICOP Hierarchy Data Model, Dynamic Elementary Aggregate (EA) Resolution,
and Multi-Level CPI Aggregation (Class -> Group -> Division -> Headline CPI).
"""
import pytest
import numpy as np
import pandas as pd
from pipeline.coicop_hierarchy import COICOPHierarchy, COICOPNode

@pytest.fixture
def hierarchy():
    return COICOPHierarchy.load_default()

def test_hierarchy_structure_and_counts(hierarchy):
    """Verifies that hierarchy contains all 4 tiers and correct number of nodes."""
    assert len(hierarchy.divisions) == 12
    assert len(hierarchy.groups) == 27
    assert len(hierarchy.classes) == 49
    # Exactly 76 Elementary Aggregates (leaves) summing to 100.000%
    assert len(hierarchy.elementary_aggregates) == 76
    total_ea_weight = sum(ea.weight for ea in hierarchy.elementary_aggregates.values())
    assert pytest.approx(total_ea_weight, 0.0001) == 100.0

def test_child_weights_do_not_exceed_parent(hierarchy):
    """Validation Check 1: Child weights must not exceed parent weight."""
    for code, node in hierarchy.nodes.items():
        if node.has_weighted_children:
            for child_code in node.children_codes:
                child = hierarchy.nodes[child_code]
                assert child.weight <= node.weight + 1e-6, (
                    f"Child {child_code} weight ({child.weight}) exceeds parent {code} ({node.weight})"
                )

def test_child_weights_sum_to_parent(hierarchy):
    """Validation Check 2: Where complete, child weights should approximately sum to parent weight."""
    for code, node in hierarchy.nodes.items():
        if node.has_weighted_children:
            child_sum = sum(hierarchy.nodes[c].weight for c in node.children_codes)
            assert pytest.approx(child_sum, 0.01) == node.weight, (
                f"Parent {code} weight ({node.weight}) != children sum ({child_sum})"
            )

def test_no_parent_is_elementary_aggregate(hierarchy):
    """Validation Check 3: A parent with children must not also be included as an independent EA."""
    for code, node in hierarchy.nodes.items():
        if node.has_weighted_children:
            assert not node.is_elementary_aggregate, (
                f"Node {code} has children but is marked as is_elementary_aggregate=True!"
            )
        else:
            if node.node_level in ["Class", "Subclass"]:
                assert node.is_elementary_aggregate, (
                    f"Leaf node {code} ({node.node_level}) is not marked as is_elementary_aggregate=True!"
                )

def test_ea_mapping_invariance(hierarchy):
    """Validation Checks 6, 7, 8:
    Every EA maps to exactly one Class,
    every Class maps to exactly one Group,
    every Group maps to exactly one Division.
    """
    for code, ea in hierarchy.elementary_aggregates.items():
        assert ea.class_code is not None, f"EA {code} has no class_code"
        assert ea.class_code in hierarchy.classes, f"Class {ea.class_code} not in classes"
        
        cls_node = hierarchy.classes[ea.class_code]
        assert cls_node.group_code is not None, f"Class {cls_node.node_code} has no group_code"
        assert cls_node.group_code in hierarchy.groups, f"Group {cls_node.group_code} not in groups"
        
        grp_node = hierarchy.groups[cls_node.group_code]
        assert grp_node.division_code is not None, f"Group {grp_node.node_code} has no division_code"
        assert grp_node.division_code in hierarchy.divisions, f"Division {grp_node.division_code} not in divisions"

def test_case_a_class_with_subclasses(hierarchy):
    """Tests Case A: Class 01.1.1 (Bread and cereals) has 8 leaf subclasses."""
    cls_code = "01.1.1"
    cls_node = hierarchy.classes[cls_code]
    assert cls_node.has_weighted_children is True
    assert cls_node.is_elementary_aggregate is False
    
    # Check that children sum exactly to Class weight
    child_eas = hierarchy.get_elementary_aggregates_for_class(cls_code)
    assert len(child_eas) == 8
    sub_sum = sum(ea.weight for ea in child_eas)
    assert pytest.approx(sub_sum, 0.001) == cls_node.weight
    assert pytest.approx(cls_node.weight, 0.001) == 8.274

def test_case_b_class_without_subclasses(hierarchy):
    """Tests Case B: Class 01.1.5 (Oils and fats) has NO subclasses.
    The Class itself is the Elementary Aggregate.
    """
    cls_code = "01.1.5"
    cls_node = hierarchy.classes[cls_code]
    assert cls_node.has_weighted_children is False
    assert cls_node.is_elementary_aggregate is True
    
    child_eas = hierarchy.get_elementary_aggregates_for_class(cls_code)
    assert len(child_eas) == 1
    assert child_eas[0].node_code == "01.1.5"
    assert pytest.approx(child_eas[0].weight, 0.001) == 0.920

def test_product_to_ea_mapping_uniqueness(hierarchy):
    """Validation Checks 4 & 5:
    Every active product must map to exactly one EA.
    No product may contribute to more than one EA.
    """
    sample_codes = [
        ("01.1.1.1.1", "Jasmine Rice 5kg", "01.1.1.1.1"), # Exact match
        ("01.1.1.1.2", "White Rice 5kg", "01.1.1.1.2"),   # Exact match
        ("01.1.1.1", "Fragrant Jasmine Rice", "01.1.1.1.1"), # Coarse code resolved via title
        ("01.1.1.1", "Ordinary Rice", "01.1.1.1.2"),         # Coarse code resolved via title
        ("01.1.1.2", "French Baguette", "01.1.1.2"),      # Exact match
        ("01.1.1", "Instant Noodles", "01.1.1.3"),        # Coarse class code resolved via title
        ("01.1.5", "Cooking Oil 1L", "01.1.5"),           # Case B class is EA
        ("01.1.5.1", "Palm Oil", "01.1.5"),              # Deeper code rolls up to Case B EA
        ("02.1.3", "Angkor Beer", "02.1.3"),              # Case B class is EA
        ("02.1.3.1", "Heineken Can", "02.1.3"),           # Deeper code rolls up to Case B EA
        ("07.2.2.1", "Gasoline EA95", "07.2.2.1"),        # Case A subclass EA
        ("07.2.2", "Diesel Fuel", "07.2.2.2"),            # Coarse class resolved via title
    ]
    
    for raw_code, name, expected_ea in sample_codes:
        resolved_ea = hierarchy.map_product_to_ea(raw_code, name)
        assert resolved_ea == expected_ea, f"Mapping failed for ({raw_code}, {name}): got {resolved_ea}, expected {expected_ea}"
        ea_node = hierarchy.elementary_aggregates[resolved_ea]
        assert ea_node.is_elementary_aggregate is True
