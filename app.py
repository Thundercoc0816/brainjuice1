import os, glob
import pandas as pd
from dash import Dash, html, dcc, Input, Output, dash_table
import plotly.express as px
from flask import send_from_directory

# ---------- PATHS (relative to this file) ----------
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CSV_PATH   = os.path.join(BASE_DIR, "merged_sku_image_sales.csv")
MAP_PATH   = os.path.join(BASE_DIR, "drive_map.csv")    # images ↔ drive_id map
IMAGES_DIR = os.path.join(BASE_DIR, "images")           # optional local fallback

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

# Require main data
_require(CSV_PATH, "merged_sku_image_sales.csv")

# ---------- LOAD & CLEAN DATA ----------
df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")

# Normalize column names you rely on (keep originals otherwise)
# Expecting: SKU, images, Total Count, Total Net Sales
if "SKU" not in df.columns or "images" not in df.columns:
    raise ValueError(f"[STARTUP] CSV must include columns 'SKU' and 'images'. Found: {list(df.columns)}")

# Clean revenue/count columns robustly
def _clean_money(s):
    s = str(s)
    s = s.replace(",", "")
    return "".join(ch for ch in s if (ch.isdigit() or ch in ".-"))

df["Total Net Sales"] = pd.to_numeric(
    df["Total Net Sales"].astype(str).map(_clean_money),
    errors="coerce"
).fillna(0.0)

df["Total Count"] = pd.to_numeric(df["Total Count"], errors="coerce").fillna(0)

# Merge drive map (case/space tolerant)
if os.path.exists(MAP_PATH):
    dm = pd.read_csv(MAP_PATH, encoding="utf-8-sig")
    if not {"images", "drive_id"}.issubset(dm.columns):
        print("[BOOT][WARN] drive_map.csv missing columns: images, drive_id (skipping merge)")
        df["drive_id"] = None
    else:
        dm["images_lc"] = dm["images"].astype(str).str.strip().str.lower()
        df["images_lc"] = df["images"].astype(str).str.strip().str.lower()
        df = df.merge(dm[["images_lc", "drive_id"]], on="images_lc", how="left")
else:
    df["drive_id"] = None

# ---------- IMAGE URL HELPERS ----------
def find_local_image(images_dir, name):
    if not images_dir or not name:
        return None
    base, ext = os.path.splitext(str(name))
    candidates = []
    if ext:
        candidates += [base + ".*", base.lower() + ".*", base.upper() + ".*"]
    else:
        for e in [".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"]:
            candidates += [base + e, base.lower() + e, base.upper() + e]
    for pat in candidates:
        matches = glob.glob(os.path.join(images_dir, pat))
        if matches:
            return os.path.basename(matches[0])
    return None

def image_url_from_row(row):
    did = row.get("drive_id")
    if pd.notna(did) and str(did).strip():
        return f"https://drive.google.com/uc?export=view&id={did}"
    # fallback: if images column already contains a URL
    imgname = str(row.get("images") or "").strip()
    if imgname.startswith("http://") or imgname.startswith("https://"):
        return imgname
    # fallback: local file
    local = find_local_image(IMAGES_DIR, imgname)
    if local:
        return f"/img/{local}"
    return None

# Precompute totals
total_units = int(df["Total Count"].sum())
total_revenue = float(df["Total Net Sales"].sum())

# ---------- DASH APP ----------
app = Dash(__name__)
server = app.server  # <-- expose Flask server for Gunicorn/Render

