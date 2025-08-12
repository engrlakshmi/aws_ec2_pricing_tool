from recommender import recommend_instances

if __name__ == "__main__":
    region = "us-east-1"
    os = "Linux"
    vcpu = 2
    memory = 4
    duration_months = 12
    bursty = True

    top_recs = recommend_instances(
        vcpu_required=vcpu,
        memory_required=memory,
        os=os,
        region=region,
        usage_months=duration_months,
        burstable_ok=bursty
    )

    print("\nTop Instance Recommendations:\n")
    for rec in top_recs:
        print(f"{rec['InstanceType']:12} | {rec['vCPU']} vCPU | {rec['MemoryGiB']} GiB | "
              f"OnDemand: ${rec['OnDemandHr']:.4f}/hr | SP(1yr): ${rec['SP_1yr_Hr']:.4f}/hr | "
              f"Preferred: {rec['PricingModel']} @ ${rec['PreferredCost']}/mo")
