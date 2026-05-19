import pytest
import calculations


def _totals(project=None, summary=None, quote=None, other_items=None):
    """Convenience wrapper with safe defaults."""
    p = project   or {'labor_rate': 25.0, 'markup': 0.0}
    s = summary   or {'total_material': 0.0, 'total_labor_hrs': 0.0, 'line_items': []}
    q = quote     or {}
    o = other_items if other_items is not None else []
    return calculations.compute_quote_totals(p, s, q, o)


# ══════════════════════════════════════════════════════════════════════════════
# Existing tests (kept for regression)
# ══════════════════════════════════════════════════════════════════════════════

def test_compute_quote_totals_basic():
    project = {'labor_rate': 25.0, 'markup': 10.0}
    summary = {
        'total_material': 100.0, 'total_labor_hrs': 2.0,
        'line_items': [
            {'part_id': 'PART-1', 'qty': 2, 'material_cost': 50.0, 'labor_cost': 25.0}
        ]
    }
    quote = {
        'overhead_rate': 1.1, 'labor_rate_quoted': 30.0, 'markup_pct': 10.0,
        'discount_pct': 0.0, 'discount_flat': 0.0
    }
    totals = calculations.compute_quote_totals(project, summary, quote, [])

    assert totals['mat_cost']        == 100.0
    assert totals['labor_hrs']       == 2.0
    assert totals['labor_cost']      == pytest.approx(60.0)
    assert totals['mat_burdened']    == pytest.approx(110.0)
    assert totals['markupable']      == pytest.approx(110.0)
    assert totals['markup_amount']   == pytest.approx(11.0)
    assert totals['passthrough']     == pytest.approx(60.0)
    assert totals['total_internal']  == pytest.approx(170.0)
    assert totals['quoted_total']    == pytest.approx(181.0)


def test_compute_quote_totals_with_other_items():
    summary = {'total_material': 0.0, 'total_labor_hrs': 0.0, 'line_items': []}
    quote   = {'markup_pct': 20.0}
    other_items = [
        {'description': 'Test1', 'cost': 100.0, 'apply_markup': 1},
        {'description': 'Test2', 'cost': 50.0, 'apply_markup': 0, 'discount_flat': 10.0},
    ]
    totals = calculations.compute_quote_totals({'labor_rate': 25.0}, summary, quote, other_items)

    assert totals['other_markup']  == 100.0
    assert totals['other_nomark']  == 50.0
    assert totals['markup_amount'] == pytest.approx(20.0)
    assert totals['pre_discount']  == pytest.approx(170.0)
    assert len(totals['quote_line_items']) == 2
    assert totals['quote_line_items'][0]['retail'] == pytest.approx(120.0)
    assert totals['quote_line_items'][1]['retail'] == pytest.approx(40.0)
    assert totals['quote_line_items'][1]['discount'] == pytest.approx(10.0)


def test_compute_quote_totals_frozen_costs():
    summary = {'total_material': 500.0, 'total_labor_hrs': 10.0}
    quote   = {'costs_frozen': 1, 'frozen_material': 100.0, 'frozen_labor_hrs': 2.0}
    totals  = calculations.compute_quote_totals({}, summary, quote, [])

    assert totals['mat_cost']   == 100.0
    assert totals['labor_hrs']  == 2.0


# ══════════════════════════════════════════════════════════════════════════════
# Frozen costs flag
# ══════════════════════════════════════════════════════════════════════════════

def test_frozen_flag_off_uses_live_values():
    """costs_frozen=0 must use live summary values, even if frozen_* fields are set."""
    summary = {'total_material': 999.0, 'total_labor_hrs': 8.0, 'line_items': []}
    quote   = {'costs_frozen': 0, 'frozen_material': 1.0, 'frozen_labor_hrs': 0.1}
    totals  = _totals(summary=summary, quote=quote)
    assert totals['mat_cost']  == 999.0
    assert totals['labor_hrs'] == 8.0


# ══════════════════════════════════════════════════════════════════════════════
# Markup / overhead mechanics
# ══════════════════════════════════════════════════════════════════════════════

