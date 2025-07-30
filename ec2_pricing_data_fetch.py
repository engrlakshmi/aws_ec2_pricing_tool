# --- Streamlit EC2 Pricing Tool (Fixed: all regions display) ---

import streamlit as st
import pandas as pd
import boto3
import requests
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
import math

# --- Constants ---
LOG_FILE = "error_log.txt"
PAGE_SIZE = 50
MAX_THREADS = 20

#If we failed to fetch regions from AWS boto3 then we will use this 
region_list = ['ap-south-2', 'ap-south-1', 'eu-south-1', 'eu-south-2', 'me-central-1', 'ca-central-1', 
               'eu-central-1', 'eu-central-2', 'us-west-1', 'us-west-2', 'af-south-1', 'eu-north-1', 
               'eu-west-3', 'eu-west-2', 'eu-west-1', 'ap-northeast-3', 'ap-northeast-2', 'me-south-1', 
               'ap-northeast-1', 'sa-east-1', 'ap-southeast-1', 'ap-southeast-2', 'ap-southeast-3', 
               'ap-southeast-4', 'us-east-1', 'us-east-2']

st.cache_resource.clear()
# --- Helpers ---
def log_error(msg: str):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now()} - {msg}\n")

def parse_memory(mem_str: str) -> float:
    try:
        return float(mem_str.replace("GiB", "").strip())
    except Exception:
        return math.nan

@st.cache_resource(show_spinner=False)
def get_ec2_client():
    return boto3.client(
        "ec2",
        #aws_access_key_id='ss',
        #aws_secret_access_key='ss',
        #aws_session_token='ss',
        region_name="us-east-1")

@st.cache_data(show_spinner=False)
def get_all_regions():
    try:
        regions = get_ec2_client().describe_regions(AllRegions=True)
        return sorted([r["RegionName"] for r in regions["Regions"] if r["OptInStatus"] in {"opt-in-not-required", "opted-in"}])
    except Exception as e:
        log_error(f"Region Fetch Error: {e}")
        return region_list

@st.cache_data(show_spinner=False)
def get_all_instance_types():
    paginator = get_ec2_client().get_paginator("describe_instance_types")
    types = [it["InstanceType"] for page in paginator.paginate() for it in page["InstanceTypes"]]
    return sorted(types)

@st.cache_data(show_spinner=False)
def fetch_offer_file(region: str):
    try:
        url = f"https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/{region}/index.json"
        r = requests.get(url, timeout=90)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log_error(f"Offer Fetch Error ({region}): {e}")
        return {"products": {}, "terms": {}}

@st.cache_data(show_spinner=False)
def load_dynamic_filter_options(sample_region="us-east-1"):
    def normalize(val):
        if not val or not isinstance(val, str):
            return None
        return val.strip().lower().replace(" ", "")

    data = fetch_offer_file(sample_region)
    products = data.get("products", {})
    terms_all = data.get("terms", {})

    raw_sets = {
        "PurchaseOption": {},
        "OfferingClass": {},
        "LeaseContractLength": {},
        "PreInstalledSw": {},
        "OperatingSystem": {},
        "Tenancy": {},
    }

    for sku, prod in products.items():
        attr = prod.get("attributes", {})
        for k, ak in [("OperatingSystem", "operatingSystem"), ("PreInstalledSw", "preInstalledSw"), ("Tenancy", "tenancy")]:
            val = attr.get(ak)
            norm = normalize(val)
            if norm:
                raw_sets[k][norm] = val

        for term_cat in ["Reserved", "OnDemand", "SavingsPlan"]:
            for term_obj in terms_all.get(term_cat, {}).get(sku, {}).values():
                term_attr = term_obj.get("termAttributes", {})
                for k in ["PurchaseOption", "OfferingClass", "LeaseContractLength"]:
                    val = term_attr.get(k)
                    norm = normalize(val)
                    if norm:
                        raw_sets[k][norm] = val

    return {
        k: sorted(set(raw_sets[k].values())) for k in raw_sets
    }

@st.cache_data(show_spinner=False)
def load_family_options(sample_region="us-east-1"):
    data = fetch_offer_file(sample_region)
    families = set()
    for sku, prod in data.get("products", {}).items():
        inst = prod.get("attributes", {}).get("instanceType")
        if inst and "." in inst:
            families.add(inst.split(".")[0])
    return sorted(families)

def _in_filter(value, allowed_set):
    return True if not allowed_set else value in allowed_set

