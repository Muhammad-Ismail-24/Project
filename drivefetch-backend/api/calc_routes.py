from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/calc", tags=["Calculators"])

# ==========================================
# PYDANTIC SCHEMAS FOR CALCULATORS
# ==========================================

class FuelRequest(BaseModel):
    car_segment_cc: int = Field(..., description="Engine capacity in CC", ge=1)
    daily_commute_km: int = Field(..., description="Average daily commute distance in kilometers", ge=0)

class TransferRequest(BaseModel):
    engine_cc: int = Field(..., description="Engine capacity in CC", ge=1)
    is_filer: bool = Field(..., description="Tax status: Filer (True) or Non-Filer (False)")

class TokenRequest(BaseModel):
    engine_cc: int = Field(..., description="Engine capacity in CC", ge=1)
    is_filer: bool = Field(..., description="Tax status: Filer (True) or Non-Filer (False)")
    province: str = Field(..., description="Province of registration (Punjab, Sindh, KPK, Islamabad)")


# ==========================================
# POST ENDPOINTS
# ==========================================

@router.post("/fuel")
def calculate_monthly_fuel(req: FuelRequest):
    """Calculates estimated monthly fuel cost in PKR based on engine CC and daily commute.
    Assumes standard PKR 300/L rate.
    """
    cc = req.car_segment_cc
    commute = req.daily_commute_km
    
    # Generic Pakistani fuel averages based on engine CC
    if cc < 1000:
        km_per_liter = 16.0  # e.g., Alto, WagonR
    elif cc <= 1300:
        km_per_liter = 13.0  # e.g., Vitz, Swift, Yaris 1.3
    elif cc <= 1600:
        km_per_liter = 11.0  # e.g., Civic, Corolla 1.6
    elif cc <= 2000:
        km_per_liter = 9.0   # e.g., Sportage, Tucson, Altis Grande 1.8
    else:
        km_per_liter = 7.0   # e.g., Fortuner, Prado, Land Cruiser

    monthly_distance = commute * 30
    liters_required = monthly_distance / km_per_liter
    petrol_price = 300  # Hardcoded PKR/L petrol price
    monthly_cost = round(liters_required * petrol_price)

    return {
        "monthly_distance_km": monthly_distance,
        "km_per_liter_average": km_per_liter,
        "monthly_fuel_cost_pkr": monthly_cost
    }


@router.post("/transfer-fee")
def calculate_transfer_costs(req: TransferRequest):
    """Calculates mock Excise transfer fee and FBR withholding tax.
    Imposes a high withholding penalty on non-filers.
    """
    cc = req.engine_cc
    filer = req.is_filer

    # 1. Excise Transfer Fee
    if cc < 1000:
        transfer_fee = 5000
    elif cc < 1800:
        transfer_fee = 15000
    else:
        transfer_fee = 30000

    # 2. FBR Withholding Tax (WHT)
    if cc < 1000:
        wht = 10000 if filer else 30000
    elif cc < 1500:
        wht = 25000 if filer else 75000
    elif cc < 2000:
        wht = 50000 if filer else 150000
    else:
        wht = 100000 if filer else 300000

    total_cost = transfer_fee + wht

    return {
        "excise_transfer_fee": transfer_fee,
        "withholding_tax": wht,
        "non_filer_penalty": 0 if filer else (wht - (wht // 3)),
        "total_transfer_cost_pkr": total_cost
    }


@router.post("/token-tax")
def calculate_annual_token_tax(req: TokenRequest):
    """Calculates mock annual token tax in Pakistan based on province, CC, and tax status."""
    cc = req.engine_cc
    filer = req.is_filer
    prov = req.province.strip().lower()

    # Base tax scale
    if cc < 1000:
        base_tax = 1500
    elif cc <= 1300:
        base_tax = 3000
    elif cc <= 1500:
        base_tax = 5000
    elif cc <= 2000:
        base_tax = 10000
    else:
        base_tax = 20000

    # FBR Income Tax withholding on annual tokens
    if cc <= 1300:
        income_tax = 1500 if filer else 4500
    else:
        income_tax = 4000 if filer else 12000

    # Province adjustments (KPK/Sindh base multipliers)
    province_multiplier = 1.0
    if prov in ["sindh", "kpk"]:
        province_multiplier = 1.15
    elif prov == "islamabad":
        province_multiplier = 0.95

    total_tax = round((base_tax + income_tax) * province_multiplier)

    return {
        "base_token_tax": base_tax,
        "annual_withholding_tax": income_tax,
        "province_adjustment_factor": province_multiplier,
        "total_annual_token_tax_pkr": total_tax
    }
