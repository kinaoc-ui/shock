import os
import glob
import re
from datetime import datetime
import pandas as pd
import streamlit as st
import yfinance as yf

# 設定網頁介面為寬屏模式
st.set_page_config(layout="wide", page_title="美股兩日動態數據對比工具")

def get_all_local_csvs():
    """搜尋當前資料夾下所有符合格式的 CSV，依檔名日期從新到舊排序"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_pattern = os.path.join(script_dir, "new_*.csv")
    csv_files = glob.glob(search_pattern)
    if csv_files:
        csv_files.sort(reverse=True)
        return csv_files
    return []

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

def trigger_sync(uploaded_file):
    """觸發後台同步機制（利用 Session State 防止重複提交）"""
    if st.session_state.get(f"synced_{uploaded_file.name}") is None:
        if push_to_github_backend(uploaded_file.name, uploaded_file.getvalue()):
            st.session_state[f"synced_{uploaded_file.name}"] = True
            st.toast(f"🚀 {uploaded_file.name} 已成功自動上傳並永久儲存至 GitHub！", icon="✨")

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
    st.markdown("💡 **提示：** 正常情況下你**只需要上傳「1️⃣ 最新一日 CSV」** 即可。如果你想查看過往日子，**請勿上傳檔案**，直接使用下方的歷史切換選單。")
    
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        uploaded_new = st.file_uploader("1️⃣ 上傳最新一日 CSV (格式：new_YYYY-MM-DD.csv)", type=["csv"])
    with col_up2:
        uploaded_old = st.file_uploader("2️⃣ [選填] 上傳前一日 CSV (格式：new_YYYY-MM-DD.csv)", type=["csv"])

    df_new, df_old = None, None
    data_source_msg = ""
    
    # 獲取系統雲端現有的舊檔案清單
    local_files = get_all_local_csvs()

    # --- 核心分支處理邏輯 ---
    if uploaded_new and uploaded_old:
        # 情況 A：兩份都有上傳 -> 完全採用網頁端
        df_new = load_and_clean_csv(uploaded_new)
        df_old = load_and_clean_csv(uploaded_old)
        data_source_msg = f"📂 **當前數據來源：** 網頁端手動上傳兩份 CSV \n* 最新：`{uploaded_new.name}`\n* 前日：`{uploaded_old.name}`"
        trigger_sync(uploaded_new)
        trigger_sync(uploaded_old)

    elif uploaded_new and not uploaded_old:
        # 情況 B：只上傳最新一份 -> 自動智能配對雲端上最新的一份舊檔案
        df_new = load_and_clean_csv(uploaded_new)
        
        if local_files:
            target_old_file = local_files[0]
            if os.path.basename(target_old_file) == uploaded_new.name and len(local_files) >= 2:
                target_old_file = local_files[1]
                
            df_old = load_and_clean_csv(target_old_file)
            data_source_msg = f"📂 **當前數據來源：** 智能混合模式\n* 最新（網頁上傳）：`{uploaded_new.name}`\n* 前日（雲端自動匹配）：`{os.path.basename(target_old_file)}`"
        else:
            st.error("❌ 雲端系統內找不到任何歷史數據，請同時上傳前一日的 CSV 進行首度初始化！")
        
        trigger_sync(uploaded_new)

    elif not uploaded_new and uploaded_old:
        # 情況 C：只上傳舊一份
        df_old = load_and_clean_csv(uploaded_old)
        if local_files:
            target_new_file = local_files[0]
            if os.path.basename(target_new_file) == uploaded_old.name and len(local_files) >= 2:
                target_new_file = local_files[1]
            df_new = load_and_clean_csv(target_new_file)
            data_source_msg = f"📂 **當前數據來源：** 智能混合模式\n* 最新（雲端自動匹配）：`{os.path.basename(target_new_file)}`\n* 前日（網頁上傳）：`{uploaded_old.name}`"
        trigger_sync(uploaded_old)

    else:
        # 情況 D：完全冇上傳 -> 開放【歷史日期切換選單】
        st.write("---")
        st.markdown("### 📜 歷史數據快速切換")
        
        if len(local_files) >= 2:
            # 建立歷史日期映射表
            options = []
            file_map = {}
            
            for i, f in enumerate(local_files[:-1]): # 最後一個檔案因為沒有「更舊的一天」可比對，故排除
                filename = os.path.basename(f)
                # 正則提取 YYYY-MM-DD
                date_match = re.search(r'new_(\d{4}-\d{2}-\d{2})', filename)
                date_str = date_match.group(1) if date_match else filename
                
                display_name = f"📅 {date_str}" + (" (最新雲端數據)" if i == 0 else "")
                options.append(display_name)
                file_map[display_name] = (f, local_files[i+1]) # 目前日子 與 比他舊一天的日子
                
            selected_option = st.selectbox(
                "請選擇你想查閱的歷史基準日（系統會自動對比其前一天的數據）：", 
                options,
                index=0
            )
            
            chosen_new_file, chosen_old_file = file_map[selected_option]
            df_new = load_and_clean_csv(chosen_new_file)
            df_old = load_and_clean_csv(chosen_old_file)
            
            data_source_msg = f"🏛️ **當前數據來源：** 查閱歷史存檔 \n* **新一日（基準）：** `{os.path.basename(chosen_new_file)}` \n* **舊一日（對比）：** `{os.path.basename(chosen_old_file)}`"
        elif len(local_files) == 1:
            df_new = load_and_clean_csv(local_files[0])
            st.warning("⚠️ 目前雲端只有一份 CSV，無法進行兩日對比。請在上方上傳更多歷史數據。")
            return
        else:
            st.info("👋 **歡迎使用！請在上方「數據上傳區」投入最新一日的 CSV 檔案。**")
            return

    if df_new is None or df_old is None:
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
