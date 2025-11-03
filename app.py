import os
import pandas as pd
from dash import Dash, html, dcc, Input, Output
import plotly.express as px

# ✅ 1. Put this near the top, right after your imports
BASE_DIR  = r"C:\Users\17745\OneDrive\Desktop\Brain juice\New folder"
CSV_PATH  = os.path.join(BASE_DIR, "merged_sku_image_sales.csv")
MAP_PATH  = os.path.join(BASE_DIR, "drive_map.csv")

# ✅ 2. Load your main CSV
df = pd.read_csv(CSV_PATH)

# ✅ 3. Add this to merge with drive_map.csv (image links)
if os.path.exists(MAP_PATH):
    drive_map = pd.read_csv(MAP_PATH)[["images", "drive_id"]]
    df = df.merge(drive_map, on="images", how="left")
else:
    df["drive_id"] = None

# ✅ 4. Add this helper function (below the merge)
def image_url(row):
    did = row.get("drive_id")
    if pd.notna(did) and str(did).strip():
        return f"https://drive.google.com/uc?export=view&id={did}"
    # fallback if not found
    return f"/images/{row['images']}" if os.path.exists(os.path.join(BASE_DIR, "images", str(row['images']))) else None

df["img_url"] = df.apply(image_url, axis=1)

# ✅ 5. Continue with your Dash layout and callbacks as before
app = Dash(__name__)

app.layout = html.Div([
    html.H1("商品销售可视化 Dashboard"),
    dcc.Dropdown(
        id='sku-dropdown',
        options=[{'label': sku, 'value': sku} for sku in df["SKU"].unique()],
        value=df["SKU"].iloc[0]
    ),
    html.Div(id='product-info'),
    dcc.Graph(id='sales-pie')
])

@app.callback(
    [Output('product-info', 'children'),
     Output('sales-pie', 'figure')],
    Input('sku-dropdown', 'value')
)
def update_display(sku):
    r = df[df["SKU"] == sku].iloc[0]
    img = html.Img(src=r["img_url"], style={"height": "300px"}) if r["img_url"] else html.P("No image available.")
    fig = px.pie(df, values="Total Net Sales", names="SKU", title="销售占比前十商品").update_traces(textinfo='percent+label')
    return html.Div([
        html.H3(f"SKU：{r['SKU']}"),
        img,
        html.P(f"销量（Total Count）：{r['Total Count']}"),
        html.P(f"收入（Total Net Sales）：${r['Total Net Sales']}"),
    ]), fig

if __name__ == "__main__":
    app.run(debug=True, port=8051)

    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
