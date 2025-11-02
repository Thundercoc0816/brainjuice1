import os, glob
import pandas as pd
from dash import Dash, html, dcc, Input, Output, dash_table
import plotly.express as px
from flask import send_from_directory

# === 路径 ===
BASE_DIR   = r"C:\Users\17745\OneDrive\Desktop\Brain juice\New folder"
CSV_PATH   = os.path.join(BASE_DIR, "merged_sku_image_sales.csv")
IMAGES_DIR = os.path.join(BASE_DIR, "images")

# === 读取并清洗数据（不改列名）===
df = pd.read_csv(CSV_PATH)

# 收入列去掉 $、逗号、空格等；空值按 0 处理
rev_clean = (
    df["Total Net Sales"].astype(str)
      .str.replace(r"[^0-9.\-]", "", regex=True)
      .replace({"": "0", ".": "0", "-": "0"})
)
df["Total Net Sales"] = pd.to_numeric(rev_clean, errors="coerce").fillna(0.0)
df["Total Count"] = pd.to_numeric(df["Total Count"], errors="coerce").fillna(0)

total_units = int(df["Total Count"].sum())
total_revenue = float(df["Total Net Sales"].sum())

# === 图片查找：大小写/扩展名容错 ===
def find_image_case_insensitive(images_dir, name):
    base, ext = os.path.splitext(str(name))
    if not base:
        return None
    patterns = []
    if ext:
        # 有扩展名：尝试任意大小写/同名不同大小写
        patterns += [base + ".*", base.lower() + ".*", base.upper() + ".*"]
    else:
        # 无扩展名：尝试常见扩展
        for e in [".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"]:
            patterns += [base + e, base.lower() + e, base.upper() + e]
    for p in patterns:
        m = glob.glob(os.path.join(images_dir, p))
        if m:
            return m[0]
    return None

# === Dash 应用 ===
app = Dash(__name__)
server = app.server

# 静态路由：按文件名返回图片
@server.route("/img/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_DIR, filename)

app.layout = html.Div([
    html.H1("商品销售总览", style={"textAlign": "center", "marginBottom": "6px"}),

    html.Div([
        html.H3(f"总销量（件）：{total_units:,}", style={"marginRight": "20px"}),
        html.H3(f"总收入（$）：{total_revenue:,.2f}")
    ], style={"display": "flex", "justifyContent": "center", "gap": "20px"}),

    html.Div([
        dcc.RadioItems(
            id="metric",
            options=[
                {"label": "按销量占比", "value": "Total Count"},
                {"label": "按收入占比", "value": "Total Net Sales"},
            ],
            value="Total Count",
            labelStyle={"marginRight": "16px"}
        )
    ], style={"textAlign": "center", "marginBottom": "8px"}),

    # 两列布局：左饼图（Top10），右“全部数据”表
    html.Div([
        html.Div([dcc.Graph(id="pie-chart")], style={"flex": "2", "minWidth": "600px"}),
        html.Div([
            html.H3("全部数据（Excel 风格）"),
            dash_table.DataTable(
                id="all-table",
                columns=[
                    {"name": "SKU", "id": "SKU"},
                    {"name": "销量（Total Count）", "id": "Total Count", "type": "numeric"},
                    {"name": "收入（Total Net Sales）", "id": "Total Net Sales", "type": "numeric", "format": {}},
                    {"name": "图片文件名（images）", "id": "images"},
                ],
                data=df.sort_values("Total Count", ascending=False).to_dict("records"),
                page_size=15,
                sort_action="native",
                filter_action="native",
                style_table={"overflowX": "auto", "maxHeight": "80vh", "overflowY": "auto"},
                style_cell={"padding": "6px", "textAlign": "center"},
                style_header={"fontWeight": "bold", "backgroundColor": "#f2f2f2"},
            ),
            html.Button("下载全部数据（CSV）", id="btn-download-all", n_clicks=0, style={"marginTop": "10px"}),
            dcc.Download(id="download-all")
        ], style={"flex": "1", "minWidth": "360px", "paddingLeft": "16px"})
    ], style={"display": "flex", "gap": "10px"}),

    html.Hr(),

    # 单个 SKU 详情（含图片预览）
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

# === 回调：Top10 饼图（其余并入“Other”），右侧表显示“全部数据” ===
@app.callback(
    Output("pie-chart", "figure"),
    Input("metric", "value")
)
def make_pie(metric):
    d = df.sort_values(metric, ascending=False).reset_index(drop=True)
    top_n = 10
    top = d.head(top_n).copy()
    others = d.iloc[top_n:].copy()

    # 构造饼图数据（Top10 + Other 聚合），右侧表格始终是“全部数据”，无需在此处理
    if not others.empty:
        other_row = pd.DataFrame({
            "SKU": ["Other"],
            "Total Count": [others["Total Count"].sum()],
            "Total Net Sales": [others["Total Net Sales"].sum()]
        })
        pie_df = pd.concat([top, other_row], ignore_index=True)
    else:
        pie_df = top

    title = "销量占比（Top 10 + 其它）" if metric == "Total Count" else "收入占比（Top 10 + 其它）"
    fig = px.pie(
        pie_df,
        values=metric,
        names="SKU",
        title=title,
        hole=0.25
    )
    fig.update_traces(textinfo="label+percent", textfont_size=14,
                      hovertemplate="SKU=%{label}<br>%{value:,.2f}")
    fig.update_layout(height=820, margin=dict(l=30, r=30, t=60, b=30), showlegend=True)
    return fig

# === 下载全部数据 ===
@app.callback(
    Output("download-all", "data"),
    Input("btn-download-all", "n_clicks"),
    prevent_initial_call=True
)
def download_all(n_clicks):
    if not n_clicks:
        return None
    # 列顺序
    out = df[["SKU", "Total Count", "Total Net Sales", "images"]].copy()
    return dcc.send_data_frame(out.to_csv, "all_data.csv", index=False)

# === 单个 SKU 详情（带图片容错查找）===
@app.callback(
    Output("detail", "children"),
    Input("sku", "value")
)
def show_detail(sku):
    if not sku:
        return html.Div("请选择一个 SKU。")

    row = df[df["SKU"].astype(str) == str(sku)]
    if row.empty:
        return html.Div("未找到该 SKU。")

    r = row.iloc[0]
    resolved = find_image_case_insensitive(IMAGES_DIR, r["images"])
    if resolved:
        img_name = os.path.basename(resolved)
        img = html.Img(src=f"/img/{img_name}",
                       style={"width": "220px", "border": "1px solid #ccc", "borderRadius": "8px", "padding": "4px"})
    else:
        img = html.Div("图片未找到")

    return html.Div([
        html.H4(f"SKU：{r['SKU']}"),
        img,
        html.P(f"销量（Total Count）：{int(r['Total Count'])}", style={"fontWeight": "bold"}),
        html.P(f"收入（Total Net Sales）：${float(r['Total Net Sales']):,.2f}", style={"fontWeight": "bold"})
    ])

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8050))  # cloud will inject PORT
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)