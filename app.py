import streamlit as st
import pandas as pd
import sys, os
import itertools

# Add parent directory to import local modules
sys.path.append(os.path.abspath(".."))

# Custom imports
import ec2_sp_backend
from ec2_pricing_data_fetch import (
    get_all_instance_types,
    get_all_regions,
    load_dynamic_filter_options,
    load_family_options,
    fetch_pricing,
)

# --- Constants ---
PAGE_SIZE = 20
st.set_page_config(page_title="AWS EC2 Pricing Tool", layout="wide")
st.title("💸 AWS EC2 Pricing Tool")

# --- Mode Selection ---
# mode = st.radio("Choose Pricing Type:", ["💰 Savings Plan", "📊 On-Demand & Reserved"], horizontal=True)
mode = st.radio(
    "Choose Pricing Type:",
    options=["💰 Savings Plan", "📊 On-Demand & Reserved"],
    index = 0,
    horizontal=True,
)


# --- Cache Static Data ---
@st.cache_data
def get_instance_types():
    return get_all_instance_types()

# @st.cache_data
# def get_regions():
#     return get_all_regions()

instance_types = get_instance_types()
# all_regions = get_regions()

# --- Session State ---
for k, v in {"data": pd.DataFrame(), "page": 1, "is_loading": False}.items():
    st.session_state.setdefault(k, v)
# if mode == "":
#     st.title("💸 AWS EC2 Pricing Tool")
# ================================================================================
# 💰 SAVINGS PLAN SECTION
# ================================================================================
if mode == "💰 Savings Plan":
    # st.title("Savings Plan Data")
    st.sidebar.header("🔍 Filter Criteria (Savings Plan)")
    # st.sidebar.markdown("🧭 **Use the filters below to customize your Saving Plans pricing query.**")

    # Static filter options
    aws_regions = sorted(ec2_sp_backend.region_name_map.keys())
    operating_systems = sorted(ec2_sp_backend.operation_by_platform_dict.keys())
    tenancy_options = list(ec2_sp_backend.tenancy_dict.values())
    sp_types = ["ComputeSavingsPlans", "EC2InstanceSavingsPlans"]
    terms = ["1yr", "3yr"]
    purchasing_options = ["No Upfront", "Partial Upfront", "All Upfront"]
    family =  load_family_options()
    # Sidebar filters
    selected_regions = st.sidebar.multiselect("AWS Region (e.g. us-east-1, ap-south-1)", aws_regions, key="sp_region")
    selected_os = st.sidebar.multiselect("Operating System (e.g. Linux/UNIX, Windows)", operating_systems, key="sp_os")
    selected_tenancy = st.sidebar.multiselect("Tenancy (e.g. Shared, Dedicated Host)", tenancy_options, key="sp_tenancy")
    seleted_instance_family = st.sidebar.multiselect("Instance Family (e.g. t3, m5, c7g)", load_family_options(), key="sp_family")
    selected_instance_types = st.sidebar.multiselect("Instance Type (e.g. t3.medium, m5.large)", instance_types, key="sp_instance")
    selected_sp_types = st.sidebar.multiselect("Savings Plan Type (e.g. ComputeSavingsPlans, EC2InstanceSavingsPlans)", sp_types, key="sp_type")
    selected_terms = st.sidebar.multiselect("Term (e.g. 1yr, 3yr)", terms, key="sp_term")
    selected_purchasing = st.sidebar.multiselect("Purchasing Option (e.g. No Upfront, Partial Upfront)", purchasing_options, key="sp_purchase")

    # Apply defaults if no selection
    selected_regions = selected_regions or aws_regions
    selected_os = selected_os or operating_systems
    selected_tenancy = selected_tenancy or tenancy_options
    selected_instance_types = selected_instance_types or instance_types
    seleted_instance_family = seleted_instance_family or family
    selected_sp_types = selected_sp_types or sp_types
    selected_terms = selected_terms or terms
    selected_purchasing = selected_purchasing or purchasing_options

    if st.sidebar.button("💡 Get Savings Plan Pricing", key="btn_sp"):
        results = []

        with st.spinner("Fetching savings plan data..."):
            combinations = itertools.product(
                selected_regions,
                selected_os,
                selected_tenancy,
                selected_instance_types,
                selected_sp_types,
                selected_terms,
                selected_purchasing
            )

            for region, os_input, tenancy, instance_type, sp_type, term, purchasing_option in combinations:
                try:
                    usage_operation = ec2_sp_backend.operation_by_platform_dict[os_input]
                    instance_family = instance_type.split('.')[0]
                    ec2_sp_backend.check_input_parameters(usage_operation, tenancy, sp_type, term, purchasing_option)

                    try:
                        sp_rate = ec2_sp_backend.get_savings_plan_rate(
                            region_code=region,
                            usage_operation=usage_operation,
                            instance_family=instance_family,
                            instance_type=instance_type,
                            tenancy=tenancy,
                            sp_type=sp_type,
                            term=term,
                            purchasing_option=purchasing_option
                        )
                    except Exception:
                        sp_rate = None

                    try:
                        on_demand_rate = ec2_sp_backend.get_on_demand_rate(
                            region_code=region,
                            usage_operation=usage_operation,
                            instance_type=instance_type,
                            tenancy=tenancy
                        )
                        if on_demand_rate == 0:
                            on_demand_rate = None
                    except Exception:
                        on_demand_rate = None

                    if sp_rate is not None and on_demand_rate is not None:
                        savings_percent = f"{round((1 - (sp_rate / on_demand_rate)) * 100, 1)}%"
                    else:
                        savings_percent = "N/A"

                    results.append({
                        "AWS Region": region,
                        "Operating System": os_input,
                        "Instance Type": instance_type,
                        "Tenancy": tenancy,
                        "Savings Plan Type": sp_type,
                        "Term": term,
                        "Purchasing Option": purchasing_option,
                        "Savings Plan Rate ($)": sp_rate if sp_rate is not None else "N/A",
                        "On-Demand Rate ($)": on_demand_rate if on_demand_rate is not None else "N/A",
                        "Savings over On-Demand (%)": savings_percent
                    })

                except Exception:
                    results.append({
                        "AWS Region": region,
                        "Operating System": os_input,
                        "Instance Type": instance_type,
                        "Tenancy": tenancy,
                        "Savings Plan Type": sp_type,
                        "Term": term,
                        "Purchasing Option": purchasing_option,
                        "Savings Plan Rate ($)": "N/A",
                        "On-Demand Rate ($)": "N/A",
                        "Savings over On-Demand (%)": "N/A"
                    })

        result_df = pd.DataFrame(results)
        st.success("✅ Pricing fetched successfully!")
        st.dataframe(result_df, use_container_width=True)

        csv_data = result_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", data=csv_data, file_name="savings_plan_output.csv", mime="text/csv")