@st.cache_data(show_spinner=False)
def fetch_pricing(region: str, filters: dict):
    data = fetch_offer_file(region)
    products = data.get("products", {})
    terms_all = data.get("terms", {})
    itypes = filters.get("instance_types", set())
    tenancies = filters.get("tenancies", set())
    op_sys = filters.get("operating_systems", set())
    purchase_opts = filters.get("purchase_options", set())
    offer_classes = filters.get("offering_classes", set())
    lease_terms = filters.get("lease_terms", set())
    pre_sw = filters.get("pre_sw", set())
    term_types = filters.get("term_types") or ["OnDemand", "Reserved"]
    families = filters.get("families", set())
    vcpu_min, vcpu_max = filters.get("vcpu_range", (0, 128))
    mem_min, mem_max = filters.get("mem_range", (0.0, 2048.0))

    results = []
    for sku, product in products.items():
        attrs = product.get("attributes", {})
        inst_type = attrs.get("instanceType")
        if not inst_type:
            continue

        family = inst_type.split(".")[0]
        if itypes and inst_type not in itypes:
            continue
        if tenancies and attrs.get("tenancy") not in tenancies:
            continue
        if op_sys and attrs.get("operatingSystem") not in op_sys:
            continue
        if pre_sw and attrs.get("preInstalledSw") not in pre_sw:
            continue
        if families and family not in families:
            continue

        try:
            vcpu_val = int(attrs.get("vcpu", 0))
        except:
            vcpu_val = 0
        if vcpu_val < vcpu_min or vcpu_val > vcpu_max:
            continue

        mem_val = parse_memory(attrs.get("memory", "0"))
        if mem_val < mem_min or mem_val > mem_max:
            continue

        for term_category in term_types:
            sku_terms = terms_all.get(term_category, {}).get(sku, {})
            for term_id, term_data in sku_terms.items():
                t_attrs = term_data.get("termAttributes", {})
                if not _in_filter(t_attrs.get("PurchaseOption"), purchase_opts):
                    continue
                if not _in_filter(t_attrs.get("OfferingClass"), offer_classes):
                    continue
                if not _in_filter(t_attrs.get("LeaseContractLength"), lease_terms):
                    continue
                for price_dim in term_data.get("priceDimensions", {}).values():
                    try:
                        price = float(price_dim.get("pricePerUnit", {}).get("USD", 0.0))
                    except:
                        price = 0.0
                    results.append({
                        "Region": region,
                        "Location": attrs.get("location"),
                        "Instance Type": inst_type,
                        "Current Generation": attrs.get("currentGeneration"),
                        "Instance Family": attrs.get("instanceFamily"),
                        "Family": family,
                        "vCPU": vcpu_val,
                        "Memory": attrs.get("memory"),
                        "Memory (GiB)": mem_val,
                        "Storage": attrs.get("storage"),
                        "Network Performance": attrs.get("networkPerformance"),
                        "Processor Architecture": attrs.get("processorArchitecture"),
                        "Storage Media": attrs.get("storageMedia"),
                        "Tenancy": attrs.get("tenancy"),
                        "EBS Optimized": attrs.get("ebsOptimized"),
                        "Dedicated EBS Throughput": attrs.get("dedicatedEbsThroughput"),
                        "Processor Features": attrs.get("processorFeatures"),
                        "Physical Processor": attrs.get("physicalProcessor"),
                        "Operating System": attrs.get("operatingSystem"),
                        "License Model": attrs.get("licenseModel"),
                        "Pre Installed S/W": attrs.get("preInstalledSw"),
                        "Region Code": attrs.get("regionCode"),
                        "ServiceName": attrs.get("servicecode", "AmazonEC2"),
                        "TermType": term_category,
                        "PurchaseOption": t_attrs.get("PurchaseOption"),
                        "OfferingClass": t_attrs.get("OfferingClass"),
                        "LeaseContractLength": t_attrs.get("LeaseContractLength"),
                        "Unit": price_dim.get("unit"),
                        "PricePerUnit": price,
                        "EffectiveDate": term_data.get("effectiveDate"),
                    })
    return results


@st.cache_data(show_spinner=False)
def load_family_options(sample_region="us-east-1"):
    data = fetch_offer_file(sample_region)
    families = set()
    for sku, prod in data.get("products", {}).items():
        inst = prod.get("attributes", {}).get("instanceType")
        if inst and "." in inst:
            families.add(inst.split(".")[0])
    return sorted(families)


# --- Streamlit UI ---
#st.set_page_config(page_title="AWS EC2 Pricing Tool", layout="wide")
#st.title("💸 AWS EC2 Pricing Tool")

# for k, v in {"data": pd.DataFrame(), "page": 1, "is_loading": False}.items():
#     st.session_state.setdefault(k, v)

# st.sidebar.header("🔍 Filter Options")
# regions_sel = st.sidebar.multiselect("Region", get_all_regions(), default=["us-east-1"])
# instance_types_sel = st.sidebar.multiselect("Instance Type", get_all_instance_types())
# term_types_sel = st.sidebar.multiselect("Term Type (e.g. OnDemand, reserved)", ["OnDemand", "Reserved"])
# # regions_sel = st.sidebar.multiselect("Region", get_all_regions())
# # instance_types_sel = st.sidebar.multiselect("Instance Type", get_all_instance_types())
# # term_types_sel = st.sidebar.multiselect("Term Type", ["OnDemand", "Reserved", "SavingsPlan"])

