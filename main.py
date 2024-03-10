from datetime import datetime
import os
from dash import Dash, html, dash_table, dcc, callback, Output, Input, State
import pandas as pd
import plotly.express as px
import akshare as ak
from pipetools import pipe
from cfkv import KVStore
from dotenv import load_dotenv
import json
import dash_bootstrap_components as dbc
from pipetools import pipe
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware


ASSET_PREFIX = Path("assets")
INDEX_PE_PB_FNAME = ASSET_PREFIX / 'index_pe_pb.csv'
INDEX_A_FNAME = ASSET_PREFIX / 'index_a.csv'
INDEX_HK_FNAME = ASSET_PREFIX / 'index_hk.csv'


PREFERRED_INDEXES = ['上证指数', '深证成指', '创业板指', '中证红利', '中证500', '沪深300'
                     '中证全指', '中证100', '中证200', '中证700', '中证800', '中证1000',
                     '中证国债', '中证城投', '中证企业债', '中证转债', '中证地产', '中证医药',
                     '中证消费', '中证银行', '中证信息', '中证环保', '中证传媒', '上证50',
                     '中证2000', '中证证券', '中证保险', '中证酒', '中证军工', '中证医疗', '中证医药', 
                     '医疗保健', '中证传媒', '中证全指房地产']
# Initialize the app
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
# FastAPI app
fastapi_app = FastAPI()

# Mount Dash app
fastapi_app.mount("/", WSGIMiddleware(app.server))


def is_data_outdated(index_fp):
    '''check the existence and mtime is today or not, if not, download it from akshare'''
    if not os.path.exists(index_fp):
        return True
    
    mdate = datetime.utcfromtimestamp(os.path.getmtime(index_fp)).date()
    today = pd.to_datetime('today').date()
    return mdate < today

def download_or_cache_data():

    if is_data_outdated(INDEX_PE_PB_FNAME):
        pbpe_df = ak.index_value_name_funddb()
        pbpe_df.to_csv(INDEX_PE_PB_FNAME, index=False)

    if is_data_outdated(INDEX_HK_FNAME):
        df_hk = ak.stock_hk_index_spot_em()
        df_hk.to_csv(INDEX_HK_FNAME, index=False)
    
    if is_data_outdated(INDEX_A_FNAME):
        df_a = ak.stock_zh_index_spot_sina()
        df_a.to_csv(INDEX_A_FNAME, index=False)
    
    return pd.read_csv(INDEX_PE_PB_FNAME), pd.concat((pd.read_csv(INDEX_HK_FNAME), pd.read_csv(INDEX_A_FNAME)))

    
def prepare_df():
    '''check the existence and mtime is today or not, if not, download it from akshare'''
    pbpe_df, index_df = download_or_cache_data()
    # merge by different column name
    pbpe_df['PEPB分位均值'] = (pbpe_df['PE分位'] + pbpe_df['PB分位']) / 2
    df = pd.merge(pbpe_df, index_df[['名称', '最新价', '代码']], left_on='指数名称', right_on='名称', how='left')
    df.drop(columns=['名称'], inplace=True)
    df.rename(columns={'代码': '指数代码2'}, inplace=True)
    

    # 本轮下跌幅度
    df['上轮最高价'] = 0
    df['上轮最高回撤百分'] = df['上轮最高价'] / df['最新价'] - 1
    df['上轮回撤年数'] = 0  # TODO

    # 历史平均幅度和年数
    df['平均最高价'] = 0
    df['平均最大回撤百分'] = (df['平均最高价'] / df['最新价']) - 1
    df['平均最大回撤年'] = 0 # TODO

    # load the marked highest and date

    # calc the value delta, years delta, value delta with inflation

    # format all float to 2 decimal
    df = df.applymap(lambda x: round(x, 2) if isinstance(x, float) else x)
    return df.drop_duplicates(subset=['指数名称'])

