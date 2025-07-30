
# AWS EC2 Pricing Tool

This Streamlit-based web app allows users to **compare AWS EC2 pricing options** across:
- 💰 **General Compute and EC2 Savings Plans**
- 📊 **On-Demand & Reserved Instances**

It provides flexible filtering, real-time data fetching via AWS Pricing APIs, and supports CSV download for further analysis.

---

## 🚀 Features

- **Dynamic UI**: Switch between Savings Plan and On-Demand pricing filters with a single click.
- **Multi-filter Search**: Filter by region, instance type, family, OS, term, tenancy, purchase option, etc.
- **Savings Plan vs On-Demand Comparison**
- **Paginated Results** for large datasets
- **Downloadable CSV output**
- **Responsive UI** with helpful examples for each input

---

## 🧩 Tech Stack

| Component        | Tech                               |
|------------------|-------------------------------------|
| UI Framework     | [Streamlit](https://streamlit.io)   |
| Cloud Pricing    | AWS Pricing API (via `boto3`)       |
| Data Processing  | Python, Pandas                      |
| Export Formats   | CSV                                 |

---

## 📦 Setup Instructions

### 1. Clone this repo

```bash
git clone link

Once you run the code refresh first and then use radio buttons. modify this
