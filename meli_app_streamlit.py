import os
import requests
import json
import pandas as pd
import streamlit as st

from datetime import datetime, timedelta
from collections import defaultdict
from google.cloud import storage
from google.oauth2 import service_account

# Import MeLi JSON from Cloud Storage
credentials = service_account.Credentials.from_service_account_file(os.environ['SERVICE_ACCOUNT_CREDENTIALS'])

client = storage.Client(credentials = credentials)
bucket_name = 'meli_auth_file'
file_name = 'meli_access.json'

# Get the bucket and the blob (file)
bucket = client.bucket(bucket_name)
blob = bucket.blob(file_name)

# Download the JSON file
meli_access = json.loads(blob.download_as_string())

# Get access token
access_token = meli_access['access_token']

# Import catalog file
path = 'https://raw.githubusercontent.com/francocibils/supermetrics_update/main/amazon_sku_listado.xlsx'
catalog = pd.read_excel(path, engine = 'openpyxl')

catalog['MLM'] = catalog['MLM'].str.rstrip()
catalog['MLM2'] = catalog['MLM2'].str.rstrip()

# Define codes dataframe
codes_df = pd.DataFrame(data = catalog[['MLM', 'MLM2']].values, index = catalog['Universal code'], columns = ['MLM', 'MLM2'])

# Streamlit
st.title('Mercado Libre - Visits by brand')
st.markdown('Get the visits from a specified date range for all brands included in the catalog for Mercado Libre marketplace.')

st.header('Visits')

from_date = st.date_input(label = 'Insert starting date').strftime("%Y-%m-%d")
to_date = st.date_input(label = 'Insert ending date').strftime("%Y-%m-%d")

if st.button('Get visits'):
    from_date_dt = datetime.strptime(from_date, '%Y-%m-%d')
    to_date_dt = datetime.strptime(to_date, '%Y-%m-%d')

    days_diff = (to_date_dt - from_date_dt).days
    to_date_meli = (to_date_dt + timedelta(days = 1)).strftime('%Y-%m-%d')

    # Extract visits
    item_visits_by_code = {}

    for code in codes_df.index:
        
        item_dict =  dict(codes_df.loc[code])
        item_visits = {}

        for item in item_dict.values():
            if item == 'No code':
                item_visits[item] = None
            else:
                url = f"https://api.mercadolibre.com/items/{item}/visits/time_window"

                headers = {
                    'Authorization': f'Bearer {access_token}'
                }

                params = {
                    'last': 2 + days_diff,
                    'unit': 'day',
                    'ending': to_date_meli
                }

                item_response = requests.get(url, headers = headers, params = params)
                results_data = item_response.json()['results']

                filtered_totals = [
                    {'date': datetime.strptime(entry['date'], '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d'), 'total': entry['total']}
                    for entry in results_data
                    if from_date_dt <= datetime.strptime(entry['date'], '%Y-%m-%dT%H:%M:%SZ') <= to_date_dt
                ]

                item_visits[item] = filtered_totals

        item_visits_by_code[code] = item_visits

    # Create visits dataframe
    aggregated_totals = defaultdict(lambda: defaultdict(int))

    # Populate the defaultdict with aggregated totals
    for key, subdict in item_visits_by_code.items():
        for inner_key, records in subdict.items():
            if records is not None:
                for record in records:
                    date = record['date']
                    total = record['total']
                    aggregated_totals[key][date] += total

    # Convert defaultdict to a regular dictionary for DataFrame construction
    aggregated_totals = {key: dict(values) for key, values in aggregated_totals.items()}

    # Convert aggregated_totals to a DataFrame
    df = pd.DataFrame.from_dict(aggregated_totals, orient = 'index')
    df = df.reindex(sorted(df.columns), axis = 1)
    df.index.name = 'Universal code'
    df.columns = 'Visits - ' + df.columns

    # Create dataframe with visits and grouped by product dataframe with visits
    full_df = pd.merge(catalog, df, on = 'Universal code', how = 'inner')
    summary_df = full_df.groupby('Family').sum()[[i for i in full_df.columns if 'Visits' in i]]

    keep_rows = ['Aeroski', 'Eagle eyes', 'Green Marvel', 'Rotaflex', 'Skoon', 'Terracoat', 'Xshock', 'Xtender', 'Zamba']
    summary_df = summary_df.loc[keep_rows]

    st.subheader(f'Visits for all brands from {from_date} to {to_date} by day.')
    st.dataframe(summary_df)
