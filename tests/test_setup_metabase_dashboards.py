"""
tests/test_setup_metabase_dashboards.py
───────────────────────────────────────
Unit tests for scripts/setup_metabase_dashboards.py ensuring:
- Dashboard parameter definitions (COICOP Division, Store Selector)
- Template tag generation on cards
- Parameter mappings on dashboard card placements
- New cards (4-Digit Class Breakdown, Top Weighted Inflation Contributors)
"""

import json
from unittest.mock import MagicMock, patch

from scripts.setup_metabase_dashboards import (
    create_or_update_card,
    create_or_update_dashboard,
    place_card_on_dashboard,
)


def test_create_or_update_card_with_template_tags():
    """Verify create_or_update_card persists template-tags in dataset_query."""
    mock_cur = MagicMock()
    mock_cur.fetchone.side_effect = [None, (101,)]  # None on SELECT, (101,) on RETURNING id

    template_tags = {
        "coicop_division": {
            "id": "tt_test",
            "name": "coicop_division",
            "display-name": "COICOP Division",
            "type": "text",
        }
    }

    card_id = create_or_update_card(
        mock_cur,
        name="Test Card",
        description="A test card",
        display="table",
        query_sql="SELECT * FROM test [[ WHERE coicop_division = {{coicop_division}} ]]",
        viz_settings={"table.pivot_column": None},
        collection_id=10,
        db_id=2,
        creator_id=1,
        template_tags=template_tags,
    )
    assert card_id == 101

    assert mock_cur.execute.called
    insert_call = mock_cur.execute.call_args[0]
    sql_stmt = insert_call[0]
    args = insert_call[1]

    assert "INSERT INTO report_card" in sql_stmt
    dataset_query_str = args[5]
    dataset_query = json.loads(dataset_query_str)
    assert dataset_query["database"] == 2
    assert dataset_query["native"]["template-tags"]["coicop_division"]["name"] == "coicop_division"


def test_create_or_update_dashboard_with_parameters():
    """Verify create_or_update_dashboard persists dashboard parameters."""
    mock_cur = MagicMock()
    mock_cur.fetchone.side_effect = [None, (202,)]  # None on SELECT, (202,) on RETURNING id

    parameters = [
        {
            "id": "param_div",
            "name": "COICOP Division",
            "slug": "coicop_division",
            "type": "category",
            "sectionId": "string",
        }
    ]

    dash_id = create_or_update_dashboard(
        mock_cur,
        name="Test Dashboard",
        description="Dashboard with filters",
        collection_id=5,
        parameters=parameters,
    )
    assert dash_id == 202

    assert mock_cur.execute.called
    insert_call = mock_cur.execute.call_args[0]
    sql_stmt = insert_call[0]
    args = insert_call[1]

    assert "INSERT INTO report_dashboard" in sql_stmt
    params_str = args[5]
    params = json.loads(params_str)
    assert len(params) == 1
    assert params[0]["slug"] == "coicop_division"


def test_place_card_on_dashboard_with_parameter_mappings():
    """Verify place_card_on_dashboard stores parameter_mappings."""
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = None  # New placement

    mappings = [
        {
            "parameter_id": "param_div",
            "card_id": 42,
            "target": ["variable", ["template-tag", "coicop_division"]],
        }
    ]

    place_card_on_dashboard(
        mock_cur,
        dashboard_id=1,
        card_id=42,
        col=0,
        row=11,
        size_x=12,
        size_y=8,
        viz_settings={},
        parameter_mappings=mappings,
    )

    assert mock_cur.execute.called
    insert_call = mock_cur.execute.call_args[0]
    sql_stmt = insert_call[0]
    args = insert_call[1]

    assert "INSERT INTO report_dashboardcard" in sql_stmt
    mappings_str = args[8]
    stored_mappings = json.loads(mappings_str)
    assert len(stored_mappings) == 1
    assert stored_mappings[0]["parameter_id"] == "param_div"
    assert stored_mappings[0]["target"] == ["variable", ["template-tag", "coicop_division"]]


@patch("scripts.setup_metabase_dashboards.get_db_connection")
def test_provision_all_creates_dashboards_and_cards(mock_get_conn):
    """Verify provision_all provisions all 3 dashboards with filters and the new cards."""
    from scripts.setup_metabase_dashboards import provision_all

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_get_conn.return_value = mock_conn

    last_query = [""]

    def mock_fetchone():
        q = last_query[0].upper()
        if "SELECT ID FROM METABASE_DATABASE" in q:
            return (2,)
        if "SELECT ID FROM" in q:
            return None  # Pretend no existing row so INSERT is triggered
        if "RETURNING ID" in q:
            return (1,)
        return (1,)

    mock_cur.fetchone.side_effect = mock_fetchone

    created_cards = []
    created_dashboards = []

    def mock_execute(sql, *args):
        last_query[0] = str(sql)
        sql_str = str(sql)
        if "INSERT INTO report_dashboard (" in sql_str and args:
            params = args[0]
            created_dashboards.append(params[2])  # Dashboard name
        elif "INSERT INTO report_card (" in sql_str and args:
            params = args[0]
            created_cards.append(params[2])  # Card name
        return None

    mock_cur.execute = mock_execute

    provision_all()

    # Verify 3 canonical dashboards provisioned
    assert len(created_dashboards) == 3
    assert any("Macro CPI" in d for d in created_dashboards)
    assert any("Operations" in d for d in created_dashboards)
    assert any("Silver Data Quality" in d for d in created_dashboards)

    # Verify new cards added to Dashboard 1
    assert "4-Digit COICOP Class Breakdown & MoM Rates" in created_cards
    assert "Top Weighted Inflation Contributors (CPI Impact)" in created_cards