# load the dat
df = prepare_df()
# App layout
app.layout = html.Div([
    dcc.Markdown('### 指数看板'),
    
    dbc.Textarea(id='controls-and-textarea', title='保存和恢复最爱', rows=4, value=', '.join(PREFERRED_INDEXES), size='lg'),
    dbc.Button('粘贴列表后点击恢复清单', size='lg', id='controls-and-restore-button', n_clicks=0),
    dcc.Dropdown(options=[{'label':i, 'value':i} for i in df['指数名称'].unique()], 
                 value=PREFERRED_INDEXES, 
                 multi=True,
                 id='controls-and-radio-item'),

    dash_table.DataTable(data=df.to_dict('records'),
                         id='controls-and-table', 
                         sort_action='native',
                         page_size=50),
    dcc.Graph(figure={}, id='controls-and-graph-pe'),
    dcc.Graph(figure={}, id='controls-and-graph-pb'),
    dcc.Graph(figure={}, id='controls-and-graph-avgpepb'),
    

    dbc.Row([dbc.Col(dcc.Graph(figure=px.scatter(df.sort_values(by='指数名称'), x='指数名称', y='PE分位', height=800, title='全市场PE分位分布-点图'))),
             dbc.Col(dcc.Graph(figure=px.scatter(df, x='指数名称', y='PB分位', height=800, title='全市场PB分位分布-点图'))),
    ]),

    dbc.Row([dbc.Col(dcc.Graph(figure=px.histogram(df, x='PE分位', title='全市场PE分位分布-直方图'))),
            dbc.Col(dcc.Graph(figure=px.histogram(df, x='PB分位', title='全市场PB分位分布-直方图')))]),

    dbc.Row([dbc.Col(dcc.Graph(figure=px.histogram(df, x='最新PE', title='全市场PE值分布-直方图'))),
            dbc.Col(dcc.Graph(figure=px.histogram(df, x='最新PB', title='全市场PB值分布-直方图')))]),

])

# Add controls to build the interaction
# update table
@callback(
    Output(component_id='controls-and-table', component_property='data'),
    Input(component_id='controls-and-radio-item', component_property='value'),
)
def update_table(name: list):
    '''return the df that column '指数名称' contains the name which in the list of name'''
    return df[df['指数名称'].isin(name)].to_dict('records')

# update pe of favorite indexes
@callback(
    Output(component_id='controls-and-graph-pe', component_property='figure'),
    Input(component_id='controls-and-radio-item', component_property='value'),
)
def update_graph_pe(name: list):
    '''return the df that column '指数名称' contains the name which in the list of name'''
    data = df[df['指数名称'].isin(name)]
    fig = px.scatter(data, x='指数名称', y='PE分位', title='已选指数PE分位')
    return fig

# update pb of favorite indexes
@callback(
    Output(component_id='controls-and-graph-pb', component_property='figure'),
    Input(component_id='controls-and-radio-item', component_property='value'),
)
def update_graph_pb(name: list):
    '''return the df that column '指数名称' contains the name which in the list of name'''
    data = df[df['指数名称'].isin(name)]
    fig = px.scatter(data, x='指数名称', y='PB分位', title='已选指数PB分位')
    return fig

# update avgpepb of favorite indexes
@callback(
    Output(component_id='controls-and-graph-avgpepb', component_property='figure'),
    Input(component_id='controls-and-radio-item', component_property='value'),
)
def update_graph_avgpepb(name: list):
    '''return the df that column '指数名称' contains the name which in the list of name'''
    data = df[df['指数名称'].isin(name)]
    fig = px.scatter(data, x='指数名称', y='PEPB分位均值', title='已选指数PEPB分位平均值')
    return fig

# restore the favorites from the textarea
@callback(
    Output(component_id='controls-and-radio-item', component_property='value'),
    Input(component_id='controls-and-restore-button', component_property='n_clicks'),
    State(component_id='controls-and-textarea', component_property='value'),
)
def update_dropdown(n_clicks, favorites):
    '''restore the favorites from the textarea'''
    data = favorites.strip().replace(' ', '').replace('，', ',').split(',')
    return data

# update the textarea when dropdown changes
@callback(
    Output(component_id='controls-and-textarea', component_property='value'),
    Input(component_id='controls-and-radio-item', component_property='value'),
)
def update_favorites(name: list):
    '''update the favorites to the textarea when dropdown changes'''
    data = ', '.join(name)
    return data


# Run the app
if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=8050)