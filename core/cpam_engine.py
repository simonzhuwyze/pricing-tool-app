"""
CPAM Calculation Engine
Translated from Power BI DAX measures (extracted from Pricing Tool_metric.vpax)

Tables referenced:
  - Measures Rev: Net Revenue components
  - Measures Cost: COGS components
  - Measures Margin: Profit metrics
"""

from dataclasses import dataclass, field
from typing import Optional


# Channel-specific promotion discount factors (from DAX Promotion Total measure)
PROMO_CHANNEL_FACTORS = {
    "Home Depot US": 0.5,
    "Home Depot CA": 0.5,
    "Best Buy": 0.75,
    "Walmart 1P": 0.8,
    "Amazon 1P": 0.9,
}

# Shipping revenue per unit by channel (from DAX Shipping Revenue measure)
SHIPPING_REVENUE = {
    "DTC US": 0.77,
    "DTC CA": 0.77,
    "TikTok Shop": 0.47,
}


@dataclass
class ChannelAssumptions:
    """All assumptions needed for one SKU in one channel."""
    channel: str
    # From Input_SKU_PO Discount (SharePoint List)
    po_discount_rate: float = 0.0       # "Retail Margin" discount rate
    # From Channel Terms (SharePoint List)
    chargeback_rate: float = 0.0
    total_discount_rate: float = 0.0    # Retail Discounts & Allowances rate
    # From Input_SKU_Return Rate
    return_rate: float = 0.0
    # From Input_SKU_Outbound Shipping
    outbound_shipping: float = 0.0
    # From Input_SKU_CostAssumptions
    inbound_freight: float = 0.0
    warehouse_storage: float = 0.0
    amazon_fba: float = 0.0
    expected_product_life: float = 0.0
    # From Sales & Marketing Expenses
    customer_service_rate: float = 0.0
    cc_fee_rate: float = 0.0
    marketing_rate: float = 0.0
    # Channel mix (user input, 0-1)
    channel_mix: float = 0.0


@dataclass
class ProductInfo:
    """Product-level information."""
    sku: str
    product_name: str = ""
    product_group: str = ""      # "Cameras", "Smart Home", etc. (from SKU Mapping)
    product_category: str = ""   # "Wired", "Door Locks", etc. (from SKU Mapping)
    product_line: str = ""       # "Bulbs", etc. (from SKU Mapping)
    reference_sku: str = ""


@dataclass
class StaticAssumptions:
    """Global static assumptions (from Static Assumptions SharePoint List)."""
    uid_cam: float = 0.20
    royalties_cam: float = 0.20
    royalties_bulb_rate: float = 0.05   # 5% of Net Revenue
    monthly_cloud_cost_cam: float = 0.0
    monthly_cloud_cost_noncam: float = 0.0
    eos_rate: float = 0.0               # Excess, Obsolete & Shrinkage %


@dataclass
class UserInputs:
    """User-adjustable inputs (top-level controls)."""
    msrp: float = 0.0
    fob: float = 0.0
    tariff_rate: float = 0.0           # As percentage (e.g., 10.0 = 10%)
    promotion_mix: float = 0.0         # Percentage of units sold under promo (0-100)
    promo_percentage: float = 0.0      # Promo discount % (0-100), 0 means use absolute values
    promo_absolute_values: dict = field(default_factory=dict)  # channel -> absolute promo $ from library