# ================================================================================
# 📊 ON-DEMAND / RESERVED SECTION
# ================================================================================
# elif mode == "📊 On-Demand & Reserved":
else:
    # st.title("On-Demand & Reserved Data")
    st.sidebar.header("🔍 Filter Criteria (On-Demand / Reserved)")
    regions_sel = st.sidebar.multiselect("Region (e.g. us-east-1, ap-south-1)", get_all_regions(), key="od_region")
    family_sel = st.sidebar.multiselect("Instance Family (e.g. t3, m5, r6g)", load_family_options(), key="od_family")
    instance_types_sel = st.sidebar.multiselect("Instance Type (e.g. t3.micro, m5.large)", instance_types, key="od_instance")

    # Load dynamic options
    dynamic_opts = load_dynamic_filter_options()
    operating_systems_sel = st.sidebar.multiselect("Operating System (e.g. Linux/UNIX, Windows)", dynamic_opts["OperatingSystem"], key="od_os")
    term_types_sel = st.sidebar.multiselect("Term Type (e.g. OnDemand, Reserved)", ["OnDemand", "Reserved"], default=["OnDemand", "Reserved"], key="od_term")
    tenancies_sel = st.sidebar.multiselect("Tenancy (e.g. Shared, Dedicated Instance)", dynamic_opts["Tenancy"], key="od_tenancy")
    purchase_opt_sel = st.sidebar.multiselect("Purchase Option (e.g. No Upfront, All Upfront)", dynamic_opts["PurchaseOption"], key="od_po")
    offering_class_sel = st.sidebar.multiselect("Offering Class (e.g. standard, convertible)", dynamic_opts["OfferingClass"], key="od_class")
    lease_term_sel = st.sidebar.multiselect("Lease Contract Length (e.g. 1yr, 3yr)", dynamic_opts["LeaseContractLength"], key="od_lease")
    pre_sw_sel = st.sidebar.multiselect("Pre Installed S/W (e.g. NA, SQL Server)", dynamic_opts["PreInstalledSw"], key="od_sw")

    # vCPU and Memory filters
    with st.sidebar:
        st.markdown("### ⚙️ Instance Specs")
        col1, col2 = st.columns(2)
        vcpu_min = col1.number_input("Min vCPU", 0, 128, 0, key="vcpu_min")
        vcpu_max = col2.number_input("Max vCPU", 0, 128, 128, key="vcpu_max")
        col3, col4 = st.columns(2)
        mem_min = col3.number_input("Min Memory (GiB)", 0.0, 2048.0, 0.0, key="mem_min")
        mem_max = col4.number_input("Max Memory (GiB)", 0.0, 2048.0, 2048.0, key="mem_max")

    # Build filter dictionary
    filter_params = {
        "instance_types": set(instance_types_sel),
        "tenancies": set(tenancies_sel),
        "operating_systems": set(operating_systems_sel),
        "purchase_options": set(purchase_opt_sel),
        "offering_classes": set(offering_class_sel),
        "lease_terms": set(lease_term_sel),
        "pre_sw": set(pre_sw_sel),
        "term_types": term_types_sel,
        "families": set(family_sel),
        "vcpu_range": (vcpu_min, vcpu_max),
        "mem_range": (mem_min, mem_max),
    }

    if st.sidebar.button("🔎 Fetch Pricing", key="btn_od"):
        st.session_state["is_loading"] = True
        st.session_state["page"] = 1
        st.session_state["data"] = pd.DataFrame()

        with st.spinner("⏳ Fetching pricing data..."):
            results = []
            progress_bar = st.progress(0)
            for idx, region in enumerate(regions_sel):
                results.extend(fetch_pricing(region, filter_params))
                progress_bar.progress((idx + 1) / len(regions_sel))
            st.session_state["data"] = pd.DataFrame(results)
            st.session_state["is_loading"] = False

    # Show results with pagination
    df = st.session_state["data"]
    if st.session_state["is_loading"]:
        st.info("⏳ Fetching data, please wait...")
    elif not df.empty:
        st.markdown(f"**🔢 Total records: {len(df)}**")
        st.subheader("📊 Full Results")
        st.dataframe(df, use_container_width=True)

        # CSV Download Button (entire data)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Full Data as CSV",
            data=csv,
            file_name="on_demand_reserved_pricing.csv",
            mime="text/csv",
            key="download_csv"
        )
    else:
        st.info("ℹ️ No data fetched yet. Use the sidebar to select filters and click 'Fetch Pricing'.")