# # Load dynamic options
# dynamic_opts = load_dynamic_filter_options()
# operating_systems_sel = st.sidebar.multiselect("Operating System (e.g. Windows, Linux)", dynamic_opts["OperatingSystem"])
# tenancies_sel = st.sidebar.multiselect("Tenancy (e.g. Shared, Host)", dynamic_opts["Tenancy"])
# purchase_opt_sel = st.sidebar.multiselect("Purchase Option (e.g. All Upfront, No Upfront, Partial Upfront)", dynamic_opts["PurchaseOption"])
# offering_class_sel = st.sidebar.multiselect("Offering Class (e.g. Convertible, Standard)", dynamic_opts["OfferingClass"])
# lease_term_sel = st.sidebar.multiselect("Lease Contract Length (e.g. 1 Yr, 3 Yr)", dynamic_opts["LeaseContractLength"])
# pre_sw_sel = st.sidebar.multiselect("Pre Installed S/W (e.g. SQL Web, SQL Ent)", dynamic_opts["PreInstalledSw"])
# family_sel = st.sidebar.multiselect("Instance Family (e.g.m5, c5)", load_family_options())


# with st.sidebar:
#     st.markdown("### ⚙️ Instance Specs")

#     col1, col2 = st.columns(2)
#     with col1:
#         vcpu_min = st.number_input("Min vCPU", min_value=0, max_value=128, value=0, step=1)
#     with col2:
#         vcpu_max = st.number_input("Max vCPU", min_value=0, max_value=128, value=128, step=1)

#     col3, col4 = st.columns(2)
#     with col3:
#         mem_min = st.number_input("Min Memory (GiB)", min_value=0.0, max_value=2048.0, value=0.0, step=1.0)
#     with col4:
#         mem_max = st.number_input("Max Memory (GiB)", min_value=0.0, max_value=2048.0, value=2048.0, step=1.0)

# filter_params = {
#     "instance_types": set(instance_types_sel),
#     "tenancies": set(tenancies_sel),
#     "operating_systems": set(operating_systems_sel),
#     "purchase_options": set(purchase_opt_sel),
#     "offering_classes": set(offering_class_sel),
#     "lease_terms": set(lease_term_sel),
#     "pre_sw": set(pre_sw_sel),
#     # "term_types": term_types_sel or ["OnDemand"],
#     "term_types": term_types_sel if term_types_sel else ["OnDemand", "Reserved"],
#     "families": set(family_sel),
#     "vcpu_range": (vcpu_min, vcpu_max),
#     "mem_range": (mem_min, mem_max),
# }

# if st.sidebar.button("🔎 Fetch Pricing"):
#     st.session_state["is_loading"] = True
#     st.session_state["page"] = 1
#     st.session_state["data"] = pd.DataFrame()

#     with st.spinner("⏳ Fetching pricing data..."):
#         results = []
#         progress_bar = st.progress(0)
#         for idx, region in enumerate(regions_sel):
#             results.extend(fetch_pricing(region, filter_params))
#             progress_bar.progress((idx + 1) / len(regions_sel))
#         st.session_state["data"] = pd.DataFrame(results)
#         st.session_state["is_loading"] = False

# df = st.session_state["data"]
# if st.session_state["is_loading"]:
#     st.info("⏳ Fetching data, please wait...")
# elif not df.empty:
#     total_pages = (len(df) - 1) // PAGE_SIZE + 1
#     page = st.session_state["page"]
#     start, end = (page - 1) * PAGE_SIZE, page * PAGE_SIZE
#     st.markdown(f"**🔢 Total records: {len(df)}**")
#     st.subheader(f"📊 Results (Page {page} of {total_pages})")
#     st.dataframe(df.iloc[start:end], use_container_width=True)

#     if len(df) > PAGE_SIZE:
#         n1, n2, n3 = st.columns([1, 6, 1])
#         with n1:
#             if st.button("⬅️ Prev", key="prev") and page > 1:
#                 st.session_state["page"] -= 1
#         with n3:
#             if st.button("➡️ Next", key="next") and page < total_pages:
#                 st.session_state["page"] += 1

#     # col_dl, _ = st.columns([2, 8])
#     # with col_dl:
#     #     if not df.empty:
#     #         output = BytesIO()
#     #         wb = Workbook()
#     #         added = False

#     #         for reg in regions_sel:
#     #             reg_df = df[df["Region"] == reg]
#     #             if reg_df.empty:
#     #                 continue
#     #             ws = wb.create_sheet(title=reg[:31])
#     #             for row in dataframe_to_rows(reg_df, index=False, header=True):
#     #                 ws.append(row)
#     #             added = True

#     #         if added:
#     #             default_sheet = wb.active
#     #             wb.remove(default_sheet)

#     #         wb.save(output)
#     #         output.seek(0)
#     #         st.download_button("⬇️ Download Excel", output, "aws_ec2_pricing_by_region.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
#     #     else:
#     #         st.warning("⚠️ No data available to download.")
# else:
#     st.info("ℹ️ No data fetched yet. Use the sidebar to select filters and click 'Fetch Pricing'.")