@dataclass
class CPAMBreakdown:
    """Complete CPAM calculation result for one channel."""
    channel: str

    # Revenue
    msrp: float = 0.0
    shipping_revenue: float = 0.0
    retail_margin: float = 0.0          # Negative (discount off MSRP)
    po_price: float = 0.0
    retail_discounts: float = 0.0       # Negative
    pre_promo_retailer_price: float = 0.0
    promotion: float = 0.0             # Negative
    price_paid_by_enduser: float = 0.0
    post_promo_retailer_price: float = 0.0
    chargebacks: float = 0.0           # Negative
    returns_replacements: float = 0.0  # Negative
    other_contra_revenue: float = 0.0
    net_revenue: float = 0.0

    # Cost of Goods
    fob: float = 0.0
    inbound_freight: float = 0.0
    tariff: float = 0.0
    landed_cost: float = 0.0
    outbound_shipping: float = 0.0
    warehouse_storage: float = 0.0
    shipping_cost: float = 0.0
    cloud_cost_lifetime: float = 0.0
    eos: float = 0.0
    uid: float = 0.0
    royalties: float = 0.0
    other_cost: float = 0.0
    cost_of_goods: float = 0.0

    # Sales & Marketing
    customer_service: float = 0.0
    cc_platform_fees: float = 0.0
    marketing: float = 0.0
    sales_marketing_expenses: float = 0.0

    # Profit Metrics
    gross_profit: float = 0.0
    gross_margin_pct: float = 0.0
    cpam_dollar: float = 0.0
    cpam_pct: float = 0.0

    # Full Price / Blended
    net_revenue_fullprice: float = 0.0
    cpam_dollar_full: float = 0.0
    cpam_pct_full: float = 0.0
    net_revenue_blended: float = 0.0
    cpam_dollar_blended: float = 0.0
    cpam_pct_blended: float = 0.0

    # Channel mix
    channel_mix: float = 0.0


