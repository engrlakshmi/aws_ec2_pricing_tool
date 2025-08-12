
AWS EC2 Pricing Tool and Recommendation System
This Streamlit-based web app lets you compare AWS EC2 pricing options across:

💰 General Compute & EC2 Savings Plans

📊 On-Demand & Reserved Instances

It provides flexible filtering, real-time AWS Pricing API queries, CSV downloads, and instance recommendations based on workload requirements.

🚀 Features
Dynamic UI – Instantly switch between Savings Plan and On-Demand filters with a single click.


Multi-filter Search – Filter by region, instance type, family, OS, term, tenancy, purchase option, etc.

Savings Plan vs. On-Demand Comparison

Paginated Results – Smooth navigation through large datasets

Downloadable CSV Output

Responsive UI – Examples provided for each input

💡 Recommendation System – Suggests the best EC2 instance types and pricing models for your workload.

🧩 Tech Stack
Component	Tech
UI Framework	Streamlit
Cloud Pricing	AWS Pricing API (via boto3)
Data Processing	Python, Pandas
Export Formats	CSV

📦 Setup Instructions
1. Clone this repo
bash
Copy
Edit
git clone <repo-link>
cd aws_ec2_pricing_tool
2. Install dependencies
bash
Copy
Edit
pip install -r requirements.txt
3. Configure AWS credentials
Make sure your AWS CLI is configured with valid credentials:

bash
Copy
Edit
aws configure
4. Run the app
bash
Copy
Edit
streamlit run app.py
Important: After the app loads in your browser, refresh the page once before using the radio buttons to ensure correct functionality.

📜 Usage Notes
Requires AWS credentials with access to the Pricing API

Works for all public AWS regions

Supports both 1-year and 3-year term comparisons

CSV export includes both pricing models for offline analysis

🔮 Recommendation System
The built-in Recommendation System analyzes your workload requirements and suggests the most cost-effective EC2 configuration.

How it works:

Input your workload specs – vCPU, memory, OS, region, expected usage duration, and burst requirements.

Candidate filtering – Filters EC2 instances matching your technical needs.

Cost evaluation – Compares On-Demand, Savings Plans, and Reserved Instances to find the cheapest suitable option.

Top recommendations – 

Displays the top 3 instances with:

1. Instance type

2. vCPU & RAM

3. Hourly cost (On-Demand & SP)

4. Recommended pricing model

5. Estimated monthly cost