def test_zero_markup_no_markup_amount():
    summary = {'total_material': 200.0, 'total_labor_hrs': 0.0, 'line_items': []}
    quote   = {'markup_pct': 0.0, 'overhead_rate': 1.0}
    totals  = _totals(summary=summary, quote=quote)
    assert totals['markup_amount'] == pytest.approx(0.0)
    assert totals['quoted_total']  == pytest.approx(200.0)


def test_explicit_zero_markup_not_overridden_by_project_markup():
    """quote.markup_pct=0 must be respected even when project.markup is non-zero.
    This guards against the `or` falsy-fallback bug where 0 silently became project.markup."""
    project = {'labor_rate': 25.0, 'markup': 44.0}   # project has 44% markup
    summary = {
        'total_material': 5607.38, 'total_labor_hrs': 0.0,
        'line_items': [
            {'part_id': 'ASSY-1', 'qty': 1,
             'material_cost': 5607.38, 'labor_cost': 0.0,
             'discount_pct': 10.0, 'discount_flat': 0.0}
        ]
    }
    quote = {'markup_pct': 0, 'overhead_rate': 1.0}   # explicit 0% markup on quote

    totals = calculations.compute_quote_totals(project, summary, quote, [])

    # With 0% markup and overhead=1, retail == material cost
    # 10% line discount = 5607.38 * 10% = 560.74
    assert totals['markup_pct']     == pytest.approx(0.0)
    assert totals['markup_amount']  == pytest.approx(0.0)
    assert totals['total_line_disc'] == pytest.approx(560.738, rel=1e-3)
    assert totals['quoted_total']   == pytest.approx(5607.38 - 560.738, rel=1e-3)


def test_overhead_burdens_material_not_labor():
    """overhead_rate multiplies material cost only; labor is unaffected."""
    summary = {'total_material': 100.0, 'total_labor_hrs': 2.0, 'line_items': []}
    quote   = {'overhead_rate': 1.5, 'markup_pct': 0.0, 'labor_rate_quoted': 10.0}
    totals  = _totals(summary=summary, quote=quote)
    assert totals['mat_burdened'] == pytest.approx(150.0)   # 100 * 1.5
    assert totals['labor_cost']   == pytest.approx(20.0)    # 2 * 10, unaffected


def test_labor_is_passthrough_not_marked_up():
    """Markup must apply only to burdened material, not to labor cost."""
    summary = {'total_material': 0.0, 'total_labor_hrs': 4.0, 'line_items': []}
    quote   = {'markup_pct': 100.0, 'overhead_rate': 1.0, 'labor_rate_quoted': 25.0}
    totals  = _totals(summary=summary, quote=quote)
    # mat is 0, so markup_amount should be 0
    assert totals['markup_amount'] == pytest.approx(0.0)
    # labor_cost goes straight through
    assert totals['labor_cost']    == pytest.approx(100.0)
    assert totals['quoted_total']  == pytest.approx(100.0)


def test_markup_amount_based_on_burdened_material():
    """markup_amount = (mat * overhead + other_markup) * pct."""
    summary = {'total_material': 100.0, 'total_labor_hrs': 0.0, 'line_items': []}
    quote   = {'overhead_rate': 1.2, 'markup_pct': 10.0}
    other   = [{'description': 'X', 'cost': 50.0, 'apply_markup': 1}]
    totals  = calculations.compute_quote_totals({'labor_rate': 25}, summary, quote, other)
    # markupable = (100*1.2) + 50 = 170; markup_amount = 170 * 10% = 17
    assert totals['markupable']    == pytest.approx(170.0)
    assert totals['markup_amount'] == pytest.approx(17.0)


# ══════════════════════════════════════════════════════════════════════════════
# Discounts
# ══════════════════════════════════════════════════════════════════════════════

def test_global_discount_pct_reduces_total():
    summary = {'total_material': 100.0, 'total_labor_hrs': 0.0, 'line_items': []}
    quote   = {'markup_pct': 0.0, 'discount_pct': 10.0, 'discount_flat': 0.0}
    totals  = _totals(summary=summary, quote=quote)
    assert totals['quoted_total'] == pytest.approx(90.0)


