import os
import glob
import re
from datetime import datetime
import pandas as pd
import streamlit as st
import yfinance as yf

# 設定網頁介面為寬屏模式
st.set_page_config(layout="wide", page_title="美股兩日動態數據對比工具")

def get_latest_two_csvs():
    """自動搜尋當前資料夾下，依檔名日期排序（倒序）最新兩個 new_*.csv 檔案"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_pattern = os.path.join(script_dir, "new_*.csv")
    csv_files = glob.glob(search_pattern)
    
    if len(csv_files) < 2:
        return None, None
        
    # 直接用檔名文字（包含 YYYY-MM-DD）做倒序排序
    csv_files.sort(reverse=True)
    return csv_files[0], csv_files[1]

def push_to_github_backend(file_name, file_bytes):
    """【後台自動化核心】將網頁收到的 CSV 即時經後台 Commit & Push 回 GitHub"""
    if "GITHUB_TOKEN" not in st.secrets:
        return False
        
    try:
        from github import Github
        token = st.secrets["GITHUB_TOKEN"]
        repo_name = "kinaoc-ui/shock"  # 你嘅專案路徑
        
        g = Github(token)
        repo = g.get_repo(repo_name)
        
        # 檢查 GitHub 內原本有冇同名檔案，有就覆蓋，冇就新建
        try:
            contents = repo.get_contents(file_name)
            repo.update_file(contents.path, f"Auto-update {file_name} via web", file_bytes, contents.sha)
        except:
            repo.create_file(file_name, f"Auto-upload {file_name} via web", file_bytes)
        return True
    except Exception as e:
        st.warning(f"後台自動備份到 GitHub 失敗（但不影響本次運算）: {e}")
        return False

def load_and_clean_csv(file_path_or_buffer):
    """讀取 CSV 並清洗欄位名稱與代號（含缺失欄位自動補底）"""
    try:
        df = pd.read_csv(file_path_or_buffer)
        df.rename(columns={df.columns[0]: 'Symbol'}, inplace=True)
        df['Symbol'] = df['Symbol'].astype(str).str.strip()
        
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
    """純記憶體生成 TradingView 專用導入格式的文字內容"""
    if df_added.empty and df_removed.empty and top_gainers.empty and top_losers.empty:
        return ""

    output = []
    
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

    if not df_added.empty:
        df_ad = df_added.copy()
        df_ad['部門板塊'] = df_ad['部門板塊'].fillna('Unclassified').astype(str).str.strip()
        df_ad['行業'] = df_ad['行業'].fillna('Unclassified').astype(str).str.strip()
        added_groups = df_ad.groupby(['部門板塊', '行業'])
        for (sector, industry), group in added_groups:
            output.append(f"### up_{sector} — {industry}\n")
            for symbol in group['Symbol']: output.append(f"{symbol}\n")
            output.append("\n")

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
    if pd.isna(val) or val == 0: return "N/A"
    if val >= 1e12: return f"${val / 1e12:.2f} T"
    if val >= 1e9: return f"${val / 1e9:.2f} B"
    if val >= 1e6: return f"${val / 1e6:.2f} M"
    return f"${val:,.0f}"

def main():
    st.title("📊 美股兩日清單動態對比 + 盤前即時監控大盤")
    st.write("---")

    st.markdown("### 📁 數據上傳區")
    st.markdown("當你在網頁端上傳新 CSV 檔，系統會**全自動將檔案備份同步回 GitHub** 儲存，以後無論點樣 F5 重新整理數據都唔會消失！")
    
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        uploaded_new = st.file_uploader("1️⃣ 上傳最新一日 CSV (格式必須為 new_YYYY-MM-DD.csv)", type=["csv"])
    with col_up2:
        uploaded_old = st.file_uploader("2️⃣ 上傳前一日 CSV (格式必須為 new_YYYY-MM-DD.csv)", type=["csv"])

    df_new, df_old = None, None
    data_source_msg = ""

    if uploaded_new and uploaded_old:
        df_new = load_and_clean_csv(uploaded_new)
        df_old = load_and_clean_csv(uploaded_old)
        data_source_msg = "📂 **當前數據來源：** 網頁端手動上傳的 CSV 數據"
        
        # 【核心觸發】利用 Session State 鎖定，防止重新渲染時無故重複提交
        if st.session_state.get(f"synced_{uploaded_new.name}") is None:
            if push_to_github_backend(uploaded_new.name, uploaded_new.getvalue()):
                st.session_state[f"synced_{uploaded_new.name}"] = True
                st.toast(f"🚀 {uploaded_new.name} 已成功自動上傳並永久儲存至 GitHub！", icon="✨")
                
        if st.session_state.get(f"synced_{uploaded_old.name}") is None:
            if push_to_github_backend(uploaded_old.name, uploaded_old.getvalue()):
                st.session_state[f"synced_{uploaded_old.name}"] = True
                st.toast(f"🚀 {uploaded_old.name} 已成功自動上傳並永久儲存至 GitHub！", icon="✨")
    else:
        new_file, old_file = get_latest_two_csvs()
        if new_file and old_file:
            df_new = load_and_clean_csv(new_file)
            df_old = load_and_clean_csv(old_file)
            data_source_msg = f"📅 **當前數據來源：** GitHub 雲端儲存數據 \n* **新一日（當前）：** `{os.path.basename(new_file)}` \n* **舊一日（前天）：** `{os.path.basename(old_file)}`"

    if df_new is None or df_old is None:
        st.info("👋 **歡迎使用！請在上方「數據上傳區」直接投入兩份 CSV 檔案。**")
        return

    st.success(data_source_msg)

    # 比對邏輯
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

    # 產生下載
    today_str = datetime.now().strftime("%Y-%m-%d")
    txt_content = generate_tradingview_watchlist_content(df_added_info, df_removed_info, top_10_gainers, top_10_losers)
    
    if txt_content:
        st.download_button(
            label="📥 點擊下載今日 TradingView 分類導入檔 (.txt)",
            data=txt_content,
            file_name=f"TV_Watchlist_{today_str}.txt",
            mime="text/plain",
            use_container_width=True
        )

    # 數據看板呈現
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
        if not df_added_info.empty: st.dataframe(df_added_info, width='stretch', hide_index=True)
        else: st.write("今日無新增股票。")
            
    with col_rem:
        st.error(f"➖ **被剔除/消失股票 (共 {len(removed_symbols)} 隻)**")
        if not df_removed_info.empty: st.dataframe(df_removed_info, width='stretch', hide_index=True)
        else: st.write("今日無消失股票。")

    st.write("---")

    # 聯網爬即時報價
    all_target_syms = list(set(top_10_gainers['Symbol'].tolist() + top_10_losers['Symbol'].tolist()))
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