def calculate_channel_cpam(
    inputs: UserInputs,
    product: ProductInfo,
    channel_assumptions: ChannelAssumptions,
    static: StaticAssumptions,
) -> CPAMBreakdown:
    """
    Calculate complete CPAM breakdown for one SKU in one channel.
    Direct translation of DAX measures from the Power BI semantic model.
    """
    ch = channel_assumptions.channel
    result = CPAMBreakdown(channel=ch)

    # --- User Inputs ---
    msrp = inputs.msrp
    fob = inputs.fob
    tariff_rate_pct = inputs.tariff_rate  # e.g., 10.0 for 10%
    promotion_mix = inputs.promotion_mix / 100.0  # Convert to 0-1
    promo_pct = inputs.promo_percentage / 100.0

    result.msrp = msrp
    result.fob = fob
    result.channel_mix = channel_assumptions.channel_mix

    # === NET REVENUE COMPONENTS (Measures Rev) ===

    # Retail Margin = -PO_Discount_Rate * MSRP
    result.retail_margin = -channel_assumptions.po_discount_rate * msrp

    # PO Price = MSRP + Retail Margin
    result.po_price = msrp + result.retail_margin

    # Retail Discounts & Allowances = -Total_Discount * PO Price
    result.retail_discounts = -channel_assumptions.total_discount_rate * result.po_price

    # Pre-promo Retailer Price = PO Price + Retail Discounts & Allowances
    result.pre_promo_retailer_price = result.po_price + result.retail_discounts

    # Promotion Total (complex logic from DAX)
    if promo_pct == 0:
        # Use absolute values from promotion library
        promo_total = inputs.promo_absolute_values.get(ch, 0.0)
    else:
        factor = PROMO_CHANNEL_FACTORS.get(ch, 1.0)
        promo_total = msrp * promo_pct * factor

    result.promotion = -promo_total

    # Price Paid by End-User = MSRP + Promotion
    result.price_paid_by_enduser = msrp + result.promotion

    # Post-promo Retailer Price = PO Price + Promotion + Retail Discounts & Allowances
    result.post_promo_retailer_price = (
        result.po_price + result.promotion + result.retail_discounts
    )

    # Chargebacks = -PO Price * Chargeback Rate
    result.chargebacks = -result.po_price * channel_assumptions.chargeback_rate

    # Returns & Replacements = -Post-promo Retailer Price * Return Rate
    result.returns_replacements = (
        -result.post_promo_retailer_price * channel_assumptions.return_rate
    )

    # Other Contra Revenue
    result.other_contra_revenue = result.chargebacks + result.returns_replacements

    # Shipping Revenue
    result.shipping_revenue = SHIPPING_REVENUE.get(ch, 0.0)

    # Net Revenue = Post-promo Retailer Price + Other Contra Revenue + Shipping Revenue
    result.net_revenue = (
        result.post_promo_retailer_price
        + result.other_contra_revenue
        + result.shipping_revenue
    )

    # Net Revenue FullPrice (no promo scenario)
    result.net_revenue_fullprice = (
        result.po_price
        + result.retail_discounts
        - result.pre_promo_retailer_price * channel_assumptions.return_rate
        + result.chargebacks
        + result.shipping_revenue
    )

    # Net Revenue Blended
    result.net_revenue_blended = (
        result.net_revenue_fullprice * (1 - promotion_mix)
        + result.net_revenue * promotion_mix
    )

    # === COST OF GOODS (Measures Cost) ===

    # Tariff = Tariff_Rate * FOB / 100
    result.tariff = tariff_rate_pct * fob / 100.0

    # Inbound Freight & Insurance
    result.inbound_freight = channel_assumptions.inbound_freight

    # Landed Cost = FOB + Inbound Freight + Tariff
    result.landed_cost = fob + result.inbound_freight + result.tariff

    # Outbound Shipping
    result.outbound_shipping = channel_assumptions.outbound_shipping

    # Warehouse Storage & Handling: Amazon 3P uses FBA fee instead
    if ch == "Amazon 3P":
        result.warehouse_storage = channel_assumptions.amazon_fba
    else:
        result.warehouse_storage = channel_assumptions.warehouse_storage

    # Shipping Cost = Outbound + Warehouse
    result.shipping_cost = result.outbound_shipping + result.warehouse_storage

    # Cloud Cost per Month (depends on product group)
    is_camera = product.product_group == "Cameras"
    is_bulb = product.product_line == "Bulbs"
    cloud_monthly = (
        static.monthly_cloud_cost_cam if is_camera
        else static.monthly_cloud_cost_noncam
    )

    # Cloud Cost (Lifetime) = Expected Product Life * Cloud Cost per Month
    result.cloud_cost_lifetime = (
        channel_assumptions.expected_product_life * cloud_monthly
    )

    # UID: 0.20 for Cameras, 0 otherwise
    result.uid = static.uid_cam if is_camera else 0.0

    # Excess, Obsolete & Shrinkage = Landed Cost * EOS%
    result.eos = result.landed_cost * static.eos_rate

    # Royalties: Cameras (product_group) = fixed $0.20, Bulbs (product_line) = 5% Net Rev, else 0
    if is_camera:
        result.royalties = static.royalties_cam
    elif is_bulb:
        result.royalties = static.royalties_bulb_rate * result.net_revenue
    else:
        result.royalties = 0.0

    # Other Cost = Cloud + EOS + UID + Royalties
    result.other_cost = (
        result.cloud_cost_lifetime + result.eos + result.uid + result.royalties
    )

    # Cost of Goods = Landed Cost + Shipping Cost + Other Cost
    result.cost_of_goods = result.landed_cost + result.shipping_cost + result.other_cost

    # === SALES & MARKETING (Measures Cost) ===

    # Customer Service = Rate * Post-promo Retailer Price
    result.customer_service = (
        channel_assumptions.customer_service_rate * result.post_promo_retailer_price
    )

    # Credit-card & Platform fees = Rate * Price Paid by End-User (+ $0.99 for Amazon 3P)
    result.cc_platform_fees = (
        channel_assumptions.cc_fee_rate * result.price_paid_by_enduser
    )
    if ch == "Amazon 3P":
        result.cc_platform_fees += 0.99

    # Marketing = Rate * MSRP
    result.marketing = channel_assumptions.marketing_rate * msrp

    # Sales & Marketing Expenses total
    result.sales_marketing_expenses = (
        result.customer_service + result.cc_platform_fees + result.marketing
    )

    # === PROFIT METRICS (Measures Margin) ===

    # Gross Profit = Net Revenue - Cost of Goods
    result.gross_profit = result.net_revenue - result.cost_of_goods

    # Gross Margin %
    result.gross_margin_pct = (
        result.gross_profit / result.net_revenue if result.net_revenue != 0 else 0
    )

    # CPAM $ (Promotional) = Gross Profit - S&M Expenses
    result.cpam_dollar = result.gross_profit - result.sales_marketing_expenses

    # CPAM % = CPAM $ / Net Revenue
    result.cpam_pct = (
        result.cpam_dollar / result.net_revenue if result.net_revenue != 0 else 0
    )

    # Full Price S&M (from DAX: Sales & Marketing Expenses FullPrice)
    sm_fullprice_customer_service = (
        channel_assumptions.customer_service_rate * result.pre_promo_retailer_price
    )
    sm_fullprice_cc = channel_assumptions.cc_fee_rate * result.price_paid_by_enduser
    if ch == "Amazon 3P":
        sm_fullprice_cc += 0.99
    sm_fullprice = sm_fullprice_customer_service + sm_fullprice_cc + result.marketing

    # CPAM $ Full = Net Revenue FullPrice - Cost of Goods - S&M FullPrice
    result.cpam_dollar_full = (
        result.net_revenue_fullprice - result.cost_of_goods - sm_fullprice
    )

    # CPAM % Full
    result.cpam_pct_full = (
        result.cpam_dollar_full / result.net_revenue_fullprice
        if result.net_revenue_fullprice != 0 else 0
    )

    # CPAM $ Blended = Full*(1-PromoMix) + Promo*PromoMix
    result.cpam_dollar_blended = (
        result.cpam_dollar_full * (1 - promotion_mix)
        + result.cpam_dollar * promotion_mix
    )

    # CPAM % Blended
    result.cpam_pct_blended = (
        result.cpam_dollar_blended / result.net_revenue_blended
        if result.net_revenue_blended != 0 else 0
    )

    return result


