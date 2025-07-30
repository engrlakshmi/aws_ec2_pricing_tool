import requests
import json
import boto3
from pprint import pprint
import logging
# Use credentials from environment 
pricing_client = boto3.client(
    'pricing',
    region_name='ss',
        #aws_access_key_id='s',
        #aws_secret_access_key='s',
        #aws_session_token='s',
)
# Log config
logging.basicConfig(filename='pricing_log.txt',filemode='w',level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
#ref. mapping https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/billing-info-fields.html
# Mapping: Operating System name → Usage Operation Code (used in Savings Plan JSON)
operation_by_platform_dict = {"Linux/UNIX": "RunInstances",
                             # "Red Hat BYOL Linux": "RunInstances:00g0",
                              "Red Hat Enterprise Linux": "RunInstances:0010",
                              "Red Hat Enterprise Linux with HA": "RunInstances:1010",
                              "Red Hat Enterprise Linux with SQL Server Standard and HA": "RunInstances:1014",
                              "Red Hat Enterprise Linux with SQL Server Enterprise and HA": "RunInstances:1110",
                              "Red Hat Enterprise Linux with SQL Server Standard": "RunInstances:0014",
                              "Red Hat Enterprise Linux with SQL Server Web": "RunInstances:0210",
                              "Red Hat Enterprise Linux with SQL Server Enterprise": "RunInstances:0110",
                              #"SQL Server Enterprise": "RunInstances:0100",
                              #"SQL Server Standard": "RunInstances:0004",
                              #"SQL Server Web": "RunInstances:0200",
                              "SUSE Linux": "RunInstances:000g",
                              "Ubuntu Pro": "RunInstances:0g00",
                              "Windows": "RunInstances:0002",
                              #"Windows BYOL": "RunInstances:0800",
                              "Windows with SQL Server Enterprise": "RunInstances:0102",
                              "Windows with SQL Server Standard": "RunInstances:0006",
                              "Windows with SQL Server Web": "RunInstances:0202"}

#tenancy dictionary
#ref. https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/describe_instances.html
tenancy_dict = {"default":"Shared",
                "dedicated":"Dedicated Instance",
                "host":"Dedicated Host"}

tenancy_friendly_to_api = {
    "Shared": "shared",
    "Dedicated Instance": "dedicated",
    "Dedicated Host": "host"
}

#Load region index for Savings Plan pricing
region_price = {};
region_price_index_api_url = "https://pricing.us-east-1.amazonaws.com/savingsPlan/v1.0/aws/AWSComputeSavingsPlan/current/region_index.json"
response_region_price_index = requests.get(region_price_index_api_url, timeout=5)
region_price_index = response_region_price_index.json()['regions']



def get_pricing_by_region(region_code):
    if (region_code not in region_price): #check if region pricing is already loaded
        for region in region_price_index:
            if (region['regionCode'] == region_code):
                region_price_api_url = "https://pricing.us-east-1.amazonaws.com" + region['versionUrl']
                region_price_response = requests.get(region_price_api_url, timeout=5)
                #save pricing by region
                region_price[region_code] = region_price_response.json()
                break
    return region_price[region_code]

def get_savings_plan_rate(region_code, usage_operation, instance_family, instance_type, tenancy, sp_type, term, purchasing_option):
    region_price = get_pricing_by_region(region_code)
    sku = ''
    sp_rate = None
    products = region_price['products']

    # Step 1: Find correct SKU
    for product in products:
        if (product['attributes']['purchaseOption'] == purchasing_option and
            product['attributes']['purchaseTerm'] == term and
            product['productFamily'] == sp_type and
            #(sp_type == "ComputeSavingsPlans" or product['attributes']['instanceType'] == instance_family)
            ((sp_type == "ComputeSavingsPlans") or
             (sp_type == "EC2InstanceSavingsPlans" and 'instanceType' in product['attributes'] and product['attributes']['instanceType'] == instance_family)
            )):
            sku = product['sku']
            break  # Use the first match

    

    if not sku:
        logging.warning(f"No SKU found for {sp_type} - {instance_family} in {region_code} ({term}, {purchasing_option})")
        return None

    # Step 2: Find matching savings plan rate using SKU
    terms = region_price['terms']['savingsPlan']
    for term_entry in terms:
        if term_entry['sku'] == sku:
            for rate in term_entry['rates']:
                if usage_operation == rate['discountedOperation']:
                    dut = rate['discountedUsageType']

                    # Tenancy: Shared
                    if tenancy == 'Shared':
                        if dut.endswith("-BoxUsage:" + instance_type):
                            sp_rate = float(rate['discountedRate']['price'])
                            break
                        elif region_code == 'us-east-1' and dut == "BoxUsage:" + instance_type:
                            sp_rate = float(rate['discountedRate']['price'])
                            break

                    # Tenancy: Dedicated Instance
                    elif tenancy == 'Dedicated Instance' and dut.endswith("DedicatedUsage:" + instance_type):
                        sp_rate = float(rate['discountedRate']['price'])
                        break

                    # Tenancy: Dedicated Host
                    elif tenancy == 'Dedicated Host' and dut.endswith("HostUsage:" + instance_family):
                        sp_rate = float(rate['discountedRate']['price'])
                        break
            break  # Exit after processing matching SKU

    if sp_rate is None:
        logging.warning(f"No rate found for {instance_type} in {region_code} ({sp_type}, {tenancy}, {term}, {purchasing_option})")
        return None

    return sp_rate

  
# Validates input parameters to avoid runtime failures
    
def check_input_parameters(usage_operation, tenancy, sp_type, term, purchasing_option):
    #check usage_operation
    if (usage_operation not in operation_by_platform_dict.values()):
        raise ValueError('Usage operation unknown, check the Operating System input parameter', usage_operation)
    #check tenancy
    if (tenancy not in tenancy_dict.values()):
        raise ValueError('Tenancy unknown, check Tenancy input parameter', tenancy)
    #check sp_type
    if (sp_type != "EC2InstanceSavingsPlans" and sp_type != "ComputeSavingsPlans"):
        raise ValueError('Savings Plan Type unknown, check Savings Plan Type input parameter', sp_type)
    #check term
    if (term != "1yr" and term != "3yr"):
        raise ValueError('Term unknown, check Term input parameter', term)
    #check purchasing_option
    if (purchasing_option != "No Upfront" and purchasing_option != "Partial Upfront" and purchasing_option != "All Upfront"):
        raise ValueError('Purchasing Option unknown, check Purchasing Option input parameter', purchasing_option)

#  Mapping: Usage Operation Code → Pricing API OS Name (for On-Demand price queries)
operation_code_to_pricing_os = {
   
    "RunInstances": "Linux",
    "RunInstances:0002": "Windows",
    "RunInstances:0800": "Windows",
    "RunInstances:0004": "Windows",
    "RunInstances:0100": "Windows",
    "RunInstances:0200": "Windows",
    "RunInstances:0006": "Windows",
    "RunInstances:0102": "Windows",
    "RunInstances:0202": "Windows",
    "RunInstances:0010": "RHEL",
    "RunInstances:00g0": "RHEL", 
    "RunInstances:0014": "RHEL",
    "RunInstances:0110": "RHEL",
    "RunInstances:0210": "RHEL",
    "RunInstances:1010": "Red Hat Enterprise Linux with HA",
    "RunInstances:1014": "Red Hat Enterprise Linux with HA",
    "RunInstances:1110": "Red Hat Enterprise Linux with HA",
    "RunInstances:000g": "SUSE",
    "RunInstances:0g00": "Ubuntu Pro"

}
# Mapping: AWS Region Code → Region Name (used in On-Demand Pricing API)
region_name_map = {
    'us-east-1': 'US East (N. Virginia)',
    'us-east-2': 'US East (Ohio)',
    'us-west-1': 'US West (N. California)',
    'us-west-2': 'US West (Oregon)',
    'af-south-1': 'Africa (Cape Town)',
    'ap-east-1': 'Asia Pacific (Hong Kong)',
    'ap-south-1': 'Asia Pacific (Mumbai)',
    'ap-south-2': 'Asia Pacific (Hyderabad)',
    'ap-northeast-1': 'Asia Pacific (Tokyo)',
    'ap-northeast-2': 'Asia Pacific (Seoul)',
    'ap-northeast-3': 'Asia Pacific (Osaka)',
    'ap-southeast-1': 'Asia Pacific (Singapore)',
    'ap-southeast-2': 'Asia Pacific (Sydney)',
    'ap-southeast-3': 'Asia Pacific (Jakarta)',
    'ap-southeast-5': 'Asia Pacific (Malaysia)',
    'ap-southeast-7': 'Asia Pacific (Thailand)',
    'ap-east-2': 'Asia Pacific (Taipei)',
    'ca-central-1': 'Canada (Central)',
    'ca-west-1': 'Canada (Calgary)',
    'eu-central-1': 'EU (Frankfurt)',
    'eu-central-2': 'EU (Zurich)',
    'eu-west-1': 'EU (Ireland)',
    'eu-west-2': 'EU (London)',
    'eu-west-3': 'EU (Paris)',
    'eu-south-1': 'EU (Milan)',
    'eu-south-2': 'EU (Spain)',
    'eu-north-1': 'EU (Stockholm)',
    'il-central-1': 'Israel (Tel Aviv)',
    'me-central-1': 'Middle East (UAE)',
    'me-south-1': 'Middle East (Bahrain)',
    'mx-central-1': 'Mexico (Central)',
    'sa-east-1': 'South America (São Paulo)',
    'us-gov-east-1': 'AWS GovCloud (US-East)',
    'us-gov-west-1': 'AWS GovCloud (US-West)'
}

from pprint import pprint  # Add this at the top if not already

def get_on_demand_rate(region_code, usage_operation, instance_type, tenancy):
    """
    Fetches the On-Demand rate from AWS Pricing API based on region, instance type, OS, and tenancy.
    """
    location = region_name_map.get(region_code)
    if not location:
        logging.warning(f"Region '{region_code}' not mapped.")
        return 0.0

    # Build filters based on OS, tenancy, and optional SQL licensing
    def build_filters(os_friendly, usage_operation, include_operation=True):
        api_tenancy = tenancy_friendly_to_api.get(tenancy, tenancy.lower())
        filters = [
            {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
            {"Type": "TERM_MATCH", "Field": "location", "Value": location},
            {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": os_friendly},
            {"Type": "TERM_MATCH", "Field": "tenancy", "Value": api_tenancy},
            #{"Type": "TERM_MATCH", "Field": "tenancy", "Value": tenancy},
            {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
        ]
        # Optional SQL licensing filters
        preinstalled_sw_map = {
            "RunInstances:0002": "NA",  # Windows
            "RunInstances:0800": "NA",
            "RunInstances:0004": "SQL Std",
            "RunInstances:0006": "SQL Std",
            "RunInstances:0014": "SQL Std",
            "RunInstances:0100": "SQL Ent",
            "RunInstances:0102": "SQL Ent",
            "RunInstances:0110": "SQL Ent",
            "RunInstances:0200": "SQL Web",
            "RunInstances:0202": "SQL Web",
            "RunInstances:0210": "SQL Web",
            "RunInstances:0010": "NA",
            "RunInstances:1010": "NA",
            "RunInstances:1014": "SQL Std",
            "RunInstances:1110": "SQL Ent",
            "RunInstances:000g": "NA",
            "RunInstances:0g00": "NA"
        }
        pre_val = preinstalled_sw_map.get(usage_operation)
        if pre_val and pre_val != "NA":
            filters.append({"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": pre_val})
        #if include_operation:
            #filters.append({"Type": "TERM_MATCH", "Field": "operation", "Value": usage_operation})
        #return filters
            # Skip operation for Linux (RunInstances), as AWS often omits it
        if include_operation and usage_operation != "RunInstances":
            filters.append({"Type": "TERM_MATCH", "Field": "operation", "Value": usage_operation})
        return filters

    def fetch_price(os_friendly, usage_operation, include_operation=True):
        filters = build_filters(os_friendly, usage_operation, include_operation)
        try:
            # Query AWS Pricing API
            response = pricing_client.get_products(
                ServiceCode='AmazonEC2',
                Filters=filters,
                MaxResults=100
            )
            if not response['PriceList']:
                return None

            for product_json in response['PriceList']:
                product = json.loads(product_json)
                attrs = product['product']['attributes']

                if attrs.get('instanceType') != instance_type:
                    continue

                for term in product['terms']['OnDemand'].values():
                    for dim in term['priceDimensions'].values():
                        return float(dim['pricePerUnit']['USD'])
        except Exception as e:
            logging.error(f"Exception in get_on_demand_rate: {e}")
            return None
        return None

    os_friendly = operation_code_to_pricing_os.get(usage_operation)
    if not os_friendly:
        logging.warning(f"OS not mapped for usage operation: {usage_operation}")
        return 0.0

    # First attempt with operation filter
    price = fetch_price(os_friendly, usage_operation, include_operation=True)
    if price is not None:
        return price

    # Retry without operation filter (in case operation mismatches or is missing)
    price = fetch_price(os_friendly, usage_operation, include_operation=False)
    if price is not None:
        return price

    # DEBUG: Try to inspect what products AWS returns (if any)
    preinstalled_sw_map = {
        "RunInstances:0002": "NA",  # Windows
        "RunInstances:0800": "NA",
        "RunInstances:0004": "SQL Std",
        "RunInstances:0006": "SQL Std",
        "RunInstances:0014": "SQL Std",
        "RunInstances:0100": "SQL Ent",
        "RunInstances:0102": "SQL Ent",
        "RunInstances:0110": "SQL Ent",
        "RunInstances:0200": "SQL Web",
        "RunInstances:0202": "SQL Web",
        "RunInstances:0210": "SQL Web",
        "RunInstances:0010": "NA",
        "RunInstances:1010": "NA",
        "RunInstances:1014": "SQL Std",
        "RunInstances:1110": "SQL Ent",
        "RunInstances:000g": "NA",
        "RunInstances:0g00": "NA"
    }

    debug_filters = [
    {"Type": "TERM_MATCH", "Field": "location", "Value": location},
    {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
    {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": os_friendly},
]

# Only add tenancy if not Shared (some Shared prices omit it)
    if tenancy != "Shared":
        debug_filters.append({"Type": "TERM_MATCH", "Field": "tenancy", "Value": tenancy})

# Only add preInstalledSw if not NA
    pre_val = preinstalled_sw_map.get(usage_operation, "NA")
    if pre_val != "NA":
        debug_filters.append({"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": pre_val})

# Optional: add capacitystatus if no result
    debug_filters.append({"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"})


    try:
        debug_resp = pricing_client.get_products(
            ServiceCode='AmazonEC2',
            Filters=debug_filters,
            MaxResults=100
        )
        logging.debug(f"Raw AWS pricing products for {instance_type} in {region_code} (Tenancy={tenancy}, OS={os_friendly})")
        logging.debug(json.dumps(debug_resp['PriceList'], indent=2))
    except Exception as e:
        logging.error(f"Could not query debug filters: {e}")

        logging.error(f"No On-Demand price found for {instance_type} in {region_code} (usage_operation={usage_operation}) even after fallback")
    return 0.0



# import requests
# import json
# import boto3

# # Use credentials from environment 
# pricing_client = boto3.client(
#     'pricing',
#     region_name='us-east-1',
#         aws_access_key_id='ASIAWDAJEUR6TH3ZQNZ6',
#         aws_secret_access_key='WylZADJSFkfW8X3F85lAEOq3vQNeGxgCvF/oUcHB',
#         aws_session_token='IQoJb3JpZ2luX2VjELH//////////wEaCXVzLWVhc3QtMSJGMEQCIEAzsbpMrVcPjMJEqeHsplaBA++4UKS3IDGtEcsdUG8iAiA4d6TL6DnLaDdaYhbfJmpIsjdz/Dh1/Br8uJRjTFbUcyqVAwi6//////////8BEAMaDDQxODc3ODQ4OTk4MSIMtealzzIWQaf8v8lqKukCxDRp6WTWUvjbJ/nVHa1UbaSzXWfxXXxtiMZEAYsW2muXtoQgpTpjqeVuO+3YWb9QuMz8hfzuDKmjslOpvD/+r9Lpvd+DAQcvbQmQk3q/BT8btRRykQah6RKqMsGlBEzx69oNeH7OESzaAD1W1EPq3mUz8TELipoXZPix+zKfPI+rmUwMNY/icpnbWjajuXEK3ZKE09At/eFDQYYqmgFLAEsNVJcIbwgkpNN26O8RPL8AcS9owYDsIQICcVJ1rLtTa9HA7BDaqn6TitUzYKwi5j37PYUvH9nSbQy2rALWGx163vfyjNj+4T+cA9nzUPP8YgHc10/iZhJiJSGHLgsgPUJBoOb0haTdmAA92cM7YWKIudV6fxW26bj2g702P+q9czWVQUXTm4717/9fiOh9blYL8URAd9tX5QD3+vFAz/mOiY6OzEl/1cTaffXg3ihdDCrnSO6QaCj6vT2ZHPCZ/M5Zr9ZCzD0mBjCe+L3DBjqnAXT9NCM2dg3WZi2CW+0g7qMHbKkvBi+zOuflv0NGd6w7xe2twjHGPfTkJnSvLvcJXf/lufLh9vu0/caAlDa7IpWQ/FLk3PI/WNsc7t2vFE4mhxEoaDPgk775nm64avZUQ/o29+tgqKvHScPIGuAKNMOkRcLfK0saFpRhQJcnPxkN90nu66vkOs+sugHqelTtBXGSqmFa+JIOQn4dEItdBQt55QhqrIYl',
# )

# #ref. mapping https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/billing-info-fields.html
# # Mapping: Operating System name → Usage Operation Code (used in Savings Plan JSON)
# operation_by_platform_dict = {"Linux/UNIX": "RunInstances",
#                               "Red Hat BYOL Linux": "RunInstances:00g0",
#                               "Red Hat Enterprise Linux": "RunInstances:0010",
#                               "Red Hat Enterprise Linux with HA": "RunInstances:1010",
#                               "Red Hat Enterprise Linux with SQL Server Standard and HA": "RunInstances:1014",
#                               "Red Hat Enterprise Linux with SQL Server Enterprise and HA": "RunInstances:1110",
#                               "Red Hat Enterprise Linux with SQL Server Standard": "RunInstances:0014",
#                               "Red Hat Enterprise Linux with SQL Server Web": "RunInstances:0210",
#                               "Red Hat Enterprise Linux with SQL Server Enterprise": "RunInstances:0110",
#                               "SQL Server Enterprise": "RunInstances:0100",
#                               "SQL Server Standard": "RunInstances:0004",
#                               "SQL Server Web": "RunInstances:0200",
#                               "SUSE Linux": "RunInstances:000g",
#                               "Ubuntu Pro": "RunInstances:0g00",
#                               "Windows": "RunInstances:0002",
#                               "Windows BYOL": "RunInstances:0800",
#                               "Windows with SQL Server Enterprise": "RunInstances:0102",
#                               "Windows with SQL Server Standard": "RunInstances:0006",
#                               "Windows with SQL Server Web": "RunInstances:0202"}

# #tenancy dictionary
# #ref. https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/describe_instances.html
# tenancy_dict = {"default":"Shared",
#                 "dedicated":"Dedicated Instance",
#                 "host":"Dedicated Host"}


# #Load region index for Savings Plan pricing
# region_price = {};
# region_price_index_api_url = "https://pricing.us-east-1.amazonaws.com/savingsPlan/v1.0/aws/AWSComputeSavingsPlan/current/region_index.json"
# response_region_price_index = requests.get(region_price_index_api_url, timeout=20)
# region_price_index = response_region_price_index.json()['regions']

# # get pricing by region
# def get_pricing_by_region(region_code):
#     if (region_code not in region_price): #check if region pricing is already loaded
#         for region in region_price_index:
#             if (region['regionCode'] == region_code):
#                 region_price_api_url = "https://pricing.us-east-1.amazonaws.com" + region['versionUrl']
#                 region_price_response = requests.get(region_price_api_url, timeout=20)
#                 #save pricing by region
#                 region_price[region_code] = region_price_response.json()
#                 break
#     return region_price[region_code]


# def get_savings_plan_rate(region_code, usage_operation, instance_family, instance_type, tenancy, sp_type, term, purchasing_option):
#     region_price = get_pricing_by_region(region_code)
#     sku = ''
#     sp_rate = None
#     products = region_price['products']
#     # find correct SKU in the json response
#     for product in products:
#         if (product['attributes']['purchaseOption'] == purchasing_option and
#             product['attributes']['purchaseTerm'] == term and
#             product['productFamily'] == sp_type and
#             (sp_type == "ComputeSavingsPlans" or product['attributes']['instanceType'] == instance_family)):
#             sku = product['sku']

#     # find savings plan rate in the json response given the SKU
#     terms = region_price['terms']['savingsPlan']
#     for term in terms:
#         if (term['sku'] == sku):
#             rates = term['rates']
#             for rate in rates:
#                 if (usage_operation == rate['discountedOperation']):
#                     #tenancy SHARED                     
#                     if (tenancy == 'Shared'):
#                         if (rate['discountedUsageType'].endswith("-BoxUsage:" + instance_type)):
#                             sp_rate = float(rate['discountedRate']['price'])
#                             break
#                         #handle us-east-1 BoxUsage:<instance_type> others <region-code>-BoxUsage:<instance_type>
#                         elif (region_code == 'us-east-1' and rate['discountedUsageType'] == "BoxUsage:" + instance_type):
#                             sp_rate = float(rate['discountedRate']['price'])
#                             break
#                     #tenancy DEDICATED INSTANCE
#                     elif (tenancy == 'Dedicated Instance' and rate['discountedUsageType'].endswith("DedicatedUsage:" + instance_type)):
#                         sp_rate = float(rate['discountedRate']['price'])
#                         break
#                     #tenancy DEDICATED HOST
#                     elif (tenancy == 'Dedicated Host' and rate['discountedUsageType'].endswith("HostUsage:" + instance_family)):
#                         sp_rate = float(rate['discountedRate']['price'])
#                         break
#             break

#     # handle rate not found
#     if (sp_rate is None):
#         raise ValueError('Rate not found', sku)

#     return sp_rate

# # Validates input parameters to avoid runtime failures
    
# def check_input_parameters(usage_operation, tenancy, sp_type, term, purchasing_option):
#     #check usage_operation
#     if (usage_operation not in operation_by_platform_dict.values()):
#         raise ValueError('Usage operation unknown, check the Operating System input parameter', usage_operation)
#     #check tenancy
#     if (tenancy not in tenancy_dict.values()):
#         raise ValueError('Tenancy unknown, check Tenancy input parameter', tenancy)
#     #check sp_type
#     if (sp_type != "EC2InstanceSavingsPlans" and sp_type != "ComputeSavingsPlans"):
#         raise ValueError('Savings Plan Type unknown, check Savings Plan Type input parameter', sp_type)
#     #check term
#     if (term != "1yr" and term != "3yr"):
#         raise ValueError('Term unknown, check Term input parameter', term)
#     #check purchasing_option
#     if (purchasing_option != "No Upfront" and purchasing_option != "Partial Upfront" and purchasing_option != "All Upfront"):
#         raise ValueError('Purchasing Option unknown, check Purchasing Option input parameter', purchasing_option)

# #  Mapping: Usage Operation Code → Pricing API OS Name (for On-Demand price queries)
# operation_code_to_pricing_os = {
   
#     "RunInstances": "Linux",
#     "RunInstances:0002": "Windows",
#     "RunInstances:0800": "Windows",
#     "RunInstances:0004": "Windows",
#     "RunInstances:0100": "Windows",
#     "RunInstances:0200": "Windows",
#     "RunInstances:0006": "Windows",
#     "RunInstances:0102": "Windows",
#     "RunInstances:0202": "Windows",
#     "RunInstances:0010": "RHEL",
#     "RunInstances:00g0": "RHEL", 
#     "RunInstances:0014": "RHEL",
#     "RunInstances:0110": "RHEL",
#     "RunInstances:0210": "RHEL",
#     "RunInstances:1010": "Red Hat Enterprise Linux with HA",
#     "RunInstances:1014": "Red Hat Enterprise Linux with HA",
#     "RunInstances:1110": "Red Hat Enterprise Linux with HA",
#     "RunInstances:000g": "SUSE",
#     "RunInstances:0g00": "Ubuntu Pro"

# }
# # Mapping: AWS Region Code → Region Name (used in On-Demand Pricing API)
# region_name_map = {
#     'us-east-1': 'US East (N. Virginia)',
#     'us-east-2': 'US East (Ohio)',
#     'us-west-1': 'US West (N. California)',
#     'us-west-2': 'US West (Oregon)',
#     'af-south-1': 'Africa (Cape Town)',
#     'ap-east-1': 'Asia Pacific (Hong Kong)',
#     'ap-south-1': 'Asia Pacific (Mumbai)',
#     'ap-south-2': 'Asia Pacific (Hyderabad)',
#     'ap-northeast-1': 'Asia Pacific (Tokyo)',
#     'ap-northeast-2': 'Asia Pacific (Seoul)',
#     'ap-northeast-3': 'Asia Pacific (Osaka)',
#     'ap-southeast-1': 'Asia Pacific (Singapore)',
#     'ap-southeast-2': 'Asia Pacific (Sydney)',
#     'ap-southeast-3': 'Asia Pacific (Jakarta)',
#     'ap-southeast-5': 'Asia Pacific (Malaysia)',
#     'ap-southeast-7': 'Asia Pacific (Thailand)',
#     'ap-east-2': 'Asia Pacific (Taipei)',
#     'ca-central-1': 'Canada (Central)',
#     'ca-west-1': 'Canada (Calgary)',
#     'eu-central-1': 'Europe (Frankfurt)',
#     'eu-central-2': 'Europe (Zurich)',
#     'eu-west-1': 'Europe (Ireland)',
#     'eu-west-2': 'Europe (London)',
#     'eu-west-3': 'Europe (Paris)',
#     'eu-south-1': 'Europe (Milan)',
#     'eu-south-2': 'Europe (Spain)',
#     'eu-north-1': 'Europe (Stockholm)',
#     'il-central-1': 'Israel (Tel Aviv)',
#     'me-central-1': 'Middle East (UAE)',
#     'me-south-1': 'Middle East (Bahrain)',
#     'mx-central-1': 'Mexico (Central)',
#     'sa-east-1': 'South America (São Paulo)',
#     'us-gov-east-1': 'AWS GovCloud (US-East)',
#     'us-gov-west-1': 'AWS GovCloud (US-West)'
# }

# def get_on_demand_rate(region_code, usage_operation, instance_type, tenancy):
#     """
#     Fetches the On-Demand rate from AWS Pricing API based on region, instance type, OS, and tenancy.
#     """
#     location = region_name_map.get(region_code)
#     if not location:
#         print(f"[WARN] Region '{region_code}' not mapped.")
#         return 0.0
#     # Build filters based on OS, tenancy, and optional SQL licensing
#     def build_filters(os_friendly, usage_operation, include_operation=True):
#         filters = [
#             {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
#             {"Type": "TERM_MATCH", "Field": "location", "Value": location},
#             {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": os_friendly},
#             {"Type": "TERM_MATCH", "Field": "tenancy", "Value": tenancy},
#             {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
#         ]
#         # Optional SQL licensing filters
#         preinstalled_sw_map = {
#             "RunInstances:0002": "NA",  # Windows
#             "RunInstances:0800": "NA",
#             "RunInstances:0004": "SQL Std",
#             "RunInstances:0006": "SQL Std",
#             "RunInstances:0014": "SQL Std",
#             "RunInstances:0100": "SQL Ent",
#             "RunInstances:0102": "SQL Ent",
#             "RunInstances:0110": "SQL Ent",
#             "RunInstances:0200": "SQL Web",
#             "RunInstances:0202": "SQL Web",
#             "RunInstances:0210": "SQL Web",
#             "RunInstances:0010": "NA",
#             "RunInstances:1010": "NA",
#             "RunInstances:1014": "SQL Std",
#             "RunInstances:1110": "SQL Ent",
#             "RunInstances:000g": "NA",
#             "RunInstances:0g00": "NA"
#         }
#         pre_val = preinstalled_sw_map.get(usage_operation)
#         if pre_val and pre_val != "NA":
#             filters.append({"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": pre_val})
#         if include_operation:
#             filters.append({"Type": "TERM_MATCH", "Field": "operation", "Value": usage_operation})
#         return filters

#     def fetch_price(os_friendly, usage_operation, include_operation=True):
#         filters = build_filters(os_friendly, usage_operation, include_operation)
#         try:
#             # Query AWS Pricing API
#             response = pricing_client.get_products(
#                 ServiceCode='AmazonEC2',
#                 Filters=filters,
#                 MaxResults=100
#             )
#             if not response['PriceList']:
#                 return None

#             for product_json in response['PriceList']:
#                 product = json.loads(product_json)
#                 attrs = product['product']['attributes']

#                 if attrs.get('instanceType') != instance_type:
#                     continue

#                 for term in product['terms']['OnDemand'].values():
#                     for dim in term['priceDimensions'].values():
#                         return float(dim['pricePerUnit']['USD'])
#         except Exception as e:
#             print(f"[ERROR] Exception in get_on_demand_rate: {e}")
#             return None
#         return None
    
#     os_friendly = operation_code_to_pricing_os.get(usage_operation)
#     if not os_friendly:
#         print(f"[WARN] OS not mapped for usage operation: {usage_operation}")
#         return 0.0

#     price = fetch_price(os_friendly, usage_operation, include_operation=True)
#     if price is not None:
#         return price

#     print(f"[ERROR] No On-Demand price found for {instance_type} in {region_code} with usage_operation={usage_operation}")
#     return 0.0