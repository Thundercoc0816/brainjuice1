import os, glob
import pandas as pd
from dash import Dash, html, dcc, Input, Output, dash_table
import plotly.express as px
from flask import send_from_directory

# ---------- 路径设置 ----------
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CSV_PATH   = os.path.join(BASE_DIR, "merged_sku_image_sales.csv")
MAP_PATH   = os.path.join(BASE_DIR, "drive_map.csv")
IMAGES_DIR = os.path.join(BASE_DIR, "images")

print("[启动] BASE_DIR:", BASE_DIR)
print("[启动] 文件:", sorted(os.listdir(BASE_DIR)))
print("[启动] CSV存在?", os.path.exists(CSV_PATH), "->", CSV_PATH)
print("[启动] MAP存在?", os.path.exists(MAP_PATH), "->", MAP_PATH)

def _require(path: str, label: str):
    if not os.path.exists(path):
        raise FileNotFoundError(f"[启动错误] 缺少 {label} 文件: {path}")

_require(CSV_PATH, "merged_sku_image_sales.csv")

# ---------- 加载数据 ----------
df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")

def _clean_money(s):
    s = str(s).replace(",", "")
    return "".join(ch for ch in s if (ch.isdigit() or ch in ".-"))

df["Total Net Sales"] = pd.to_numeric(df["Total Net Sales"].astype(str).map(_clean_money), errors="coerce").fillna(0.0)
df["Total Count"] = pd.to_numeric(df["Total Count"], errors="coerce").fillna(0)

# ---------- 合并 Drive 映射 ----------
if os.path.exists(MAP_PATH):
    dm = pd.read_csv(MAP_PATH, encoding="utf-8-sig")
    if {"images","drive_id"}.issubset(dm.columns):
        dm["images_lc"] = dm["images"].astype(str).str.strip().str.lower()
        df["images_lc"] = df["images"].astype(str).str.strip().str.lower()
        df = df.merge(dm[["images_lc","drive_id"]], on="images_lc", how="left")
    else:
        df["drive_id"] = None
else:
    df["drive_id"] = None

# ---------- 图片路径 ----------
def find_local_image(images_dir, name):
    if not images_dir or not name:
        return None
    base, ext = os.path.splitext(str(name))
    candidates = []
    if ext:
        candidates += [base + ".*", base.lower() + ".*", base.upper() + ".*"]
    else:
        for e in [".jpg",".jpeg",".png",".JPG",".JPEG",".PNG"]:
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
    imgname = str(row.get("images") or "").strip()
    if imgname.startswith("http://") or imgname.startswith("https://"):
        return imgname
    local = find_local_image(IMAGES_DIR, imgname)
    if local:
        return f"/img/{local}"
    return None

total_units = int(df["Total Count"].sum())
total_revenue = float(df["Total Net Sales"].sum())

# ---------- Dash 应用 ----------
app = Dash(__name__)
server = app.server  # Render用

@server.route("/img/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_DIR, filename)

app.layout = html.Div([
    html.H1("商品销售可视化系统", style={"textAlign": "center"}),

    html.Div([
        html.H3(f"总销售数量：{total_units:,}", style={"marginRight": "20px"}),
        html.H3(f"总销售额：${total_revenue:,.2f}")
    ], style={"display": "flex", "justifyContent": "center", "gap": "20px"}),

    html.Div([
        dcc.RadioItems(
            id="metric",
            options=[{"label": "按数量", "value": "Total Count"},
                     {"label": "按销售额", "value": "Total Net Sales"}],
            value="Total Count",
            labelStyle={"marginRight": "16px"}
        )
    ], style={"textAlign": "center"}),

    html.Div([
        html.Div([dcc.Graph(id="pie-chart")], style={"flex": "2"}),
        html.Div([
            html.H3("全部数据表（类似Excel）"),
            dash_table.DataTable(
                id="all-table",
                columns=[
                    {"name": "SKU", "id": "SKU"},
                    {"name": "销售数量", "id": "Total Count", "type": "numeric"},
                    {"name": "销售额", "id": "Total Net Sales", "type": "numeric"},
                    {"name": "图片名/链接", "id": "images"},
                ],
                data=df.sort_values("Total Count", ascending=False)[
                    ["SKU", "Total Count", "Total Net Sales", "images"]
                ].to_dict("records"),
                page_size=15,
                sort_action="native",
                filter_action="native",
                style_table={"overflowX": "auto", "maxHeight": "80vh"},
                style_cell={"padding": "6px", "textAlign": "center"},
                style_header={"fontWeight": "bold", "backgroundColor": "#f2f2f2"},
            ),
            html.Button("下载所有数据 (CSV)", id="btn-download", n_clicks=0, style={"marginTop": "10px"}),
            dcc.Download(id="download-all")
        ], style={"flex": "1", "paddingLeft": "16px"})
    ], style={"display": "flex", "gap": "10px"}),

    html.Hr(),

    html.Div([
        html.H3("选择SKU查看详情："),
        dcc.Dropdown(
            id="sku",
            options=[{"label": str(s), "value": str(s)} for s in df["SKU"]],
            placeholder="选择SKU",
            style={"width": "320px"}
        ),
        html.Div(id="detail", style={"marginTop": "14px"})
    ], style={"textAlign": "center"}),
])

# ---------- 回调 ----------
@app.callback(
    Output("pie-chart", "figure"),
    Input("metric", "value")
)
def make_pie(metric):
    d = df.sort_values(metric, ascending=False)
    top = d.head(10)
    others = d.iloc[10:]
    if not others.empty:
        other_row = pd.DataFrame({"SKU": ["其他"], "Total Count": [others["Total Count"].sum()], "Total Net Sales": [others["Total Net Sales"].sum()]})
        pie_df = pd.concat([top, other_row], ignore_index=True)
    else:
        pie_df = top
    title = "前10商品 + 其他（按数量）" if metric == "Total Count" else "前10商品 + 其他（按销售额）"
    fig = px.pie(pie_df, values=metric, names="SKU", title=title, hole=0.25)
    fig.update_traces(textinfo="label+percent", textfont_size=14)
    fig.update_layout(height=800)
    return fig

@app.callback(
    Output("download-all", "data"),
    Input("btn-download", "n_clicks"),
    prevent_initial_call=True
)
def download_all(n):
    out = df[["SKU", "Total Count", "Total Net Sales", "images"]]
    return dcc.send_data_frame(out.to_csv, "所有数据.csv", index=False)

@app.callback(
    Output("detail", "children"),
    Input("sku", "value")
)
def show_detail(sku):
    if not sku:
        return html.Div("请选择SKU。")
    r = df[df["SKU"].astype(str) == str(sku)]
    if r.empty:
        return html.Div("未找到该SKU。")
    row = r.iloc[0]
    url = image_url_from_row(row)
    img = html.Img(src=url, style={"width": "220px", "border": "1px solid #ccc", "borderRadius": "8px", "padding": "4px"}) if url else html.Div("无图片")
    return html.Div([
        html.H4(f"SKU：{row['SKU']}"),
        img,
        html.P(f"销售数量：{int(row['Total Count'])}", style={"fontWeight": "bold"}),
        html.P(f"销售额：${float(row['Total Net Sales']):,.2f}", style={"fontWeight": "bold"})
    ])

# ---------- 启动 ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

