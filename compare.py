import os
import glob
import re
from datetime import datetime  # 導入日期模組
import pandas as pd
import streamlit as st
import yfinance as yf

# 設定網頁介面為寬屏模式
st.set_page_config(layout="wide", page_title="美股兩日動態數據對比工具")

def get_latest_two_csvs():
    """自動搜尋當前資料夾下，最新修改/日期的兩個 new_*.csv 檔案"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_pattern = os.path.join(script_dir, "new_*.csv")
    csv_files = glob.glob(search_pattern)
    
    if len(csv_files) < 2:
        return None, None
    csv_files.sort(key=os.path.getmtime, reverse=True)
    return csv_files[0], csv_files[1]

def load_and_clean_csv(file_path_or_buffer):
    """讀取 CSV 並清洗欄位名稱與代號（含缺失欄位自動補底，支援上傳與本地讀取）"""
    try:
        df = pd.read_csv(file_path_or_buffer)
        df.rename(columns={df.columns[0]: 'Symbol'}, inplace=True)
        df['Symbol'] = df['Symbol'].astype(str).str.strip()
        
        # 定義預期的標準欄位名稱對照表
        standard_cols = {
            'description': 'Description',
            'price': 'Price',
            'sector': 'Sector',
            'industry': 'Industry',
            'market capitalization': 'Market capitalization',
            'price to earnings ratio': 'Price to earnings ratio'
        }
        
        rename_dict = {}
        for col in df.columns:
            cleaned_col = str(col).strip().lower()
            if cleaned_col in standard_cols:
                rename_dict[col] = standard_cols[cleaned_col]
        
        df.rename(columns=rename_dict, inplace=True)
        
        # 防呆自動補底
        if 'Description' not in df.columns: df['Description'] = 'N/A'
        if 'Price' not in df.columns: df['Price'] = 0.0
        if 'Sector' not in df.columns: df['Sector'] = 'Unclassified'
        if 'Industry' not in df.columns: df['Industry'] = 'Unclassified'
        if 'Market capitalization' not in df.columns: df['Market capitalization'] = 0
        if 'Price to earnings ratio' not in df.columns: df['Price to earnings ratio'] = 0
            
        return df
    except Exception as e:
        st.error(f"讀取數據失敗: {e}")
        return None

def fetch_live_market_data(symbols):
    """全自動連線 Yahoo Finance 抓取盤前/盤後即時價格及變幅"""
    live_data = {}
    if not symbols:
        return live_data
        
    try:
        tickers = yf.Tickers(' '.join(symbols))
        for sym in symbols:
            try:
                info = tickers.tickers[sym].info
                state = "常規"
                current_price = info.get('regularMarketPrice')
                prev_close = info.get('previousClose', 1)
                
                if info.get('preMarketPrice'):
                    current_price = info.get('preMarketPrice')
                    state = "盤前 🌅"
                elif info.get('postMarketPrice'):
                    current_price = info.get('postMarketPrice')
                    state = "盤後 🌃"
                
                if current_price and prev_close:
                    live_pct = ((current_price - prev_close) / prev_close) * 100
                    live_data[sym] = {
                        '即時市況': state,
                        '最新即時價': current_price,
                        '即時總變幅 %': live_pct
                    }
            except:
                continue
    except Exception as e:
        st.warning(f"即時盤前數據獲取失敗: {e}")
    return live_data

def generate_tradingview_watchlist_content(df_added, df_removed, top_gainers, top_losers):
    """純記憶體生成 TradingView 專用導入格式的文字內容 (支援 Sector + Industry 雙層分組標頭)"""
    if df_added.empty and df_removed.empty and top_gainers.empty and top_losers.empty:
        return ""

    output = []
    
    # ======= 1. 兩日漲跌最強的 20 隻動能核心股 =======
    if not top_gainers.empty:
        df_tg = top_gainers.copy()
        df_tg['部門板塊'] = df_tg['部門板塊'].fillna('Unclassified').astype(str).str.strip()
        df_tg['行業'] = df_tg['行業'].fillna('Unclassified').astype(str).str.strip()
        tg_groups = df_tg.groupby(['部門板塊', '行業'])
        for (sector, industry), group in tg_groups:
            output.append(f"### Top_Gainers — {sector} — {industry}\n")
            for symbol in group['Symbol']: output.append(f"{symbol}\n")
            output.append("\n")

    if not top_losers.empty:
        df_tl = top_losers.copy()
        df_tl['部門板塊'] = df_tl['部門板塊'].fillna('Unclassified').astype(str).str.strip()
        df_tl['行業'] = df_tl['行業'].fillna('Unclassified').astype(str).str.strip()
        tl_groups = df_tl.groupby(['部門板塊', '行業'])
        for (sector, industry), group in tl_groups:
            output.append(f"### Top_Losers — {sector} — {industry}\n")
            for symbol in group['Symbol']: output.append(f"{symbol}\n")
            output.append("\n")

    # ======= 2. 處理 [新增進榜] 的股票 =======
    if not df_added.empty:
        df_ad = df_added.copy()
        df_ad['部門板塊'] = df_ad['部門板塊'].fillna('Unclassified').astype(str).str.strip()
        df_ad['行業'] = df_ad['行業'].fillna('Unclassified').astype(str).str.strip()
        added_groups = df_ad.groupby(['部門板塊', '行業'])
        for (sector, industry), group in added_groups:
            output.append(f"### up_{sector} — {industry}\n")
            for symbol in group['Symbol']: output.append(f"{symbol}\n")
            output.append("\n")

    # ======= 3. 處理 [被剔除/消失] 的股票 =======
    if not df_removed.empty:
        df_rm = df_removed.copy()
        df_rm['部門板塊'] = df_rm['部門板塊'].fillna('Unclassified').astype(str).str.strip()
        df_rm['行業'] = df_rm['行業'].fillna('Unclassified').astype(str).str.strip()
        removed_groups = df_rm.groupby(['部門板塊', '行業'])
        for (sector, industry), group in removed_groups:
            output.append(f"### down_{sector} — {industry}\n")
            for symbol in group['Symbol']: output.append(f"{symbol}\n")
            output.append("\n")
            
    return "".join(output)

def format_market_cap(val):
    """將巨大的市值數字格式化為易讀的 T/B/M 單位"""
    if pd.isna(val) or val == 0:
        return "N/A"
    if val >= 1e12: return f"${val / 1e12:.2f} T"
    if val >= 1e9: return f"${val / 1e9:.2f} B"
    if val >= 1e6: return f"${val / 1e6:.2f} M"
    return f"${val:,.0f}"

def main():
    st.title("📊 美股兩日清單動態對比 + 盤前即時監控大盤")
    st.write("---")

    # ==================== 📁 數據上傳區 ====================
    st.markdown("### 📁 數據上傳區")
    st.markdown("你可以直接丟入新的 CSV 覆蓋數據；如不上傳，系統會自動載入 GitHub 預設數據：")
    
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        uploaded_new = st.file_uploader("1️⃣ 上傳最新一日 CSV (New)", type=["csv"])
    with col_up2:
        uploaded_old = st.file_uploader("2️⃣ 上傳前一日 CSV (Old)", type=["csv"])

    df_new = None
    df_old = None
    data_source_msg = ""
    is_manual_upload = False

    if uploaded_new and uploaded_old:
        df_new = load_and_clean_csv(uploaded_new)
        df_old = load_and_clean_csv(uploaded_old)
        data_source_msg = "📂 **當前數據來源：** 網頁端手動上傳的 CSV 數據"
        is_manual_upload = True
    else:
        new_file, old_file = get_latest_two_csvs()
        if new_file and old_file:
            df_new = load_and_clean_csv(new_file)
            df_old = load_and_clean_csv(old_file)
            data_source_msg = f"📅 **當前數據來源：** 系統內置預載數據 \n* **新一日：** `{os.path.basename(new_file)}` \n* **舊一日：** `{os.path.basename(old_file)}`"

    if df_new is None or df_old is None:
        st.info("👋 **歡迎使用！請在上方「數據上傳區」上傳檔案**\n\n請直接將兩份由 TradingView 匯出的 CSV 檔案拖放到上面的框框中，系統就會立刻顯示分析結果！")
        return

    st.success(data_source_msg)

    # 檢查是否缺少 Industry
    if 'Industry' in df_new.columns and (df_new['Industry'] == 'Unclassified').all():
        st.warning("⚠️ **提示：** 偵測到 CSV 檔案中缺少 'Industry' 欄位。")

    # ==================== 📥 終極修正：萬能下載按鈕（放喺最顯眼位置） ====================
    set_new = set(df_new['Symbol'])
    set_old = set(df_old['Symbol'])
    added_symbols = list(set_new - set_old)
    removed_symbols = list(set_old - set_new)

    df_added_info = df_new[df_new['Symbol'].isin(added_symbols)][['Symbol', 'Description', 'Price', 'Sector', 'Industry']].rename(
        columns={'Sector': '部門板塊', 'Industry': '行業'}
    )
    df_removed_info = df_old[df_old['Symbol'].isin(removed_symbols)][['Symbol', 'Description', 'Price', 'Sector', 'Industry']].rename(
        columns={'Sector': '部門板塊', 'Industry': '行業'}
    )

    common_symbols = list(set_new & set_old)
    df_new_sub = df_new[df_new['Symbol'].isin(common_symbols)][['Symbol', 'Price', 'Description', 'Sector', 'Industry', 'Market capitalization']]
    df_old_sub = df_old[df_old['Symbol'].isin(common_symbols)][['Symbol', 'Price']]
    df_merge = pd.merge(df_new_sub, df_old_sub, on='Symbol', suffixes=('_new', '_old'))
    df_merge['兩日變幅 %'] = ((df_merge['Price_new'] - df_merge['Price_old']) / df_merge['Price_old']) * 100
    df_merge.rename(columns={'Price_new': '最新收盤價 (新)', 'Price_old': '前日收盤價 (舊)', 'Market capitalization': '市值 (USD)', 'Sector': '部門板塊', 'Industry': '行業'}, inplace=True)

    top_10_gainers = df_merge.sort_values(by='兩日變幅 %', ascending=False).head(10)
    top_10_losers = df_merge.sort_values(by='兩日變幅 %', ascending=True).head(10)

    # 生成文字內容
    today_str = datetime.now().strftime("%Y-%m-%d")
    txt_content = generate_tradingview_watchlist_content(df_added_info, df_removed_info, top_10_gainers, top_10_losers)
    
    if txt_content:
        # 1. 如果係你自己部電腦 Local 跑，順便自動塞一個實體 txt 檔入你 Desktop 資料夾放底
        if not is_manual_upload:
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                local_file_path = os.path.join(script_dir, f"{today_str}.txt")
                with open(local_file_path, "w", encoding="utf-8") as lf:
                    lf.write(txt_content)
            except:
                pass
        
        # 2. 【全網共享下載掣】無論邊個開條 Link，一律喺最上面 show 出下載按鈕！
        st.download_button(
            label="📥 點擊下載今日 TradingView 分類導入檔 (.txt)",
            data=txt_content,
            file_name=f"TV_Watchlist_{today_str}.txt",
            mime="text/plain",
            use_container_width=True
        )

    # ==================== 🔍 HEADER 摘要與數據呈現 ====================
    st.markdown("### 🔍 當前數據篩選特徵摘要")
    total_stocks = len(df_new)
    unique_sectors = df_new['Sector'].nunique()
    valid_mcap = df_new[df_new['Market capitalization'] > 0]['Market capitalization']
    min_mcap_str = format_market_cap(valid_mcap.min()) if not valid_mcap.empty else "N/A"
    max_mcap_str = format_market_cap(valid_mcap.max()) if not valid_mcap.empty else "N/A"
    
    met_1, met_2, met_3, met_4 = st.columns(4)
    met_1.metric(label="📊 總進榜標的", value=f"{total_stocks} 隻")
    met_2.metric(label="🏢 涵蓋板塊數量", value=f"{unique_sectors} 個")
    met_3.metric(label="📉 篩選最低市值", value=min_mcap_str)
    met_4.metric(label="📈 篩選最高市值", value=max_mcap_str)
    st.write("---")

    col_add, col_rem = st.columns(2)
    with col_add:
        st.success(f"➕ **新增進榜股票 (共 {len(added_symbols)} 隻)**")
        if added_symbols: st.dataframe(df_added_info, width='stretch', hide_index=True)
        else: st.write("今日無新增股票。")
            
    with col_rem:
        st.error(f"➖ **被剔除/消失股票 (共 {len(removed_symbols)} 隻)**")
        if removed_symbols: st.dataframe(df_removed_info, width='stretch', hide_index=True)
        else: st.write("今日無消失股票。")

    st.write("---")

    # 聯網抓即時數據
    top_gainers_syms = top_10_gainers['Symbol'].tolist()
    top_losers_syms = top_10_losers['Symbol'].tolist()
    all_target_syms = list(set(top_gainers_syms + top_losers_syms))
    
    with st.spinner('🔄 正在同步美股聯網，抓取最新盤前/盤後即時報價...'):
        live_quotes = fetch_live_market_data(all_target_syms)
    
    df_merge['即時市況'] = df_merge['Symbol'].map(lambda x: live_quotes[x]['即時市況'] if x in live_quotes else 'CSV歷史')
    df_merge['即時價'] = df_merge['Symbol'].map(lambda x: live_quotes[x]['最新即時價'] if x in live_quotes else None)
    df_merge['即時總變幅 %'] = df_merge['Symbol'].map(lambda x: live_quotes[x]['即時總變幅 %'] if x in live_quotes else None)
    df_merge['即時價'] = df_merge['即時價'].fillna(df_merge['最新收盤價 (新)'])
    df_merge['即時總變幅 %'] = df_merge['即時總變幅 %'].fillna(df_merge['兩日變幅 %'])

    top_10_gainers_live = df_merge.sort_values(by='兩日變幅 %', ascending=False).head(10)
    top_10_losers_live = df_merge.sort_values(by='兩日變幅 %', ascending=True).head(10)

    cols_to_show = ['Symbol', 'Description', '即時市況', '即時總變幅 %', '即時價', '兩日變幅 %', '最新收盤價 (新)', '前日收盤價 (舊)', '部門板塊', '行業', '市值 (USD)']

    st.subheader("🔥 兩日最強動能排行榜 (Top 10 Gainers) — 支援盤前即時聯網")
    st.dataframe(
        top_10_gainers_live[cols_to_show].style.format({
            '兩日變幅 %': '{:+.2f}%', '最新收盤價 (新)': '${:.2f}', '前日收盤價 (舊)': '${:.2f}', '市值 (USD)': '{:,.0f}',
            '即時總變幅 %': '{:+.2f}%', '即時價': '${:.2f}'
        }).background_gradient(subset=['即時總變幅 %'], cmap='Greens'), width='stretch', hide_index=True
    )

    st.write(" ")
    st.subheader("🩸 兩日失速暴跌排行榜 (Top 10 Losers) — 支援盤前即時聯網")
    st.dataframe(
        top_10_losers_live[cols_to_show].style.format({
            '兩日變幅 %': '{:+.2f}%', '最新收盤價 (新)': '${:.2f}', '前日收盤價 (舊)': '${:.2f}', '市值 (USD)': '{:,.0f}',
            '即時總變幅 %': '{:+.2f}%', '即時價': '${:.2f}'
        }).background_gradient(subset=['即時總變幅 %'], cmap='Reds'), width='stretch', hide_index=True
    )

if __name__ == "__main__":
    main()
