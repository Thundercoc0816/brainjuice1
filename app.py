import os, glob
import pandas as pd
from dash import Dash, html, dcc, Input, Output, dash_table
import plotly.express as px
from flask import send_from_directory

# ================== 路径（相对，兼容本地与 Render） ==================
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CSV_PATH   = os.path.join(BASE_DIR, "merged_sku_image_sales.csv")
MAP_PATH   = os.path.join(BASE_DIR, "drive_map.csv")     # images ↔ drive_id
IMAGES_DIR = os.path.join(BASE_DIR, "images")            # 本地回退目录（可没有）

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

_require(CSV_PATH, "merged_sku_image_sales.csv")

# ================== 加载并清洗数据 ==================
df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")

if "SKU" not in df.columns or "images" not in df.columns:
    raise ValueError(f"[STARTUP] CSV must include columns 'SKU' and 'images'. Found: {list(df.columns)}")

def _clean_money(s):
    s = str(s).replace(",", "")
    return "".join(ch for ch in s if (ch.isdigit() or ch in ".-"))

df["Total Net Sales"] = pd.to_numeric(
    df["Total Net Sales"].astype(str).map(_clean_money),
    errors="coerce"
).fillna(0.0)

df["Total Count"] = pd.to_numeric(df["Total Count"], errors="coerce").fillna(0)

# —— 合并 Google Drive 映射（大小写/空格容错） ——
if os.path.exists(MAP_PATH):
    dm = pd.read_csv(MAP_PATH, encoding="utf-8-sig")
    if {"images", "drive_id"}.issubset(dm.columns):
        dm["images_lc"] = dm["images"].astype(str).str.strip().str.lower()
        df["images_lc"] = df["images"].astype(str).str.strip().str.lower()
        df = df.merge(dm[["images_lc", "drive_id"]], on="images_lc", how="left")
    else:
        print("[BOOT][WARN] drive_map.csv missing required columns: images, drive_id")
        df["drive_id"] = None
else:
    df["drive_id"] = None

# ================== 图片 URL 生成 ==================
def find_local_image(images_dir, name):
    if not images_dir or not name:
        return None
    base, ext = os.path.splitext(str(name))
    patterns = []
    if ext:
        patterns += [base + ".*", base.lower() + ".*", base.upper() + ".*"]
    else:
        for e in [".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"]:
            patterns += [base + e, base.lower() + e, base.upper() + e]
    for p in patterns:
        m = glob.glob(os.path.join(images_dir, p))
        if m:
            return os.path.basename(m[0])
    return None

def image_url_from_row(row):
    """
    生成可嵌入的图片URL：
    1) 优先使用 Google Drive 缩略图端点（最稳定）；
    2) 若 images 已是 http(s) 链接，直接用；
    3) 否则尝试本地 images 回退。
    """
    did = row.get("drive_id")
    if pd.notna(did) and str(did).strip():
        did = str(did).strip()
        return f"https://drive.google.com/thumbnail?id={did}&sz=w1000"

    imgname = str(row.get("images") or "").strip()
    if imgname.startswith(("http://", "https://")):
        return imgname

    local = find_local_image(IMAGES_DIR, imgname)
    if local:
        return f"/img/{local}"
    return None

# 预计算总计
total_units = int(df["Total Count"].sum())
total_revenue = float(df["Total Net Sales"].sum())

# ================== Dash 应用 ==================
app = Dash(__name__)
server = app.server  # 供 Gunicorn/Render 使用

@server.route("/img/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_DIR, filename)

app.layout = html.Div([
    html.H1("商品销售可视化系统", style={"textAlign": "center", "marginBottom": "6px"}),

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
    ], style={"textAlign": "center", "marginBottom": "8px"}),

    html.Div([
        html.Div([dcc.Graph(id="pie-chart")], style={"flex": "2", "minWidth": "600px"}),
        html.Div([
            html.H3("全部数据表（类似 Excel）"),
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
                style_table={"overflowX": "auto", "maxHeight": "80vh", "overflowY": "auto"},
                style_cell={"padding": "6px", "textAlign": "center"},
                style_header={"fontWeight": "bold", "backgroundColor": "#f2f2f2"},
            ),
            html.Button("下载所有数据（CSV）", id="btn-download", n_clicks=0, style={"marginTop": "10px"}),
            dcc.Download(id="download-all")
        ], style={"flex": "1", "minWidth": "360px", "paddingLeft": "16px"})
    ], style={"display": "flex", "gap": "10px"}),

    html.Hr(),

    html.Div([
        html.H3("选择 SKU 查看详情："),
        dcc.Dropdown(
            id="sku",
            options=[{"label": str(s), "value": str(s)} for s in df["SKU"]],
            placeholder="选择 SKU",
            style={"width": "320px"}
        ),
        html.Div(id="detail", style={"marginTop": "14px"})
    ], style={"textAlign": "center"}),

], style={"maxWidth": "1500px", "margin": "0 auto", "padding": "10px"})

# ================== 回调 ==================
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
            "SKU": ["其他"],
            "Total Count": [others["Total Count"].sum()],
            "Total Net Sales": [others["Total Net Sales"].sum()]
        })
        pie_df = pd.concat([top, other_row], ignore_index=True)
    else:
        pie_df = top

    title = "前10 + 其他（按数量）" if metric == "Total Count" else "前10 + 其他（按销售额）"
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
    return dcc.send_data_frame(out.to_csv, "所有数据.csv", index=False)

@app.callback(
    Output("detail", "children"),
    Input("sku", "value")
)
def show_detail(sku):
    if not sku:
        return html.Div("请选择 SKU。")
    row = df[df["SKU"].astype(str) == str(sku)]
    if row.empty:
        return html.Div("未找到该 SKU。")
    r = row.iloc[0]
    url = image_url_from_row(r)

    img = (
        html.Img(
            src=url,
            style={"width": "240px", "border": "1px solid #ccc", "borderRadius": "8px", "padding": "4px"}
        ) if url else html.Div("图片未找到")
    )

    # 调试信息：显示 drive_id 与最终URL，便于点击验证
    debug = html.Div([
        html.Div(f"drive_id：{str(r.get('drive_id'))}"),
        html.Div([
            html.Span("图片链接："),
            html.A(url if url else "(无)", href=url if url else "#", target="_blank",
                   style={"wordBreak": "break-all"})
        ])
    ], style={"marginTop": "8px", "fontSize": "12px", "color": "#555"})

    return html.Div([
        html.H4(f"SKU：{r['SKU']}"),
        img,
        debug,
        html.P(f"销售数量：{int(r['Total Count'])}", style={"fontWeight": "bold"}),
        html.P(f"销售额：${float(r['Total Net Sales']):,.2f}", style={"fontWeight": "bold"})
    ])

# ================== 运行（本地 & 云端） ==================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