def calculate_weighted_cpam(
    channel_results: list[CPAMBreakdown],
) -> Optional[CPAMBreakdown]:
    """
    Calculate weighted average CPAM across all channels.
    Replicates the DAX 'Weighted Avg CPAM $' and 'CPAM Summary Output' measures.
    """
    active = [r for r in channel_results if r.channel_mix > 0]
    if not active:
        return None

    total_mix = sum(r.channel_mix for r in active)
    if total_mix == 0:
        return None

    result = CPAMBreakdown(channel="Weighted Avg")
    result.channel_mix = total_mix

    # Weighted average for all numeric fields
    numeric_fields = [
        'msrp', 'shipping_revenue', 'retail_margin', 'po_price',
        'retail_discounts', 'pre_promo_retailer_price', 'promotion',
        'price_paid_by_enduser', 'post_promo_retailer_price',
        'chargebacks', 'returns_replacements', 'other_contra_revenue',
        'net_revenue', 'fob', 'inbound_freight', 'tariff', 'landed_cost',
        'outbound_shipping', 'warehouse_storage', 'shipping_cost',
        'cloud_cost_lifetime', 'eos', 'uid', 'royalties', 'other_cost',
        'cost_of_goods', 'customer_service', 'cc_platform_fees', 'marketing',
        'sales_marketing_expenses', 'gross_profit', 'cpam_dollar',
        'net_revenue_fullprice', 'cpam_dollar_full',
        'net_revenue_blended', 'cpam_dollar_blended',
    ]
    for f in numeric_fields:
        weighted_sum = sum(getattr(r, f) * r.channel_mix for r in active)
        setattr(result, f, weighted_sum / total_mix)

    # Percentage fields: recompute from weighted dollar values
    if result.net_revenue != 0:
        result.gross_margin_pct = result.gross_profit / result.net_revenue
        result.cpam_pct = result.cpam_dollar / result.net_revenue
    if result.net_revenue_fullprice != 0:
        result.cpam_pct_full = result.cpam_dollar_full / result.net_revenue_fullprice
    if result.net_revenue_blended != 0:
        result.cpam_pct_blended = result.cpam_dollar_blended / result.net_revenue_blended

    return result
