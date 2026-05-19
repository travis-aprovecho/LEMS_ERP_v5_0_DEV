from typing import Any

def compute_quote_totals(project: dict[str, Any], summary: dict[str, Any], quote: dict[str, Any], other_items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Single Source of Truth (SSOT) for Quote pricing calculations.
    Returns a dictionary of calculated fields needed for the Quote view and saving to DB.
    """
    # Use frozen costs if locked, otherwise live BOM values
    if quote.get('costs_frozen') and quote.get('frozen_material') is not None:
        mat_cost   = float(quote.get('frozen_material') or 0)
        labor_hrs  = float(quote.get('frozen_labor_hrs') or 0)
    else:
        mat_cost   = float(summary.get('total_material') or 0)
        labor_hrs  = float(summary.get('total_labor_hrs') or 0)

    # labor_rate_quoted lives in the quote — default to project rate on first visit
    labor_rate_quoted = float(quote.get('labor_rate_quoted') or 0)
    if labor_rate_quoted == 0:
        labor_rate_quoted = float(project.get('labor_rate') or 25)
    
    labor_cost    = labor_hrs * labor_rate_quoted
    overhead_rate = float(quote.get('overhead_rate') or 1.0)
    mat_burdened  = mat_cost * overhead_rate

    freight_in    = float(quote.get('freight_inbound')  or 0)
    freight_out   = float(quote.get('freight_outbound') or 0)
    gas_cost      = float(quote.get('cal_gases_cost')   or 0)
    gas_freight   = float(quote.get('cal_gases_freight') or 0)
    training_cost = float(quote.get('training_cost')    or 0)
    extras_total  = freight_in + freight_out + gas_cost + gas_freight + training_cost

    # Explicit None-check: quote.markup_pct=0 must be honored as "no markup".
    # Using `or` would treat 0 as falsy and silently fall back to project.markup.
    _q_markup  = quote.get('markup_pct')
    markup_pct = float(_q_markup if _q_markup is not None else (project.get('markup') or 0))

    # ── Other / custom line items ──────────────────────────────────────────────
    # Use raw cost as the markup base (our actual spend).
    # Customer discounts are applied to the retail price, not to our cost,
    # so internal cost and gross margin remain accurate.
    other_markup      = 0.0
    other_nomark      = 0.0
    total_other_disc  = 0.0
    quote_line_items  = []

    for oi in other_items:
        raw_cost  = float(oi.get('cost', 0))
        disc_pct  = float(oi.get('discount_pct')  or 0)
        disc_flat = float(oi.get('discount_flat') or 0)

        if oi.get('apply_markup'):
            other_markup += raw_cost                          # full cost → markup base
            base_retail   = raw_cost * (1 + markup_pct / 100)
        else:
            other_nomark += raw_cost                          # full cost → passthrough
            base_retail   = raw_cost

        # Discount applies to the customer-facing retail, not our cost
        disc_amount = min(base_retail, base_retail * (disc_pct / 100) + disc_flat)
        net_retail  = max(0.0, base_retail - disc_amount)
        total_other_disc += disc_amount

        if oi.get('description'):
            quote_line_items.append({
                'desc':     oi.get('description') or '—',
                'qty':      1,
                'retail':   net_retail,
                'discount': disc_amount,          # combined pct + flat for display
            })

    other_total = other_markup + other_nomark

    markupable    = mat_burdened + other_markup
    markup_amount = markupable * (markup_pct / 100)
    passthrough   = labor_cost + extras_total + other_nomark
    total_internal = mat_burdened + passthrough + other_markup   # full raw costs
    pre_discount   = markupable + markup_amount + passthrough    # full retail (pre-discount)

    discount_pct  = float(quote.get('discount_pct')  or 0)
    discount_flat = float(quote.get('discount_flat') or 0)
    global_discount_component = pre_discount * (discount_pct / 100) + discount_flat

    # ── Hardware line items ────────────────────────────────────────────────────
    # NOTE: item['material_cost'] and item['labor_cost'] are ALREADY qty-scaled
    # (calc_bom_summary multiplies by qty_mult). Do NOT multiply by qty again.
    total_line_disc = 0.0
    hardware_lines  = []
    for item in summary.get('line_items', []):
        if item.get('item_type') == 'DELETED': continue
        qty         = float(item.get('qty', 1))
        item_mat    = float(item.get('material_cost', 0)) * overhead_rate            # already qty-scaled
        item_lbr    = float(item.get('labor_hrs', 0)) * labor_rate_quoted           # recomputed from hrs × quoted rate — do NOT use item.labor_cost, which is pre-baked at project.labor_rate
        item_retail = item_mat * (1 + markup_pct / 100) + item_lbr                 # extended retail
        disc_pct_i  = float(item.get('discount_pct') or 0)
        disc_flat_i = float(item.get('discount_flat') or 0)
        item_disc   = min(item_retail, (item_retail * disc_pct_i / 100) + disc_flat_i)
        total_line_disc += item_disc
        hardware_lines.append({
            'desc':     item.get('plain_desc') or item.get('part_id'),
            'qty':      qty,
            'retail':   item_retail - item_disc,
            'discount': item_disc,
        })

    quote_line_items = hardware_lines + quote_line_items

    # ── Final waterfall ────────────────────────────────────────────────────────
    # Item-level discounts (hardware + custom) come off first;
    # the global % discount applies to whatever remains.
    total_item_disc  = total_line_disc + total_other_disc
    overall_discount = (total_item_disc
                        + max(0, pre_discount - total_item_disc) * (discount_pct / 100)
                        + discount_flat)
    quoted_total     = max(0.0, pre_discount - overall_discount)
    kit_subtotal     = markupable + markup_amount - total_item_disc
    gross_margin_pct = (quoted_total - total_internal) / quoted_total * 100 if quoted_total > 0 else 0


    return {
        "mat_cost": mat_cost,
        "labor_hrs": labor_hrs,
        "labor_cost": labor_cost,
        "labor_rate_quoted": labor_rate_quoted,
        "overhead_rate": overhead_rate,
        "mat_burdened": mat_burdened,
        "freight_inbound": freight_in,
        "freight_outbound": freight_out,
        "cal_gases_cost": gas_cost,
        "cal_gases_freight": gas_freight,
        "training_cost": training_cost,
        "markup_pct": markup_pct,
        "other_markup": other_markup,
        "other_nomark": other_nomark,
        "other_total": other_total,
        "markupable": markupable,
        "markup_amount": markup_amount,
        "passthrough": passthrough,
        "total_internal": total_internal,
        "pre_discount": pre_discount,
        "discount_pct": discount_pct,
        "discount_flat": discount_flat,
        "global_discount_component": global_discount_component,
        "total_line_disc": total_line_disc,
        "total_other_disc": total_other_disc,
        "total_item_disc": total_item_disc,
        "overall_discount": overall_discount,
        "quoted_total": quoted_total,

        "kit_subtotal": kit_subtotal,
        "gross_margin_pct": gross_margin_pct,
        "quote_line_items": quote_line_items,
    }
