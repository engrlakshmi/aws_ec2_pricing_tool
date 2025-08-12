import pandas as pd
from core import get_on_demand_rate, get_savings_plan_rate
from mappings import get_all_regions, region_name_map
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


INSTANCE_DB = [
    {"instanceType": "t3.micro", "vCPU": 2, "memoryGiB": 1, "burstable": True},
    {"instanceType": "t3.small", "vCPU": 2, "memoryGiB": 2, "burstable": True},
    {"instanceType": "t3a.small", "vCPU": 2, "memoryGiB": 2, "burstable": True},
    {"instanceType": "m5.large", "vCPU": 2, "memoryGiB": 8, "burstable": False},
    {"instanceType": "m6g.medium", "vCPU": 1, "memoryGiB": 4, "burstable": False},
    
]

def recommend_instances(vcpu_required, memory_required, os, region, usage_months, burstable_ok=True):
    recommendations = []

    for inst in INSTANCE_DB:
        if inst["vCPU"] < vcpu_required or inst["memoryGiB"] < memory_required:
            continue
        if not burstable_ok and inst["burstable"]:
            continue

        instance_type = inst["instanceType"]

        try:
            ondemand = get_on_demand_rate(region, instance_type, os)
            sp_1yr = get_savings_plan_rate(region, instance_type, os, term="1yr", plan_type="Compute")

            if ondemand is None or sp_1yr is None:
                continue

            # Cost evaluation
            if usage_months < 3:
                preferred = "On-Demand"
                cost = ondemand * 24 * 30
            else:
                preferred = "1yr SP"
                cost = sp_1yr * 24 * 30

            recommendations.append({
                "InstanceType": instance_type,
                "vCPU": inst["vCPU"],
                "MemoryGiB": inst["memoryGiB"],
                "OnDemandHr": ondemand,
                "SP_1yr_Hr": sp_1yr,
                "PreferredCost": round(cost, 2),
                "PricingModel": preferred
            })

        except Exception as e:
            logger.warning(f"Error processing {instance_type}: {e}")
            continue

    # Sort by cost
    sorted_recs = sorted(recommendations, key=lambda x: x["PreferredCost"])

    return sorted_recs[:3]  # Top 3