# Static route for local images (fallback)
@server.route("/img/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_DIR, filename)

app.layout = html.Div([
    html.H1("Product Sales Overview", style={"textAlign": "center", "marginBottom": "6px"}),

    html.Div([
        html.H3(f"Total Units Sold: {total_units:,}", style={"marginRight": "20px"}),
        html.H3(f"Total Revenue: ${total_revenue:,.2f}")
    ], style={"display": "flex", "justifyContent": "center", "gap": "20px"}),

    html.Div([
        dcc.RadioItems(
            id="metric",
            options=[{"label": "By Units", "value": "Total Count"},
                     {"label": "By Revenue", "value": "Total Net Sales"}],
            value="Total Count",
            labelStyle={"marginRight": "16px"}
        )
    ], style={"textAlign": "center", "marginBottom": "8px"}),

    html.Div([
        html.Div([dcc.Graph(id="pie-chart")], style={"flex": "2", "minWidth": "600px"}),
        html.Div([
            html.H3("All Data (Excel-style)"),
            dash_table.DataTable(
                id="all-table",
                columns=[
                    {"name": "SKU", "id": "SKU"},
                    {"name": "Units (Total Count)", "id": "Total Count", "type": "numeric"},
                    {"name": "Revenue (Total Net Sales)", "id": "Total Net Sales", "type": "numeric"},
                    {"name": "Image (filename/URL)", "id": "images"},
                ],
                data=df.sort_values("Total Count", ascending=False)[
                    ["SKU", "Total Count", "Total Net Sales", "images"]
                ].to_dict("records"),
                page_size=15,
                sort_action="native",
                filter_action="native",
                style_table={"overflowX": "auto", "maxHeight": "80vh", "overflowY": "auto"},
                style_cell={"padding": "6px", "textAlign": "center"},
                style_header={"fontWeight": "bold", "backgroundColor": "#f2f2f2"},
            ),
            html.Button("Download All Data (CSV)", id="btn-download", n_clicks=0, style={"marginTop": "10px"}),
            dcc.Download(id="download-all")
        ], style={"flex": "1", "minWidth": "360px", "paddingLeft": "16px"})
    ], style={"display": "flex", "gap": "10px"}),

    html.Hr(),

    html.Div([
        html.H3("Select SKU for details:"),
        dcc.Dropdown(
            id="sku",
            options=[{"label": str(s), "value": str(s)} for s in df["SKU"]],
            placeholder="Select SKU",
            style={"width": "320px"}
        ),
        html.Div(id="detail", style={"marginTop": "14px"})
    ], style={"textAlign": "center"}),

], style={"maxWidth": "1500px", "margin": "0 auto", "padding": "10px"})

# ---------- CALLBACKS ----------
@app.callback(
    Output("pie-chart", "figure"),
    Input("metric", "value")
)
def make_pie(metric):
    d = df.sort_values(metric, ascending=False).reset_index(drop=True)
    top_n = 10
    top = d.head(top_n).copy()
    others = d.iloc[top_n:].copy()

    if not others.empty:
        other_row = pd.DataFrame({
            "SKU": ["Other"],
            "Total Count": [others["Total Count"].sum()],
            "Total Net Sales": [others["Total Net Sales"].sum()]
        })
        pie_df = pd.concat([top, other_row], ignore_index=True)
    else:
        pie_df = top

    title = "Top 10 + Others (Units)" if metric == "Total Count" else "Top 10 + Others (Revenue)"
    fig = px.pie(pie_df, values=metric, names="SKU", title=title, hole=0.25)
    fig.update_traces(textinfo="label+percent", textfont_size=14,
                      hovertemplate="SKU=%{label}<br>%{value:,.2f}")
    fig.update_layout(height=820, margin=dict(l=30, r=30, t=60, b=30), showlegend=True)
    return fig

@app.callback(
    Output("download-all", "data"),
    Input("btn-download", "n_clicks"),
    prevent_initial_call=True
)
def download_all(n):
    out = df[["SKU", "Total Count", "Total Net Sales", "images"]].copy()
    return dcc.send_data_frame(out.to_csv, "all_data.csv", index=False)

@app.callback(
    Output("detail", "children"),
    Input("sku", "value")
)
def show_detail(sku):
    if not sku:
        return html.Div("Select a SKU.")
    row = df[df["SKU"].astype(str) == str(sku)]
    if row.empty:
        return html.Div("Not found.")

    r = row.iloc[0]
    url = image_url_from_row(r)
    img = html.Img(
        src=url, style={"width": "220px", "border": "1px solid #ccc", "borderRadius": "8px", "padding": "4px"}
    ) if url else html.Div("Image not found")

    return html.Div([
        html.H4(f"SKU: {r['SKU']}"),
        img,
        html.P(f"Units (Total Count): {int(r['Total Count'])}", style={"fontWeight": "bold"}),
        html.P(f"Revenue (Total Net Sales): ${float(r['Total Net Sales']):,.2f}", style={"fontWeight": "bold"})
    ])

# ---------- RUN (local & cloud) ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