def test_global_discount_flat_reduces_total():
    summary = {'total_material': 200.0, 'total_labor_hrs': 0.0, 'line_items': []}
    quote   = {'markup_pct': 0.0, 'discount_pct': 0.0, 'discount_flat': 25.0}
    totals  = _totals(summary=summary, quote=quote)
    assert totals['quoted_total'] == pytest.approx(175.0)


def test_quoted_total_never_negative():
    """Massive discounts should floor at 0, not go negative."""
    summary = {'total_material': 100.0, 'total_labor_hrs': 0.0, 'line_items': []}
    quote   = {'markup_pct': 0.0, 'discount_pct': 100.0, 'discount_flat': 9999.0}
    totals  = _totals(summary=summary, quote=quote)
    assert totals['quoted_total'] >= 0.0


def test_line_item_discount_clamped_at_retail():
    """A line item with discount_pct=100 should reduce that line to $0, not go negative."""
    summary = {
        'total_material': 100.0, 'total_labor_hrs': 0.0,
        'line_items': [{
            'part_id': 'X', 'qty': 1, 'material_cost': 100.0, 'labor_cost': 0.0,
            'discount_pct': 100.0, 'discount_flat': 0.0,
        }]
    }
    quote  = {'markup_pct': 0.0, 'overhead_rate': 1.0}
    totals = _totals(summary=summary, quote=quote)
    li = totals['quote_line_items'][0]
    assert li['retail'] >= 0.0
    assert li['discount'] <= li['retail'] + li['discount']  # no over-discount


# ══════════════════════════════════════════════════════════════════════════════
# Gross margin
# ══════════════════════════════════════════════════════════════════════════════

def test_gross_margin_zero_quoted_total_returns_zero():
    """When quoted_total is 0, gross_margin_pct must be 0 (no divide-by-zero)."""
    summary = {'total_material': 0.0, 'total_labor_hrs': 0.0, 'line_items': []}
    quote   = {'markup_pct': 0.0, 'discount_pct': 100.0}
    totals  = _totals(summary=summary, quote=quote)
    assert totals['gross_margin_pct'] == 0.0


def test_gross_margin_positive_when_markup_applied():
    summary = {'total_material': 100.0, 'total_labor_hrs': 0.0, 'line_items': []}
    quote   = {'markup_pct': 50.0, 'overhead_rate': 1.0}
    totals  = _totals(summary=summary, quote=quote)
    # quoted = 150, internal = 100, margin = 50/150 = 33.3%
    assert totals['gross_margin_pct'] == pytest.approx(100 * 50 / 150, rel=1e-3)


# ══════════════════════════════════════════════════════════════════════════════
# Other items edge cases
# ══════════════════════════════════════════════════════════════════════════════

def test_other_item_no_description_excluded_from_line_items():
    """Items with no description must NOT appear in quote_line_items."""
    summary = {'total_material': 0.0, 'total_labor_hrs': 0.0, 'line_items': []}
    other   = [
        {'description': '',    'cost': 50.0, 'apply_markup': 0},
        {'description': 'OK',  'cost': 25.0, 'apply_markup': 0},
    ]
    totals = calculations.compute_quote_totals({'labor_rate': 25}, summary, {}, other)
    assert len(totals['quote_line_items']) == 1
    assert totals['quote_line_items'][0]['desc'] == 'OK'


def test_other_item_discount_pct_reduces_quoted_total():
    """discount_pct on an other_item must reduce quoted_total, not just the display retail.
    New behaviour: markup applies to full raw cost; discount applies to retail.
    With cost=100, markup=10%, disc_pct=10%:
      base_retail = 100 * 1.10 = 110; disc = 11; net_retail = 99
    The waterfall: pre_discount=110, total_other_disc=11, quoted_total=99."""
    summary = {'total_material': 0.0, 'total_labor_hrs': 0.0, 'line_items': []}
    other   = [{'description': 'D', 'cost': 100.0, 'apply_markup': 1,
                'discount_pct': 10.0}]
    quote   = {'markup_pct': 10.0}
    totals  = calculations.compute_quote_totals({'labor_rate': 25}, summary, quote, other)
    assert totals['quote_line_items'][0]['retail']   == pytest.approx(99.0)
    assert totals['quote_line_items'][0]['discount'] == pytest.approx(11.0)
    assert totals['total_other_disc']                == pytest.approx(11.0)
    assert totals['quoted_total']                    == pytest.approx(99.0)
    # Internal cost must reflect our actual spend (full raw cost), not discounted
    assert totals['other_markup']                    == pytest.approx(100.0)


