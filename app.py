import os, glob
import pandas as pd
from dash import Dash, html, dcc, Input, Output, dash_table
import plotly.express as px
from flask import send_from_directory

# ---------- PATHS (relative to this file) ----------
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))  # /opt/render/project/src in Render
CSV_PATH  = os.path.join(BASE_DIR, "merged_sku_image_sales.csv")
MAP_PATH  = os.path.join(BASE_DIR, "drive_map.csv")
IMAGES_DIR = os.path.join(BASE_DIR, "images")  # optional local fallback; can be absent

print("[BOOT] BASE_DIR:", BASE_DIR)
print("[BOOT] Files in BASE_DIR:", sorted(os.listdir(BASE_DIR)))
print("[BOOT] CSV exists?", os.path.exists(CSV_PATH), "->", CSV_PATH)
print("[BOOT] MAP exists?", os.path.exists(MAP_PATH), "->", MAP_PATH)

def _require(path: str, label: str):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"[STARTUP] Missing {label} at {path}\n"
            f"Contents of BASE_DIR ({BASE_DIR}):\n  " + "\n  ".join(sorted(os.listdir(BASE_DIR)))
        )

# Require the main CSV; drive_map is optional
_require(CSV_PATH, "merged_sku_image_sales.csv")

# ---------- LOAD DATA ----------
# robust CSV read (handles BOM and stray $/commas later)
df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")

# Drive map (optional)
if os.path.exists(MAP_PATH):
    dm = pd.read_csv(MAP_PATH, encoding="utf-8-sig")
    if {"images", "drive_id"}.issubset(dm.columns):
        dm["images"] = dm["images"].astype(str).str.strip()
        df["images"] = df["images"].astype(str).str.strip()
        df = df.merge(dm[["images", "drive_id"]], on="images", how="left")
    else:
        print("[BOOT][WARN] drive_map.csv missing required columns: images, drive_id")
else:
    df["drive_id"] = None



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
    import os
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)