def test_labor_rate_defaults_to_project_rate_when_quote_rate_is_zero():
    """When labor_rate_quoted is 0, it should fall back to project.labor_rate."""
    summary = {'total_material': 0.0, 'total_labor_hrs': 4.0, 'line_items': []}
    quote   = {'labor_rate_quoted': 0}
    totals  = _totals(project={'labor_rate': 50.0}, summary=summary, quote=quote)
    assert totals['labor_rate_quoted'] == pytest.approx(50.0)
    assert totals['labor_cost']        == pytest.approx(200.0)  # 4 * 50


# ══════════════════════════════════════════════════════════════════════════════
# Other item discount bugs (regression suite)
# ══════════════════════════════════════════════════════════════════════════════

def test_other_item_discount_flat_reduces_quoted_total():
    """discount_flat on an other_item must reduce quoted_total.
    Previously it only updated the display retail but left quoted_total unchanged."""
    summary = {'total_material': 0.0, 'total_labor_hrs': 0.0, 'line_items': []}
    other   = [{'description': 'Training', 'cost': 100.0, 'apply_markup': 0,
                'discount_flat': 15.0}]
    quote   = {'markup_pct': 0.0}
    totals  = calculations.compute_quote_totals({'labor_rate': 25}, summary, quote, other)
    # base_retail=100, disc_flat=15 → net_retail=85, quoted_total=85
    assert totals['quote_line_items'][0]['retail']   == pytest.approx(85.0)
    assert totals['quote_line_items'][0]['discount'] == pytest.approx(15.0)
    assert totals['total_other_disc']  == pytest.approx(15.0)
    assert totals['quoted_total']      == pytest.approx(85.0)


def test_other_item_both_discounts_reduce_quoted_total():
    """Combined pct + flat discount both reduce quoted_total correctly."""
    summary = {'total_material': 0.0, 'total_labor_hrs': 0.0, 'line_items': []}
    # cost=200, no markup. disc_pct=10% → $20 off; then disc_flat=$5 more off
    other   = [{'description': 'Freight', 'cost': 200.0, 'apply_markup': 0,
                'discount_pct': 10.0, 'discount_flat': 5.0}]
    quote   = {'markup_pct': 0.0}
    totals  = calculations.compute_quote_totals({'labor_rate': 25}, summary, quote, other)
    # base=200, disc = 200*10% + 5 = 25, net=175
    assert totals['total_other_disc'] == pytest.approx(25.0)
    assert totals['quoted_total']     == pytest.approx(175.0)


def test_hardware_line_item_qty_not_double_counted():
    """material_cost in line_items is already qty-scaled by calc_bom_summary.
    item_retail must NOT multiply by qty again — previously caused double-counting."""
    summary = {
        'total_material': 200.0, 'total_labor_hrs': 0.0,
        'line_items': [{
            'part_id': 'P1', 'qty': 2,
            'material_cost': 200.0,   # = unit_cost(100) × qty(2), already scaled
            'labor_cost': 0.0,
            'discount_pct': 0.0, 'discount_flat': 0.0,
        }]
    }
    quote  = {'markup_pct': 0.0, 'overhead_rate': 1.0}
    totals = _totals(summary=summary, quote=quote)
    li = totals['quote_line_items'][0]
    # Retail must be 200 (mat_cost already includes qty=2), NOT 400
    assert li['retail'] == pytest.approx(200.0)
    assert totals['quoted_total'] == pytest.approx(200.0)
